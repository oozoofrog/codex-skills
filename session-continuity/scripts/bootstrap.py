#!/usr/bin/env python3
"""Create continuity files without replacing existing rules or task states."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
import sys


ASSETS = Path(__file__).resolve().parent.parent / "assets"


def git(repo, *args, allowed=(0,)):
    result = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode not in allowed:
        raise ValueError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.rstrip("\n")


def local_path(repo, relative, directory=False):
    """Reject links and conflicting types before writing repository files."""
    path = repo
    parts = Path(relative).parts
    for index, part in enumerate(parts):
        path = path / part
        if path.is_symlink():
            raise ValueError(f"Symbolic link requires manual handling: {path}")
        if path.exists():
            is_directory = index < len(parts) - 1 or directory
            if (is_directory and not path.is_dir()) or (
                not is_directory and not path.is_file()
            ):
                raise ValueError(f"Unexpected file type: {path}")
    return path


def append_block(path, block):
    original = path.read_bytes() if path.exists() else b""
    newline = b"\r\n" if b"\r\n" in original else b"\n"
    separator = b"" if not original else (
        newline if original.endswith(b"\n") else newline * 2
    )
    with path.open("ab") as output:
        output.write(separator + block.encode("utf-8").replace(b"\n", newline))
    print(f"ADDED: {path}")


def initialize(repo, ignore_work):
    agents = local_path(repo, "AGENTS.md")
    work = local_path(repo, ".codex/work", directory=True)
    template = local_path(repo, ".codex/work/_template.md")
    ignore = local_path(repo, ".gitignore") if ignore_work else None
    existing = agents.read_text(encoding="utf-8-sig") if agents.exists() else ""
    section = (ASSETS / "agents-section.md").read_text(encoding="utf-8")
    state_template = (ASSETS / "task-state.md").read_text(encoding="utf-8")
    # A name in prose or an example also causes a conservative skip; inspect it.
    has_section = "codex session continuity" in existing.casefold()
    needs_ignore = False
    if ignore_work:
        # Use Git's own matching rules, including global excludes and negations.
        ignored = git(
            repo, "check-ignore", "--no-index", "--", ".codex/work/",
            allowed=(0, 1),
        )
        needs_ignore = not ignored

    if has_section:
        print("PRESERVED: AGENTS.md mentions Codex Session Continuity; inspect coverage.")
    else:
        append_block(agents, section)
    work.mkdir(parents=True, exist_ok=True)
    if template.exists():
        print(f"PRESERVED: {template}")
    else:
        with template.open("x", encoding="utf-8", newline="\n") as output:
            output.write(state_template)
        print(f"CREATED: {template}")

    if needs_ignore:
        append_block(ignore, "# Local Codex task checkpoints\n/.codex/work/\n")
    elif ignore_work:
        print("PRESERVED: existing Git ignore rules already exclude .codex/work/.")
    else:
        print("OPTIONAL: Git exclusion recommended; use init --ignore-work to opt in.")
    print("No tests run. Existing tracked files remain tracked.")


def start(repo, task_id, goal):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", task_id):
        raise ValueError("task-id: 1–64 lowercase letters/digits/_/-, starting with a letter or digit")
    if not goal.strip():
        raise ValueError("goal must not be blank")
    target = local_path(repo, f".codex/work/{task_id}.md")
    if target.exists():
        raise ValueError(f"State already exists; read and resume it, do not overwrite: {target}")
    template = local_path(repo, ".codex/work/_template.md")
    if not template.is_file():
        raise ValueError("Run init first: .codex/work/_template.md is missing")
    branch = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", allowed=(0, 1))
    head = git(repo, "rev-parse", "--verify", "--quiet", "HEAD", allowed=(0, 1))
    status = git(repo, "status", "--short", "--untracked-files=all")
    values = {
        "TASK_ID": task_id,
        "UPDATED_AT": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "REPO_ROOT": str(repo),
        "BRANCH": branch or "(detached HEAD)",
        "HEAD": head or "(unborn: no commit yet)",
        "GOAL": goal.strip(),
        "GIT_STATUS": "\n".join("    " + line for line in status.splitlines())
        if status else "(clean at capture time)",
    }
    content = template.read_text(encoding="utf-8")
    content = re.sub(r"\{\{([A-Z_]+)\}\}", lambda m: values.get(m[1], m[0]), content)
    with target.open("x", encoding="utf-8", newline="\n") as output:
        output.write(content)
    print(f"CREATED: {target}")
    print("Fill Definition of Done, Relevant Files and Exact Next Action from actual evidence.")
    print("No tests run. Resume by reading AGENTS.md, state, Git status/HEAD/diff, relevant files.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init_parser = commands.add_parser("init", help="add missing continuity rules and state template")
    init_parser.add_argument("--repo", required=True, type=Path, help="exact Git worktree root")
    init_parser.add_argument("--ignore-work", action="store_true", help="opt in to Git exclusion")
    start_parser = commands.add_parser("start", help="create one task state, refusing overwrite")
    start_parser.add_argument("--repo", required=True, type=Path, help="exact Git worktree root")
    start_parser.add_argument("--task-id", required=True)
    start_parser.add_argument("--goal", required=True)
    args = parser.parse_args()
    try:
        repo = args.repo.expanduser().resolve(strict=True)
        actual_root = Path(git(repo, "rev-parse", "--show-toplevel")).resolve()
        if repo != actual_root:
            raise ValueError(f"Use the exact Git worktree root: {actual_root}")
        if args.command == "init":
            initialize(repo, args.ignore_work)
        else:
            start(repo, args.task_id, args.goal)
    except (OSError, ValueError, UnicodeError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
