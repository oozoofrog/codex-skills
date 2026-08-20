# Selective skill installation

`scripts/manage_skills.py` installs only the top-level skill packages you name. It does not copy `.system/` mirrors or every repository directory.

For a first installation, prefer the network paths in [`plugin-installation.md`](./plugin-installation.md). They use Codex's bundled `$skill-installer` or Plugin marketplace and do not require the user to invoke Python. The manager documented here remains useful for a reviewed checkout, offline use, and atomic updates.

## List available packages

```bash
python3 scripts/manage_skills.py list
python3 scripts/manage_skills.py list --format json
```

Each package is reported as:

- `not-installed`: no destination exists;
- `current`: installed tree hash matches this checkout;
- `different`: a valid installation exists with different content;
- `conflict`: the destination exists but is not a valid Skill directory.

## Install selected packages

```bash
python3 scripts/manage_skills.py install gptpro
python3 scripts/manage_skills.py install gptpro another-skill
```

The default destination is `${CODEX_HOME:-~/.codex}/skills`. Use `--dest` for an isolated or test installation.

## Preview and update

```bash
python3 scripts/manage_skills.py install gptpro --dry-run
python3 scripts/manage_skills.py install gptpro --update
```

An existing differing Skill is never replaced without `--update`. Updates are copied to a staging directory, tree-hash checked, and swapped into place. A failed swap restores the prior installation.

The manager rejects symlinks inside Skill packages and ignores cache artifacts such as `__pycache__` and `*.pyc`.

## Install directly from GitHub

Codex's bundled `$skill-installer` can install a fresh package without cloning this repository or exposing its helper implementation to the user:

```text
$skill-installer Install gptpro from https://github.com/oozoofrog/codex-skills/tree/main/gptpro
```

The bundled installer refuses to overwrite an existing destination. Use a reviewed checkout plus `manage_skills.py --update` for updates.

For Plugin installation and the repository marketplace, see [`plugin-installation.md`](./plugin-installation.md).
