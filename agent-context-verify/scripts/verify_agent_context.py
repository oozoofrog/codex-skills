#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DOC_NAMES = {'AGENTS.md', 'AGENTS.override.md', 'CONTEXT.md'}
MARKDOWN_LINK = re.compile(r'\[[^\]]+\]\(([^)]+)\)')
CODE_REF = re.compile(r'`([^`\n]+)`')
FILEISH = re.compile(r'(/|\\.md$|\\.json$|\\.toml$|\\.py$|\\.sh$|^AGENTS\\.md$|^AGENTS\\.override\\.md$|^CONTEXT\\.md$|^docs/)')


def load_text(path: Path) -> str:
    return path.read_text(encoding='utf-8', errors='ignore')


def add(findings, severity: str, where: str, message: str) -> None:
    findings.append((severity, where, message))


def normalize_target(raw: str) -> Path:
    path = Path(raw).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise SystemExit(f'오류: 대상 디렉터리가 없습니다: {path}')
    return path


def discover_docs(target: Path) -> list[Path]:
    docs: list[Path] = []
    for name in DOC_NAMES:
        docs.extend(target.rglob(name))
    return sorted(set(docs))


def resolve_local_ref(base: Path, ref: str) -> Path | None:
    ref = ref.strip()
    if not ref or ref.startswith(('http://', 'https://', 'mailto:', '#')):
        return None
    if ref.startswith('file://'):
        ref = ref.removeprefix('file://')
        return Path(ref)
    return (base / ref).resolve()


def verify_links(doc: Path, text: str, target: Path, findings) -> None:
    rel = str(doc.relative_to(target))
    base = doc.parent
    for ref in MARKDOWN_LINK.findall(text):
        if ref.startswith(('http://', 'https://', 'mailto:', '#')):
            continue
        resolved = resolve_local_ref(base, ref)
        if resolved is None:
            continue
        if not resolved.exists():
            add(findings, 'critical', rel, f'missing markdown link target: {ref}')


def verify_code_refs(doc: Path, text: str, target: Path, findings) -> None:
    rel = str(doc.relative_to(target))
    base = doc.parent
    for ref in CODE_REF.findall(text):
        candidate = ref.strip()
        if any(token in candidate for token in ['<', '>', '...']):
            continue
        if candidate.startswith('~'):
            continue
        if candidate.endswith('/') and not candidate.startswith(('./', '../', 'docs/')):
            continue
        if any(ch.isspace() for ch in candidate):
            continue
        if not FILEISH.search(candidate):
            continue
        resolved = resolve_local_ref(base, candidate)
        if resolved is None:
            continue
        if not resolved.exists():
            add(findings, 'warning', rel, f'missing code/file reference: {candidate}')


def build_summary(target: Path, docs: list[Path], findings, strengths):
    unique_strengths = sorted(dict.fromkeys(strengths))
    return {
        'report_type': 'agent-context-verify',
        'schema_version': 1,
        'target': str(target),
        'documents_found': len(docs),
        'findings_count': len(findings),
        'strengths_count': len(unique_strengths),
        'findings': [{'severity': s, 'where': w, 'message': m} for s, w, m in findings],
        'strengths': unique_strengths,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Verify AGENTS/CONTEXT documents against the repo tree.')
    parser.add_argument('target', nargs='?', default='.', help='검증 대상 루트 (기본값: 현재 디렉터리)')
    parser.add_argument('--json-out', help='machine summary JSON을 저장할 파일 경로')
    args = parser.parse_args()

    target = normalize_target(args.target)
    findings = []
    strengths = []

    docs = discover_docs(target)
    if docs:
        strengths.append(f'found {len(docs)} instruction/context document(s)')
    else:
        add(findings, 'warning', 'root', 'no AGENTS.md / AGENTS.override.md / CONTEXT.md files found')

    for doc in docs:
        rel = str(doc.relative_to(target))
        strengths.append(f'checked {rel}')
        text = load_text(doc)
        verify_links(doc, text, target, findings)
        verify_code_refs(doc, text, target, findings)

    order = {'critical': 0, 'warning': 1, 'info': 2}
    findings.sort(key=lambda x: (order.get(x[0], 9), x[1], x[2]))

    print('# Agent Context Verification Report')
    print()
    print(f'- Target: `{target}`')
    print(f'- Documents found: `{len(docs)}`')
    print(f'- Findings: `{len(findings)}`')
    print(f'- Strengths: `{len(dict.fromkeys(strengths))}`')
    print()
    print('## Summary')
    if findings:
        print('- instruction/context 문서에서 깨진 링크 또는 오래된 파일 참조가 발견되었습니다.')
    else:
        print('- 깨진 링크나 파일 참조를 찾지 못했습니다.')
    print()
    print('## Findings')
    if not findings:
        print('- None')
    else:
        for severity, where, message in findings:
            print(f'- [{severity}] `{where}` — {message}')
    print()
    print('## Recommended fixes')
    if not findings:
        print('1. 현재 링크/파일 참조 상태를 유지합니다.')
    else:
        print('1. `critical` 링크부터 실제 경로로 수정합니다.')
        print('2. `warning` 파일 참조는 리팩터링 이후 새 경로/문구로 갱신합니다.')
    print()
    print('## Machine summary')
    summary = build_summary(target, docs, findings, strengths)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.json_out:
        out_path = Path(args.json_out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
