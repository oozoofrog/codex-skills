#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

CONTEXT_FILENAMES = {"CLAUDE.md", "CONTEXT.md", "AGENTS.md"}
COMMON_EXTENSIONS = {
    ".md",
    ".txt",
    ".py",
    ".sh",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".swift",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".rb",
    ".go",
    ".rs",
    ".java",
    ".kt",
}
DEFAULT_IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "dist",
    "build",
    "out",
    "coverage",
    ".next",
    ".turbo",
    ".venv",
    "venv",
    "__pycache__",
    "DerivedData",
}
DEFAULT_LINE_LIMITS = {
    "CLAUDE.md": {"hint": 150, "error": 200},
    "CONTEXT.md": {"hint": 120},
    "AGENTS.md": {"hint": 120},
}
SECTION_SIGNALS = {
    "CLAUDE.md": [
        ("commands", ["command", "commands", "명령"]),
        ("architecture", ["architecture", "아키텍처"]),
        ("context-entry-points", ["context tree", "entry point", "entry points", "컨텍스트", "subsystem", "서브시스템"]),
    ],
    "CONTEXT.md": [
        ("scope", ["scope", "범위", "책임"]),
        ("key-files", ["key files", "key file", "핵심 파일"]),
        ("local-rules", ["local rules", "rules", "규칙"]),
        ("verification", ["verification", "검증"]),
    ],
    "AGENTS.md": [
        ("collaboration", ["collaboration", "협업"]),
        ("output-contract", ["output contract", "출력 계약"]),
        ("review", ["review", "리뷰"]),
    ],
}
DEFAULT_MAX_CODE_BLOCK_LINES = 80
DEFAULT_CONFIG_FILES = (
    ".context-audit.yml",
    ".context-audit.yaml",
    ".context-audit.json",
)

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
CODE_FENCE_RE = re.compile(r"```.*?```", re.S)
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", re.M)
TODO_RE = re.compile(r"\bTODO\b|\[TODO[:\]]", re.IGNORECASE)


@dataclass
class Issue:
    severity: str
    kind: str
    source: str
    target: str
    message: str


@dataclass
class Hint:
    kind: str
    source: str
    message: str


@dataclass
class DocSummary:
    path: str
    line_count: int
    inbound_links: int
    outbound_links: int
    local_ref_count: int
    heading_count: int


@dataclass
class AuditConfig:
    strict: bool = False
    require_root_claude: bool = True
    allow_nested_claude: bool = False
    ignore_dirs: set[str] = field(default_factory=lambda: set(DEFAULT_IGNORE_DIRS))
    exclude_globs: tuple[str, ...] = ()
    line_limits: dict[str, dict[str, int]] = field(
        default_factory=lambda: {name: limits.copy() for name, limits in DEFAULT_LINE_LIMITS.items()}
    )
    max_code_block_lines: int = DEFAULT_MAX_CODE_BLOCK_LINES


def strip_inline_comment(line: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    output: list[str] = []

    for char in line:
        if escaped:
            output.append(char)
            escaped = False
            continue

        if char == "\\" and (in_single or in_double):
            output.append(char)
            escaped = True
            continue

        if char == "'" and not in_double:
            in_single = not in_single
            output.append(char)
            continue

        if char == '"' and not in_single:
            in_double = not in_double
            output.append(char)
            continue

        if char == "#" and not in_single and not in_double:
            break

        output.append(char)

    return "".join(output).rstrip()


def split_inline_list(raw: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    escaped = False

    for char in raw:
        if escaped:
            current.append(char)
            escaped = False
            continue

        if char == "\\" and (in_single or in_double):
            current.append(char)
            escaped = True
            continue

        if char == "'" and not in_double:
            in_single = not in_single
            current.append(char)
            continue

        if char == '"' and not in_single:
            in_double = not in_double
            current.append(char)
            continue

        if char == "," and not in_single and not in_double:
            items.append("".join(current).strip())
            current = []
            continue

        current.append(char)

    tail = "".join(current).strip()
    if tail:
        items.append(tail)
    return items


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "":
        return ""

    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None

    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(item) for item in split_inline_list(inner)]

    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]

    if re.fullmatch(r"-?\d+", value):
        return int(value)

    return value


def parse_simple_yaml(text: str) -> dict[str, Any]:
    processed: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        if "\t" in raw_line:
            raise ValueError("Tabs are not supported in .context-audit.yml; use spaces.")

        cleaned = strip_inline_comment(raw_line)
        if not cleaned.strip():
            continue

        indent = len(cleaned) - len(cleaned.lstrip(" "))
        processed.append((indent, cleaned.strip()))

    if not processed:
        return {}

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if index >= len(processed):
            return {}, index

        current_indent, current_text = processed[index]
        if current_indent < indent:
            return {}, index

        if current_text.startswith("- "):
            items: list[Any] = []
            while index < len(processed):
                item_indent, item_text = processed[index]
                if item_indent < indent:
                    break
                if item_indent != indent or not item_text.startswith("- "):
                    raise ValueError(f"Invalid list indentation near '{item_text}'.")

                payload = item_text[2:].strip()
                index += 1

                if payload == "":
                    nested, index = parse_block(index, indent + 2)
                    items.append(nested)
                    continue

                if payload.endswith(":") and ":" not in payload[:-1]:
                    key = payload[:-1].strip()
                    nested, index = parse_block(index, indent + 2)
                    items.append({key: nested})
                    continue

                items.append(parse_scalar(payload))

            return items, index

        mapping: dict[str, Any] = {}
        while index < len(processed):
            item_indent, item_text = processed[index]
            if item_indent < indent:
                break
            if item_indent != indent:
                raise ValueError(f"Invalid mapping indentation near '{item_text}'.")
            if item_text.startswith("- "):
                break

            key, sep, raw_value = item_text.partition(":")
            if not sep:
                raise ValueError(f"Expected 'key: value' syntax near '{item_text}'.")

            key = key.strip()
            raw_value = raw_value.strip()
            index += 1

            if raw_value == "":
                if index < len(processed) and processed[index][0] > item_indent:
                    nested, index = parse_block(index, processed[index][0])
                    mapping[key] = nested
                else:
                    mapping[key] = {}
            else:
                mapping[key] = parse_scalar(raw_value)

        return mapping, index

    parsed, index = parse_block(0, processed[0][0])
    if index != len(processed):
        raise ValueError("Could not parse the entire config file.")
    if not isinstance(parsed, dict):
        raise ValueError("Top-level config must be a mapping.")
    return parsed


def parse_config_file(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(raw)
    else:
        data = parse_simple_yaml(raw)
    if not isinstance(data, dict):
        raise ValueError("Config root must be an object/mapping.")
    return data


def ensure_bool(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{label} must be a boolean.")


def ensure_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer.")
    return value


def ensure_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of strings.")
    return value


def load_audit_config(root: Path, config_path: str | None) -> tuple[AuditConfig, str]:
    resolved_path: Path | None = None
    if config_path:
        resolved_path = Path(config_path).expanduser().resolve()
        if not resolved_path.exists():
            raise ValueError(f"Config file not found: {resolved_path}")
    else:
        for filename in DEFAULT_CONFIG_FILES:
            candidate = (root / filename).resolve()
            if candidate.exists():
                resolved_path = candidate
                break

    config = AuditConfig()
    if resolved_path is None:
        return config, "defaults"

    data = parse_config_file(resolved_path)

    checks = data.get("checks", {})
    if checks and not isinstance(checks, dict):
        raise ValueError("checks must be a mapping when provided.")

    if "strict" in data:
        config.strict = ensure_bool(data["strict"], "strict")
    if "require_root_claude" in data:
        config.require_root_claude = ensure_bool(data["require_root_claude"], "require_root_claude")
    if "allow_nested_claude" in data:
        config.allow_nested_claude = ensure_bool(data["allow_nested_claude"], "allow_nested_claude")

    if "require_root_claude" in checks:
        config.require_root_claude = ensure_bool(checks["require_root_claude"], "checks.require_root_claude")
    if "allow_nested_claude" in checks:
        config.allow_nested_claude = ensure_bool(checks["allow_nested_claude"], "checks.allow_nested_claude")

    if "ignore_dirs" in data:
        config.ignore_dirs.update(ensure_string_list(data["ignore_dirs"], "ignore_dirs"))
    if "exclude_globs" in data:
        config.exclude_globs = tuple(ensure_string_list(data["exclude_globs"], "exclude_globs"))
    if "max_code_block_lines" in data:
        config.max_code_block_lines = ensure_int(data["max_code_block_lines"], "max_code_block_lines")

    if "line_limits" in data:
        line_limits = data["line_limits"]
        if not isinstance(line_limits, dict):
            raise ValueError("line_limits must be a mapping.")

        for doc_name, limits in line_limits.items():
            if not isinstance(doc_name, str):
                raise ValueError("line_limits keys must be strings.")
            if not isinstance(limits, dict):
                raise ValueError(f"line_limits.{doc_name} must be a mapping.")

            merged = config.line_limits.setdefault(doc_name, {})
            for key, raw_limit in limits.items():
                if key not in {"hint", "error"}:
                    raise ValueError(f"line_limits.{doc_name}.{key} is unsupported; use hint or error.")
                merged[key] = ensure_int(raw_limit, f"line_limits.{doc_name}.{key}")

    return config, str(resolved_path)


def should_ignore(path: Path, root: Path, config: AuditConfig) -> bool:
    rel_parts = path.relative_to(root).parts
    if any(part in config.ignore_dirs for part in rel_parts):
        return True

    rel_posix = path.relative_to(root).as_posix()
    return any(fnmatch.fnmatch(rel_posix, pattern) for pattern in config.exclude_globs)


def iter_files(root: Path, config: AuditConfig) -> Iterable[Path]:
    for path in root.rglob("*"):
        if should_ignore(path, root, config):
            continue
        if path.is_file():
            yield path


def discover_context_docs(root: Path, config: AuditConfig) -> list[Path]:
    return sorted(
        [path for path in iter_files(root, config) if path.name in CONTEXT_FILENAMES],
        key=lambda path: path.relative_to(root).as_posix(),
    )


def strip_code_fences(text: str) -> str:
    return CODE_FENCE_RE.sub("", text)


def extract_headings(text: str) -> list[str]:
    return [match.strip() for match in HEADING_RE.findall(text)]


def is_local_link(target: str) -> bool:
    return bool(target) and not target.startswith(("http://", "https://", "mailto:", "#"))


def looks_like_path(token: str) -> bool:
    token = token.strip().strip(".,:;()[]{}")
    if not token or " " in token:
        return False
    if any(char in token for char in ("*", "?", "|")):
        return False
    if token.startswith(("$", "<", "@", "node:")):
        return False

    explicit_relative = token.startswith(("./", "../", "/"))
    suffix = Path(token.rstrip("/")).suffix.lower()
    if explicit_relative:
        return True
    return "/" in token and suffix in COMMON_EXTENSIONS


def resolve_reference(source: Path, target: str) -> Path:
    clean_target = target.split("#", 1)[0].strip()
    path = Path(clean_target)
    if path.is_absolute():
        return path.resolve()
    return (source.parent / path).resolve()


def collect_references(doc: Path) -> tuple[str, list[str], list[str], list[str]]:
    raw = doc.read_text(encoding="utf-8", errors="ignore")
    without_fences = strip_code_fences(raw)

    headings = extract_headings(without_fences)
    markdown_targets = [match.strip() for match in LINK_RE.findall(without_fences) if is_local_link(match.strip())]

    inline_targets: list[str] = []
    for token in CODE_SPAN_RE.findall(without_fences):
        stripped = token.strip()
        if looks_like_path(stripped):
            inline_targets.append(stripped)

    return raw, headings, markdown_targets, inline_targets


def heading_has_signal(headings: list[str], keywords: list[str]) -> bool:
    lowered = [heading.lower() for heading in headings]
    return any(keyword.lower() in heading for heading in lowered for keyword in keywords)


def build_doc_hints(
    *,
    doc_name: str,
    doc_rel: str,
    line_count: int,
    headings: list[str],
    local_ref_count: int,
    config: AuditConfig,
) -> list[Hint]:
    hints: list[Hint] = []

    hint_limit = config.line_limits.get(doc_name, {}).get("hint")
    if hint_limit is not None and line_count > hint_limit:
        hints.append(
            Hint(
                kind="long-document-candidate",
                source=doc_rel,
                message=f"현재 {line_count}라인입니다. {doc_name}는 더 짧게 유지하거나 하위 문서로 분리할지 검토하세요.",
            )
        )

    signals = SECTION_SIGNALS.get(doc_name, [])
    missing_sections = [label for label, keywords in signals if not heading_has_signal(headings, keywords)]
    if missing_sections:
        hints.append(
            Hint(
                kind="missing-recommended-section-signal",
                source=doc_rel,
                message=f"권장 섹션 신호가 약합니다: {', '.join(missing_sections)}",
            )
        )

    if doc_name in {"CLAUDE.md", "CONTEXT.md"} and local_ref_count == 0:
        hints.append(
            Hint(
                kind="no-local-path-reference",
                source=doc_rel,
                message="로컬 파일/하위 문서 참조가 없습니다. 실제 코드/문서 구조와의 연결이 충분한지 확인하세요.",
            )
        )

    return hints


def find_oversized_code_blocks(text: str, limit: int) -> list[tuple[int, int, int]]:
    blocks: list[tuple[int, int, int]] = []
    inside = False
    start_line = 0
    content_lines = 0

    for line_no, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("```"):
            if not inside:
                inside = True
                start_line = line_no
                content_lines = 0
            else:
                if content_lines > limit:
                    blocks.append((start_line, line_no, content_lines))
                inside = False
                start_line = 0
                content_lines = 0
            continue

        if inside:
            content_lines += 1

    return blocks


def build_expected_context_links(root: Path, docs: list[Path]) -> list[tuple[str, str]]:
    context_docs = [doc.resolve() for doc in docs if doc.name == "CONTEXT.md"]
    context_by_dir = {doc.parent.resolve(): doc for doc in context_docs}
    expected: list[tuple[str, str]] = []

    for child in context_docs:
        current = child.parent.resolve().parent
        parent_context: Path | None = None

        while current == root.resolve() or root.resolve() in current.parents:
            if current in context_by_dir:
                parent_context = context_by_dir[current]
                break
            if current == root.resolve():
                break
            current = current.parent

        if parent_context is not None:
            expected.append((str(parent_context), str(child)))

    return expected


def build_report(root: Path, config: AuditConfig, config_source: str) -> dict[str, Any]:
    context_docs = discover_context_docs(root, config)
    issues: list[Issue] = []
    hints: list[Hint] = []
    graph: dict[str, set[str]] = defaultdict(set)
    inbound: dict[str, int] = defaultdict(int)
    doc_paths = {doc.resolve(): doc.relative_to(root).as_posix() for doc in context_docs}
    doc_meta: dict[str, dict[str, Any]] = {}

    root_claude = (root / "CLAUDE.md").resolve()
    if config.require_root_claude and not root_claude.exists():
        issues.append(
            Issue(
                severity="warning",
                kind="missing-root-claude",
                source="/",
                target="CLAUDE.md",
                message="루트 CLAUDE.md가 없습니다. 전역 앵커 문서를 두는 것을 권장합니다.",
            )
        )

    nested_claudes = [
        doc.relative_to(root).as_posix()
        for doc in context_docs
        if doc.name == "CLAUDE.md" and doc.resolve() != root_claude
    ]
    if not config.allow_nested_claude:
        for nested in nested_claudes:
            issues.append(
                Issue(
                    severity="warning",
                    kind="nested-claude",
                    source=nested,
                    target="CLAUDE.md",
                    message="중첩 CLAUDE.md가 있습니다. 실제 우선순위와 compaction 전략을 문서화했는지 확인하세요.",
                )
            )

    for doc in context_docs:
        doc_rel = doc.relative_to(root).as_posix()
        raw, headings, markdown_refs, inline_refs = collect_references(doc)
        local_ref_count = len(markdown_refs) + len(inline_refs)
        line_count = len(raw.splitlines())
        doc_meta[doc_rel] = {
            "headings": headings,
            "local_ref_count": local_ref_count,
            "line_count": line_count,
        }

        error_limit = config.line_limits.get(doc.name, {}).get("error")
        if error_limit is not None and line_count > error_limit:
            kind = "root-claude-too-long" if doc.resolve() == root_claude else "line-limit-exceeded"
            message = (
                f"루트 CLAUDE.md가 {line_count}라인입니다. {error_limit}라인 이내 유지 권장 기준을 초과했습니다."
                if doc.resolve() == root_claude
                else f"{doc.name}가 {line_count}라인입니다. 설정된 오류 기준 {error_limit}라인을 초과했습니다."
            )
            issues.append(
                Issue(
                    severity="error",
                    kind=kind,
                    source=doc_rel,
                    target=str(line_count),
                    message=message,
                )
            )

        if TODO_RE.search(raw):
            issues.append(
                Issue(
                    severity="warning",
                    kind="todo-marker",
                    source=doc_rel,
                    target=doc.name,
                    message="TODO 또는 플레이스홀더가 남아 있습니다.",
                )
            )

        for start, end, block_lines in find_oversized_code_blocks(raw, config.max_code_block_lines):
            issues.append(
                Issue(
                    severity="warning",
                    kind="oversized-code-block",
                    source=doc_rel,
                    target=f"lines {start}-{end}",
                    message=f"코드 블록/로그 블록이 {block_lines}라인입니다. 큰 예시나 로그는 분리 문서로 옮기세요.",
                )
            )

        all_refs = [("markdown", ref) for ref in markdown_refs] + [("inline", ref) for ref in inline_refs]
        for ref_kind, ref in all_refs:
            resolved = resolve_reference(doc, ref)
            if not resolved.exists():
                issues.append(
                    Issue(
                        severity="error",
                        kind="broken-reference",
                        source=doc_rel,
                        target=ref,
                        message=f"{ref_kind} 참조가 실제 경로로 해석되지 않습니다.",
                    )
                )
                continue

            if resolved in doc_paths:
                target_rel = doc_paths[resolved]
                if target_rel != doc_rel and target_rel not in graph[doc_rel]:
                    graph[doc_rel].add(target_rel)
                    inbound[target_rel] += 1

    for doc in context_docs:
        rel = doc.relative_to(root).as_posix()
        if doc.name == "CONTEXT.md" and inbound[rel] == 0:
            issues.append(
                Issue(
                    severity="warning",
                    kind="orphan-context-candidate",
                    source=rel,
                    target="",
                    message="다른 컨텍스트 문서에서 링크되지 않았습니다. 의도된 독립 문서인지 확인하세요.",
                )
            )

    edge_set = {(source, target) for source, targets in graph.items() for target in targets}
    for parent_abs, child_abs in build_expected_context_links(root, context_docs):
        parent_rel = doc_paths[Path(parent_abs)]
        child_rel = doc_paths[Path(child_abs)]
        if (parent_rel, child_rel) not in edge_set:
            issues.append(
                Issue(
                    severity="warning",
                    kind="missing-parent-child-link",
                    source=parent_rel,
                    target=child_rel,
                    message="가장 가까운 부모 CONTEXT.md에서 이 하위 CONTEXT.md를 직접 링크하는 것이 좋습니다.",
                )
            )

    doc_summaries: list[DocSummary] = []
    for doc in context_docs:
        rel = doc.relative_to(root).as_posix()
        headings = list(doc_meta[rel]["headings"])
        local_ref_count = int(doc_meta[rel]["local_ref_count"])
        line_count = int(doc_meta[rel]["line_count"])

        hints.extend(
            build_doc_hints(
                doc_name=doc.name,
                doc_rel=rel,
                line_count=line_count,
                headings=headings,
                local_ref_count=local_ref_count,
                config=config,
            )
        )

        doc_summaries.append(
            DocSummary(
                path=rel,
                line_count=line_count,
                inbound_links=inbound[rel],
                outbound_links=len(graph[rel]),
                local_ref_count=local_ref_count,
                heading_count=len(headings),
            )
        )

    return {
        "root": str(root),
        "config": {
            "source": config_source,
            "strict": config.strict,
            "require_root_claude": config.require_root_claude,
            "allow_nested_claude": config.allow_nested_claude,
            "ignore_dirs": sorted(config.ignore_dirs),
            "exclude_globs": list(config.exclude_globs),
            "line_limits": config.line_limits,
            "max_code_block_lines": config.max_code_block_lines,
        },
        "documents": [asdict(summary) for summary in doc_summaries],
        "issues": [asdict(issue) for issue in issues],
        "hints": [asdict(hint) for hint in hints],
        "stats": {
            "documents": len(context_docs),
            "errors": sum(1 for issue in issues if issue.severity == "error"),
            "warnings": sum(1 for issue in issues if issue.severity == "warning"),
            "hints": len(hints),
        },
    }


def print_human_report(report: dict[str, Any]) -> None:
    print(f"Context root: {report['root']}")
    print(f"Config: {report['config']['source']} | strict={report['config']['strict']}")
    print(f"Documents: {report['stats']['documents']}")
    print(
        f"Errors: {report['stats']['errors']} | "
        f"Warnings: {report['stats']['warnings']} | "
        f"Hints: {report['stats']['hints']}"
    )
    print()

    if report["documents"]:
        print("[Documents]")
        for doc in report["documents"]:
            print(
                f"- {doc['path']} | {doc['line_count']} lines | "
                f"headings={doc['heading_count']} local_refs={doc['local_ref_count']} | "
                f"inbound={doc['inbound_links']} outbound={doc['outbound_links']}"
            )
        print()

    print("[Issues]")
    if report["issues"]:
        for issue in report["issues"]:
            target = f" -> {issue['target']}" if issue["target"] else ""
            print(f"- {issue['severity'].upper()} [{issue['kind']}] {issue['source']}{target}: {issue['message']}")
    else:
        print("- 없음")

    print()
    print("[Content Accuracy Hints]")
    if report["hints"]:
        for hint in report["hints"]:
            print(f"- HINT [{hint['kind']}] {hint['source']}: {hint['message']}")
    else:
        print("- 없음")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify hierarchical AI context documents in a repository.")
    parser.add_argument("--root", required=True, help="Repository root to audit")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a human-readable report")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings as well as errors")
    parser.add_argument("--config", help="Optional path to .context-audit.yml/.yaml/.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(f"[ERROR] invalid root: {root}", file=sys.stderr)
        return 2

    try:
        config, config_source = load_audit_config(root, args.config)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERROR] failed to load config: {exc}", file=sys.stderr)
        return 2

    config.strict = config.strict or args.strict

    report = build_report(root, config, config_source)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human_report(report)

    has_errors = report["stats"]["errors"] > 0
    has_warnings = report["stats"]["warnings"] > 0
    return 1 if has_errors or (config.strict and has_warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
