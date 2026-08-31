#!/usr/bin/env python3
"""Validate the Desktop-only gptpro orchestration Skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse


REQUIRED_FILES = (
    "SKILL.md",
    "README.md",
    "agents/openai.yaml",
    "scripts/gptpro.py",
    "scripts/validate_structure.py",
    "references/advisory-validation.md",
    "references/desktop-workflow.md",
    "references/failure-reporting.md",
    "references/human-takeover.md",
    "references/legacy-receipts.md",
    "references/manifest-schema.md",
    "references/security.md",
    "references/standing-approval.md",
    "references/supplemental-documents.md",
    "references/user-manual.md",
    "references/workflow.md",
    "templates/base-prompt.md.tpl",
    "templates/mode-architecture.md.tpl",
    "templates/mode-ask.md.tpl",
    "templates/mode-debug.md.tpl",
    "templates/mode-plan.md.tpl",
    "templates/mode-review.md.tpl",
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


class ValidationError(Exception):
    pass


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
    if values.get("name") != root.name:
        errors.append("SKILL.md name must match the Skill directory")
    ui = (root / "agents/openai.yaml").read_text(encoding="utf-8")
    if "$gptpro" not in ui or "$gptpro-mcp" in ui:
        errors.append("Base UI metadata must explicitly invoke only $gptpro")


def validate_links(root: Path, errors: list[str]) -> None:
    pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    for source in sorted(root.rglob("*.md")):
        text = source.read_text(encoding="utf-8")
        for raw in pattern.findall(text):
            target = raw.strip().strip("<>").split("#", 1)[0]
            if not target or urlparse(target).scheme or target.startswith("//"):
                continue
            local = (source.parent / unquote(target)).resolve()
            try:
                local.relative_to(root)
            except ValueError:
                errors.append(f"Local link escapes Skill root: {source.relative_to(root)} -> {raw}")
                continue
            if not local.exists():
                errors.append(f"Broken local link: {source.relative_to(root)} -> {raw}")


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
    files = {
        root / "scripts/gptpro.py",
        root / "scripts/validate_structure.py",
        *sorted((root / "runtime").rglob("*.py")),
        *sorted((root / "tests").rglob("*.py")),
    }
    for path in sorted(files):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append(f"Python validation failed for {path.relative_to(root)}: {exc}")
    for relative in ("scripts/gptpro.py", "scripts/validate_structure.py"):
        if (root / relative).stat().st_mode & 0o111 == 0:
            errors.append(f"Executable script lacks an execute bit: {relative}")


def validate_base_boundary(root: Path, errors: list[str]) -> None:
    forbidden_paths = (
        root / "scripts/gptpro_mcp.py",
        root / "runtime",
        root / "references/request-correlation.md",
        root / "references/web-mcp.md",
        root / "references/browser-first.md",
        root / "references/browser-handoff.md",
        root / "references/browser-policy.md",
        root / "references/response-monitor.md",
    )
    for path in forbidden_paths:
        if path.is_file() or (path.is_dir() and any(item.is_file() for item in path.rglob("*"))):
            errors.append(f"Desktop-only base retains a removed runtime path: {path.relative_to(root)}")
    source = (root / "scripts/gptpro.py").read_text(encoding="utf-8")
    required = (
        '"component": "gptpro"',
        '"mcp_runtime": False',
        '"delivery_channels": ["desktop-ui"]',
        '"browser_delivery": False',
        '"cdp": False',
        '"electron_private_api": False',
        "GPTPRO_MCP_COMPONENT_REQUIRED",
        "gptpro-context-export-v1",
    )
    missing = [token for token in required if token not in source]
    if missing:
        errors.append(f"Desktop-only component boundary is incomplete: {missing}")
    forbidden_tokens = (
        "runtime.gptpro_mcp",
        "runtime.gptpro_browser",
        "command_browser_plan",
        "command_response_monitor_plan",
        "remote-debugging-port",
        "electronBridge",
    )
    retained = [token for token in forbidden_tokens if token in source]
    if retained:
        errors.append(f"Desktop-only base retains forbidden delivery code: {retained}")


def validate_visible_app_identity(root: Path, errors: list[str]) -> None:
    """Keep the Codex display name separate from the ChatGPT-visible app name."""

    documents = {
        "SKILL.md": (
            "# GPT Pro Collaborator",
            "--chatgpt-app-name 'gptpro'",
            "`gptpro` is the ChatGPT plugin/app name",
        ),
        "README.md": (
            "Skill 이름은 `GPT Pro Collaborator`",
            "App 이름은 `gptpro`",
        ),
        "references/user-manual.md": (
            "ChatGPT Plugins에 보이는 App 이름은 `gptpro`",
            "Codex의 Skill/Plugin 목록에서는 `GPT Pro Collaborator`",
        ),
        "references/desktop-workflow.md": (
            "`GPT Pro Collaborator`: Codex",
            "`gptpro`: ChatGPT Plugins",
            "`gpt-pro-collaborator`: owner-only",
        ),
    }
    for relative, required in documents.items():
        try:
            text = (root / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"Unable to inspect ChatGPT app identity in {relative}: {exc}")
            continue
        missing = [token for token in required if token not in text]
        if missing:
            errors.append(f"ChatGPT app identity contract is incomplete in {relative}: {missing}")
    try:
        skill = (root / "SKILL.md").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return
    if "--chatgpt-app-name 'GPT Pro Collaborator'" in skill:
        errors.append("Copyable consult command conflates the Codex display name with the ChatGPT app")


def package_files(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if (
            not path.is_file()
            or any(part in IGNORED_NAMES for part in path.relative_to(root).parts)
            or path.suffix in {".pyc", ".pyo"}
        ):
            continue
        result[path.relative_to(root).as_posix()] = sha256_file(path)
    return result


def validate_mirror(root: Path, mirror: Path, errors: list[str]) -> None:
    if not mirror.is_dir():
        errors.append(f"Mirror directory not found: {mirror}")
        return
    source_files = package_files(root)
    mirror_files = package_files(mirror)
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
            validate_base_boundary(root, errors)
            validate_visible_app_identity(root, errors)
    if mirror is not None and root.is_dir():
        validate_mirror(root, mirror.expanduser().resolve(), errors)
    return {
        "valid": not errors,
        "skill_root": str(root),
        "mirror": str(mirror.expanduser().resolve()) if mirror else None,
        "checks": [
            "required-files",
            "frontmatter",
            "local-links",
            "prompt-placeholders",
            "python-syntax-and-mode",
            "desktop-only-component-boundary",
            "chatgpt-visible-app-identity",
            *(("standalone-plugin-mirror",) if mirror else ()),
        ],
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
