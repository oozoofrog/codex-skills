#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path

KEBAB = re.compile(r'^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$')
MAX_SKILL_LINES = 500
VALID_REVIEW_MODES = {'none', 'optional', 'required'}
EXPLICIT_ONLY_MARKERS = (
    '명시적으로 요청했을 때만',
    '명시 호출만',
    '명시적으로 사용할 때만',
    'explicit-only',
    'explicitly asks',
    'explicitly asked',
    'explicit invocation only',
)
EVALUATOR_NATIVE_MARKERS = (
    'evaluator-native',
    'audit',
    'auditor',
    'verify',
    'verification',
    'review',
    'reviewer',
    'validation',
    'validator',
    'doctor',
    '감사',
    '검증',
    '리뷰',
    '점검',
)
GENERATOR_CLAIM_MARKERS = (
    'create',
    'scaffold',
    'bootstrap',
    'generate',
    'build',
    'implement',
    'release',
    'publish',
    'write',
    'ship',
    'construct',
    'author',
    '생성',
    '구현',
    '릴리스',
    '배포',
    '작성',
    '구축',
    '초기화',
)
REQUIRED_MODE_MARKERS = GENERATOR_CLAIM_MARKERS + (
    'workflow',
    'orchestr',
    'loop',
    'plan',
    'design',
    'long-running',
    'automation',
    '연구',
    '반복',
    '오케스트레이션',
    '워크플로',
    '자동화',
    '설계',
)
ACTION_STATUS_TOKENS = {
    'pass',
    'refine',
    'pivot',
    'rescope',
    'escalate',
    'stop',
    'warning',
    'critical',
    'info',
}
OPERATOR_SECTION_PATTERNS = {
    'When to use/When it fits': re.compile(r'(?m)^##\s+(When to use|When it fits)\b'),
    'Do not use when': re.compile(r'(?m)^##\s+Do not use when\b'),
    'Quick start': re.compile(r'(?m)^##\s+Quick start\b'),
    'Output expectation': re.compile(r'(?m)^##\s+Output expectation\b'),
}


def parse_frontmatter(text: str):
    if not text.startswith('---\n'):
        return None, text
    end = text.find('\n---\n', 4)
    if end == -1:
        return None, text
    raw = text[4:end]
    body = text[end + 5 :]
    meta = {}
    for line in raw.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if ':' not in line:
            continue
        k, v = line.split(':', 1)
        meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, body


def load_text(path: Path):
    return path.read_text(encoding='utf-8', errors='ignore')


def find_skills(root: Path):
    return sorted(root.glob('.agents/skills/**/SKILL.md'))


def extract_markdown_section(body: str, title: str):
    pattern = rf'(?ms)^## {re.escape(title)}\s*\n(.*?)(?=^## \S|\Z)'
    match = re.search(pattern, body)
    return match.group(1).strip() if match else None


def parse_review_harness(section: str):
    items = {}
    for line in section.splitlines():
        match = re.match(r'-\s*([^:]+):\s*(.+?)\s*$', line.strip())
        if match:
            items[match.group(1).strip()] = match.group(2).strip()
    return items


def parse_allow_implicit_invocation(yaml_text: str):
    match = re.search(r'(?m)^\s*allow_implicit_invocation:\s*(true|false)\s*$', yaml_text)
    if not match:
        return None
    return match.group(1) == 'true'


def parse_openai_interface_field(yaml_text: str, field: str):
    match = re.search(rf'(?m)^\s*{re.escape(field)}:\s*(.+?)\s*$', yaml_text)
    if not match:
        return ''
    return match.group(1).strip().strip('"').strip("'")


def collect_status_tokens(text: str):
    return set(re.findall(r'`([^`]+)`', text))


def split_review_axes(text: str):
    normalized = (
        text.replace(' 또는 ', ',')
        .replace(' and ', ',')
        .replace(' / ', ',')
        .replace('·', ',')
        .replace('|', ',')
    )
    parts = [part.strip() for part in re.split(r'[,/]', normalized) if part.strip()]
    return parts


def has_any_marker(text: str, markers):
    lowered = text.lower()
    return any(marker in text or marker in lowered for marker in markers)


def grouped_findings(findings):
    groups = {
        'frontmatter': [],
        'operator_sections': [],
        'review_harness': [],
        'openai_yaml': [],
        'hygiene': [],
        'other': [],
    }
    for severity, where, message in findings:
        lowered = message.lower()
        bucket = 'other'
        if 'frontmatter' in lowered or 'description' in lowered or 'kebab-case' in lowered:
            bucket = 'frontmatter'
        elif 'operator section' in lowered or 'quick start' in lowered or 'output expectation' in lowered:
            bucket = 'operator_sections'
        elif 'review harness' in lowered or '평가축' in lowered or '자동 다음 행동' in lowered or 'mode `' in lowered:
            bucket = 'review_harness'
        elif 'openai.yaml' in lowered or 'allow_implicit_invocation' in lowered:
            bucket = 'openai_yaml'
        elif 'readme.md' in lowered or 'references/' in lowered or 'long (' in lowered:
            bucket = 'hygiene'
        groups[bucket].append({'severity': severity, 'where': where, 'message': message})
    return groups


def recommended_fixes(findings):
    fixes: list[str] = []
    grouped = grouped_findings(findings)
    if grouped['frontmatter']:
        fixes.append('frontmatter name/description과 kebab-case 규칙부터 정리합니다.')
    if grouped['operator_sections']:
        fixes.append('When to use / Do not use when / Quick start / Output expectation 섹션을 보강합니다.')
    if grouped['review_harness']:
        fixes.append('Review Harness mode, 평가축, 자동 다음 행동을 실제 스킬 위험도와 맞게 수정합니다.')
    if grouped['openai_yaml']:
        fixes.append('openai.yaml 메타데이터와 explicit-only / implicit invocation 정책을 정렬합니다.')
    if grouped['hygiene']:
        fixes.append('불필요한 README, 과도한 본문 길이, references 분리 상태를 정리합니다.')
    if not fixes and findings:
        fixes.append('warning / critical finding을 우선순위 순으로 수정합니다.')
    return fixes


def build_summary(target: Path, skills: list[Path], findings, strengths):
    unique_strengths = sorted(dict.fromkeys(strengths))
    return {
        'report_type': 'codex-skill-audit',
        'schema_version': 1,
        'target': str(target),
        'skills_found': len(skills),
        'findings_count': len(findings),
        'strengths_count': len(unique_strengths),
        'findings': [{'severity': s, 'where': w, 'message': m} for s, w, m in findings],
        'grouped_findings': grouped_findings(findings),
        'recommended_fixes': recommended_fixes(findings),
        'strengths': unique_strengths,
    }


def main():
    parser = argparse.ArgumentParser(description='Audit a Codex skill repository.')
    parser.add_argument('target', nargs='?', default='.', help='감사 대상 루트 (기본값: 현재 디렉터리)')
    parser.add_argument('--json-out', help='machine summary JSON을 저장할 파일 경로')
    args = parser.parse_args()

    target = Path(args.target).resolve()
    findings = []
    strengths = []

    if (target / 'AGENTS.md').exists():
        strengths.append('repo root AGENTS.md exists')
    else:
        findings.append(('warning', 'root', 'AGENTS.md is missing at repository root'))

    skills = find_skills(target)
    if not skills:
        findings.append(('critical', 'root', 'no SKILL.md files found under .agents/skills'))
    else:
        strengths.append(f'found {len(skills)} skill(s) under .agents/skills')

    names = {}
    for skill_file in skills:
        skill_dir = skill_file.parent
        rel = skill_file.relative_to(target)
        text = load_text(skill_file)
        meta, body = parse_frontmatter(text)

        if meta is None:
            findings.append(('critical', str(rel), 'missing or malformed YAML frontmatter'))
            continue

        name = meta.get('name', '')
        desc = meta.get('description', '')
        if not name:
            findings.append(('critical', str(rel), 'frontmatter.name is missing'))
        elif not KEBAB.match(name):
            findings.append(('warning', str(rel), f'frontmatter.name is not kebab-case: {name}'))
        else:
            names.setdefault(name, []).append(str(rel))

        if not desc:
            findings.append(('critical', str(rel), 'frontmatter.description is missing'))
        elif len(desc) < 24:
            findings.append(('warning', str(rel), 'description is very short; trigger scope may be unclear'))

        total_lines = text.count('\n') + 1
        if total_lines > MAX_SKILL_LINES:
            findings.append(('warning', str(rel), f'SKILL.md is long ({total_lines} lines); move details to references/'))

        if (skill_dir / 'README.md').exists():
            findings.append(('warning', str(rel), 'skill directory contains README.md; keep auxiliary docs out of skill dir'))

        for section_name, pattern in OPERATOR_SECTION_PATTERNS.items():
            if not pattern.search(body):
                findings.append(('warning', str(rel), f'missing operator section `{section_name}`'))

        review_section = extract_markdown_section(body, 'Review Harness')
        if review_section is None:
            findings.append(('warning', str(rel), 'missing Review Harness section'))
            review_items = {}
        else:
            review_items = parse_review_harness(review_section)
            mode = review_items.get('mode')
            if not mode:
                findings.append(('warning', str(rel), 'Review Harness section is missing mode'))
            elif mode not in VALID_REVIEW_MODES:
                findings.append(('warning', str(rel), f'invalid Review Harness mode: {mode}'))
            else:
                strengths.append(f'{rel} declares Review Harness mode `{mode}`')

            standard_ref = review_items.get('공통 기준', '')
            if 'docs/review-harness.md' not in standard_ref:
                findings.append(('warning', str(rel), 'Review Harness section should reference docs/review-harness.md'))

            if not (review_items.get('planner') or review_items.get('generator')):
                findings.append(('warning', str(rel), 'Review Harness section should declare planner or generator'))

            for field in ('evaluator', 'artifacts/evidence', 'pass condition'):
                if field not in review_items:
                    findings.append(('warning', str(rel), f'Review Harness section is missing `{field}`'))

        openai_yaml = skill_dir / 'agents' / 'openai.yaml'
        interface_short_description = ''
        interface_default_prompt = ''
        allow_implicit = None
        if openai_yaml.exists():
            yaml_text = load_text(openai_yaml)
            if 'display_name:' not in yaml_text or 'short_description:' not in yaml_text:
                findings.append(('warning', str(openai_yaml.relative_to(target)), 'openai.yaml exists but interface metadata looks incomplete'))
            else:
                strengths.append(f'{rel} has agents/openai.yaml')

            interface_short_description = parse_openai_interface_field(yaml_text, 'short_description')
            interface_default_prompt = parse_openai_interface_field(yaml_text, 'default_prompt')
            allow_implicit = parse_allow_implicit_invocation(yaml_text)
            if allow_implicit is None:
                findings.append(('warning', str(openai_yaml.relative_to(target)), 'allow_implicit_invocation is missing or malformed'))

            lowered_body = body.lower()
            explicit_only = any(marker in body for marker in EXPLICIT_ONLY_MARKERS) or any(marker in lowered_body for marker in EXPLICIT_ONLY_MARKERS)
            if explicit_only and allow_implicit is True:
                findings.append(('warning', str(openai_yaml.relative_to(target)), 'skill body says explicit-only but allow_implicit_invocation is true'))
            if allow_implicit is False and not explicit_only:
                findings.append(('warning', str(openai_yaml.relative_to(target)), 'allow_implicit_invocation is false but SKILL.md does not clearly declare explicit-only usage'))
        else:
            findings.append(('info', str(rel), 'agents/openai.yaml is optional but absent'))

        skill_summary_text = ' '.join(
            part for part in (
                desc,
                interface_short_description,
                interface_default_prompt,
                extract_markdown_section(body, 'When to use') or extract_markdown_section(body, 'When it fits') or '',
            ) if part
        )

        references_dir = skill_dir / 'references'
        if references_dir.exists():
            strengths.append(f'{rel} has references/')

        scripts_dir = skill_dir / 'scripts'
        if scripts_dir.exists():
            for script in sorted(scripts_dir.glob('*')):
                if script.is_file() and script.suffix in {'.py', '.sh'}:
                    strengths.append(f'{script.relative_to(target)} present')

        if review_section is not None:
            axes_value = review_items.get('평가축')
            if not axes_value:
                findings.append(('warning', str(rel), 'Review Harness section is missing `평가축`'))
            else:
                axes = split_review_axes(axes_value)
                if len(axes) < 2:
                    findings.append(('warning', str(rel), 'Review Harness `평가축` should list at least two evaluation axes'))

            auto_actions = review_items.get('자동 다음 행동')
            if not auto_actions:
                findings.append(('warning', str(rel), 'Review Harness section is missing `자동 다음 행동`'))
            else:
                tokens = collect_status_tokens(auto_actions)
                status_tokens = {token for token in tokens if token in ACTION_STATUS_TOKENS}
                if not status_tokens:
                    findings.append(('warning', str(rel), 'Review Harness `자동 다음 행동` should reference at least one backticked status token'))
                elif review_items.get('mode') in {'optional', 'required'} and 'pass' not in status_tokens:
                    findings.append(('warning', str(rel), 'Review Harness `자동 다음 행동` should include `pass` for optional/required skills'))

            mode = review_items.get('mode')
            if mode == 'none':
                evaluator_native = has_any_marker(skill_summary_text, EVALUATOR_NATIVE_MARKERS) or has_any_marker(review_items.get('evaluator', ''), EVALUATOR_NATIVE_MARKERS)
                if not evaluator_native:
                    findings.append(('warning', str(rel), 'Review Harness mode `none` looks mismatched with the skill summary; evaluator-native/review language is not clear'))
                if has_any_marker(skill_summary_text, GENERATOR_CLAIM_MARKERS) and not has_any_marker(skill_summary_text, EVALUATOR_NATIVE_MARKERS):
                    findings.append(('warning', str(rel), 'evaluator-native skill summary overclaims generator/build behavior for mode `none`'))
            elif mode == 'required':
                if not has_any_marker(skill_summary_text, REQUIRED_MODE_MARKERS):
                    findings.append(('warning', str(rel), 'Review Harness mode `required` looks mismatched with the surrounding skill description'))

    for name, paths in names.items():
        if len(paths) > 1:
            findings.append(('critical', name, 'duplicate skill name used in multiple SKILL.md files: ' + ', '.join(paths)))

    order = {'critical': 0, 'warning': 1, 'info': 2}
    findings.sort(key=lambda x: (order.get(x[0], 9), x[1], x[2]))

    print('# Codex Skill Audit Report')
    print()
    print(f'- Target: `{target}`')
    print(f'- Skills found: `{len(skills)}`')
    print(f'- Findings: `{len(findings)}`')
    print(f'- Strengths: `{len(strengths)}`')
    print()

    print('## Findings')
    if not findings:
        print('- None')
    else:
        for severity, where, message in findings:
            print(f'- [{severity}] `{where}` — {message}')
    print()
    print('## Grouped summary')
    grouped = grouped_findings(findings)
    if not any(grouped.values()):
        print('- None')
    else:
        for key, items in grouped.items():
            if items:
                print(f'- `{key}`: {len(items)}')
    print()
    print('## Recommended fixes')
    fixes = recommended_fixes(findings)
    if not fixes:
        print('1. 현재 구조를 유지합니다.')
    else:
        for idx, item in enumerate(fixes, start=1):
            print(f'{idx}. {item}')
    print()

    print('## Strengths')
    unique_strengths = sorted(dict.fromkeys(strengths))
    if not unique_strengths:
        print('- None')
    else:
        for item in unique_strengths:
            print(f'- {item}')
    print()

    print('## Machine summary')
    summary = build_summary(target, skills, findings, strengths)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.json_out:
        out_path = Path(args.json_out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
