#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SEVERITIES = ('critical', 'warning', 'info', 'strength')
LABELS = {'critical': 'CRITICAL', 'warning': 'WARNING', 'info': 'INFO', 'strength': 'STRENGTH'}


def read_json(path: str) -> dict:
    if path == '-':
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding='utf-8')
    return json.loads(raw)


def build_summary(payload: dict) -> dict:
    scope = str(payload.get('scope', '')).strip()
    findings = payload.get('findings', []) or []
    strengths = payload.get('strengths', []) or []
    priority_fixes = payload.get('priority_fixes', []) or []
    counts = {severity: 0 for severity in SEVERITIES}
    normalized_findings = []

    for idx, item in enumerate(findings, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f'오류: findings[{idx}] 는 object여야 합니다.')
        severity = str(item.get('severity', '')).strip()
        if severity not in SEVERITIES:
            raise SystemExit(f'오류: findings[{idx}].severity 는 {SEVERITIES} 중 하나여야 합니다.')
        normalized = {
            'severity': severity,
            'title': str(item.get('title', '')).strip(),
            'where': str(item.get('where', '')).strip(),
            'why': str(item.get('why', '')).strip(),
            'fix': str(item.get('fix', '')).strip(),
        }
        evidence = str(item.get('evidence', '')).strip()
        if evidence:
            normalized['evidence'] = evidence
        for key in ('title', 'where', 'why', 'fix'):
            if not normalized[key]:
                raise SystemExit(f'오류: findings[{idx}].{key} 가 비어 있습니다.')
        counts[severity] += 1
        normalized_findings.append(normalized)

    summary_text = str(payload.get('summary', '')).strip()
    if not summary_text:
        summary_text = f'총 {len(normalized_findings)}개 finding과 {len([s for s in strengths if str(s).strip()])}개 strength가 있습니다.'

    return {
        'report_type': 'agent-context-audit',
        'schema_version': 1,
        'scope': scope,
        'summary': summary_text,
        'findings_count': len(normalized_findings),
        'findings_by_severity': counts,
        'findings': normalized_findings,
        'strengths': [str(item).strip() for item in strengths if str(item).strip()],
        'priority_fixes': [str(item).strip() for item in priority_fixes if str(item).strip()],
    }


def render_markdown(summary: dict, title: str) -> str:
    lines = [f'# {title}', '', '## Summary', f'- 감사 범위: `{summary["scope"]}`', f'- 판정: {summary["summary"]}']
    lines.append(f'- findings: `{summary["findings_count"]}` (critical={summary["findings_by_severity"]["critical"]}, warning={summary["findings_by_severity"]["warning"]}, info={summary["findings_by_severity"]["info"]}, strength={summary["findings_by_severity"]["strength"]})')
    lines.extend(['', '## Findings'])

    if not summary['findings']:
        lines.append('- 핵심 findings: 없음')
    else:
        for finding in summary['findings']:
            lines.append(f'- [{LABELS[finding["severity"]]}] {finding["title"]}')
            lines.append(f'  - 위치: `{finding["where"]}`')
            lines.append(f'  - 이유: {finding["why"]}')
            lines.append(f'  - 수정 방향: {finding["fix"]}')
            if finding.get('evidence'):
                lines.append(f'  - 근거: {finding["evidence"]}')

    lines.extend(['', '## Strengths'])
    if summary['strengths']:
        for item in summary['strengths']:
            lines.append(f'- {item}')
    else:
        lines.append('- None')

    lines.extend(['', '## Priority fixes'])
    if summary['priority_fixes']:
        for idx, item in enumerate(summary['priority_fixes'], start=1):
            lines.append(f'{idx}. {item}')
    else:
        lines.append('1. 현재 구조를 유지합니다.')

    lines.extend(['', '## Machine summary', '```json', json.dumps(summary, ensure_ascii=False, indent=2), '```', ''])
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description='Format agent-context-audit findings into a fixed report shape.')
    parser.add_argument('--input', required=True, help='입력 JSON 경로 또는 - (stdin)')
    parser.add_argument('--title', default='Agent Context Audit Report', help='Markdown 보고서 제목')
    parser.add_argument('--json-out', help='machine summary JSON 저장 경로')
    parser.add_argument('--markdown-out', help='Markdown 보고서 저장 경로')
    args = parser.parse_args()

    payload = read_json(args.input)
    summary = build_summary(payload)
    markdown = render_markdown(summary, args.title)
    print(markdown, end='')

    if args.json_out:
        out = Path(args.json_out).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    if args.markdown_out:
        out = Path(args.markdown_out).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding='utf-8')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
