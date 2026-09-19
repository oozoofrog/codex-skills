"""Serialize the two Jev launchers without taking over an existing controller."""

import fcntl
import os
import signal
import subprocess
import sys
from pathlib import Path


def main():
    directory = Path.home() / ".local/state/jev"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "controller.lock").open("a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(
                "Another Jev controller is active. Stop it before switching tools.",
                file=sys.stderr,
            )
            return 4
        child = subprocess.Popen(sys.argv[1:], start_new_session=True)

        def forward(signum, _frame):
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass

        signal.signal(signal.SIGINT, forward)
        signal.signal(signal.SIGTERM, forward)
        result = child.wait()
        return result if result >= 0 else 128 - result


if __name__ == "__main__":
    raise SystemExit(main())
