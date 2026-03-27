#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

KEBAB = re.compile(r'^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$')
MAX_SKILL_LINES = 500


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


def main():
    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
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

        openai_yaml = skill_dir / 'agents' / 'openai.yaml'
        if openai_yaml.exists():
            yaml_text = load_text(openai_yaml)
            if 'display_name:' not in yaml_text or 'short_description:' not in yaml_text:
                findings.append(('warning', str(openai_yaml.relative_to(target)), 'openai.yaml exists but interface metadata looks incomplete'))
            else:
                strengths.append(f'{rel} has agents/openai.yaml')
        else:
            findings.append(('info', str(rel), 'agents/openai.yaml is optional but absent'))

        references_dir = skill_dir / 'references'
        if references_dir.exists():
            strengths.append(f'{rel} has references/')

        scripts_dir = skill_dir / 'scripts'
        if scripts_dir.exists():
            for script in sorted(scripts_dir.glob('*')):
                if script.is_file() and script.suffix in {'.py', '.sh'}:
                    strengths.append(f'{script.relative_to(target)} present')

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

    print('## Strengths')
    if not strengths:
        print('- None')
    else:
        for item in sorted(dict.fromkeys(strengths)):
            print(f'- {item}')
    print()

    print('## Machine summary')
    summary = {
        'target': str(target),
        'skills_found': len(skills),
        'findings': [{'severity': s, 'where': w, 'message': m} for s, w, m in findings],
        'strengths': sorted(dict.fromkeys(strengths)),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
