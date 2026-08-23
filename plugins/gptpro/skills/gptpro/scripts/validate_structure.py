#!/usr/bin/env python3
"""Validate the gptpro Skill structure without third-party dependencies."""

from __future__ import annotations

import argparse
import ast
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
    "references/browser-handoff.md",
    "references/github-transport.md",
    "references/human-takeover.md",
    "references/manifest-schema.md",
    "references/security.md",
    "references/web-mcp.md",
    "references/workflow.md",
    "runtime/__init__.py",
    "runtime/gptpro_mcp/__init__.py",
    "runtime/gptpro_mcp/schema.py",
    "templates/base-prompt.md.tpl",
    "templates/mode-architecture.md.tpl",
    "templates/mode-ask.md.tpl",
    "templates/mode-debug.md.tpl",
    "templates/mode-plan.md.tpl",
    "templates/mode-review.md.tpl",
    "tests/test_gptpro.py",
    "tests/test_web_mcp_foundation.py",
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
    python_files = (
        "scripts/gptpro.py",
        "scripts/validate_structure.py",
        "runtime/__init__.py",
        "runtime/gptpro_mcp/__init__.py",
        "runtime/gptpro_mcp/schema.py",
        "tests/test_gptpro.py",
        "tests/test_web_mcp_foundation.py",
    )
    for relative in python_files:
        path = skill_root / relative
        try:
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            errors.append(f"Python validation failed for {relative}: {exc}")
    for relative in ("scripts/gptpro.py", "scripts/validate_structure.py"):
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

    allowed_assignments = {
        "PROTOCOL_PROFILE",
        "SERVER_NAME",
        "SERVER_VERSION",
        "SERVER_INSTRUCTIONS",
        "DEFAULT_LIMITS",
        "HARD_LIMITS",
        "COMMON_ANNOTATIONS",
        "TOOL_CATALOG",
        "TOOL_NAMES",
    }
    allowed_functions = {
        "_string_property",
        "canonical_json_bytes",
        "tool_schema_payload",
        "tool_schema_sha256",
        "validate_limits",
    }
    assignments: dict[str, ast.expr] = {}
    top_level_errors: list[str] = []
    for index, statement in enumerate(tree.body):
        if isinstance(statement, ast.Expr):
            if index == 0 and isinstance(statement.value, ast.Constant) and isinstance(
                statement.value.value, str
            ):
                continue
            top_level_errors.append(type(statement).__name__)
        elif isinstance(statement, (ast.Import, ast.ImportFrom)):
            continue
        elif isinstance(statement, ast.Assign):
            if len(statement.targets) != 1 or not isinstance(statement.targets[0], ast.Name):
                top_level_errors.append("complex assignment")
                continue
            name = statement.targets[0].id
            if name in assignments:
                top_level_errors.append(f"duplicate assignment {name!r}")
                continue
            assignments[name] = statement.value
        elif isinstance(statement, ast.AnnAssign):
            if not isinstance(statement.target, ast.Name) or statement.value is None:
                top_level_errors.append("complex annotated assignment")
                continue
            name = statement.target.id
            if name in assignments:
                top_level_errors.append(f"duplicate assignment {name!r}")
                continue
            assignments[name] = statement.value
        elif isinstance(statement, ast.FunctionDef):
            if statement.name not in allowed_functions or statement.decorator_list:
                top_level_errors.append(f"function {statement.name!r}")
            defaults = [*statement.args.defaults, *statement.args.kw_defaults]
            if any(
                default is not None and any(isinstance(node, ast.Call) for node in ast.walk(default))
                for default in defaults
            ):
                top_level_errors.append(f"function default {statement.name!r}")
        else:
            top_level_errors.append(type(statement).__name__)
    unexpected_assignments = sorted(set(assignments) - allowed_assignments)
    missing_assignments = sorted(allowed_assignments - set(assignments))
    if top_level_errors or unexpected_assignments or missing_assignments:
        errors.append(
            "Web MCP schema fixture has unsafe or unexpected top-level structure; "
            f"statements={top_level_errors}, assignments={unexpected_assignments}, "
            f"missing={missing_assignments}"
        )
        return

    for name, value in assignments.items():
        if name in {"TOOL_CATALOG", "TOOL_NAMES"}:
            continue
        if any(isinstance(node, ast.Call) for node in ast.walk(value)):
            errors.append(f"Web MCP schema fixture assignment {name!r} contains a call")
            return

    try:
        expected_names = (
            "gptpro_package_info",
            "gptpro_repo_read",
            "gptpro_repo_search",
        )
        expected_annotations = {
            "readOnlyHint": True,
            "destructiveHint": False,
            "openWorldHint": False,
            "idempotentHint": True,
        }
        annotations = ast.literal_eval(assignments["COMMON_ANNOTATIONS"])
        if annotations != expected_annotations:
            errors.append("Web MCP common tool annotations are unsafe")

        catalog = assignments["TOOL_CATALOG"]
        if not isinstance(catalog, (ast.Tuple, ast.List)):
            raise ValidationError("TOOL_CATALOG must be a static tuple or list")
        found_names: list[str] = []
        for entry in catalog.elts:
            if not isinstance(entry, ast.Dict):
                raise ValidationError("TOOL_CATALOG entries must be static dictionaries")
            fields: dict[str, ast.expr] = {}
            for key, value in zip(entry.keys, entry.values, strict=True):
                if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                    raise ValidationError("TOOL_CATALOG keys must be string literals")
                fields[key.value] = value
            name_node = fields.get("name")
            if not isinstance(name_node, ast.Constant) or not isinstance(name_node.value, str):
                raise ValidationError("Each Web MCP tool must have one static name")
            found_names.append(name_node.value)
            annotation_node = fields.get("annotations")
            if not isinstance(annotation_node, ast.Name) or annotation_node.id != "COMMON_ANNOTATIONS":
                raise ValidationError(f"Web MCP tool {name_node.value!r} has unsafe annotations")
            for call in (node for node in ast.walk(entry) if isinstance(node, ast.Call)):
                if (
                    not isinstance(call.func, ast.Name)
                    or call.func.id != "_string_property"
                    or call.args
                    or len(call.keywords) != 1
                    or call.keywords[0].arg != "maximum"
                    or not isinstance(call.keywords[0].value, ast.Constant)
                    or isinstance(call.keywords[0].value.value, bool)
                    or not isinstance(call.keywords[0].value.value, int)
                ):
                    raise ValidationError("TOOL_CATALOG contains an unsafe call expression")
        found_names_tuple = tuple(sorted(found_names))
        if found_names_tuple != expected_names:
            errors.append(
                "Web MCP phase-1 tool names must be the exact read-only catalog; "
                f"found={found_names_tuple!r}"
            )
        expected_tool_names_expression = ast.parse(
            'tuple(sorted(tool["name"] for tool in TOOL_CATALOG))', mode="eval"
        ).body
        if ast.dump(assignments["TOOL_NAMES"], include_attributes=False) != ast.dump(
            expected_tool_names_expression,
            include_attributes=False,
        ):
            errors.append("Web MCP TOOL_NAMES must derive only from the static catalog")
    except (TypeError, ValueError, ValidationError) as exc:
        errors.append(f"Web MCP schema fixture validation failed: {exc}")


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
    for relative in ("scripts/gptpro.py", "scripts/validate_structure.py"):
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
