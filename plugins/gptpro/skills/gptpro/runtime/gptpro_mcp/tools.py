"""Bounded package_info, literal search, and line-range read tools."""

from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from .archive import VerifiedArchive, strict_posix_path
from .authorization import AuthorizationGrant, AuthorizationProvider
from .cursor import CursorCodec, arguments_sha256
from .errors import CancelledError, ToolError, invalid_argument
from .schema import PROTOCOL_PROFILE, TOOL_NAMES, canonical_json_bytes, tool_schema_sha256


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def success_result(tool: str, package_id: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "structuredContent": {
            "ok": True,
            "tool": tool,
            "package_id": package_id,
            "result": result,
        },
        "content": [
            {
                "type": "text",
                "text": (
                    "Returned approved bounded repository evidence; use structuredContent "
                    "for the exact result."
                ),
            }
        ],
        "isError": False,
    }


def error_result(error: ToolError) -> dict[str, Any]:
    return {
        "structuredContent": {"ok": False, "error": error.envelope()},
        "content": [{"type": "text", "text": f"{error.code}: the read-only request was rejected."}],
        "isError": True,
    }


class DisclosureCommitter(Protocol):
    """Phase-3 hook that must durably authorize and audit before content is returned."""

    def commit_before_return(
        self,
        *,
        grant: AuthorizationGrant,
        tool: str,
        request_id_sha256: str,
        arguments_sha256: str,
        audit_metadata: dict[str, Any],
        calls_used: int,
        disclosed_bytes: int,
    ) -> None: ...

    def record_rejection(
        self,
        *,
        grant: AuthorizationGrant,
        tool: str,
        request_id_sha256: str,
        arguments_sha256: str,
        error_code: str,
        calls_used: int,
    ) -> None: ...


class FixtureDisclosureCommitter:
    """No-op used only with injected static grants in local unit fixtures."""

    def commit_before_return(self, **kwargs: Any) -> None:
        del kwargs

    def record_rejection(self, **kwargs: Any) -> None:
        del kwargs


class DenyDisclosureCommitter:
    """Production-safe default until a durable Phase-3 audit committer is injected."""

    def commit_before_return(self, **kwargs: Any) -> None:
        del kwargs
        raise ToolError(
            "AUDIT_UNAVAILABLE",
            "Repository evidence cannot be returned without a durable disclosure audit.",
            recovery="Activate the approved package through the complete gptpro runtime.",
        )

    def record_rejection(self, **kwargs: Any) -> None:
        self.commit_before_return(**kwargs)


class ToolRuntime:
    """Single-session disclosure executor with in-memory Phase-2 limits."""

    def __init__(
        self,
        authorization: AuthorizationProvider,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        committer: DisclosureCommitter | None = None,
    ) -> None:
        self._authorization = authorization
        self._monotonic = monotonic
        self._committer = committer or DenyDisclosureCommitter()
        self._execute_lock = threading.Lock()
        self._session_key: tuple[str, str] | None = None
        self._calls_used = 0
        self._disclosed_bytes = 0

    def call(
        self,
        name: str,
        arguments: Any,
        *,
        cancelled: threading.Event | None = None,
        request_id: Any = None,
    ) -> dict[str, Any]:
        cancel = cancelled or threading.Event()
        if name not in TOOL_NAMES:
            raise invalid_argument("The requested tool name is not in the static catalog.")
        if not isinstance(arguments, dict):
            raise invalid_argument()
        package_id = arguments.get("package_id")
        if not isinstance(package_id, str) or not 1 <= len(package_id) <= 128:
            raise invalid_argument("package_id must be a non-empty string of at most 128 characters.")
        grant = self._authorization.resolve(package_id)
        grant.validate(package_id)
        limits = grant.limits
        started = self._monotonic()

        def checkpoint() -> None:
            if cancel.is_set():
                raise CancelledError
            if self._monotonic() - started > limits["tool_timeout_seconds"]:
                raise ToolError(
                    "TIMEOUT",
                    "The bounded read-only operation exceeded its time limit.",
                    retryable=True,
                    recovery="Retry with a smaller path set, result count, or line range.",
                )

        with self._execute_lock:
            checkpoint()
            self._select_session(grant)
            if self._calls_used >= limits["max_tool_calls"]:
                raise ToolError(
                    "CALL_LIMIT_EXCEEDED",
                    "The approved session tool-call limit has been reached.",
                    recovery="Stop this session and obtain approval for a new session.",
                )
            try:
                request_hash = _sha256(canonical_json_bytes(request_id))
                argument_hash = _sha256(canonical_json_bytes(arguments))
            except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
                raise invalid_argument(
                    "The request id and arguments must be bounded canonical UTF-8 JSON values."
                ) from exc
            self._calls_used += 1
            projected_calls = self._calls_used
            try:
                snapshot = VerifiedArchive.open(grant, checkpoint=checkpoint)
                checkpoint()
                if name == "gptpro_package_info":
                    result, disclosure = self._package_info(
                        snapshot, arguments, projected_calls=projected_calls, checkpoint=checkpoint
                    )
                elif name == "gptpro_repo_read":
                    result, disclosure = self._read(snapshot, arguments, checkpoint=checkpoint)
                else:
                    result, disclosure = self._search(snapshot, arguments, checkpoint=checkpoint)
                projected_disclosure = self._disclosed_bytes + disclosure
                if projected_disclosure > limits["max_session_disclosure_bytes"]:
                    raise ToolError(
                        "DISCLOSURE_BUDGET_EXCEEDED",
                        "The approved session disclosure budget would be exceeded.",
                        recovery="Stop this session and obtain approval for a new bounded session.",
                    )
                result.setdefault("disclosure", {})["session_disclosed_bytes"] = projected_disclosure
                if name == "gptpro_package_info":
                    result["session"]["calls_used"] = projected_calls
                    result["session"]["disclosed_bytes"] = projected_disclosure
                response = success_result(name, package_id, result)
                if len(canonical_json_bytes(response)) > limits["max_result_bytes"]:
                    raise ToolError(
                        "RESULT_LIMIT_EXCEEDED",
                        "The model-visible tool result exceeds the approved per-call byte limit.",
                        retryable=True,
                        recovery="Request fewer paths, fewer matches, or a smaller line range.",
                    )
                checkpoint()
                current = self._authorization.resolve(package_id)
                current.validate(package_id)
                if (
                    current.package_id,
                    current.session_id_sha256,
                    current.manifest_sha256,
                    current.archive_sha256,
                ) != (
                    grant.package_id,
                    grant.session_id_sha256,
                    grant.manifest_sha256,
                    grant.archive_sha256,
                ):
                    raise ToolError(
                        "CONTENT_DRIFT",
                        "The active authorization changed while repository evidence was prepared.",
                        recovery="Discard this result and start a new approved session.",
                    )
            except (ToolError, CancelledError) as exc:
                error_code = exc.code if isinstance(exc, ToolError) else "CANCELLED"
                self._committer.record_rejection(
                    grant=grant,
                    tool=name,
                    request_id_sha256=request_hash,
                    arguments_sha256=argument_hash,
                    error_code=error_code,
                    calls_used=projected_calls,
                )
                raise
            except Exception as exc:
                self._committer.record_rejection(
                    grant=grant,
                    tool=name,
                    request_id_sha256=request_hash,
                    arguments_sha256=argument_hash,
                    error_code="TOOL_EXECUTION_FAILED",
                    calls_used=projected_calls,
                )
                raise ToolError(
                    "TOOL_EXECUTION_FAILED",
                    "The bounded read-only operation failed before returning content.",
                    recovery="Stop this session if the failure repeats.",
                ) from exc
            self._committer.commit_before_return(
                grant=current,
                tool=name,
                request_id_sha256=request_hash,
                arguments_sha256=argument_hash,
                audit_metadata=_audit_metadata(name, result),
                calls_used=projected_calls,
                disclosed_bytes=projected_disclosure,
            )
            self._disclosed_bytes = projected_disclosure
            return response

    def _select_session(self, grant: AuthorizationGrant) -> None:
        key = (grant.package_id, grant.session_id_sha256)
        if self._session_key != key:
            self._session_key = key
            self._calls_used = 0
            self._disclosed_bytes = 0

    def _package_info(
        self,
        snapshot: VerifiedArchive,
        raw: dict[str, Any],
        *,
        projected_calls: int,
        checkpoint: Callable[[], None],
    ) -> tuple[dict[str, Any], int]:
        _reject_unknown(raw, {"package_id", "include_paths", "path_page_size", "cursor"})
        include_paths = _boolean(raw.get("include_paths", False), "include_paths")
        page_size = _integer(raw.get("path_page_size", 50), "path_page_size", minimum=1, maximum=200)
        limits = snapshot.grant.limits
        if page_size > limits["max_path_page_size"]:
            raise invalid_argument("path_page_size exceeds the approved session limit.")
        normalized = {
            "package_id": snapshot.grant.package_id,
            "include_paths": include_paths,
            "path_page_size": page_size,
        }
        bound_hash = arguments_sha256(normalized)
        start = 0
        cursor = raw.get("cursor")
        if cursor is not None:
            if not include_paths:
                raise invalid_argument("A package_info cursor requires include_paths=true.")
            position = CursorCodec(snapshot.grant).decode(
                cursor,
                tool="gptpro_package_info",
                arguments_hash=bound_hash,
            )
            start = _cursor_integer(position, "path_index")
        paths: list[dict[str, Any]] = []
        next_cursor: str | None = None
        disclosure = 0
        if include_paths:
            if start > len(snapshot.files):
                raise _cursor_error()
            selected = snapshot.files[start : start + page_size]
            for item in selected:
                checkpoint()
                paths.append({"path": item.path, "size": item.size, "sha256": item.sha256})
                disclosure += len(item.path.encode("utf-8"))
            next_index = start + len(selected)
            if next_index < len(snapshot.files):
                next_cursor = CursorCodec(snapshot.grant).encode(
                    tool="gptpro_package_info",
                    arguments_hash=bound_hash,
                    next_position={"path_index": next_index},
                )
        manifest = snapshot.grant.manifest
        disclosure_contract = manifest["mcp_disclosure"]
        repository = manifest.get("repository", {})
        hashes = manifest.get("hashes", {})
        result = {
            "package_id": snapshot.grant.package_id,
            "mode": manifest.get("mode"),
            "git_sha": repository.get("git_sha"),
            "packaged_tree_sha256": hashes.get("packaged_tree_sha256"),
            "snapshot": "immutable-local-archive",
            "file_set_sha256": disclosure_contract.get("file_set_sha256"),
            "potential_files": disclosure_contract.get("potential_files"),
            "potential_bytes": disclosure_contract.get("potential_bytes"),
            "protocol_profile": PROTOCOL_PROFILE,
            "tool_schema_sha256": tool_schema_sha256(),
            "limits": dict(snapshot.grant.limits),
            "session": {
                "expires_at": _utc_text(snapshot.grant.expires_at),
                "idle_expires_at": _utc_text(snapshot.grant.idle_expires_at),
                "calls_used": projected_calls,
                "disclosed_bytes": self._disclosed_bytes + disclosure,
            },
            "allowed_paths_page": paths,
            "next_cursor": next_cursor,
        }
        return result, disclosure

    def _read(
        self,
        snapshot: VerifiedArchive,
        raw: dict[str, Any],
        *,
        checkpoint: Callable[[], None],
    ) -> tuple[dict[str, Any], int]:
        _reject_unknown(raw, {"package_id", "path", "start_line", "end_line", "cursor"})
        path = strict_posix_path(raw.get("path"))
        start_line = _integer(raw.get("start_line", 1), "start_line", minimum=1)
        end_raw = raw.get("end_line")
        end_line = None if end_raw is None else _integer(end_raw, "end_line", minimum=1)
        if end_line is not None and end_line < start_line:
            raise ToolError(
                "RANGE_INVALID",
                "end_line must be greater than or equal to start_line.",
                retryable=True,
                recovery="Use a valid 1-based inclusive line range.",
            )
        limits = snapshot.grant.limits
        if end_line is not None and end_line - start_line + 1 > limits["max_requested_lines"]:
            raise ToolError(
                "RANGE_INVALID",
                "The requested line span exceeds the approved hard limit.",
                retryable=True,
                recovery="Request a smaller line range.",
            )
        normalized = {
            "package_id": snapshot.grant.package_id,
            "path": path,
            "start_line": start_line,
            "end_line": end_line,
        }
        bound_hash = arguments_sha256(normalized)
        position_line = start_line
        if raw.get("cursor") is not None:
            position = CursorCodec(snapshot.grant).decode(
                raw["cursor"],
                tool="gptpro_repo_read",
                arguments_hash=bound_hash,
            )
            position_line = _cursor_integer(position, "next_line", minimum=1)
        item = snapshot.file(path)
        lines = item.data.splitlines(keepends=True)
        total_lines = len(lines)
        if total_lines == 0:
            if position_line != 1:
                raise ToolError(
                    "RANGE_INVALID",
                    "The requested line starts beyond the end of the approved file.",
                    retryable=True,
                    recovery="Request line 1 for this empty file.",
                )
            requested_end = 0
        else:
            requested_end = total_lines if end_line is None else min(end_line, total_lines)
            if position_line > total_lines or position_line < start_line:
                raise ToolError(
                    "RANGE_INVALID",
                    "The requested line starts beyond the approved range.",
                    retryable=True,
                    recovery="Use a line within the approved file and requested range.",
                )
            if end_line is None and requested_end - start_line + 1 > limits["max_requested_lines"]:
                raise ToolError(
                    "RANGE_INVALID",
                    "The implicit line range to EOF exceeds the approved hard limit.",
                    retryable=True,
                    recovery="Provide an explicit end_line within the approved line-span limit.",
                )
        fragments: list[bytes] = []
        content_bytes = 0
        current = position_line
        while current <= requested_end:
            checkpoint()
            line = lines[current - 1]
            if len(line) > limits["max_read_content_bytes"]:
                raise ToolError(
                    "RESULT_LIMIT_EXCEEDED",
                    "One repository line exceeds the approved read-result byte limit.",
                    retryable=True,
                    recovery="Search for a smaller excerpt or exclude the oversized file.",
                )
            if content_bytes + len(line) > limits["max_read_content_bytes"]:
                break
            fragments.append(line)
            content_bytes += len(line)
            current += 1
        fragment = b"".join(fragments)
        try:
            text = fragment.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ToolError(
                "ENCODING_UNSUPPORTED",
                "A requested line boundary does not decode as strict UTF-8.",
                recovery="Prepare a package with supported UTF-8 text boundaries.",
            ) from exc
        complete = current > requested_end
        next_cursor = None
        if not complete:
            next_cursor = CursorCodec(snapshot.grant).encode(
                tool="gptpro_repo_read",
                arguments_hash=bound_hash,
                next_position={"next_line": current},
            )
        returned_start = position_line
        returned_end = current - 1
        result = {
            "path": path,
            "file_sha256": item.sha256,
            "file_size": item.size,
            "requested": {"start_line": start_line, "end_line": end_line},
            "returned": {"start_line": returned_start, "end_line": returned_end},
            "text": text,
            "fragment_sha256": _sha256(fragment),
            "complete": complete,
            "next_cursor": next_cursor,
            "disclosure": {"content_bytes": content_bytes},
        }
        return result, len(path.encode("utf-8")) + content_bytes

    def _search(
        self,
        snapshot: VerifiedArchive,
        raw: dict[str, Any],
        *,
        checkpoint: Callable[[], None],
    ) -> tuple[dict[str, Any], int]:
        _reject_unknown(
            raw,
            {
                "package_id",
                "query",
                "paths",
                "case_sensitive",
                "max_results",
                "context_lines",
                "cursor",
            },
        )
        query = raw.get("query")
        try:
            query_bytes = query.encode("utf-8", "strict") if isinstance(query, str) else b""
        except UnicodeEncodeError:
            query_bytes = b""
        if (
            not isinstance(query, str)
            or not query.strip()
            or not query_bytes
            or "\0" in query
            or "\r" in query
            or "\n" in query
        ):
            raise ToolError(
                "SEARCH_QUERY_INVALID",
                "Search requires one non-empty single-line literal UTF-8 query.",
                retryable=True,
                recovery="Use a bounded literal query without NUL, CR, or LF.",
            )
        limits = snapshot.grant.limits
        if len(query) > limits["max_query_chars"]:
            raise ToolError(
                "SEARCH_QUERY_INVALID",
                "The literal query exceeds the approved character limit.",
                retryable=True,
                recovery="Use a shorter literal query.",
            )
        case_sensitive = _boolean(raw.get("case_sensitive", True), "case_sensitive")
        max_results = _integer(raw.get("max_results", 25), "max_results", minimum=1, maximum=100)
        context_lines = _integer(raw.get("context_lines", 2), "context_lines", minimum=0, maximum=10)
        if max_results > limits["max_search_results"] or context_lines > limits["max_context_lines"]:
            raise invalid_argument("Search result or context limits exceed the approved session limits.")
        paths_raw = raw.get("paths")
        if paths_raw is None:
            paths: list[str] = []
        elif not isinstance(paths_raw, list) or len(paths_raw) > limits["max_path_filters"]:
            raise invalid_argument("paths must be a bounded array of approved path filters.")
        else:
            paths = []
            for value in paths_raw:
                if not isinstance(value, str):
                    raise ToolError(
                        "PATH_INVALID",
                        "A search path filter is invalid.",
                        retryable=True,
                        recovery="Use exact approved paths or one subtree suffix ending in /**.",
                    )
                paths.append(value)
        filtered = _filter_files(snapshot, paths)
        normalized = {
            "package_id": snapshot.grant.package_id,
            "query": query,
            "paths": paths,
            "case_sensitive": case_sensitive,
            "max_results": max_results,
            "context_lines": context_lines,
        }
        bound_hash = arguments_sha256(normalized)
        offset = 0
        if raw.get("cursor") is not None:
            position = CursorCodec(snapshot.grant).decode(
                raw["cursor"],
                tool="gptpro_repo_search",
                arguments_hash=bound_hash,
            )
            offset = _cursor_integer(position, "match_index")
        needle = query if case_sensitive else query.casefold()
        page: list[dict[str, Any]] = []
        page_payload_bytes = 0
        seen_matches = 0
        has_more = False
        for item in filtered:
            checkpoint()
            lines = item.data.splitlines(keepends=True)
            for index, line_bytes in enumerate(lines):
                checkpoint()
                line = line_bytes.decode("utf-8")
                haystack = line if case_sensitive else line.casefold()
                if needle not in haystack:
                    continue
                if seen_matches < offset:
                    seen_matches += 1
                    continue
                if len(page) >= max_results:
                    has_more = True
                    break
                start = max(0, index - context_lines)
                end = min(len(lines), index + context_lines + 1)
                excerpt_bytes = b"".join(lines[start:end])
                excerpt = excerpt_bytes.decode("utf-8")
                match = {
                    "path": item.path,
                    "line": index + 1,
                    "start_line": start + 1,
                    "end_line": end,
                    "excerpt": excerpt,
                    "file_sha256": item.sha256,
                    "excerpt_sha256": _sha256(excerpt_bytes),
                }
                match_bytes = len(canonical_json_bytes(match))
                if match_bytes > limits["max_result_bytes"]:
                    raise ToolError(
                        "RESULT_LIMIT_EXCEEDED",
                        "One search excerpt exceeds the approved result byte limit.",
                        retryable=True,
                        recovery="Retry with fewer context lines or a narrower approved file.",
                    )
                if page and page_payload_bytes + match_bytes > limits["max_result_bytes"]:
                    has_more = True
                    break
                page.append(match)
                page_payload_bytes += match_bytes
                seen_matches += 1
            if has_more:
                break
        if offset > seen_matches:
            raise _cursor_error()
        next_index = offset + len(page)
        complete = not has_more
        next_cursor = None
        if not complete:
            next_cursor = CursorCodec(snapshot.grant).encode(
                tool="gptpro_repo_search",
                arguments_hash=bound_hash,
                next_position={"match_index": next_index},
            )
        disclosure = sum(
            len(match["path"].encode("utf-8")) + len(match["excerpt"].encode("utf-8"))
            for match in page
        )
        result = {
            "query_sha256": _sha256(query_bytes),
            "matches": page,
            "returned_results": len(page),
            "complete": complete,
            "next_cursor": next_cursor,
            "disclosure": {"result_bytes": disclosure},
        }
        return result, disclosure


def _reject_unknown(arguments: dict[str, Any], allowed: set[str]) -> None:
    if set(arguments) - allowed:
        raise invalid_argument("The tool arguments contain unsupported properties.")


def _audit_metadata(tool: str, result: dict[str, Any]) -> dict[str, Any]:
    """Return bounded audit evidence without repository bodies or raw search queries."""

    common = {"result_sha256": _sha256(canonical_json_bytes(result))}
    if tool == "gptpro_package_info":
        return {
            **common,
            "paths": [
                {key: item.get(key) for key in ("path", "size", "sha256")}
                for item in result.get("allowed_paths_page", [])
                if isinstance(item, dict)
            ],
        }
    if tool == "gptpro_repo_read":
        return {
            **common,
            "path": result.get("path"),
            "file_sha256": result.get("file_sha256"),
            "requested": result.get("requested"),
            "returned": result.get("returned"),
            "fragment_sha256": result.get("fragment_sha256"),
            "content_bytes": result.get("disclosure", {}).get("content_bytes"),
        }
    return {
        **common,
        "query_sha256": result.get("query_sha256"),
        "matches": [
            {
                key: item.get(key)
                for key in (
                    "path",
                    "line",
                    "start_line",
                    "end_line",
                    "file_sha256",
                    "excerpt_sha256",
                )
            }
            for item in result.get("matches", [])
            if isinstance(item, dict)
        ],
        "result_bytes": result.get("disclosure", {}).get("result_bytes"),
    }


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise invalid_argument(f"{name} must be a boolean.")
    return value


def _integer(
    value: Any,
    name: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise invalid_argument(f"{name} must be an integer of at least {minimum}.")
    if maximum is not None and value > maximum:
        raise invalid_argument(f"{name} must not exceed {maximum}.")
    return value


def _cursor_integer(position: dict[str, Any], key: str, *, minimum: int = 0) -> int:
    value = position.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum or set(position) != {key}:
        raise _cursor_error()
    return value


def _cursor_error() -> ToolError:
    return ToolError(
        "CURSOR_INVALID",
        "The pagination cursor position is invalid for this request.",
        retryable=True,
        recovery="Restart from the original tool call without a cursor.",
    )


def _filter_files(snapshot: VerifiedArchive, filters: list[str]):
    if not filters:
        return list(snapshot.files)
    selected: dict[str, Any] = {}
    approved = {item.path: item for item in snapshot.files}
    for value in filters:
        if value.endswith("/**") and value.count("*") == 2 and "?" not in value and "[" not in value:
            base = strict_posix_path(value[:-3])
            matches = [item for item in snapshot.files if item.path.startswith(base + "/")]
            if not matches:
                raise ToolError(
                    "PATH_NOT_APPROVED",
                    "A requested search subtree is not in the approved package.",
                    retryable=True,
                    recovery="Use package_info to choose an approved path or subtree.",
                )
            for item in matches:
                selected[item.path] = item
            continue
        if any(char in value for char in "*?[]"):
            raise ToolError(
                "PATH_INVALID",
                "Search filters support only exact paths or one trailing /** subtree suffix.",
                retryable=True,
                recovery="Use an exact approved path or a subtree suffix ending in /**.",
            )
        path = strict_posix_path(value)
        item = approved.get(path)
        if item is None:
            raise ToolError(
                "PATH_NOT_APPROVED",
                "A requested search path is not in the approved package.",
                retryable=True,
                recovery="Use package_info to choose an approved path.",
            )
        selected[path] = item
    return [selected[path] for path in sorted(selected)]
