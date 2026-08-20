#!/usr/bin/env python3
"""Prepare, verify, and record attended ChatGPT Pro repository handoffs."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SCHEMA_VERSION = 1
MODES = ("plan", "ask", "review", "debug", "architecture")
PHASES = ("prepared", "approved", "submitted", "response_imported", "evaluated")
DEFAULT_REQUESTED_MODEL = "ChatGPT Pro / GPT-5.6 Sol / Intelligence: Pro"
DESTINATION = "https://chatgpt.com/"
DEFAULT_MAX_FILES = 2_000
DEFAULT_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_FILE_BYTES = 2 * 1024 * 1024

EXCLUDED_DIR_NAMES = {
    ".git",
    ".gptpro",
    ".build",
    ".cache",
    ".gradle",
    ".idea",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".swiftpm",
    ".tox",
    ".venv",
    ".vscode",
    "DerivedData",
    "Pods",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "venv",
}

EXCLUDED_FILE_PATTERNS = (
    ".DS_Store",
    "*.app",
    "*.cer",
    "*.crt",
    "*.der",
    "*.jks",
    "*.key",
    "*.keystore",
    "*.mobileprovision",
    "*.p12",
    "*.pfx",
    "*.pyc",
    "*.xcuserstate",
    "*.xcodeproj/project.xcworkspace/xcuserdata/*",
    "*.xcworkspace/xcuserdata/*",
    "id_dsa*",
    "id_ecdsa*",
    "id_ed25519*",
    "id_rsa*",
)

SENSITIVE_NAME_PATTERNS = (
    ".env",
    ".env.*",
    "*credentials*.json",
    "*credentials*.yaml",
    "*credentials*.yml",
    "*secrets*.json",
    "*secrets*.yaml",
    "*secrets*.yml",
    "*.pem",
    "*.ppk",
    "auth.json",
    "service-account*.json",
)

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("openai-style-key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    (
        "credential-assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|client[_-]?secret|password|access[_-]?token|auth[_-]?token)"
            r"\s*[:=]\s*[\"']?[A-Za-z0-9_./+=:-]{12,}"
        ),
    ),
)


class HandoffError(Exception):
    """Expected, user-actionable workflow error."""


@dataclass(frozen=True)
class SelectedFile:
    path: str
    content: bytes
    sha256: str
    size: int

    @property
    def archive_path(self) -> str:
        return f"repo/{self.path}"

    def manifest_entry(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "archive_path": self.archive_path,
            "size": self.size,
            "sha256": self.sha256,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def pretty_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise HandoffError(f"Unable to hash {path}: {exc}") from exc
    return digest.hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def write_json(path: Path, value: Any) -> None:
    atomic_write(path, pretty_json_bytes(value))


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HandoffError(f"Required artifact not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise HandoffError(f"Unable to read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise HandoffError(f"Expected a JSON object: {path}")
    return value


def run_git(repo: Path, *args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace") if binary else result.stderr
        raise HandoffError(stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def resolve_git_root(repo_arg: str) -> Path:
    requested = Path(repo_arg).expanduser().resolve()
    if not requested.is_dir():
        raise HandoffError(f"Repository directory not found: {requested}")
    output = run_git(requested, "rev-parse", "--show-toplevel")
    root = Path(str(output).strip()).resolve()
    if not root.is_dir():
        raise HandoffError(f"Git root not found: {root}")
    return root


def git_identity(root: Path) -> dict[str, Any]:
    head = str(run_git(root, "rev-parse", "HEAD")).strip()
    branch = str(run_git(root, "rev-parse", "--abbrev-ref", "HEAD")).strip()
    status_output = str(run_git(root, "status", "--porcelain=v1", "--untracked-files=all"))
    dirty_paths = []
    for line in status_output.splitlines():
        if not line:
            continue
        dirty_paths.append({"status": line[:2], "path": line[3:] if len(line) > 3 else ""})
    return {
        "root": str(root),
        "head_sha": head,
        "branch": branch,
        "clean": not dirty_paths,
        "dirty_paths": dirty_paths,
    }


def normalize_rel_path(raw: str, *, label: str) -> str:
    value = raw.strip().replace("\\", "/")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or value == "." or ".." in path.parts:
        raise HandoffError(f"{label} must be a safe workspace-relative path: {raw!r}")
    return path.as_posix()


def normalize_pattern(raw: str, *, label: str) -> str:
    value = raw.strip().replace("\\", "/")
    if not value or value.startswith("/") or ".." in PurePosixPath(value).parts:
        raise HandoffError(f"{label} must be a safe workspace-relative pattern: {raw!r}")
    return value


def matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def builtin_exclusion_reason(rel_path: str) -> str | None:
    parts = PurePosixPath(rel_path).parts
    if any(part in EXCLUDED_DIR_NAMES for part in parts[:-1]):
        return "excluded-directory"
    name = parts[-1]
    if matches_any(name, SENSITIVE_NAME_PATTERNS) or matches_any(rel_path, SENSITIVE_NAME_PATTERNS):
        return "sensitive-filename"
    if matches_any(name, EXCLUDED_FILE_PATTERNS) or matches_any(rel_path, EXCLUDED_FILE_PATTERNS):
        return "excluded-file-pattern"
    return None


def discover_candidates(root: Path) -> list[str]:
    raw = run_git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z", binary=True)
    assert isinstance(raw, bytes)
    paths: list[str] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        path = normalize_rel_path(item.decode("utf-8", "surrogateescape"), label="Git path")
        paths.append(path)
    return sorted(set(paths))


def read_file_list(path_arg: str | None) -> tuple[str | None, list[str]]:
    if not path_arg:
        return None, []
    path = Path(path_arg).expanduser().resolve()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise HandoffError(f"Unable to read file list {path}: {exc}") from exc
    values = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            values.append(normalize_rel_path(stripped, label="File-list entry"))
    return str(path), sorted(set(values))


def is_binary(content: bytes) -> bool:
    return b"\0" in content[:8192]


def secret_findings(rel_path: str, text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for detector, pattern in SECRET_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        findings.append(
            {
                "path": rel_path,
                "detector": detector,
                "line": text.count("\n", 0, match.start()) + 1,
                "action": "excluded",
            }
        )
    return findings


def tree_hash(files: Iterable[SelectedFile]) -> str:
    rows = [
        {"path": item.path, "size": item.size, "sha256": item.sha256}
        for item in sorted(files, key=lambda value: value.path)
    ]
    return sha256_bytes(canonical_json_bytes(rows))


def scan_repository(
    root: Path,
    *,
    include_patterns: list[str],
    exclude_patterns: list[str],
    file_list_entries: list[str],
    max_files: int,
    max_bytes: int,
    max_file_bytes: int,
) -> dict[str, Any]:
    candidates = discover_candidates(root)
    directed = bool(include_patterns or file_list_entries)
    exact = set(file_list_entries)
    candidate_set = set(candidates)
    warnings = [
        f"File-list entry was not found or is Git-ignored: {path}"
        for path in file_list_entries
        if path not in candidate_set
    ]
    included: list[SelectedFile] = []
    excluded: list[dict[str, str]] = []
    omitted: list[dict[str, str]] = []
    security: list[dict[str, Any]] = []

    for rel_path in candidates:
        if matches_any(rel_path, exclude_patterns):
            excluded.append({"path": rel_path, "reason": "user-exclude"})
            continue
        reason = builtin_exclusion_reason(rel_path)
        if reason:
            excluded.append({"path": rel_path, "reason": reason})
            if reason == "sensitive-filename":
                security.append(
                    {"path": rel_path, "detector": "sensitive-filename", "line": None, "action": "excluded"}
                )
            continue
        if directed and rel_path not in exact and not matches_any(rel_path, include_patterns):
            omitted.append({"path": rel_path, "reason": "not-selected"})
            continue

        source = root / rel_path
        if source.is_symlink():
            excluded.append({"path": rel_path, "reason": "symlink"})
            continue
        try:
            size = source.stat().st_size
        except OSError:
            excluded.append({"path": rel_path, "reason": "unreadable"})
            continue
        if size > max_file_bytes:
            excluded.append({"path": rel_path, "reason": "oversized-file"})
            continue
        try:
            content = source.read_bytes()
        except OSError:
            excluded.append({"path": rel_path, "reason": "unreadable"})
            continue
        if is_binary(content):
            excluded.append({"path": rel_path, "reason": "binary-file"})
            continue
        decoded = content.decode("utf-8", "replace")
        findings = secret_findings(rel_path, decoded)
        if findings:
            security.extend(findings)
            excluded.append({"path": rel_path, "reason": "secret-content"})
            continue
        included.append(
            SelectedFile(path=rel_path, content=content, sha256=sha256_bytes(content), size=len(content))
        )

    total_bytes = sum(item.size for item in included)
    if len(included) > max_files:
        raise HandoffError(f"Selected file count {len(included)} exceeds --max-files {max_files}")
    if total_bytes > max_bytes:
        raise HandoffError(f"Selected bytes {total_bytes} exceeds --max-bytes {max_bytes}")
    if not included:
        raise HandoffError("No files remained after selection and security exclusions")

    selection = {
        "mode": "directed" if directed else "whole-repository",
        "include_patterns": include_patterns,
        "exclude_patterns": exclude_patterns,
        "file_list_entries": file_list_entries,
    }
    return {
        "candidates": candidates,
        "included": included,
        "excluded": excluded,
        "omitted": omitted,
        "security": security,
        "warnings": warnings,
        "selection": selection,
        "total_bytes": total_bytes,
    }


def render_prompt(
    *,
    package_id: str,
    mode: str,
    requested_model: str,
    git: dict[str, Any],
    package_tree_hash: str,
    file_count: int,
    total_bytes: int,
    task: str,
    begin_marker: str,
    end_marker: str,
) -> str:
    skill_root = Path(__file__).resolve().parent.parent
    base_path = skill_root / "templates" / "base-prompt.md.tpl"
    mode_path = skill_root / "templates" / f"mode-{mode}.md.tpl"
    try:
        template = base_path.read_text(encoding="utf-8")
        mode_instructions = mode_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise HandoffError(f"Unable to read prompt template: {exc}") from exc
    dirty_summary = "clean at HEAD" if git["clean"] else f"dirty; {len(git['dirty_paths'])} status entries recorded"
    replacements = {
        "PACKAGE_ID": package_id,
        "MODE": mode,
        "REQUESTED_MODEL": requested_model,
        "GIT_SHA": git["head_sha"],
        "TREE_SHA": package_tree_hash,
        "DIRTY_SUMMARY": dirty_summary,
        "FILE_COUNT": str(file_count),
        "TOTAL_BYTES": str(total_bytes),
        "TASK": task.strip(),
        "MODE_INSTRUCTIONS": mode_instructions,
        "BEGIN_MARKER": begin_marker,
        "END_MARKER": end_marker,
    }
    for key, value in replacements.items():
        template = template.replace("{{" + key + "}}", value)
    unresolved = re.findall(r"\{\{[A-Z_]+\}\}", template)
    if unresolved:
        raise HandoffError(f"Unresolved prompt template values: {', '.join(sorted(set(unresolved)))}")
    return template.rstrip() + "\n"


def write_archive(path: Path, files: list[SelectedFile], internal_manifest: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for item in sorted(files, key=lambda value: value.path):
            info = zipfile.ZipInfo(item.archive_path)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, item.content)
        info = zipfile.ZipInfo("_gptpro/file-manifest.json")
        info.date_time = (1980, 1, 1, 0, 0, 0)
        info.external_attr = 0o100644 << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, internal_manifest)


def event_hash(event: dict[str, Any]) -> str:
    payload = {key: value for key, value in event.items() if key != "event_hash"}
    return sha256_bytes(canonical_json_bytes(payload))


def new_receipt(package_id: str, prepared_data: dict[str, Any]) -> dict[str, Any]:
    event = {
        "sequence": 1,
        "timestamp": utc_now(),
        "type": "prepared",
        "data": prepared_data,
        "previous_event_hash": None,
    }
    event["event_hash"] = event_hash(event)
    return {"schema_version": SCHEMA_VERSION, "package_id": package_id, "events": [event]}


def verify_receipt(receipt: dict[str, Any], package_id: str) -> None:
    if receipt.get("schema_version") != SCHEMA_VERSION or receipt.get("package_id") != package_id:
        raise HandoffError("Receipt identity or schema mismatch")
    events = receipt.get("events")
    if not isinstance(events, list) or not events:
        raise HandoffError("Receipt must contain at least one event")
    previous: str | None = None
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            raise HandoffError("Receipt contains a non-object event")
        if event.get("sequence") != index or event.get("previous_event_hash") != previous:
            raise HandoffError(f"Receipt chain mismatch at event {index}")
        actual = event_hash(event)
        if event.get("event_hash") != actual:
            raise HandoffError(f"Receipt event hash mismatch at event {index}")
        previous = actual


def append_receipt_event(handoff_dir: Path, event_type: str, data: dict[str, Any]) -> None:
    path = handoff_dir / "receipt.json"
    receipt = load_json(path)
    package_id = str(receipt.get("package_id", ""))
    verify_receipt(receipt, package_id)
    events = receipt["events"]
    event = {
        "sequence": len(events) + 1,
        "timestamp": utc_now(),
        "type": event_type,
        "data": data,
        "previous_event_hash": events[-1]["event_hash"],
    }
    event["event_hash"] = event_hash(event)
    events.append(event)
    write_json(path, receipt)


def read_task(args: argparse.Namespace) -> str:
    if bool(args.task) == bool(args.task_file):
        raise HandoffError("Provide exactly one of --task or --task-file")
    if args.task:
        task = args.task.strip()
    else:
        path = Path(args.task_file).expanduser().resolve()
        try:
            task = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise HandoffError(f"Unable to read task file {path}: {exc}") from exc
    if not task:
        raise HandoffError("Task must not be empty")
    return task


def create_package(args: argparse.Namespace) -> int:
    root = resolve_git_root(args.repo)
    git = git_identity(root)
    if args.require_clean and not git["clean"]:
        raise HandoffError("Git worktree is dirty and --require-clean was requested")
    include_patterns = [normalize_pattern(value, label="Include pattern") for value in args.include]
    exclude_patterns = [normalize_pattern(value, label="Exclude pattern") for value in args.exclude]
    output_root = (
        Path(args.output_root).expanduser().resolve()
        if args.output_root
        else root / ".gptpro" / "handoffs"
    )
    try:
        output_rel = output_root.relative_to(root).as_posix()
    except ValueError:
        output_rel = None
    if output_rel == ".":
        raise HandoffError("--output-root must not be the repository root")
    if output_rel:
        exclude_patterns.extend([output_rel, f"{output_rel}/**"])
        exclude_patterns = sorted(set(exclude_patterns))
    file_list_path, file_list_entries = read_file_list(args.file_list)
    task = read_task(args)
    scan = scan_repository(
        root,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        file_list_entries=file_list_entries,
        max_files=args.max_files,
        max_bytes=args.max_bytes,
        max_file_bytes=args.max_file_bytes,
    )
    selected: list[SelectedFile] = scan["included"]
    package_tree_hash = tree_hash(selected)
    package_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{args.mode}-{secrets.token_hex(4)}"
    begin_marker = f"BEGIN_GPTPRO_RESPONSE:{package_id}"
    end_marker = f"END_GPTPRO_RESPONSE:{package_id}"
    prompt = render_prompt(
        package_id=package_id,
        mode=args.mode,
        requested_model=args.requested_model,
        git=git,
        package_tree_hash=package_tree_hash,
        file_count=len(selected),
        total_bytes=scan["total_bytes"],
        task=task,
        begin_marker=begin_marker,
        end_marker=end_marker,
    )
    selection = dict(scan["selection"])
    selection["file_list_path"] = file_list_path
    file_entries = [item.manifest_entry() for item in selected]
    internal = {
        "schema_version": SCHEMA_VERSION,
        "package_id": package_id,
        "git": git,
        "selection": selection,
        "files": file_entries,
        "totals": {"included_files": len(selected), "included_bytes": scan["total_bytes"]},
        "packaged_tree_sha256": package_tree_hash,
    }
    internal_bytes = pretty_json_bytes(internal)

    summary = {
        "package_id": package_id,
        "git_head_sha": git["head_sha"],
        "clean": git["clean"],
        "included_files": len(selected),
        "included_bytes": scan["total_bytes"],
        "excluded_files": len(scan["excluded"]),
        "omitted_files": len(scan["omitted"]),
        "security_findings": len(scan["security"]),
        "packaged_tree_sha256": package_tree_hash,
    }
    if args.dry_run:
        print(json.dumps(summary, sort_keys=True, indent=2))
        return 0

    handoff_dir = output_root / package_id
    if handoff_dir.exists():
        raise HandoffError(f"Handoff directory already exists: {handoff_dir}")
    handoff_dir.mkdir(parents=True)
    prompt_path = handoff_dir / "prompt.md"
    archive_path = handoff_dir / f"context-{package_id}.zip"
    atomic_write(prompt_path, prompt.encode("utf-8"))
    write_archive(archive_path, selected, internal_bytes)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "package_id": package_id,
        "created_at": utc_now(),
        "mode": args.mode,
        "task": task,
        "destination": DESTINATION,
        "requested_model": args.requested_model,
        "git": git,
        "selection": selection,
        "limits": {
            "max_files": args.max_files,
            "max_bytes": args.max_bytes,
            "max_file_bytes": args.max_file_bytes,
        },
        "files": file_entries,
        "excluded": scan["excluded"],
        "omitted_by_selection": scan["omitted"],
        "security_findings": scan["security"],
        "warnings": scan["warnings"],
        "totals": {
            "candidate_files": len(scan["candidates"]),
            "included_files": len(selected),
            "included_bytes": scan["total_bytes"],
            "excluded_files": len(scan["excluded"]),
            "omitted_files": len(scan["omitted"]),
        },
        "response_markers": {"begin": begin_marker, "end": end_marker},
        "artifacts": {
            "prompt": prompt_path.name,
            "archive": archive_path.name,
            "state": "state.json",
            "receipt": "receipt.json",
        },
        "hashes": {
            "packaged_tree_sha256": package_tree_hash,
            "prompt_sha256": sha256_file(prompt_path),
            "archive_sha256": sha256_file(archive_path),
            "internal_manifest_sha256": sha256_bytes(internal_bytes),
        },
    }
    manifest_path = handoff_dir / "manifest.json"
    write_json(manifest_path, manifest)
    manifest_hash = sha256_file(manifest_path)
    state = {
        "schema_version": SCHEMA_VERSION,
        "package_id": package_id,
        "phase": "prepared",
        "updated_at": utc_now(),
        "git_head_sha": git["head_sha"],
        "artifact_hashes": {
            "manifest_sha256": manifest_hash,
            "prompt_sha256": manifest["hashes"]["prompt_sha256"],
            "archive_sha256": manifest["hashes"]["archive_sha256"],
        },
        "approval": None,
        "submission": None,
        "response": None,
        "evaluation": None,
    }
    write_json(handoff_dir / "state.json", state)
    receipt = new_receipt(
        package_id,
        {
            "manifest_sha256": manifest_hash,
            "prompt_sha256": manifest["hashes"]["prompt_sha256"],
            "archive_sha256": manifest["hashes"]["archive_sha256"],
            "packaged_tree_sha256": package_tree_hash,
            "git_head_sha": git["head_sha"],
        },
    )
    write_json(handoff_dir / "receipt.json", receipt)
    print(json.dumps({**summary, "handoff_dir": str(handoff_dir)}, sort_keys=True, indent=2))
    return 0


def validate_handoff_dir(path_arg: str) -> Path:
    path = Path(path_arg).expanduser().resolve()
    if not path.is_dir():
        raise HandoffError(f"Handoff directory not found: {path}")
    return path


def verify_package(handoff_dir: Path) -> dict[str, Any]:
    manifest_path = handoff_dir / "manifest.json"
    manifest = load_json(manifest_path)
    state = load_json(handoff_dir / "state.json")
    receipt = load_json(handoff_dir / "receipt.json")
    package_id = manifest.get("package_id")
    if manifest.get("schema_version") != SCHEMA_VERSION or not isinstance(package_id, str):
        raise HandoffError("Manifest identity or schema mismatch")
    if state.get("schema_version") != SCHEMA_VERSION or state.get("package_id") != package_id:
        raise HandoffError("State identity or schema mismatch")
    if state.get("phase") not in PHASES:
        raise HandoffError(f"Unknown state phase: {state.get('phase')}")
    verify_receipt(receipt, package_id)
    if receipt["events"][-1].get("type") != state.get("phase"):
        raise HandoffError("Receipt's latest event does not match the current state phase")

    artifacts = manifest.get("artifacts")
    hashes = manifest.get("hashes")
    files = manifest.get("files")
    if not isinstance(artifacts, dict) or not isinstance(hashes, dict) or not isinstance(files, list):
        raise HandoffError("Manifest artifact, hash, or file fields are invalid")
    state_hashes = state.get("artifact_hashes")
    if not isinstance(state_hashes, dict):
        raise HandoffError("State artifact hashes are invalid")
    manifest_hash = sha256_file(manifest_path)
    if state_hashes.get("manifest_sha256") != manifest_hash:
        raise HandoffError("Manifest hash no longer matches state")

    def artifact_path(key: str) -> Path:
        value = artifacts.get(key)
        if not isinstance(value, str) or not value or PurePosixPath(value).name != value:
            raise HandoffError(f"Unsafe or missing artifact name: {key}")
        return handoff_dir / value

    prompt_path = artifact_path("prompt")
    archive_path = artifact_path("archive")
    expected_hashes = {
        "manifest_sha256": manifest_hash,
        "prompt_sha256": sha256_file(prompt_path),
        "archive_sha256": sha256_file(archive_path),
    }
    if expected_hashes["prompt_sha256"] != hashes.get("prompt_sha256"):
        raise HandoffError("Prompt hash mismatch")
    if expected_hashes["archive_sha256"] != hashes.get("archive_sha256"):
        raise HandoffError("Archive hash mismatch")
    if any(
        state_hashes.get(key) != value for key, value in expected_hashes.items()
    ):
        raise HandoffError("State artifact hashes do not match current artifacts")

    if PHASES.index(state["phase"]) >= PHASES.index("response_imported"):
        response_state = state.get("response")
        if not isinstance(response_state, dict):
            raise HandoffError("Response state is missing")
        raw_response_path = handoff_dir / "raw_response.md"
        response_path = handoff_dir / "response.md"
        if sha256_file(raw_response_path) != response_state.get("raw_response_sha256"):
            raise HandoffError("Raw response hash mismatch")
        if sha256_file(response_path) != response_state.get("response_sha256"):
            raise HandoffError("Imported response hash mismatch")
    if state["phase"] == "evaluated":
        evaluation_state = state.get("evaluation")
        if not isinstance(evaluation_state, dict):
            raise HandoffError("Evaluation state is missing")
        evaluation_path = handoff_dir / "evaluation.json"
        if sha256_file(evaluation_path) != evaluation_state.get("evaluation_sha256"):
            raise HandoffError("Evaluation hash mismatch")
        evaluation = load_json(evaluation_path)
        if evaluation.get("package_id") != package_id:
            raise HandoffError("Evaluation package identity mismatch")
        if evaluation.get("response_sha256") != state["response"]["response_sha256"]:
            raise HandoffError("Evaluation response identity mismatch")

    expected_members = {str(entry.get("archive_path")): entry for entry in files}
    expected_members["_gptpro/file-manifest.json"] = None
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise HandoffError("Archive contains duplicate members")
            for name in names:
                pure = PurePosixPath(name)
                if pure.is_absolute() or ".." in pure.parts:
                    raise HandoffError(f"Archive contains unsafe member: {name}")
            if set(names) != set(expected_members):
                raise HandoffError("Archive member set does not match manifest")
            internal_bytes = archive.read("_gptpro/file-manifest.json")
            if sha256_bytes(internal_bytes) != hashes.get("internal_manifest_sha256"):
                raise HandoffError("Internal manifest hash mismatch")
            internal = json.loads(internal_bytes.decode("utf-8"))
            if internal.get("package_id") != package_id or internal.get("files") != files:
                raise HandoffError("Internal manifest identity or file list mismatch")
            if internal.get("packaged_tree_sha256") != hashes.get("packaged_tree_sha256"):
                raise HandoffError("Internal packaged-tree hash mismatch")
            for name, entry in expected_members.items():
                if entry is None:
                    continue
                data = archive.read(name)
                if len(data) != entry.get("size") or sha256_bytes(data) != entry.get("sha256"):
                    raise HandoffError(f"Archived file hash mismatch: {name}")
    except (OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        raise HandoffError(f"Unable to verify archive: {exc}") from exc

    return {
        "manifest": manifest,
        "state": state,
        "receipt": receipt,
        "manifest_path": manifest_path,
        "prompt_path": prompt_path,
        "archive_path": archive_path,
        "manifest_sha256": expected_hashes["manifest_sha256"],
    }


def command_verify(args: argparse.Namespace) -> int:
    handoff_dir = validate_handoff_dir(args.handoff_dir)
    verified = verify_package(handoff_dir)
    manifest = verified["manifest"]
    state = verified["state"]
    print(
        json.dumps(
            {
                "verified": True,
                "package_id": manifest["package_id"],
                "phase": state["phase"],
                "included_files": manifest["totals"]["included_files"],
                "included_bytes": manifest["totals"]["included_bytes"],
                "security_findings": len(manifest["security_findings"]),
                "git_head_sha": manifest["git"]["head_sha"],
                "git_clean": manifest["git"]["clean"],
            },
            sort_keys=True,
            indent=2,
        )
    )
    return 0


def next_action(phase: str) -> str:
    return {
        "prepared": "show manifest summary and obtain package-specific user approval",
        "approved": "perform visible ChatGPT Pro general Chat handoff",
        "submitted": "wait for completion and import the package-marked response",
        "response_imported": "independently validate the advisory response",
        "evaluated": "report the verified result and any separately authorized implementation",
    }[phase]


def command_status(args: argparse.Namespace) -> int:
    handoff_dir = validate_handoff_dir(args.handoff_dir)
    verified = verify_package(handoff_dir)
    manifest = verified["manifest"]
    state = verified["state"]
    payload = {
        "package_id": manifest["package_id"],
        "phase": state["phase"],
        "next_action": next_action(state["phase"]),
        "destination": manifest["destination"],
        "requested_model": manifest["requested_model"],
        "prompt_path": str(verified["prompt_path"]),
        "archive_path": str(verified["archive_path"]),
        "manifest_path": str(verified["manifest_path"]),
        "response_markers": manifest["response_markers"],
        "git": manifest["git"],
        "totals": manifest["totals"],
        "security_findings": manifest["security_findings"],
        "warnings": manifest["warnings"],
    }
    print(json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


def require_phase(state: dict[str, Any], expected: str) -> None:
    if state.get("phase") != expected:
        raise HandoffError(f"Expected phase {expected!r}, found {state.get('phase')!r}")


def command_approve(args: argparse.Namespace) -> int:
    if not args.confirm_transmission:
        raise HandoffError("Approval requires --confirm-transmission after the user approves the exact package")
    if not args.approved_by.strip():
        raise HandoffError("--approved-by must not be empty")
    handoff_dir = validate_handoff_dir(args.handoff_dir)
    verified = verify_package(handoff_dir)
    state = verified["state"]
    require_phase(state, "prepared")
    approval = {
        "approved_at": utc_now(),
        "approved_by": args.approved_by,
        "destination": verified["manifest"]["destination"],
        "manifest_sha256": verified["manifest_sha256"],
    }
    state["phase"] = "approved"
    state["updated_at"] = approval["approved_at"]
    state["approval"] = approval
    write_json(handoff_dir / "state.json", state)
    append_receipt_event(handoff_dir, "approved", approval)
    print(json.dumps({"package_id": state["package_id"], "phase": "approved"}, indent=2))
    return 0


def command_mark_submitted(args: argparse.Namespace) -> int:
    if not args.confirm_sent:
        raise HandoffError("Submission recording requires --confirm-sent after visible UI confirmation")
    if not args.observed_model.strip():
        raise HandoffError("--observed-model must not be empty")
    if args.thread_url and not args.thread_url.startswith("https://chatgpt.com/"):
        raise HandoffError("--thread-url must be an https://chatgpt.com/ URL")
    handoff_dir = validate_handoff_dir(args.handoff_dir)
    verified = verify_package(handoff_dir)
    state = verified["state"]
    require_phase(state, "approved")
    requested_model = str(verified["manifest"].get("requested_model", ""))
    if args.observed_model.strip() != requested_model:
        raise HandoffError(
            "Observed model/Pro setting does not match the approved manifest; "
            "prepare a new package with an approved --requested-model instead of downgrading"
        )
    submission = {
        "submitted_at": utc_now(),
        "destination": verified["manifest"]["destination"],
        "observed_model": requested_model,
        "thread_url": args.thread_url or None,
    }
    state["phase"] = "submitted"
    state["updated_at"] = submission["submitted_at"]
    state["submission"] = submission
    write_json(handoff_dir / "state.json", state)
    append_receipt_event(handoff_dir, "submitted", submission)
    print(json.dumps({"package_id": state["package_id"], "phase": "submitted"}, indent=2))
    return 0


def extract_response(raw: str, begin: str, end: str) -> str:
    if raw.count(begin) != 1 or raw.count(end) != 1:
        raise HandoffError("Response must contain each package-specific marker exactly once")
    begin_index = raw.index(begin)
    end_index = raw.index(end)
    if begin_index >= end_index:
        raise HandoffError("Response markers are reversed")
    before = raw[:begin_index].strip()
    after = raw[end_index + len(end) :].strip()
    if before or after:
        raise HandoffError("Response contains non-whitespace content outside package markers")
    content = raw[begin_index + len(begin) : end_index].strip()
    if not content:
        raise HandoffError("Marked response content is empty")
    return content + "\n"


def command_import_response(args: argparse.Namespace) -> int:
    handoff_dir = validate_handoff_dir(args.handoff_dir)
    verified = verify_package(handoff_dir)
    state = verified["state"]
    require_phase(state, "submitted")
    try:
        raw = Path(args.response_file).expanduser().resolve().read_text(encoding="utf-8")
    except OSError as exc:
        raise HandoffError(f"Unable to read response file: {exc}") from exc
    markers = verified["manifest"]["response_markers"]
    response = extract_response(raw, markers["begin"], markers["end"])
    raw_path = handoff_dir / "raw_response.md"
    response_path = handoff_dir / "response.md"
    atomic_write(raw_path, raw.encode("utf-8"))
    atomic_write(response_path, response.encode("utf-8"))
    response_state = {
        "imported_at": utc_now(),
        "raw_response_sha256": sha256_file(raw_path),
        "response_sha256": sha256_file(response_path),
    }
    state["phase"] = "response_imported"
    state["updated_at"] = response_state["imported_at"]
    state["response"] = response_state
    write_json(handoff_dir / "state.json", state)
    append_receipt_event(handoff_dir, "response_imported", response_state)
    print(
        json.dumps(
            {"package_id": state["package_id"], "phase": "response_imported", "response_path": str(response_path)},
            indent=2,
        )
    )
    return 0


def command_record_evaluation(args: argparse.Namespace) -> int:
    if not args.summary.strip() or any(not item.strip() for item in args.evidence):
        raise HandoffError("Evaluation summary and evidence entries must not be empty")
    handoff_dir = validate_handoff_dir(args.handoff_dir)
    verified = verify_package(handoff_dir)
    state = verified["state"]
    require_phase(state, "response_imported")
    response_path = handoff_dir / "response.md"
    response_hash = sha256_file(response_path)
    if state.get("response", {}).get("response_sha256") != response_hash:
        raise HandoffError("Imported response hash no longer matches state")
    evaluation = {
        "schema_version": SCHEMA_VERSION,
        "package_id": state["package_id"],
        "evaluated_at": utc_now(),
        "verdict": args.verdict,
        "summary": args.summary.strip(),
        "evidence": args.evidence,
        "applied_git_sha": args.applied_git_sha or None,
        "response_sha256": response_hash,
    }
    evaluation_path = handoff_dir / "evaluation.json"
    write_json(evaluation_path, evaluation)
    evaluation_state = {
        "evaluated_at": evaluation["evaluated_at"],
        "verdict": evaluation["verdict"],
        "evaluation_sha256": sha256_file(evaluation_path),
        "applied_git_sha": evaluation["applied_git_sha"],
    }
    state["phase"] = "evaluated"
    state["updated_at"] = evaluation["evaluated_at"]
    state["evaluation"] = evaluation_state
    write_json(handoff_dir / "state.json", state)
    append_receipt_event(handoff_dir, "evaluated", evaluation_state)
    print(json.dumps({"package_id": state["package_id"], "phase": "evaluated", **evaluation_state}, indent=2))
    return 0


def positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Scan and package repository context")
    prepare.add_argument("--repo", default=".", help="Path inside the target Git repository")
    prepare.add_argument("--mode", choices=MODES, required=True)
    task_group = prepare.add_mutually_exclusive_group(required=True)
    task_group.add_argument("--task")
    task_group.add_argument("--task-file")
    prepare.add_argument("--requested-model", default=DEFAULT_REQUESTED_MODEL)
    prepare.add_argument("--include", action="append", default=[], help="Workspace-relative glob; repeatable")
    prepare.add_argument("--exclude", action="append", default=[], help="Workspace-relative glob; repeatable")
    prepare.add_argument("--file-list", help="UTF-8 file containing exact workspace-relative paths")
    prepare.add_argument("--output-root", help="Handoff parent directory; defaults to <repo>/.gptpro/handoffs")
    prepare.add_argument("--max-files", type=positive_int, default=DEFAULT_MAX_FILES)
    prepare.add_argument("--max-bytes", type=positive_int, default=DEFAULT_MAX_BYTES)
    prepare.add_argument("--max-file-bytes", type=positive_int, default=DEFAULT_MAX_FILE_BYTES)
    prepare.add_argument("--require-clean", action="store_true")
    prepare.add_argument("--dry-run", action="store_true")
    prepare.set_defaults(func=create_package)

    for name, help_text, func in (
        ("verify", "Verify package artifacts and receipt chain", command_verify),
        ("status", "Print machine-readable handoff status", command_status),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--handoff-dir", required=True)
        if name == "status":
            command.add_argument("--json", action="store_true", help="Compatibility flag; output is always JSON")
        command.set_defaults(func=func)

    approve = subparsers.add_parser("approve", help="Record package-specific user approval")
    approve.add_argument("--handoff-dir", required=True)
    approve.add_argument("--approved-by", required=True)
    approve.add_argument("--confirm-transmission", action="store_true")
    approve.set_defaults(func=command_approve)

    submitted = subparsers.add_parser("mark-submitted", help="Record a visibly confirmed browser submission")
    submitted.add_argument("--handoff-dir", required=True)
    submitted.add_argument("--observed-model", required=True)
    submitted.add_argument("--thread-url")
    submitted.add_argument("--confirm-sent", action="store_true")
    submitted.set_defaults(func=command_mark_submitted)

    importer = subparsers.add_parser("import-response", help="Import a package-marked ChatGPT response")
    importer.add_argument("--handoff-dir", required=True)
    importer.add_argument("--response-file", required=True)
    importer.set_defaults(func=command_import_response)

    evaluation = subparsers.add_parser("record-evaluation", help="Record Codex's evidence-backed advisory verdict")
    evaluation.add_argument("--handoff-dir", required=True)
    evaluation.add_argument("--verdict", choices=("accepted", "partially-accepted", "rejected"), required=True)
    evaluation.add_argument("--summary", required=True)
    evaluation.add_argument("--evidence", action="append", required=True)
    evaluation.add_argument("--applied-git-sha")
    evaluation.set_defaults(func=command_record_evaluation)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except HandoffError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
