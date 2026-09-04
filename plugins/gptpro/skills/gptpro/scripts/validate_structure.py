#!/usr/bin/env python3
"""Validate the gptpro v0.6 Schema-6 isolated Electron Runner and mirror."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


REQUIRED_FILES = (
    "SKILL.md",
    "README.md",
    "agents/openai.yaml",
    "scripts/gptpro.py",
    "scripts/chatgpt-desktop.js",
    "scripts/validate_structure.py",
    "runtime/__init__.py",
    "runtime/gptpro_runtime/__init__.py",
    "runtime/gptpro_runtime/approvals.py",
    "runtime/gptpro_runtime/controller.py",
    "runtime/gptpro_runtime/package.py",
    "runtime/gptpro_runtime/receipts.py",
    "runtime/gptpro_runtime/schema.py",
    "runtime/gptpro_runtime/security.py",
    "runtime/gptpro_runtime/state.py",
    "runtime/chatgpt-desktop/async-queue.js",
    "runtime/chatgpt-desktop/app-host-http.js",
    "runtime/chatgpt-desktop/cdp-client.js",
    "runtime/chatgpt-desktop/conversation-client.js",
    "runtime/chatgpt-desktop/conversation-readback.js",
    "runtime/chatgpt-desktop/delta-decoder.js",
    "runtime/chatgpt-desktop/errors.js",
    "runtime/chatgpt-desktop/model-catalog.js",
    "runtime/chatgpt-desktop/private-bridge.js",
    "references/electron-runtime.md",
    "references/failure-reporting.md",
    "references/security.md",
    "references/user-manual.md",
    "references/workflow.md",
    "templates/base-prompt.md.tpl",
    "templates/mode-architecture.md.tpl",
    "templates/mode-ask.md.tpl",
    "templates/mode-debug.md.tpl",
    "templates/mode-plan.md.tpl",
    "templates/mode-review.md.tpl",
    "tests/test_chatgpt_desktop.test.js",
    "tests/test_failure_reporting.py",
    "tests/test_gptpro.py",
    "tests/test_install_transitions.py",
)
EXPECTED_BASE_PLACEHOLDERS = {
    "CONTEXT_ARTIFACT",
    "DIRTY_SUMMARY",
    "FILE_COUNT",
    "GIT_SHA",
    "MODE",
    "MODE_INSTRUCTIONS",
    "PACKAGE_ID",
    "REQUESTED_MODEL",
    "RESPONSE_CONTRACT",
    "TASK",
    "TOTAL_BYTES",
    "TRANSPORT",
    "TRANSPORT_GUIDANCE",
    "TREE_SHA",
}
IGNORED_NAMES = {"__pycache__", ".DS_Store"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


class ValidationError(Exception):
    pass


def ignored(relative: Path) -> bool:
    return any(part in IGNORED_NAMES or " 2." in part for part in relative.parts) or relative.suffix in IGNORED_SUFFIXES


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---(?:\n|\Z)", text, re.DOTALL)
    if not match:
        raise ValidationError("SKILL.md must begin with closed YAML frontmatter")
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        field = re.fullmatch(r"([A-Za-z0-9_-]+):\s*(.+)", line)
        if not field:
            raise ValidationError("SKILL.md frontmatter must use single-line key/value fields")
        key, value = field.groups()
        if key in values:
            raise ValidationError(f"SKILL.md frontmatter repeats {key!r}")
        values[key] = value.strip().strip('"')
    return values


def validate_frontmatter(root: Path, errors: list[str]) -> None:
    try:
        values = parse_frontmatter(root / "SKILL.md")
    except (OSError, UnicodeError, ValidationError) as exc:
        errors.append(str(exc))
        return
    if set(values) != {"name", "description"}:
        errors.append("SKILL.md frontmatter keys must be exactly name and description")
    if values.get("name") != "gptpro":
        errors.append("SKILL.md name must be gptpro")
    description = values.get("description", "")
    if "$gptpro" not in description or "explicit" not in description.lower():
        errors.append("SKILL.md description must keep explicit-only $gptpro invocation wording")
    ui = (root / "agents/openai.yaml").read_text(encoding="utf-8")
    if "$gptpro" not in ui or "$gptpro-mcp" in ui:
        errors.append("UI metadata must explicitly invoke only $gptpro")


def validate_links(root: Path, errors: list[str]) -> None:
    pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    for source in sorted(root.rglob("*.md")):
        relative_source = source.relative_to(root)
        if ignored(relative_source):
            continue
        text = source.read_text(encoding="utf-8")
        for raw in pattern.findall(text):
            target = raw.strip().strip("<>").split("#", 1)[0]
            if not target or urlparse(target).scheme or target.startswith("//"):
                continue
            local = (source.parent / unquote(target)).resolve()
            try:
                local.relative_to(root)
            except ValueError:
                errors.append(f"Local link escapes Skill root: {relative_source} -> {raw}")
                continue
            if not local.exists():
                errors.append(f"Broken local link: {relative_source} -> {raw}")


def validate_templates(root: Path, errors: list[str]) -> None:
    text = (root / "templates/base-prompt.md.tpl").read_text(encoding="utf-8")
    found = set(re.findall(r"\{\{([A-Z_]+)\}\}", text))
    if found != EXPECTED_BASE_PLACEHOLDERS:
        errors.append(
            "Base prompt placeholder contract differs; "
            f"missing={sorted(EXPECTED_BASE_PLACEHOLDERS - found)}, "
            f"unexpected={sorted(found - EXPECTED_BASE_PLACEHOLDERS)}"
        )


def validate_python(root: Path, errors: list[str]) -> None:
    paths = [
        root / "scripts/gptpro.py",
        root / "scripts/validate_structure.py",
        *sorted((root / "runtime").rglob("*.py")),
        *sorted((root / "tests").rglob("*.py")),
    ]
    for path in paths:
        if ignored(path.relative_to(root)):
            continue
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append(f"Python validation failed for {path.relative_to(root)}: {exc}")
    for relative in ("scripts/gptpro.py", "scripts/chatgpt-desktop.js", "scripts/validate_structure.py"):
        if (root / relative).stat().st_mode & 0o111 == 0:
            errors.append(f"Executable script lacks an execute bit: {relative}")


def validate_javascript(root: Path, errors: list[str], checks: list[str]) -> None:
    node = shutil.which("node")
    if node is None:
        errors.append("Node is unavailable; JavaScript syntax was not validated")
        checks.append("javascript-syntax-not-run")
        return
    try:
        version = subprocess.run(
            [node, "--version"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=5, check=False,
        )
        major = int(version.stdout.strip().lstrip("v").split(".", 1)[0])
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired) as exc:
        errors.append(f"Unable to validate the Node version: {exc}")
        checks.append("javascript-syntax-not-run")
        return
    if version.returncode != 0 or major < 22:
        errors.append("Node 22 or newer is required for the Electron runtime")
    for path in [root / "scripts/chatgpt-desktop.js", *sorted((root / "runtime/chatgpt-desktop").glob("*.js"))]:
        result = subprocess.run(
            [node, "--check", str(path)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10, check=False,
        )
        if result.returncode != 0:
            errors.append(f"JavaScript syntax validation failed for {path.relative_to(root)}")
    checks.append("javascript-syntax-node-check")


def validate_runtime_boundary(root: Path, errors: list[str]) -> None:
    source = (root / "scripts/gptpro.py").read_text(encoding="utf-8")
    required = (
        '"component": "gptpro"',
        '"delivery_channels": ["desktop-electron"]',
        '"context_transports": [CONTEXT_TRANSPORT]',
        '"schema-6-inline-immutable-snapshot"',
        '"authenticated-exact-message-readback"',
        '"authenticated-response-readback"',
        '"macos-user-launcher"',
        '"local_functions": False',
        '"server_tool_fallback": False',
        '"mcp_runtime": False',
        '"browser_delivery": False',
        '"computer_use": False',
        '"secure_mcp_tunnel": False',
        '"electron_private_api": True',
        '"minimum_node_major": 22',
    )
    missing = [token for token in required if token not in source]
    if missing:
        errors.append(f"Electron component boundary is incomplete: {missing}")
    bridge_source = (root / "runtime/chatgpt-desktop/private-bridge.js").read_text(encoding="utf-8")
    app_host_source = (root / "runtime/chatgpt-desktop/app-host-http.js").read_text(encoding="utf-8")
    if "sendMessageFromView" in bridge_source or "sendMessageFromView" in app_host_source:
        errors.append("The active Electron runtime must not use the unsupported sendMessageFromView HTTP path")
    for token in ('"connect-app-host"', '"httpFetch"', '"fetch"', '"cancel"'):
        if token not in app_host_source:
            errors.append(f"The app-host HTTP compatibility boundary is missing {token}")
    forbidden_paths = (
        root / "runtime/gptpro_mcp",
        root / "runtime/gptpro_browser",
        root / "scripts/gptpro_mcp.py",
        root / "references/browser-first.md",
        root / "references/browser-handoff.md",
        root / "references/browser-policy.md",
        root / "references/response-monitor.md",
        root / "references/request-correlation.md",
        root / "references/secure-mcp-tunnel.md",
    )
    for path in forbidden_paths:
        if path.exists():
            errors.append(f"Removed transport path remains in the package: {path.relative_to(root)}")
    removed_tool_runtime = root / "runtime/gptpro_runtime/tools.py"
    if removed_tool_runtime.exists():
        errors.append("Removed local ToolRuntime module remains in the package")
    private_contract_files: list[str] = []
    for path in sorted((root / "runtime/chatgpt-desktop").glob("*.js")):
        if "electronBridge" in path.read_text(encoding="utf-8"):
            private_contract_files.append(path.name)
    if private_contract_files != ["private-bridge.js"]:
        errors.append(f"Electron renderer contract is not isolated: {private_contract_files}")
    runtime_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [root / "scripts/chatgpt-desktop.js", *sorted((root / "runtime/chatgpt-desktop").glob("*.js"))]
    )
    credential_extractors = (
        "document.cookie",
        "indexedDB.databases",
        "sessionStorage.getItem",
        'localStorage.getItem("token',
        "Authorization bearer",
    )
    retained = [token for token in credential_extractors if token in runtime_text]
    if retained:
        errors.append(f"Credential/session extraction pattern is present: {retained}")
    controller_text = (root / "runtime/gptpro_runtime/controller.py").read_text(encoding="utf-8")
    conversation_text = (root / "runtime/chatgpt-desktop/conversation-client.js").read_text(encoding="utf-8")
    readback_text = (root / "runtime/chatgpt-desktop/conversation-readback.js").read_text(encoding="utf-8")
    for token in ("ToolRuntime", "local_function_signatures"):
        if token in controller_text or token in conversation_text:
            errors.append(f"Removed local-tool runtime contract remains active: {token}")
    node_entrypoint_text = (root / "scripts/chatgpt-desktop.js").read_text(encoding="utf-8")
    if "is an internal governed command; use gptpro.py" not in node_entrypoint_text:
        errors.append("The internal Desktop ask/collect paths do not require the parent governance entrypoint")
    schema_text = (root / "runtime/gptpro_runtime/schema.py").read_text(encoding="utf-8")
    for token in (
        'CONTEXT_TRANSPORT = "inline-immutable-snapshot"',
        'INLINE_FORMAT = "gptpro-inline-context-v1"',
        'MAX_OUTBOUND_BYTES = 256 * 1024',
        'DEFAULT_MODEL_ID = "gpt-5-6-pro"',
        'CHAT_HISTORY_MODE = "normal"',
    ):
        if token not in schema_text:
            errors.append(f"Schema-6 inline boundary is missing: {token}")
    package_text = (root / "runtime/gptpro_runtime/package.py").read_text(encoding="utf-8")
    if "context.zip" in package_text or "zipfile" in package_text:
        errors.append("The unsent duplicate ZIP package remains active")
    if "continue_consultation" in controller_text or 'add_parser("continue")' in source:
        errors.append("Unproven conversation continuation remains active")
    for token in ('add_parser("launcher-install")', 'add_parser("launcher-status")', 'add_parser("launcher-uninstall")'):
        if token not in source:
            errors.append(f"User launcher CLI is incomplete: {token}")
    for token in (
        "LAUNCHER_BUNDLE_ID",
        "GPTProLauncherScriptSHA256",
        "RENAME_SWAP",
        "RENAME_EXCL",
        "_launcher_lock",
        "GPTPRO_LAUNCHER_IDENTITY_CHANGED",
        "GPTPRO_LAUNCHER_TRASH_CROSS_VOLUME",
        "process_state_unknown",
        "runner_verified",
        "RUNNER_PORT = 9223",
        "--user-data-dir=$runner_profile",
        '"ordinary_chatgpt_relaunch_required": False',
        "--remote-debugging-address=127.0.0.1",
        "automatic_app_termination\": False",
        "login_item_installed\": False",
    ):
        if token not in controller_text:
            errors.append(f"User launcher safety boundary is incomplete: {token}")
    if "waitForConversationResponse" not in conversation_text or 'add_parser("collect-response")' not in source:
        errors.append("Authenticated exact-conversation readback recovery is incomplete")
    for token in ("waitForConversationResponse", "response_readback", "conversation-readback-live-v1"):
        if token not in conversation_text:
            errors.append(f"Primary exact-message readback is incomplete: {token}")
    for token in ('completion_source: "conversation-readback-v1"', 'final.status !== "finished_successfully"', "final.end_turn !== true"):
        if token not in readback_text:
            errors.append(f"Conversation readback integrity contract is missing: {token}")


def package_files(root: Path) -> dict[str, tuple[int, str]]:
    result: dict[str, tuple[int, str]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if ignored(relative):
            continue
        if path.is_symlink():
            raise ValidationError(f"Symlink is not allowed: {relative.as_posix()}")
        if not path.is_file():
            continue
        result[relative.as_posix()] = (path.stat().st_mode & 0o777, sha256_file(path))
    return result


def validate_mirror(root: Path, mirror: Path, errors: list[str]) -> None:
    if not mirror.is_dir():
        errors.append(f"Mirror directory not found: {mirror}")
        return
    try:
        source_files = package_files(root)
        mirror_files = package_files(mirror)
    except (OSError, ValidationError) as exc:
        errors.append(str(exc))
        return
    if source_files != mirror_files:
        errors.append(
            "Plugin mirror differs from standalone Skill; "
            f"missing={sorted(set(source_files) - set(mirror_files))}, "
            f"extra={sorted(set(mirror_files) - set(source_files))}, "
            f"changed={sorted(path for path in set(source_files) & set(mirror_files) if source_files[path] != mirror_files[path])}"
        )


def validate(root_value: Path, mirror: Path | None) -> dict[str, object]:
    root = root_value.expanduser().resolve()
    errors: list[str] = []
    checks = [
        "required-files",
        "frontmatter-and-ui-trigger",
        "local-links",
        "prompt-placeholders",
        "python-syntax-and-mode",
        "electron-runtime-boundary",
    ]
    if not root.is_dir():
        errors.append(f"Skill directory not found: {root}")
    else:
        for relative in REQUIRED_FILES:
            if not (root / relative).is_file():
                errors.append(f"Required file missing: {relative}")
        if not errors:
            validate_frontmatter(root, errors)
            validate_links(root, errors)
            validate_templates(root, errors)
            validate_python(root, errors)
            validate_javascript(root, errors, checks)
            validate_runtime_boundary(root, errors)
    if mirror is not None and root.is_dir():
        validate_mirror(root, mirror.expanduser().resolve(), errors)
        checks.append("standalone-plugin-byte-and-mode-mirror")
    return {
        "valid": not errors,
        "skill_root": str(root),
        "mirror": str(mirror.expanduser().resolve()) if mirror else None,
        "checks": checks,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill-dir", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--mirror")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = validate(Path(args.skill_dir), Path(args.mirror) if args.mirror else None)
    if args.json:
        print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))
    elif result["valid"]:
        print(f"Skill structure is valid: {result['skill_root']}")
    else:
        for error in result["errors"]:
            print(f"Error: {error}", file=sys.stderr)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
