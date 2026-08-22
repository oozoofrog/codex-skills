from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from runtime.gptpro_mcp.package_lock import package_lock_path
from runtime.gptpro_mcp.package_tx import commit_lifecycle_pair, recover_lifecycle_pair
from runtime.gptpro_mcp.runtime_state import RuntimeStateError


class InjectedCrash(RuntimeError):
    pass


class PackageLifecycleTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.handoff = self.root / "handoffs" / "package-one"
        self.handoff.mkdir(parents=True)
        self.initial_state = {"schema_version": 3, "package_id": "package-one", "phase": "approved"}
        self.initial_receipt = {
            "schema_version": 3,
            "package_id": "package-one",
            "events": [{"type": "approved"}],
        }
        self.write("state.json", self.initial_state)
        self.write("receipt.json", self.initial_receipt)
        self.next_state = {**self.initial_state, "phase": "submitted"}
        self.next_receipt = {
            **self.initial_receipt,
            "events": [*self.initial_receipt["events"], {"type": "submitted"}],
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, name: str, value: object) -> None:
        path = self.handoff / name
        path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        path.chmod(0o600)

    def load(self, name: str) -> dict:
        return json.loads((self.handoff / name).read_text(encoding="utf-8"))

    def test_fault_at_each_write_boundary_rolls_forward_exact_pair(self) -> None:
        for checkpoint in ("journal", "state", "receipt"):
            with self.subTest(checkpoint=checkpoint):
                self.write("state.json", self.initial_state)
                self.write("receipt.json", self.initial_receipt)

                def crash(observed: str) -> None:
                    if observed == checkpoint:
                        raise InjectedCrash(checkpoint)

                with self.assertRaises(InjectedCrash):
                    commit_lifecycle_pair(
                        self.handoff,
                        operation="mark-submitted",
                        state=self.next_state,
                        receipt=self.next_receipt,
                        fault_injector=crash,
                    )
                self.assertTrue(recover_lifecycle_pair(self.handoff))
                self.assertEqual(self.next_state, self.load("state.json"))
                self.assertEqual(self.next_receipt, self.load("receipt.json"))
                self.assertFalse(recover_lifecycle_pair(self.handoff))

    def test_divergent_file_refuses_journal_recovery(self) -> None:
        def crash(observed: str) -> None:
            if observed == "journal":
                raise InjectedCrash(observed)

        with self.assertRaises(InjectedCrash):
            commit_lifecycle_pair(
                self.handoff,
                operation="mark-submitted",
                state=self.next_state,
                receipt=self.next_receipt,
                fault_injector=crash,
            )
        self.write("state.json", {**self.initial_state, "phase": "tampered"})
        with self.assertRaises(RuntimeStateError) as raised:
            recover_lifecycle_pair(self.handoff)
        self.assertEqual("RUNTIME_STATE_UNSAFE", raised.exception.code)

    def test_pathological_journal_json_fails_with_stable_domain_error(self) -> None:
        def crash(observed: str) -> None:
            if observed == "journal":
                raise InjectedCrash(observed)

        with self.assertRaises(InjectedCrash):
            commit_lifecycle_pair(
                self.handoff,
                operation="mark-submitted",
                state=self.next_state,
                receipt=self.next_receipt,
                fault_injector=crash,
            )
        journal = package_lock_path(self.handoff).with_suffix(".journal.json")
        journal.write_text('{"value":' + "9" * 5000 + "}\n", encoding="utf-8")
        journal.chmod(0o600)
        with self.assertRaises(RuntimeStateError) as raised:
            recover_lifecycle_pair(self.handoff)
        self.assertEqual("RUNTIME_STATE_UNSAFE", raised.exception.code)

    def test_surrogate_journal_json_fails_with_stable_domain_error(self) -> None:
        def crash(observed: str) -> None:
            if observed == "journal":
                raise InjectedCrash(observed)

        with self.assertRaises(InjectedCrash):
            commit_lifecycle_pair(
                self.handoff,
                operation="mark-submitted",
                state=self.next_state,
                receipt=self.next_receipt,
                fault_injector=crash,
            )
        journal = package_lock_path(self.handoff).with_suffix(".journal.json")
        journal.write_text(
            journal.read_text(encoding="utf-8").replace(
                "{", '{"unknown_text":"\\ud800",', 1
            ),
            encoding="utf-8",
        )
        journal.chmod(0o600)
        with self.assertRaises(RuntimeStateError) as surrogate:
            recover_lifecycle_pair(self.handoff)
        self.assertEqual("RUNTIME_STATE_UNSAFE", surrogate.exception.code)


if __name__ == "__main__":
    unittest.main()
