"""Prepare Chrome separately from task execution; never run a Jev model here."""

import json
import subprocess
import sys
from pathlib import Path


def ready():
    try:
        result = subprocess.run(
            [
                str(Path(sys.executable).with_name("browser-harness")),
                "doctor",
                "--json",
                "--require-existing-daemon",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return (
            result.returncode == 0 and json.loads(result.stdout).get("healthy") is True
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False


def prepare():
    if not ready():
        try:
            subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from browser_harness.admin import ensure_daemon; ensure_daemon(wait=5)",
                ],
                capture_output=True,
                timeout=20,
                check=False,
            )
        except subprocess.TimeoutExpired:
            pass
    connected = ready()
    print(
        json.dumps(
            {
                "status": "ready" if connected else "connection_required",
                "task_started": False,
                "next": "Run the task."
                if connected
                else (
                    "This preparation process has stopped. Inspect Chrome for its remote-debugging permission dialog; "
                    "a pending harness daemon may retain it. Approve only the requested connection, then check status. "
                    "No Jev task is waiting or will resume automatically."
                ),
            }
        ),
        flush=True,
    )
    return 0 if connected else 3


if __name__ == "__main__":
    raise SystemExit(prepare())
