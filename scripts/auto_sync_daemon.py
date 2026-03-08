#!/usr/bin/env python3

from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path


RUNNING = True


def timestamp() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")


def log(message: str) -> None:
    print(f"[auto_sync_daemon] {timestamp()} {message}", flush=True)


def run_capture(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def git_status(repo_root: Path) -> str:
    result = run_capture(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repo_root,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status failed")
    return result.stdout.strip()


def run_sync(
    repo_root: Path,
    sync_script: Path,
    branch: str | None,
) -> int:
    command = [str(sync_script), "--auto"]
    if branch:
        command.extend(["--branch", branch])

    process = subprocess.run(command, cwd=repo_root, check=False)
    return process.returncode


def acquire_lock(repo_root: Path):
    repo_hash = hashlib.sha1(str(repo_root).encode("utf-8")).hexdigest()
    lock_path = Path(tempfile.gettempdir()) / f"codex-skills-auto-sync-{repo_hash}.lock"
    lock_file = lock_path.open("w")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log(f"Another auto-sync daemon is already running: {lock_path}")
        raise SystemExit(0)
    lock_file.write(str(os.getpid()))
    lock_file.flush()
    return lock_file


def handle_signal(signum, _frame) -> None:
    global RUNNING
    RUNNING = False
    log(f"Received signal {signum}; shutting down.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch git working tree changes and auto-run repo sync after debounce."
    )
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parent.parent),
        help="Path to the git repository root",
    )
    parser.add_argument(
        "--sync-script",
        default=str(Path(__file__).resolve().parent / "sync_repo.sh"),
        help="Path to the sync script to execute",
    )
    parser.add_argument(
        "--branch",
        default="",
        help="Optional branch override for sync_repo.sh",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=15.0,
        help="Polling interval in seconds",
    )
    parser.add_argument(
        "--debounce",
        type=float,
        default=20.0,
        help="How long changes must stay stable before syncing",
    )
    parser.add_argument(
        "--retry-cooldown",
        type=float,
        default=120.0,
        help="Minimum seconds before retrying the same failed status snapshot",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    sync_script = Path(args.sync_script).expanduser().resolve()
    branch = args.branch or None

    if not repo_root.is_dir():
        print(f"Repository root not found: {repo_root}", file=sys.stderr)
        return 1
    if not sync_script.is_file():
        print(f"Sync script not found: {sync_script}", file=sys.stderr)
        return 1

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    lock_file = acquire_lock(repo_root)
    _ = lock_file

    interval = max(args.interval, 2.0)
    debounce = max(args.debounce, interval)
    retry_cooldown = max(args.retry_cooldown, debounce)

    try:
        observed_status = git_status(repo_root)
    except Exception as exc:
        log(f"Initial git status failed: {exc}")
        return 1

    log(f"Starting auto-sync daemon for {repo_root}")
    log(
        f"Settings: interval={interval:.0f}s debounce={debounce:.0f}s retry_cooldown={retry_cooldown:.0f}s"
    )
    if observed_status:
        log("Repository already has pending changes at startup; waiting for a new change before auto-sync.")

    pending_status = ""
    last_change_at = 0.0
    last_failed_status = ""
    last_failed_at = 0.0

    while RUNNING:
        try:
            current_status = git_status(repo_root)
        except Exception as exc:  # pragma: no cover - operational logging
            log(f"git status failed: {exc}")
            time.sleep(interval)
            continue

        now = time.monotonic()

        if current_status != observed_status:
            observed_status = current_status
            if current_status:
                pending_status = current_status
                last_change_at = now
                log("Detected working tree changes; waiting for debounce.")
            else:
                if pending_status:
                    log("Working tree is clean again.")
                pending_status = ""
                last_change_at = 0.0
            time.sleep(interval)
            continue

        if not pending_status:
            time.sleep(interval)
            continue

        if now - last_change_at < debounce:
            time.sleep(interval)
            continue

        if (
            pending_status == last_failed_status
            and now - last_failed_at < retry_cooldown
        ):
            time.sleep(interval)
            continue

        log("Debounce satisfied; running sync script.")
        exit_code = run_sync(repo_root, sync_script, branch)

        if exit_code == 0:
            log("Auto-sync completed successfully.")
            observed_status = git_status(repo_root)
            pending_status = ""
            last_change_at = 0.0
            last_failed_status = ""
            last_failed_at = 0.0
        else:
            log(f"Auto-sync failed with exit code {exit_code}.")
            last_failed_status = pending_status
            last_failed_at = now

        time.sleep(interval)

    log("Auto-sync daemon stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
