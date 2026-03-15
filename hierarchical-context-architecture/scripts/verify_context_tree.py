#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

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
IGNORE_DIRS = {
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
LINE_HINT_LIMITS = {
    "CLAUDE.md": 150,
    "CONTEXT.md": 120,
    "AGENTS.md": 120,
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
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
CODE_FENCE_RE = re.compile(r"```.*?```", re.S)
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", re.M)


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


def iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if path.is_file():
            yield path


def discover_context_docs(root: Path) -> list[Path]:
    return sorted(
        [path for path in iter_files(root) if path.name in CONTEXT_FILENAMES],
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


def collect_references(doc: Path) -> tuple[list[str], list[str], list[str]]:
    raw = doc.read_text(encoding="utf-8")
    without_fences = strip_code_fences(raw)

    headings = extract_headings(without_fences)
    markdown_targets = [match.strip() for match in LINK_RE.findall(without_fences) if is_local_link(match.strip())]

    inline_targets: list[str] = []
    for token in CODE_SPAN_RE.findall(without_fences):
        stripped = token.strip()
        if looks_like_path(stripped):
            inline_targets.append(stripped)

    return headings, markdown_targets, inline_targets


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
) -> list[Hint]:
    hints: list[Hint] = []

    hint_limit = LINE_HINT_LIMITS.get(doc_name)
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


def build_report(root: Path) -> dict:
    context_docs = discover_context_docs(root)
    issues: list[Issue] = []
    hints: list[Hint] = []
    graph: dict[str, set[str]] = defaultdict(set)
    inbound: dict[str, int] = defaultdict(int)
    doc_paths = {doc.resolve(): doc.relative_to(root).as_posix() for doc in context_docs}
    doc_meta: dict[str, dict[str, int | list[str]]] = {}

    root_claude = root / "CLAUDE.md"
    if not root_claude.exists():
        issues.append(
            Issue(
                severity="warning",
                kind="missing-root-claude",
                source="/",
                target="CLAUDE.md",
                message="루트 CLAUDE.md가 없습니다. 전역 앵커 문서를 두는 것을 권장합니다.",
            )
        )
    else:
        line_count = len(root_claude.read_text(encoding="utf-8").splitlines())
        if line_count > 200:
            issues.append(
                Issue(
                    severity="error",
                    kind="root-claude-too-long",
                    source="CLAUDE.md",
                    target=str(line_count),
                    message=f"루트 CLAUDE.md가 {line_count}라인입니다. 200라인 이내 유지 권장 기준을 초과했습니다.",
                )
            )

    nested_claudes = [
        doc.relative_to(root).as_posix()
        for doc in context_docs
        if doc.name == "CLAUDE.md" and doc != root_claude
    ]
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
        headings, markdown_refs, inline_refs = collect_references(doc)
        local_ref_count = len(markdown_refs) + len(inline_refs)
        doc_meta[doc_rel] = {
            "headings": headings,
            "local_ref_count": local_ref_count,
        }

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
        if rel == "CLAUDE.md":
            continue
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

    doc_summaries: list[DocSummary] = []
    for doc in context_docs:
        rel = doc.relative_to(root).as_posix()
        line_count = len(doc.read_text(encoding="utf-8").splitlines())
        headings = doc_meta[rel]["headings"]
        local_ref_count = int(doc_meta[rel]["local_ref_count"])

        hints.extend(
            build_doc_hints(
                doc_name=doc.name,
                doc_rel=rel,
                line_count=line_count,
                headings=list(headings),
                local_ref_count=local_ref_count,
            )
        )

        doc_summaries.append(
            DocSummary(
                path=rel,
                line_count=line_count,
                inbound_links=inbound[rel],
                outbound_links=len(graph[rel]),
                local_ref_count=local_ref_count,
                heading_count=len(list(headings)),
            )
        )

    return {
        "root": str(root),
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


def print_human_report(report: dict) -> None:
    print(f"Context root: {report['root']}")
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(f"[ERROR] invalid root: {root}", file=sys.stderr)
        return 2

    report = build_report(root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human_report(report)

    return 1 if report["stats"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
