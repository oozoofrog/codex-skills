#!/usr/bin/env python3
"""Validate the gptpro Skill structure without third-party dependencies."""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
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
    "scripts/gptpro_mcp.py",
    "scripts/validate_structure.py",
    "references/advisory-validation.md",
    "references/browser-handoff.md",
    "references/github-transport.md",
    "references/human-takeover.md",
    "references/manifest-schema.md",
    "references/security.md",
    "references/web-mcp.md",
    "references/workflow.md",
    "runtime/__init__.py",
    "runtime/gptpro_mcp/__init__.py",
    "runtime/gptpro_mcp/archive.py",
    "runtime/gptpro_mcp/audit.py",
    "runtime/gptpro_mcp/authorization.py",
    "runtime/gptpro_mcp/clock.py",
    "runtime/gptpro_mcp/controller.py",
    "runtime/gptpro_mcp/cursor.py",
    "runtime/gptpro_mcp/errors.py",
    "runtime/gptpro_mcp/live.py",
    "runtime/gptpro_mcp/package_lock.py",
    "runtime/gptpro_mcp/package_tx.py",
    "runtime/gptpro_mcp/protocol.py",
    "runtime/gptpro_mcp/runtime_state.py",
    "runtime/gptpro_mcp/schema.py",
    "runtime/gptpro_mcp/server.py",
    "runtime/gptpro_mcp/supervisor.py",
    "runtime/gptpro_mcp/tools.py",
    "runtime/gptpro_mcp/tunnel_client.py",
    "templates/base-prompt.md.tpl",
    "templates/mode-architecture.md.tpl",
    "templates/mode-ask.md.tpl",
    "templates/mode-debug.md.tpl",
    "templates/mode-plan.md.tpl",
    "templates/mode-review.md.tpl",
    "tests/test_gptpro.py",
    "tests/test_mcp_lifecycle.py",
    "tests/test_mcp_live.py",
    "tests/test_mcp_package_lock.py",
    "tests/test_mcp_package_tx.py",
    "tests/test_mcp_controller.py",
    "tests/test_mcp_server.py",
    "tests/test_web_mcp_foundation.py",
    "tests/test_web_mcp_runtime.py",
)

EXPECTED_FRONTMATTER_KEYS = {"name", "description"}
EXPECTED_BASE_PLACEHOLDERS = {
    "BEGIN_MARKER",
    "CONTEXT_ARTIFACT",
    "DIRTY_SUMMARY",
    "END_MARKER",
    "FILE_COUNT",
    "GIT_SHA",
    "MODE",
    "MODE_INSTRUCTIONS",
    "PACKAGE_ID",
    "REQUESTED_MODEL",
    "TASK",
    "TOTAL_BYTES",
    "TRANSPORT",
    "TRANSPORT_GUIDANCE",
    "TREE_SHA",
}
IGNORED_NAMES = {"__pycache__", ".DS_Store"}


class ValidationError(Exception):
    """A deterministic Skill structure validation failure."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_simple_frontmatter(skill_md: Path) -> dict[str, str]:
    text = skill_md.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---(?:\n|\Z)", text, re.DOTALL)
    if not match:
        raise ValidationError("SKILL.md must begin with a closed YAML frontmatter block")
    values: dict[str, str] = {}
    for line_number, line in enumerate(match.group(1).splitlines(), start=2):
        if not line.strip():
            continue
        field = re.fullmatch(r"([A-Za-z0-9_-]+):\s*(.+)", line)
        if not field:
            raise ValidationError(
                f"SKILL.md frontmatter line {line_number} must be a single-line key/value"
            )
        key, raw_value = field.groups()
        if key in values:
            raise ValidationError(f"SKILL.md frontmatter repeats key {key!r}")
        value = raw_value.strip()
        if value.startswith(('"', "'")):
            if value[0] == '"':
                try:
                    decoded = json.loads(value)
                except json.JSONDecodeError as exc:
                    raise ValidationError(f"Invalid quoted frontmatter value for {key!r}") from exc
                if not isinstance(decoded, str):
                    raise ValidationError(f"Frontmatter value for {key!r} must be a string")
                value = decoded
            elif len(value) >= 2 and value.endswith("'"):
                value = value[1:-1].replace("''", "'")
            else:
                raise ValidationError(f"Invalid quoted frontmatter value for {key!r}")
        values[key] = value
    return values


def validate_frontmatter(skill_root: Path, errors: list[str]) -> None:
    try:
        values = parse_simple_frontmatter(skill_root / "SKILL.md")
    except (OSError, UnicodeDecodeError, ValidationError) as exc:
        errors.append(str(exc))
        return
    if set(values) != EXPECTED_FRONTMATTER_KEYS:
        errors.append(
            "SKILL.md frontmatter keys must be exactly name and description; found "
            + ", ".join(sorted(values))
        )
    name = values.get("name", "")
    if name != skill_root.name or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        errors.append(f"Skill name {name!r} must match directory {skill_root.name!r} and use hyphen-case")
    description = values.get("description", "")
    if not description or len(description) > 1024:
        errors.append("Skill description must contain 1-1024 characters")
    if "$gptpro" not in (skill_root / "agents/openai.yaml").read_text(encoding="utf-8"):
        errors.append("agents/openai.yaml default prompt must explicitly invoke $gptpro")


def validate_links(skill_root: Path, errors: list[str]) -> None:
    link_pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    for source in sorted(skill_root.rglob("*.md")):
        try:
            text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"Unable to read Markdown file {source.relative_to(skill_root)}: {exc}")
            continue
        for raw_target in link_pattern.findall(text):
            target = raw_target.strip().strip("<>").split("#", 1)[0]
            if not target or urlparse(target).scheme or target.startswith("//"):
                continue
            local = (source.parent / unquote(target)).resolve()
            try:
                local.relative_to(skill_root)
            except ValueError:
                errors.append(
                    f"Local link escapes Skill root: {source.relative_to(skill_root)} -> {raw_target}"
                )
                continue
            if not local.exists():
                errors.append(
                    f"Broken local link: {source.relative_to(skill_root)} -> {raw_target}"
                )


def validate_templates(skill_root: Path, errors: list[str]) -> None:
    base = skill_root / "templates/base-prompt.md.tpl"
    try:
        placeholders = set(re.findall(r"\{\{([A-Z_]+)\}\}", base.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"Unable to read base prompt template: {exc}")
        return
    if placeholders != EXPECTED_BASE_PLACEHOLDERS:
        errors.append(
            "Base prompt placeholders differ from the expected contract; missing="
            f"{sorted(EXPECTED_BASE_PLACEHOLDERS - placeholders)}, "
            f"unexpected={sorted(placeholders - EXPECTED_BASE_PLACEHOLDERS)}"
        )


def validate_python(skill_root: Path, errors: list[str]) -> None:
    python_files = {
        skill_root / "scripts/gptpro.py",
        skill_root / "scripts/gptpro_mcp.py",
        skill_root / "scripts/validate_structure.py",
        *sorted((skill_root / "runtime").rglob("*.py")),
        *sorted((skill_root / "tests").rglob("*.py")),
    }
    for path in sorted(python_files):
        relative = path.relative_to(skill_root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"Python validation failed for {relative}: {exc}")
    for relative in (
        "scripts/gptpro.py",
        "scripts/gptpro_mcp.py",
        "scripts/validate_structure.py",
    ):
        path = skill_root / relative
        if path.exists() and path.stat().st_mode & 0o111 == 0:
            errors.append(f"Executable script lacks an execute bit: {relative}")


def validate_mcp_foundation(skill_root: Path, errors: list[str]) -> None:
    relative = "runtime/gptpro_mcp/schema.py"
    path = skill_root / relative
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        errors.append(f"Unable to inspect Web MCP schema fixture: {exc}")
        return
    allowed_imports = {"__future__", "hashlib", "json", "typing"}
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    unexpected = sorted(imported - allowed_imports)
    if unexpected:
        errors.append(f"Web MCP schema fixture imports non-stdlib modules: {unexpected}")
        return
    try:
        spec = importlib.util.spec_from_file_location("gptpro_structure_mcp_schema", path)
        if spec is None or spec.loader is None:
            raise ValidationError("unable to create module specification")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        expected_names = (
            "gptpro_package_info",
            "gptpro_repo_read",
            "gptpro_repo_search",
        )
        if module.TOOL_NAMES != expected_names:
            errors.append(
                "Web MCP phase-1 tool names must be the exact read-only catalog; "
                f"found={module.TOOL_NAMES!r}"
            )
        for tool in module.TOOL_CATALOG:
            annotations = tool.get("annotations", {})
            if annotations != {
                "readOnlyHint": True,
                "destructiveHint": False,
                "openWorldHint": False,
                "idempotentHint": True,
            }:
                errors.append(f"Web MCP tool {tool.get('name')!r} has unsafe annotations")
        if re.fullmatch(r"[0-9a-f]{64}", module.tool_schema_sha256()) is None:
            errors.append("Web MCP canonical tool-schema hash is invalid")
        module.validate_limits(dict(module.DEFAULT_LIMITS))
    except (AttributeError, TypeError, ValueError, ValidationError) as exc:
        errors.append(f"Web MCP schema fixture validation failed: {exc}")


def validate_mcp_runtime_dependencies(skill_root: Path, errors: list[str]) -> None:
    """Reject accidental third-party imports in the portable MCP runtime."""

    paths = [skill_root / "scripts/gptpro_mcp.py"] + sorted(
        (skill_root / "runtime/gptpro_mcp").glob("*.py")
    )
    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    allowed_local = {"runtime"}
    for path in paths:
        relative = path.relative_to(skill_root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"Unable to inspect MCP runtime dependencies in {relative}: {exc}")
            continue
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".", 1)[0])
        local_modules = set(allowed_local)
        if relative == "scripts/gptpro_mcp.py":
            # The stdio entrypoint loads its sibling governance module only after
            # an activation capability is present. It is packaged local code,
            # not a third-party runtime dependency.
            local_modules.add("gptpro")
        unexpected = sorted(imported - stdlib - local_modules - {"__future__"})
        if unexpected:
            errors.append(
                f"Portable MCP runtime imports third-party modules in {relative}: {unexpected}"
            )


def validate_canonical_runtime_slot(skill_root: Path, errors: list[str]) -> None:
    """Prevent a second public authorization namespace from reappearing."""

    path = skill_root / "scripts/gptpro.py"
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"Unable to inspect the lifecycle CLI runtime slot: {exc}")
        return
    if "--runtime-dir" in source:
        errors.append(
            "The lifecycle CLI must not expose --runtime-dir; all commands share one per-user slot"
        )


def package_files(skill_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(skill_root.rglob("*")):
        if not path.is_file() or any(part in IGNORED_NAMES for part in path.parts) or path.suffix == ".pyc":
            continue
        result[path.relative_to(skill_root).as_posix()] = sha256_file(path)
    return result


def validate_mirror(skill_root: Path, mirror: Path, errors: list[str]) -> None:
    if not mirror.is_dir():
        errors.append(f"Mirror directory not found: {mirror}")
        return
    primary_files = package_files(skill_root)
    mirror_files = package_files(mirror)
    if primary_files != mirror_files:
        errors.append(
            "Plugin mirror differs from standalone Skill; "
            f"missing={sorted(set(primary_files) - set(mirror_files))}, "
            f"extra={sorted(set(mirror_files) - set(primary_files))}, "
            f"changed={sorted(path for path in set(primary_files) & set(mirror_files) if primary_files[path] != mirror_files[path])}"
        )
    for relative in (
        "scripts/gptpro.py",
        "scripts/gptpro_mcp.py",
        "scripts/validate_structure.py",
    ):
        primary_mode = (skill_root / relative).stat().st_mode & 0o111
        mirror_mode = (mirror / relative).stat().st_mode & 0o111 if (mirror / relative).exists() else 0
        if primary_mode != mirror_mode:
            errors.append(f"Plugin mirror execute mode differs for {relative}")


def validate(skill_root: Path, mirror: Path | None) -> dict[str, object]:
    root = skill_root.expanduser().resolve()
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
            validate_mcp_foundation(root, errors)
            validate_mcp_runtime_dependencies(root, errors)
            validate_canonical_runtime_slot(root, errors)
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
            "web-mcp-read-only-schema",
            "web-mcp-stdlib-runtime",
            "web-mcp-canonical-runtime-slot",
            *(("standalone-plugin-mirror",) if mirror else ()),
        ],
        "errors": errors,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skill-dir",
        default=str(Path(__file__).resolve().parent.parent),
        help="Skill directory; defaults to the parent of this script",
    )
    parser.add_argument("--mirror", help="Optional Plugin mirror directory to compare byte-for-byte")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
