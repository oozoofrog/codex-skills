from __future__ import annotations

import multiprocessing
import os
import tempfile
import time
import unittest
from pathlib import Path
import sys

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from runtime.gptpro_mcp.package_lock import package_lifecycle_lock, package_lock_path
from runtime.gptpro_mcp.runtime_state import RuntimeStateError


def _hold_package_lock(handoff: str, ready: multiprocessing.synchronize.Event) -> None:
    with package_lifecycle_lock(Path(handoff), timeout=2.0):
        ready.set()
        time.sleep(1.0)


class PackageLifecycleLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.handoff = self.root / "handoffs" / "package-one"
        self.handoff.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_lock_is_owner_only_external_and_reentrant(self) -> None:
        with package_lifecycle_lock(self.handoff):
            with package_lifecycle_lock(self.handoff):
                path = package_lock_path(self.handoff)
                self.assertEqual(0o600, path.stat().st_mode & 0o777)
                self.assertEqual(os.getuid(), path.stat().st_uid)
                self.assertNotEqual(self.handoff, path.parent)

    def test_second_process_times_out_while_first_holds_lock(self) -> None:
        context = multiprocessing.get_context("spawn")
        ready = context.Event()
        process = context.Process(target=_hold_package_lock, args=(str(self.handoff), ready))
        process.start()
        try:
            self.assertTrue(ready.wait(timeout=5.0))
            with self.assertRaises(RuntimeStateError) as raised:
                with package_lifecycle_lock(self.handoff, timeout=0.1):
                    self.fail("contended package lock must not be acquired")
            self.assertEqual("LOCK_TIMEOUT", raised.exception.code)
        finally:
            process.join(timeout=5.0)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5.0)

    def test_world_writable_handoff_is_rejected(self) -> None:
        self.handoff.chmod(0o777)
        with self.assertRaises(RuntimeStateError) as raised:
            with package_lifecycle_lock(self.handoff):
                pass
        self.assertEqual("RUNTIME_STATE_UNSAFE", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
