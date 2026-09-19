#!/usr/bin/env python3
"""Preview or copy selected skills without changing Codex configuration."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
JEV_SKILLS = ('jev-calibrate', 'jev-context', 'jev-decision', 'jev-product-choice', 'jev-review-evidence', 'jev-triage', 'jev-workbench')


def reject_links(path: Path) -> None:
    for item in [*path.absolute().parents, path.absolute()]:
        if item.is_symlink():
            raise ValueError(f"Symlink destination/source component refused: {item}")


def install(destination: Path, preset: str, official: bool, apply: bool) -> dict:
    reject_links(destination)
    sources = [ROOT / 'jev-workbench']
    if preset == 'all':
        sources = [ROOT / name for name in JEV_SKILLS]
    if official:
        sources.append(ROOT / 'docs' / 'jev' / 'vendor' / 'typesafe-ai')
    for source in sources:
        reject_links(source)
        if not (source / 'SKILL.md').is_file() and not (source / 'SKILL.reference.md').is_file():
            raise ValueError(f"Missing source skill: {source}")
        if any(p.is_symlink() for p in source.rglob('*')):
            raise ValueError(f"Symlink in source tree refused: {source}")
    targets = [destination / p.name for p in sources]
    conflicts = [str(p) for p in targets if p.exists() or p.is_symlink()]
    report = {'mode': 'apply' if apply else 'preview', 'destination': str(destination.absolute()),
              'skills': [p.name for p in sources], 'conflicts': conflicts,
              'configuration_changed': False, 'network_used': False}
    if not apply:
        return report
    if conflicts:
        raise ValueError('Refusing overwrite; existing paths: ' + ', '.join(conflicts))
    destination.mkdir(parents=True, exist_ok=True)
    reject_links(destination)
    # Stage everything before creating final skill directories. No runtime or network executed.
    staging = Path(tempfile.mkdtemp(prefix='.jev-install-', dir=destination))
    completed: list[Path] = []
    try:
        for source in sources:
            shutil.copytree(source, staging / source.name,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for source in sources:
            reference = staging / source.name / 'SKILL.reference.md'
            if reference.is_file():
                reference.rename(reference.with_name('SKILL.md'))
        for source, target in zip(sources, targets):
            # Exclusive mkdir avoids replacing an existing skill, including concurrent installers.
            target.mkdir()
            completed.append(target)
            shutil.copytree(staging / source.name, target, dirs_exist_ok=True)
    except BaseException:
        for target in reversed(completed):
            shutil.rmtree(target)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    report['installed'] = [str(p.absolute()) for p in targets]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dest', type=Path, required=True, help='Explicit skill root, e.g. ~/.agents/skills')
    parser.add_argument('--preset', choices=['core', 'all'], default='core')
    parser.add_argument('--with-typesafe', action='store_true', help='Also install the MIT official documentation skill snapshot')
    parser.add_argument('--apply', action='store_true', help='Copy files; without this flag only preview')
    args = parser.parse_args()
    try:
        result = install(args.dest.expanduser(), args.preset, args.with_typesafe, args.apply)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({'status':'ERROR','message':str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
