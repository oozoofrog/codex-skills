#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SEVERITIES = ('critical', 'warning', 'info')
LABELS = {'critical': 'CRITICAL', 'warning': 'WARNING', 'info': 'INFO'}


def read_json(path: str) -> dict:
    if path == '-':
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding='utf-8')
    return json.loads(raw)


def build_summary(payload: dict) -> dict:
    scope = str(payload.get('scope', '')).strip()
    findings = payload.get('findings', []) or []
    checked = payload.get('checked', []) or []
    risks = payload.get('risks', []) or []
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
            'impact': str(item.get('impact', '')).strip(),
            'fix': str(item.get('fix', '')).strip(),
        }
        evidence = str(item.get('evidence', '')).strip()
        if evidence:
            normalized['evidence'] = evidence
        for key in ('title', 'where', 'why', 'impact', 'fix'):
            if not normalized[key]:
                raise SystemExit(f'오류: findings[{idx}].{key} 가 비어 있습니다.')
        counts[severity] += 1
        normalized_findings.append(normalized)

    blocking = counts['critical'] > 0
    summary_text = str(payload.get('summary', '')).strip()
    if not summary_text:
        if counts['critical']:
            summary_text = f'blocking issue {counts["critical"]}개를 포함해 총 {len(normalized_findings)}개 finding이 있습니다.'
        elif normalized_findings:
            summary_text = f'총 {len(normalized_findings)}개 finding이 있으며 대부분 수정 권고 수준입니다.'
        else:
            summary_text = '핵심 findings가 없습니다.'

    return {
        'report_type': 'apple-review',
        'schema_version': 1,
        'scope': scope,
        'summary': summary_text,
        'blocking': blocking,
        'findings_count': len(normalized_findings),
        'findings_by_severity': counts,
        'findings': normalized_findings,
        'checked': [str(item).strip() for item in checked if str(item).strip()],
        'risks': [str(item).strip() for item in risks if str(item).strip()],
    }


def render_markdown(summary: dict, title: str) -> str:
    lines = [f'# {title}', '', '## Summary', f'- 검토 범위: `{summary["scope"]}`']
    lines.append(f'- 판정: {summary["summary"]}')
    lines.append(f'- blocking: `{str(summary["blocking"]).lower()}`')
    lines.append(f'- findings: `{summary["findings_count"]}` (critical={summary["findings_by_severity"]["critical"]}, warning={summary["findings_by_severity"]["warning"]}, info={summary["findings_by_severity"]["info"]})')
    lines.extend(['', '## Findings'])

    if not summary['findings']:
        lines.append('- 핵심 findings: 없음')
    else:
        for finding in summary['findings']:
            lines.append(f'- [{LABELS[finding["severity"]]}] {finding["title"]}')
            lines.append(f'  - 위치: `{finding["where"]}`')
            lines.append(f'  - 이유: {finding["why"]}')
            lines.append(f'  - 영향: {finding["impact"]}')
            lines.append(f'  - 수정 방향: {finding["fix"]}')
            if finding.get('evidence'):
                lines.append(f'  - 근거: {finding["evidence"]}')

    lines.extend(['', '## Verification / Remaining risks'])
    if summary['checked']:
        lines.append('- 확인한 점:')
        for item in summary['checked']:
            lines.append(f'  - {item}')
    else:
        lines.append('- 확인한 점: 없음')

    if summary['risks']:
        lines.append('- 남은 리스크:')
        for item in summary['risks']:
            lines.append(f'  - {item}')
    else:
        lines.append('- 남은 리스크: 없음')

    lines.extend(['', '## Machine summary', '```json', json.dumps(summary, ensure_ascii=False, indent=2), '```', ''])
    return '\n'.join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description='Format Apple review findings into a fixed report shape.')
    parser.add_argument('--input', required=True, help='입력 JSON 경로 또는 - (stdin)')
    parser.add_argument('--title', default='Apple Review Report', help='Markdown 보고서 제목')
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
