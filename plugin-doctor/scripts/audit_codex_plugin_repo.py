#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'scripts'))
from packaged_plugin_parity import default_prompt_source_skills, short_description_source_skill

try:
    import tomllib  # Python 3.11+
except Exception:
    tomllib = None

KEBAB = re.compile(r'^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$')
SEMVER = re.compile(r'^\d+\.\d+\.\d+$')
VALID_INSTALL = {'NOT_AVAILABLE', 'AVAILABLE', 'INSTALLED_BY_DEFAULT'}
VALID_AUTH = {'ON_INSTALL', 'ON_USE'}


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


def extract_markdown_section(body: str, title: str):
    pattern = rf'(?ms)^## {re.escape(title)}\s*\n(.*?)(?=^## \S|\Z)'
    match = re.search(pattern, body)
    return match.group(1).strip() if match else None


def normalize_multiline(text: str):
    lines = [' '.join(line.split()) for line in text.strip().splitlines() if line.strip()]
    return '\n'.join(lines)


def code_refs_from_bullets(text: str):
    return re.findall(r'(?m)^-\s*`([^`]+)`', text)


def load_text(path: Path):
    return path.read_text(encoding='utf-8', errors='ignore')


def load_json(path: Path):
    return json.loads(load_text(path))


def parse_openai_interface_field(yaml_text: str, field: str):
    match = re.search(rf'(?m)^\s*{re.escape(field)}:\s*(.+?)\s*$', yaml_text)
    if not match:
        return ''
    return match.group(1).strip().strip('"').strip("'")


def add(findings, severity, where, message):
    findings.append((severity, where, message))


def grouped_findings(findings):
    groups = {
        'manifest_and_marketplace': [],
        'packaged_skill_drift': [],
        'readme_and_assets': [],
        'legacy_and_custom_agents': [],
        'other': [],
    }
    for severity, where, message in findings:
        bucket = 'other'
        if 'marketplace' in where or 'plugin.json' in where or 'mcp' in where:
            bucket = 'manifest_and_marketplace'
        if 'packaged' in message or 'openai.yaml' in where or 'defaultPrompt' in message or 'shortDescription' in message:
            bucket = 'packaged_skill_drift'
        if 'README' in message or 'assets' in message or 'screenshots' in message:
            bucket = 'readme_and_assets'
        if '.claude-plugin' in where or 'CLAUDE.md' in where or 'custom agent' in message:
            bucket = 'legacy_and_custom_agents'
        groups[bucket].append({'severity': severity, 'where': where, 'message': message})
    return groups


def validate_path_ref(plugin_root: Path, rel_path: str, findings, where: str, label: str):
    if not isinstance(rel_path, str):
        add(findings, 'warning', where, f'{label} should be a relative string path')
        return None
    if not rel_path.startswith('./'):
        add(findings, 'warning', where, f'{label} should start with ./ : {rel_path}')
        return None
    resolved = plugin_root / rel_path[2:]
    if not resolved.exists():
        add(findings, 'critical', where, f'{label} target missing: {rel_path}')
        return None
    return resolved


def build_summary(target: Path, skill_files: list[Path], agent_files: list[Path], plugin_manifests: list[Path], findings, strengths):
    unique_strengths = sorted(set(strengths))
    return {
        'report_type': 'plugin-doctor',
        'schema_version': 1,
        'target': str(target),
        'skills_found': len(skill_files),
        'custom_agents_found': len(agent_files),
        'packaged_plugins_found': len(plugin_manifests),
        'findings_count': len(findings),
        'strengths_count': len(unique_strengths),
        'findings': [{'severity': s, 'where': w, 'message': m} for s, w, m in findings],
        'grouped_findings': grouped_findings(findings),
        'strengths': unique_strengths,
    }


def main():
    parser = argparse.ArgumentParser(description='Audit a Codex plugin repository.')
    parser.add_argument('target', nargs='?', default='.', help='감사 대상 루트 (기본값: 현재 디렉터리)')
    parser.add_argument('--json-out', help='machine summary JSON을 저장할 파일 경로')
    args = parser.parse_args()

    target = Path(args.target).resolve()
    findings = []
    strengths = []

    if (target / 'AGENTS.md').exists():
        strengths.append('repo root AGENTS.md exists')
    else:
        add(findings, 'warning', 'root', 'AGENTS.md is missing at repository root')

    skill_files = sorted(target.glob('.agents/skills/**/SKILL.md'))
    if skill_files:
        strengths.append(f'found {len(skill_files)} repo-local skill(s)')
    else:
        add(findings, 'critical', 'root', 'no SKILL.md files found under .agents/skills')

    legacy_plugin_dirs = sorted(target.glob('**/.claude-plugin'))
    if legacy_plugin_dirs:
        for p in legacy_plugin_dirs[:20]:
            add(findings, 'warning', str(p.relative_to(target)), 'legacy Claude plugin directory present; verify it is intentionally retained')
    else:
        strengths.append('no .claude-plugin directories found')

    legacy_claude_files = sorted(target.glob('**/CLAUDE.md'))
    if legacy_claude_files:
        for p in legacy_claude_files[:20]:
            add(findings, 'info', str(p.relative_to(target)), 'CLAUDE.md present; confirm it is legacy reference material and not the active Codex instruction source')
    else:
        strengths.append('no CLAUDE.md files found')

    skill_names = {}
    for skill_file in skill_files:
        rel = skill_file.relative_to(target)
        text = load_text(skill_file)
        meta, _ = parse_frontmatter(text)
        if meta is None:
            add(findings, 'critical', str(rel), 'missing or malformed frontmatter')
            continue
        name = meta.get('name', '')
        desc = meta.get('description', '')
        if not name:
            add(findings, 'critical', str(rel), 'frontmatter.name missing')
        elif not KEBAB.match(name):
            add(findings, 'warning', str(rel), f'name is not kebab-case: {name}')
        else:
            skill_names.setdefault(name, []).append(str(rel))
        if not desc:
            add(findings, 'critical', str(rel), 'frontmatter.description missing')
        elif len(desc) < 24:
            add(findings, 'warning', str(rel), 'description is very short; implicit discovery may be weak')
        openai_yaml = skill_file.parent / 'agents' / 'openai.yaml'
        if openai_yaml.exists():
            strengths.append(f'{rel} has agents/openai.yaml')
        else:
            add(findings, 'info', str(rel), 'agents/openai.yaml is optional but absent')

    for name, paths in skill_names.items():
        if len(paths) > 1:
            add(findings, 'critical', name, 'duplicate skill name: ' + ', '.join(paths))

    agent_files = sorted(target.glob('.codex/agents/*.toml'))
    if agent_files:
        strengths.append(f'found {len(agent_files)} custom agent file(s)')

    for agent_file in agent_files:
        rel = agent_file.relative_to(target)
        if tomllib is None:
            add(findings, 'warning', str(rel), 'tomllib unavailable; cannot parse custom agent TOML')
            continue
        try:
            data = tomllib.loads(load_text(agent_file))
        except Exception as exc:
            add(findings, 'critical', str(rel), f'invalid TOML: {exc}')
            continue
        if not data.get('name'):
            add(findings, 'critical', str(rel), 'custom agent name missing')
        if not data.get('description'):
            add(findings, 'warning', str(rel), 'custom agent description missing')
        if not data.get('developer_instructions'):
            add(findings, 'warning', str(rel), 'developer_instructions missing')

    marketplace_path = target / '.agents' / 'plugins' / 'marketplace.json'
    marketplace_plugins = {}
    if marketplace_path.exists():
        try:
            marketplace = load_json(marketplace_path)
            strengths.append('plugin marketplace manifest present')
            if not marketplace.get('name'):
                add(findings, 'critical', str(marketplace_path.relative_to(target)), 'marketplace.name missing')
            interface = marketplace.get('interface')
            if not isinstance(interface, dict) or not interface.get('displayName'):
                add(findings, 'warning', str(marketplace_path.relative_to(target)), 'marketplace.interface.displayName missing or invalid')
            plugins = marketplace.get('plugins', [])
            if not isinstance(plugins, list):
                add(findings, 'critical', str(marketplace_path.relative_to(target)), 'marketplace.plugins must be an array')
                plugins = []
            for entry in plugins:
                name = entry.get('name', '')
                where = str(marketplace_path.relative_to(target))
                if not name or not KEBAB.match(name):
                    add(findings, 'warning', where, f'invalid plugin entry name: {name}')
                    continue
                if name in marketplace_plugins:
                    add(findings, 'critical', where, f'duplicate marketplace plugin entry: {name}')
                    continue
                marketplace_plugins[name] = entry
                source = entry.get('source', {})
                if not isinstance(source, dict) or source.get('source') != 'local':
                    add(findings, 'warning', where, f'marketplace plugin {name} must use local source object')
                path = source.get('path') if isinstance(source, dict) else None
                expected_path = f'./plugins/{name}'
                if path != expected_path:
                    add(findings, 'warning', where, f'marketplace plugin {name} should use source.path {expected_path}, got {path}')
                elif not (target / path[2:]).exists():
                    add(findings, 'critical', where, f'marketplace plugin path missing on disk: {path}')
                policy = entry.get('policy')
                if not isinstance(policy, dict):
                    add(findings, 'critical', where, f'marketplace plugin {name} policy missing')
                else:
                    if policy.get('installation') not in VALID_INSTALL:
                        add(findings, 'warning', where, f'marketplace plugin {name} has invalid installation policy: {policy.get("installation")}')
                    if policy.get('authentication') not in VALID_AUTH:
                        add(findings, 'warning', where, f'marketplace plugin {name} has invalid authentication policy: {policy.get("authentication")}')
                version = entry.get('version')
                if version and not SEMVER.match(str(version)):
                    add(findings, 'warning', where, f'marketplace plugin {name} version is not semver: {version}')
                if not entry.get('category'):
                    add(findings, 'warning', where, f'marketplace plugin {name} category missing')
        except Exception as exc:
            add(findings, 'critical', str(marketplace_path.relative_to(target)), f'invalid marketplace JSON: {exc}')
    else:
        add(findings, 'info', '.agents/plugins/marketplace.json', 'optional plugin marketplace manifest absent')

    plugin_manifests = sorted(target.glob('plugins/*/.codex-plugin/plugin.json'))
    packaged_plugin_names = set()
    if plugin_manifests:
        strengths.append(f'found {len(plugin_manifests)} packaged plugin manifest(s)')

    for manifest in plugin_manifests:
        rel = manifest.relative_to(target)
        plugin_root = manifest.parent.parent
        plugin_name = plugin_root.name
        try:
            data = load_json(manifest)
        except Exception as exc:
            add(findings, 'critical', str(rel), f'invalid plugin JSON: {exc}')
            continue

        packaged_plugin_names.add(plugin_name)
        name = data.get('name', '')
        if not name:
            add(findings, 'critical', str(rel), 'plugin name missing')
        elif name != plugin_name:
            add(findings, 'critical', str(rel), f'plugin manifest name {name} does not match directory {plugin_name}')
        elif not KEBAB.match(name):
            add(findings, 'warning', str(rel), f'plugin name not kebab-case: {name}')

        version = data.get('version')
        if version and not SEMVER.match(str(version)):
            add(findings, 'warning', str(rel), f'plugin version is not semver: {version}')
        if not data.get('description'):
            add(findings, 'info', str(rel), 'plugin description missing')

        if not (plugin_root / 'README.md').exists():
            add(findings, 'warning', str(plugin_root.relative_to(target)), 'plugin README.md missing')

        skills_value = data.get('skills')
        skills_dir = validate_path_ref(plugin_root, skills_value, findings, str(rel), 'skills path')
        packaged_skill_names = []
        if skills_dir is not None:
            packaged_skills = sorted(skills_dir.glob('*/SKILL.md'))
            if not packaged_skills:
                add(findings, 'critical', str(rel), 'skills path exists but no packaged SKILL.md files found')
            else:
                strengths.append(f'{plugin_name} packages {len(packaged_skills)} skill(s)')
                for packaged_skill in packaged_skills:
                    packaged_rel = packaged_skill.relative_to(target)
                    source_skill = target / '.agents' / 'skills' / packaged_skill.parent.name / 'SKILL.md'
                    packaged_skill_names.append(packaged_skill.parent.name)
                    if not source_skill.exists():
                        add(findings, 'warning', str(packaged_rel), f'packaged skill has no matching source skill: {source_skill.relative_to(target)}')
                        continue

                    packaged_text = load_text(packaged_skill)
                    source_text = load_text(source_skill)
                    _, packaged_body = parse_frontmatter(packaged_text)
                    _, source_body = parse_frontmatter(source_text)
                    packaged_review = extract_markdown_section(packaged_body, 'Review Harness')
                    source_review = extract_markdown_section(source_body, 'Review Harness')

                    if (packaged_review or source_review) and normalize_multiline(packaged_review or '') != normalize_multiline(source_review or ''):
                        add(
                            findings,
                            'warning',
                            str(packaged_rel),
                            'packaged Review Harness section drifted from source skill '
                            f'`{source_skill.relative_to(target)}`',
                        )

                    packaged_openai = packaged_skill.parent / 'agents' / 'openai.yaml'
                    source_openai = source_skill.parent / 'agents' / 'openai.yaml'
                    if packaged_openai.exists() and source_openai.exists():
                        packaged_yaml = load_text(packaged_openai)
                        source_yaml = load_text(source_openai)
                        field_map = {
                            'short_description': 'short_description',
                            'default_prompt': 'default_prompt',
                            'allow_implicit_invocation': 'allow_implicit_invocation',
                        }
                        for label, field in field_map.items():
                            if field == 'allow_implicit_invocation':
                                packaged_value = re.search(r'(?m)^\s*allow_implicit_invocation:\s*(true|false)\s*$', packaged_yaml)
                                source_value = re.search(r'(?m)^\s*allow_implicit_invocation:\s*(true|false)\s*$', source_yaml)
                                packaged_value = packaged_value.group(1) if packaged_value else ''
                                source_value = source_value.group(1) if source_value else ''
                            else:
                                packaged_value = parse_openai_interface_field(packaged_yaml, field)
                                source_value = parse_openai_interface_field(source_yaml, field)
                            if packaged_value != source_value:
                                add(
                                    findings,
                                    'warning',
                                    str(packaged_openai.relative_to(target)),
                                    f'packaged openai.yaml `{label}` drifted from source `{source_openai.relative_to(target)}`',
                                )
                    elif packaged_openai.exists() != source_openai.exists():
                        add(
                            findings,
                            'warning',
                            str(packaged_rel),
                            f'packaged/source openai.yaml presence differs from `{source_openai.relative_to(target)}`',
                        )

        readme_path = plugin_root / 'README.md'
        if readme_path.exists():
            readme_text = load_text(readme_path)
            included_skills = extract_markdown_section(readme_text, 'Included skills')
            if not included_skills:
                add(findings, 'warning', str(readme_path.relative_to(target)), 'README is missing `## Included skills` section')
            elif packaged_skill_names:
                readme_skill_refs = sorted(code_refs_from_bullets(included_skills))
                expected_skill_refs = sorted(packaged_skill_names)
                if readme_skill_refs != expected_skill_refs:
                    add(
                        findings,
                        'warning',
                        str(readme_path.relative_to(target)),
                        f'README Included skills drifted from packaged skills directory: expected {expected_skill_refs}, got {readme_skill_refs}',
                    )

            asset_section = extract_markdown_section(readme_text, 'Packaged assets')
            if not asset_section:
                add(findings, 'warning', str(readme_path.relative_to(target)), 'README is missing `## Packaged assets` section')
            else:
                required_assets = [
                    'assets/icon.svg',
                    'assets/icon.png',
                    'assets/logo.svg',
                    'assets/logo.png',
                    'assets/screenshot.svg',
                    'assets/screenshot.png',
                ]
                for asset_ref in required_assets:
                    if asset_ref not in asset_section:
                        add(findings, 'warning', str(readme_path.relative_to(target)), f'README Packaged assets section is missing `{asset_ref}`')

                optional_assets = {
                    'assets/browser-capture.png': (plugin_root / 'assets' / 'browser-capture.png').exists(),
                    'assets/live-capture.png': (plugin_root / 'assets' / 'live-capture.png').exists(),
                }
                for asset_ref, exists in optional_assets.items():
                    listed = asset_ref in asset_section
                    if exists and not listed:
                        add(findings, 'warning', str(readme_path.relative_to(target)), f'README Packaged assets section should list `{asset_ref}` because the asset exists')
                    if not exists and listed:
                        add(findings, 'warning', str(readme_path.relative_to(target)), f'README Packaged assets section lists `{asset_ref}` but the asset file is absent')

                has_mcp_file = (plugin_root / '.mcp.json').exists()
                bundled_mcp = extract_markdown_section(readme_text, 'Bundled MCP')
                if has_mcp_file and not bundled_mcp:
                    add(findings, 'warning', str(readme_path.relative_to(target)), 'README should include `## Bundled MCP` because .mcp.json exists')
                if not has_mcp_file and bundled_mcp:
                    add(findings, 'warning', str(readme_path.relative_to(target)), 'README has `## Bundled MCP` but the plugin has no .mcp.json')

        mcp_value = data.get('mcpServers')
        if isinstance(mcp_value, str):
            mcp_path = validate_path_ref(plugin_root, mcp_value, findings, str(rel), 'mcpServers path')
            if mcp_path is not None:
                try:
                    load_json(mcp_path)
                except Exception as exc:
                    add(findings, 'critical', str(mcp_path.relative_to(target)), f'invalid MCP JSON: {exc}')
        elif mcp_value is not None:
            add(findings, 'warning', str(rel), 'mcpServers should be a relative string path for packaged local plugins in this repo')

        interface = data.get('interface')
        if not isinstance(interface, dict):
            add(findings, 'critical', str(rel), 'plugin interface missing or invalid')
            interface = {}
        else:
            for key in ['displayName', 'shortDescription', 'longDescription', 'developerName', 'category', 'capabilities', 'defaultPrompt', 'brandColor']:
                if key not in interface:
                    add(findings, 'warning', str(rel), f'plugin interface.{key} missing')
            if 'capabilities' in interface and not isinstance(interface.get('capabilities'), list):
                add(findings, 'warning', str(rel), 'plugin interface.capabilities should be an array')
            if 'defaultPrompt' in interface and not isinstance(interface.get('defaultPrompt'), list):
                add(findings, 'warning', str(rel), 'plugin interface.defaultPrompt should be an array')
            for asset_field in ['composerIcon', 'logo']:
                asset_path = interface.get(asset_field)
                if asset_path:
                    validate_path_ref(plugin_root, asset_path, findings, str(rel), f'interface.{asset_field}')
            screenshots = interface.get('screenshots')
            if screenshots is not None:
                if not isinstance(screenshots, list):
                    add(findings, 'warning', str(rel), 'plugin interface.screenshots should be an array')
                else:
                    for idx, shot in enumerate(screenshots, 1):
                        validate_path_ref(plugin_root, shot, findings, str(rel), f'interface.screenshots[{idx}]')

            if isinstance(screenshots, list):
                optional_screenshot_refs = {
                    './assets/browser-capture.png': (plugin_root / 'assets' / 'browser-capture.png').exists(),
                    './assets/live-capture.png': (plugin_root / 'assets' / 'live-capture.png').exists(),
                }
                for shot_ref, exists in optional_screenshot_refs.items():
                    listed = shot_ref in screenshots
                    if exists and not listed:
                        add(findings, 'warning', str(rel), f'plugin interface.screenshots should include `{shot_ref}` because the asset exists')
                    if not exists and listed:
                        add(findings, 'warning', str(rel), f'plugin interface.screenshots includes `{shot_ref}` but the asset file is absent')

        if packaged_skill_names and isinstance(interface, dict):
            short_source_skill = short_description_source_skill(plugin_name, packaged_skill_names)
            if short_source_skill:
                source_openai = target / '.agents' / 'skills' / short_source_skill / 'agents' / 'openai.yaml'
                if source_openai.exists():
                    source_yaml = load_text(source_openai)
                    source_short = parse_openai_interface_field(source_yaml, 'short_description')
                    if source_short and interface.get('shortDescription') != source_short:
                        add(
                            findings,
                            'warning',
                            str(rel),
                            'plugin interface.shortDescription drifted from source '
                            f'`{source_openai.relative_to(target)}`',
                        )

            prompt_sources = default_prompt_source_skills(plugin_name, packaged_skill_names)
            prompts = interface.get('defaultPrompt')
            prompts = prompts if isinstance(prompts, list) else []
            for idx, source_skill in enumerate(prompt_sources):
                source_openai = target / '.agents' / 'skills' / source_skill / 'agents' / 'openai.yaml'
                if not source_openai.exists():
                    continue
                source_yaml = load_text(source_openai)
                source_prompt = parse_openai_interface_field(source_yaml, 'default_prompt')
                actual_prompt = prompts[idx] if idx < len(prompts) else ''
                if source_prompt and actual_prompt != source_prompt:
                    add(
                        findings,
                        'warning',
                        str(rel),
                        f'plugin interface.defaultPrompt[{idx}] drifted from source '
                        f'`{source_openai.relative_to(target)}`',
                    )

        marketplace_entry = marketplace_plugins.get(plugin_name)
        if marketplace_plugins and marketplace_entry is None:
            add(findings, 'warning', str(rel), f'packaged plugin {plugin_name} missing from marketplace.json')
        elif marketplace_entry is not None:
            if marketplace_entry.get('version') and version and marketplace_entry.get('version') != version:
                add(findings, 'warning', str(rel), f'marketplace version {marketplace_entry.get("version")} does not match plugin version {version}')
            if marketplace_entry.get('description') and data.get('description') and marketplace_entry.get('description') != data.get('description'):
                add(findings, 'warning', str(rel), 'marketplace description does not match plugin manifest description')

    for name in sorted(marketplace_plugins):
        if name not in packaged_plugin_names:
            add(findings, 'warning', str(marketplace_path.relative_to(target)), f'marketplace entry {name} has no packaged plugin directory')

    order = {'critical': 0, 'warning': 1, 'info': 2}
    findings.sort(key=lambda x: (order.get(x[0], 9), x[1], x[2]))

    print('# Codex Plugin Doctor Report')
    print()
    print(f'- Target: `{target}`')
    print(f'- Skills found: `{len(skill_files)}`')
    print(f'- Custom agents found: `{len(agent_files)}`')
    print(f'- Packaged plugins found: `{len(plugin_manifests)}`')
    print(f'- Findings: `{len(findings)}`')
    print(f'- Strengths: `{len(set(strengths))}`')
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
    for key, items in grouped.items():
        if not items:
            continue
        print(f'- `{key}`: {len(items)}')
    if not any(grouped.values()):
        print('- None')
    print()
    print('## Strengths')
    unique_strengths = sorted(set(strengths))
    if not unique_strengths:
        print('- None')
    else:
        for item in unique_strengths:
            print(f'- {item}')
    print()
    print('## Machine summary')
    summary = build_summary(target, skill_files, agent_files, plugin_manifests, findings, strengths)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.json_out:
        out_path = Path(args.json_out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
