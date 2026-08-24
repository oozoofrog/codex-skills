"""Strict immutable ZIP verification and archive-only repository access."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .authorization import AuthorizationGrant
from .errors import ToolError, archive_invalid
from .schema import canonical_json_bytes, contract_for_schema

MAX_FILES = 2_000
MAX_TOTAL_BYTES = 25 * 1024 * 1024
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_INTERNAL_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_CENTRAL_DIRECTORY_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 40 * 1024 * 1024
MAX_RESEARCH_ARCHIVE_BYTES = 50 * 1024 * 1024
INTERNAL_MANIFEST = "_gptpro/file-manifest.json"
_SHA256 = re.compile(r"[0-9a-f]{64}")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def strict_posix_path(value: Any, *, archive_member: bool = False) -> str:
    try:
        encoded_length = len(value.encode("utf-8", "strict")) if isinstance(value, str) else 0
    except UnicodeEncodeError:
        encoded_length = 0
    if not isinstance(value, str) or not value or not encoded_length or encoded_length > 1024:
        raise ToolError(
            "PATH_INVALID",
            "The requested path is not a strict relative POSIX path.",
            retryable=True,
            recovery="Use an exact approved workspace-relative POSIX path.",
        )
    if "\0" in value or "\\" in value or value.startswith("/"):
        raise ToolError(
            "PATH_INVALID",
            "The requested path is not a strict relative POSIX path.",
            retryable=True,
            recovery="Use an exact approved workspace-relative POSIX path.",
        )
    parts = value.split("/")
    if (
        any(part in {"", ".", ".."} for part in parts)
        or re.match(r"^[A-Za-z]:", parts[0]) is not None
        or PurePosixPath(value).as_posix() != value
    ):
        raise ToolError(
            "PATH_INVALID",
            "The requested path is not a strict relative POSIX path.",
            retryable=True,
            recovery="Use an exact approved workspace-relative POSIX path.",
        )
    if not archive_member and value.startswith("_gptpro/"):
        raise ToolError(
            "PATH_INVALID",
            "The requested path is reserved for package metadata.",
            retryable=True,
            recovery="Use an exact approved repository path.",
        )
    return value


def _archive_fault(exc: Exception | None = None, *, code: str = "ARCHIVE_MEMBER_INVALID") -> ToolError:
    error = archive_invalid(code)
    if exc is not None:
        error.__cause__ = exc
    return error


@dataclass(frozen=True)
class VerifiedFile:
    path: str
    size: int
    sha256: str
    data: bytes
    text: str


@dataclass(frozen=True)
class VerifiedEvidence:
    artifact_id: str
    size: int
    sha256: str
    data: bytes
    text: str


@dataclass(frozen=True)
class VerifiedArchive:
    """A fully checked bounded snapshot; no member is extracted to disk."""

    grant: AuthorizationGrant
    files: tuple[VerifiedFile, ...]
    evidence: tuple[VerifiedEvidence, ...] = ()
    diff_entries: tuple[dict[str, Any], ...] = ()
    workspace_index: tuple[dict[str, Any], ...] = ()

    @classmethod
    def open(
        cls,
        grant: AuthorizationGrant,
        *,
        checkpoint: Callable[[], None] | None = None,
    ) -> "VerifiedArchive":
        check = checkpoint or (lambda: None)
        check()
        grant.validate(grant.package_id)
        manifest = grant.manifest
        schema_version = manifest.get("schema_version")
        if schema_version not in {3, 4}:
            raise _archive_fault(code="PACKAGE_TAMPERED")
        contract = contract_for_schema(int(schema_version))
        hashes = manifest.get("hashes")
        disclosure = manifest.get("mcp_disclosure")
        entries = manifest.get("files")
        if not isinstance(hashes, dict) or not isinstance(disclosure, dict) or not isinstance(entries, list):
            raise _archive_fault(code="PACKAGE_TAMPERED")
        if hashes.get("archive_sha256") != grant.archive_sha256:
            raise _archive_fault(code="CONTENT_DRIFT")
        archive_bytes = _read_archive_file(
            grant.archive_path,
            maximum=MAX_RESEARCH_ARCHIVE_BYTES if schema_version == 4 else MAX_ARCHIVE_BYTES,
        )
        if sha256_bytes(archive_bytes) != grant.archive_sha256:
            raise _archive_fault(code="CONTENT_DRIFT")
        if disclosure.get("snapshot") != "immutable-local-archive":
            raise _archive_fault(code="PACKAGE_TAMPERED")
        if disclosure.get("tools") != list(contract["tool_names"]):
            raise _archive_fault(code="TOOL_SCHEMA_MISMATCH")
        connector = manifest.get("connector")
        if (
            not isinstance(connector, dict)
            or connector.get("tool_schema_sha256") != contract["tool_schema_sha256"]
        ):
            raise _archive_fault(code="TOOL_SCHEMA_MISMATCH")

        expected: dict[str, dict[str, Any]] = {}
        allowed: list[dict[str, Any]] = []
        previous: str | None = None
        normalized_paths: dict[str, str] = {}
        for entry in entries:
            check()
            if not isinstance(entry, dict):
                raise _archive_fault(code="PACKAGE_TAMPERED")
            try:
                path = strict_posix_path(entry.get("path"))
                member = strict_posix_path(entry.get("archive_path"), archive_member=True)
            except ToolError as exc:
                raise _archive_fault(exc) from exc
            if member != f"repo/{path}" or member in expected or (previous is not None and path <= previous):
                raise _archive_fault(code="PACKAGE_TAMPERED")
            previous = path
            normalized = unicodedata.normalize("NFC", path).casefold()
            if normalized in normalized_paths and normalized_paths[normalized] != path:
                raise _archive_fault(code="PACKAGE_TAMPERED")
            normalized_paths[normalized] = path
            size = entry.get("size")
            digest = entry.get("sha256")
            if (
                isinstance(size, bool)
                or not isinstance(size, int)
                or not 0 <= size <= MAX_FILE_BYTES
                or not isinstance(digest, str)
                or _SHA256.fullmatch(digest) is None
            ):
                raise _archive_fault(code="PACKAGE_TAMPERED")
            expected[member] = {"path": path, "size": size, "sha256": digest}
            allowed.append({"path": path, "size": size, "sha256": digest})
        if len(expected) > MAX_FILES or sum(item["size"] for item in allowed) > MAX_TOTAL_BYTES:
            raise _archive_fault(code="ARCHIVE_LIMIT_EXCEEDED")
        file_set_hash = sha256_bytes(canonical_json_bytes(allowed))
        if (
            disclosure.get("allowed_files") != allowed
            or disclosure.get("file_set_sha256") != file_set_hash
            or hashes.get("file_set_sha256") != file_set_hash
            or disclosure.get("potential_files") != len(allowed)
            or disclosure.get("potential_bytes") != sum(item["size"] for item in allowed)
        ):
            raise _archive_fault(code="PACKAGE_TAMPERED")

        research = manifest.get("research") if schema_version == 4 else None
        evidence_specs: list[dict[str, Any]] = []
        diff_spec: dict[str, Any] | None = None
        index_spec: dict[str, Any] | None = None
        if schema_version == 4:
            if not isinstance(research, dict):
                raise _archive_fault(code="PACKAGE_TAMPERED")
            evidence_raw = research.get("evidence")
            diff_raw = research.get("diff")
            index_raw = research.get("workspace_index")
            if not isinstance(evidence_raw, list) or not isinstance(diff_raw, dict) or not isinstance(index_raw, dict):
                raise _archive_fault(code="PACKAGE_TAMPERED")
            if (
                diff_raw.get("base") != "HEAD"
                or diff_raw.get("base_sha") != manifest.get("git", {}).get("head_sha")
            ):
                raise _archive_fault(code="PACKAGE_TAMPERED")
            artifact_ids: set[str] = set()
            evidence_contract: list[dict[str, Any]] = []
            for entry in evidence_raw:
                if not isinstance(entry, dict):
                    raise _archive_fault(code="PACKAGE_TAMPERED")
                artifact_id = entry.get("artifact_id")
                member = entry.get("archive_path")
                size = entry.get("size")
                digest = entry.get("sha256")
                if (
                    not isinstance(artifact_id, str)
                    or re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", artifact_id) is None
                    or artifact_id in artifact_ids
                    or member != f"_gptpro/evidence/{artifact_id}.txt"
                    or isinstance(size, bool)
                    or not isinstance(size, int)
                    or not 0 <= size <= 2 * 1024 * 1024
                    or not isinstance(digest, str)
                    or _SHA256.fullmatch(digest) is None
                ):
                    raise _archive_fault(code="PACKAGE_TAMPERED")
                artifact_ids.add(artifact_id)
                evidence_contract.append({"artifact_id": artifact_id, "size": size, "sha256": digest})
                evidence_specs.append(dict(entry))
                expected[str(member)] = {
                    "kind": "evidence",
                    "artifact_id": artifact_id,
                    "size": size,
                    "sha256": digest,
                }
            evidence_set_hash = sha256_bytes(canonical_json_bytes(evidence_contract))
            if (
                research.get("evidence_set_sha256") != evidence_set_hash
                or hashes.get("evidence_set_sha256") != evidence_set_hash
            ):
                raise _archive_fault(code="PACKAGE_TAMPERED")
            for label, raw, member_name, maximum in (
                ("diff", diff_raw, "_gptpro/research/diff.json", 4 * 1024 * 1024),
                ("workspace_index", index_raw, "_gptpro/research/workspace-index.json", 4 * 1024 * 1024),
            ):
                size = raw.get("size")
                digest = raw.get("sha256")
                if (
                    raw.get("archive_path") != member_name
                    or isinstance(size, bool)
                    or not isinstance(size, int)
                    or not 0 <= size <= maximum
                    or not isinstance(digest, str)
                    or _SHA256.fullmatch(digest) is None
                    or hashes.get(f"{label}_sha256") != digest
                ):
                    raise _archive_fault(code="PACKAGE_TAMPERED")
                expected[member_name] = {
                    "kind": label,
                    "size": size,
                    "sha256": digest,
                }
            diff_spec = dict(diff_raw)
            index_spec = dict(index_raw)

        verified: list[VerifiedFile] = []
        verified_evidence: list[VerifiedEvidence] = []
        verified_diff: tuple[dict[str, Any], ...] = ()
        verified_index: tuple[dict[str, Any], ...] = ()
        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                if len(infos) > MAX_FILES + 20:
                    raise _archive_fault(code="ARCHIVE_LIMIT_EXCEEDED")
                if len(names) != len(set(names)):
                    raise _archive_fault()
                expected_names = set(expected) | {INTERNAL_MANIFEST}
                if set(names) != expected_names:
                    raise _archive_fault()
                normalized_members: dict[str, str] = {}
                total_size = 0
                for info in infos:
                    check()
                    try:
                        name = strict_posix_path(info.filename, archive_member=True)
                    except ToolError as exc:
                        raise _archive_fault(exc) from exc
                    normalized = unicodedata.normalize("NFC", name).casefold()
                    if normalized in normalized_members and normalized_members[normalized] != name:
                        raise _archive_fault()
                    normalized_members[normalized] = name
                    if info.flag_bits & 0x1:
                        raise _archive_fault()
                    if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                        raise _archive_fault()
                    mode = (info.external_attr >> 16) & 0xFFFF
                    if not stat.S_ISREG(mode) or info.is_dir():
                        raise _archive_fault()
                    if name == INTERNAL_MANIFEST:
                        limit = MAX_INTERNAL_MANIFEST_BYTES
                    elif name == "_gptpro/research/diff.json":
                        limit = 4 * 1024 * 1024
                    elif name == "_gptpro/research/workspace-index.json":
                        limit = 4 * 1024 * 1024
                    else:
                        limit = MAX_FILE_BYTES
                    if info.file_size < 0 or info.file_size > limit:
                        raise _archive_fault(code="ARCHIVE_LIMIT_EXCEEDED")
                    ratio_limit = 20 if name == INTERNAL_MANIFEST else 100
                    if info.file_size and (
                        info.compress_size <= 0 or info.file_size > info.compress_size * ratio_limit
                    ):
                        raise _archive_fault(code="ARCHIVE_LIMIT_EXCEEDED")
                    total_size += info.file_size
                maximum_total = (
                    MAX_TOTAL_BYTES + MAX_INTERNAL_MANIFEST_BYTES
                    if schema_version == 3
                    else MAX_RESEARCH_ARCHIVE_BYTES
                )
                if total_size > maximum_total:
                    raise _archive_fault(code="ARCHIVE_LIMIT_EXCEEDED")
                start_dir = getattr(archive, "start_dir", None)
                archive_size = len(archive_bytes)
                if (
                    isinstance(start_dir, int)
                    and archive_size - start_dir > MAX_CENTRAL_DIRECTORY_BYTES
                ):
                    raise _archive_fault(code="ARCHIVE_LIMIT_EXCEEDED")

                internal_bytes = _read_bounded(
                    archive,
                    INTERNAL_MANIFEST,
                    MAX_INTERNAL_MANIFEST_BYTES,
                )
                if sha256_bytes(internal_bytes) != hashes.get("internal_manifest_sha256"):
                    raise _archive_fault(code="CONTENT_DRIFT")
                try:
                    internal = json.loads(internal_bytes.decode("utf-8"))
                except (UnicodeDecodeError, ValueError, RecursionError) as exc:
                    raise _archive_fault(exc) from exc
                if (
                    not isinstance(internal, dict)
                    or internal.get("schema_version") != schema_version
                    or internal.get("package_id") != grant.package_id
                    or internal.get("files") != entries
                    or internal.get("packaged_tree_sha256") != hashes.get("packaged_tree_sha256")
                    or (schema_version == 4 and internal.get("research") != research)
                ):
                    raise _archive_fault(code="CONTENT_DRIFT")

                for member in sorted(expected):
                    check()
                    item = expected[member]
                    maximum = (
                        4 * 1024 * 1024
                        if member in {
                            "_gptpro/research/diff.json",
                            "_gptpro/research/workspace-index.json",
                        }
                        else MAX_FILE_BYTES
                    )
                    data = _read_bounded(archive, member, maximum)
                    if len(data) != item["size"] or sha256_bytes(data) != item["sha256"]:
                        raise _archive_fault(code="CONTENT_DRIFT")
                    if b"\0" in data:
                        raise _archive_fault()
                    try:
                        text = data.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        raise ToolError(
                            "ENCODING_UNSUPPORTED",
                            "An approved archive member is not strict UTF-8 text.",
                            recovery="Prepare a package containing only supported text files.",
                        ) from exc
                    kind = item.get("kind", "repository")
                    if kind == "repository":
                        verified.append(
                            VerifiedFile(
                                path=item["path"],
                                size=item["size"],
                                sha256=item["sha256"],
                                data=data,
                                text=text,
                            )
                        )
                    elif kind == "evidence":
                        verified_evidence.append(
                            VerifiedEvidence(
                                artifact_id=item["artifact_id"],
                                size=item["size"],
                                sha256=item["sha256"],
                                data=data,
                                text=text,
                            )
                        )
                    else:
                        try:
                            parsed = json.loads(text)
                        except (ValueError, RecursionError) as exc:
                            raise _archive_fault(exc, code="CONTENT_DRIFT") from exc
                        if not isinstance(parsed, list) or canonical_json_bytes(parsed) != data:
                            raise _archive_fault(code="CONTENT_DRIFT")
                        if kind == "diff":
                            if not all(isinstance(entry, dict) for entry in parsed):
                                raise _archive_fault(code="CONTENT_DRIFT")
                            verified_diff = tuple(dict(entry) for entry in parsed)
                        elif kind == "workspace_index":
                            if not all(isinstance(entry, dict) for entry in parsed):
                                raise _archive_fault(code="CONTENT_DRIFT")
                            verified_index = tuple(dict(entry) for entry in parsed)
        except ToolError:
            raise
        except (OSError, KeyError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
            raise _archive_fault(exc) from exc
        if schema_version == 4:
            limits = grant.limits
            if (
                len(verified_evidence) > limits["max_evidence_files"]
                or any(item.size > limits["max_evidence_file_bytes"] for item in verified_evidence)
                or sum(item.size for item in verified_evidence) > limits["max_evidence_total_bytes"]
            ):
                raise _archive_fault(code="ARCHIVE_LIMIT_EXCEEDED")
            expected_index: list[dict[str, Any]] = []
            directories: dict[str, int] = {}
            for item in sorted(verified, key=lambda value: value.path):
                parts = item.path.split("/")
                for index in range(1, len(parts)):
                    directory = "/".join(parts[:index])
                    directories[directory] = directories.get(directory, 0) + 1
                expected_index.append(
                    {"kind": "file", "path": item.path, "size": item.size, "sha256": item.sha256}
                )
            expected_index.extend(
                {"kind": "directory", "path": path, "descendant_files": count}
                for path, count in directories.items()
            )
            expected_index.sort(key=lambda item: (str(item["path"]), str(item["kind"])))
            if list(verified_index) != expected_index:
                raise _archive_fault(code="CONTENT_DRIFT")
            files_by_path = {item.path: item for item in verified}
            previous_diff_path: str | None = None
            for entry in verified_diff:
                try:
                    path = strict_posix_path(entry.get("path"))
                except ToolError as exc:
                    raise _archive_fault(exc, code="CONTENT_DRIFT") from exc
                current = files_by_path.get(path)
                status = entry.get("status")
                if (
                    not isinstance(path, str)
                    or (previous_diff_path is not None and path <= previous_diff_path)
                    or status not in {"added", "modified", "deleted"}
                    or isinstance(entry.get("old_bytes"), bool)
                    or not isinstance(entry.get("old_bytes"), int)
                    or entry.get("old_bytes") < 0
                ):
                    raise _archive_fault(code="CONTENT_DRIFT")
                if status == "deleted":
                    if (
                        current is not None
                        or entry.get("new_sha256") is not None
                        or entry.get("new_bytes") != 0
                    ):
                        raise _archive_fault(code="CONTENT_DRIFT")
                elif (
                    current is None
                    or entry.get("new_sha256") != current.sha256
                    or entry.get("new_bytes") != current.size
                ):
                    raise _archive_fault(code="CONTENT_DRIFT")
                old_hash = entry.get("old_sha256")
                if status == "added":
                    if old_hash is not None or entry["old_bytes"] != 0:
                        raise _archive_fault(code="CONTENT_DRIFT")
                elif not isinstance(old_hash, str) or _SHA256.fullmatch(old_hash) is None:
                    raise _archive_fault(code="CONTENT_DRIFT")
                withheld = entry.get("content_withheld")
                if withheld is None:
                    patch = entry.get("diff")
                    if (
                        not isinstance(patch, str)
                        or entry.get("diff_sha256") != sha256_bytes(patch.encode("utf-8"))
                    ):
                        raise _archive_fault(code="CONTENT_DRIFT")
                elif (
                    withheld not in {"non-utf8-head-content", "secret-like-head-content"}
                    or "diff" in entry
                    or "diff_sha256" in entry
                ):
                    raise _archive_fault(code="CONTENT_DRIFT")
                previous_diff_path = path
        return cls(
            grant=grant,
            files=tuple(verified),
            evidence=tuple(sorted(verified_evidence, key=lambda item: item.artifact_id)),
            diff_entries=verified_diff,
            workspace_index=verified_index,
        )

    def file(self, path: str) -> VerifiedFile:
        strict_posix_path(path)
        for item in self.files:
            if item.path == path:
                return item
        raise ToolError(
            "PATH_NOT_APPROVED",
            "The requested path is not in the approved package.",
            retryable=True,
            recovery="Use package_info or search within the approved path set.",
        )

    def evidence_file(self, artifact_id: str) -> VerifiedEvidence:
        if not isinstance(artifact_id, str):
            raise ToolError("EVIDENCE_NOT_APPROVED", "The evidence artifact ID is invalid.")
        for item in self.evidence:
            if item.artifact_id == artifact_id:
                return item
        raise ToolError(
            "EVIDENCE_NOT_APPROVED",
            "The requested evidence artifact is not in the approved package.",
            retryable=True,
            recovery="Use package_info to choose an approved evidence artifact.",
        )


def _read_bounded(archive: zipfile.ZipFile, name: str, maximum: int) -> bytes:
    try:
        with archive.open(name, "r") as handle:
            data = handle.read(maximum + 1)
            if len(data) > maximum or handle.read(1):
                raise _archive_fault(code="ARCHIVE_LIMIT_EXCEEDED")
            return data
    except ToolError:
        raise
    except (OSError, KeyError, RuntimeError, zipfile.BadZipFile) as exc:
        raise _archive_fault(exc) from exc


def _read_archive_file(path: Path, *, maximum: int = MAX_ARCHIVE_BYTES) -> bytes:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise _archive_fault(code="PACKAGE_TAMPERED")
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | nofollow)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_mode & 0o022
            or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
        ):
            raise _archive_fault(code="PACKAGE_TAMPERED")
        if not 0 <= metadata.st_size <= maximum:
            raise _archive_fault(code="ARCHIVE_LIMIT_EXCEEDED")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > maximum or len(data) != metadata.st_size:
            raise _archive_fault(code="ARCHIVE_LIMIT_EXCEEDED")
        return data
    except ToolError:
        raise
    except OSError as exc:
        raise _archive_fault(exc, code="PACKAGE_TAMPERED") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
