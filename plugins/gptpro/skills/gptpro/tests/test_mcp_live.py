from __future__ import annotations

import hashlib
import json
import multiprocessing
import time
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
import sys

if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from runtime.gptpro_mcp.audit import AuditBinding, AuditLog
from runtime.gptpro_mcp.errors import ToolError
from runtime.gptpro_mcp.live import (
    ActiveRuntimeContext,
    ControllerLease,
    RuntimeServerLease,
    controller_lease_is_live,
    decode_session_capability,
    encode_session_capability,
)
from runtime.gptpro_mcp.runtime_state import RuntimeStateError, RuntimeStateStore
from runtime.gptpro_mcp.schema import DEFAULT_LIMITS, PROTOCOL_PROFILE, tool_schema_sha256


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def hold_controller_lease(root: str, session_hash: str, ready) -> None:
    store = RuntimeStateStore(Path(root))
    lease = ControllerLease(store, session_hash).acquire()
    ready.set()
    while True:
        _ = lease
        time.sleep(1)


class LiveRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.handoff = self.base / "handoff"
        self.handoff.mkdir(mode=0o700)
        self.archive = self.handoff / "snapshot.zip"
        self.archive.write_bytes(b"fixture")
        self.manifest_path = self.handoff / "manifest.json"
        self.manifest_path.write_text("{}\n", encoding="utf-8")
        self.capability = b"c" * 32
        self.session_hash = digest(self.capability)
        self.package_id = "live-package"
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.monotonic_now = time.monotonic()
        self.manifest_hash = digest(b"manifest")
        self.archive_hash = digest(b"archive")
        self.approval_hash = digest(b"approval")
        self.file_set_hash = digest(b"files")
        self.limits_hash = digest(
            json.dumps(DEFAULT_LIMITS, sort_keys=True, separators=(",", ":")).encode()
        )
        self.manifest = {
            "schema_version": 3,
            "package_id": self.package_id,
            "transport": {"requested": "mcp-read", "resolved": "mcp-read"},
            "delivery": {"channel": "browser", "approval_required": True},
            "connector": {
                "type": "secure-mcp-tunnel",
                "protocol_profile": PROTOCOL_PROFILE,
                "tool_schema_sha256": tool_schema_sha256(),
            },
            "mcp_disclosure": {"limits": dict(DEFAULT_LIMITS)},
        }
        self.verified = {
            "manifest": self.manifest,
            "manifest_path": self.manifest_path,
            "archive_path": self.archive,
            "manifest_sha256": self.manifest_hash,
        }
        self.store = RuntimeStateStore(self.base / "runtime")
        self.binding = AuditBinding(
            package_id=self.package_id,
            session_id_sha256=self.session_hash,
            manifest_sha256=self.manifest_hash,
            approval_event_sha256=self.approval_hash,
            archive_sha256=self.archive_hash,
            file_set_sha256=self.file_set_hash,
            tool_schema_sha256=tool_schema_sha256(),
            limits_sha256=self.limits_hash,
        )
        self.audit = AuditLog(
            self.handoff / "mcp-audit.jsonl",
            self.binding,
            runtime_store=self.store,
        )
        header = self.audit.create_header()
        candidate = {
            "package_id": self.package_id,
            "session_id_sha256": self.session_hash,
            "handoff_dir": str(self.handoff.resolve()),
            "manifest_sha256": self.manifest_hash,
            "approval_event_sha256": self.approval_hash,
            "archive_sha256": self.archive_hash,
            "file_set_sha256": self.file_set_hash,
            "tool_schema_sha256": tool_schema_sha256(),
            "mcp_target_sha256": digest(b"mcp-target"),
            "protocol_profile": PROTOCOL_PROFILE,
            "transport": "mcp-read",
            "delivery_channel": "browser",
            "connector_type": "secure-mcp-tunnel",
            "tunnel_runtime_alias": "gptpro-web",
            "tunnel_id_binding_sha256": digest(b"tunnel"),
            "tunnel_profile_sha256": digest(b"tunnel-profile"),
            "tunnel_client_binary_sha256": digest(b"tunnel-client-binary"),
            "mcp_runtime_tree_sha256": digest(b"mcp-runtime-tree"),
            "workspace_binding_confirmed": True,
            "activated_at": self.now.isoformat().replace("+00:00", "Z"),
            "expires_at": (self.now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
            "idle_ttl_seconds": 900,
            "activated_monotonic": self.monotonic_now,
            "expires_monotonic": self.monotonic_now + 3600,
            "last_activity_monotonic": self.monotonic_now,
            "audit_file": "mcp-audit.jsonl",
        }
        self.store.begin_activation(candidate)
        self.store.transition(
            self.session_hash,
            "activating",
            "active",
            updates={"audit_header_sha256": header},
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def context(
        self,
        *,
        capability: bytes | None = None,
        now=None,
        monotonic=None,
        controller_liveness=lambda store, session: True,
    ) -> ActiveRuntimeContext:
        def validate(verified: dict, state: dict, session_hash: str) -> None:
            self.assertIs(verified, self.verified)
            self.assertEqual(self.package_id, state["package_id"])
            self.assertEqual(self.session_hash, session_hash)
            self.assertEqual(self.manifest_hash, state["manifest_sha256"])

        return ActiveRuntimeContext(
            runtime_store=self.store,
            session_capability=self.capability if capability is None else capability,
            package_loader=lambda path: self.verified
            if path == self.handoff.resolve()
            else {},
            binding_validator=validate,
            audit_factory=lambda verified, session: self.audit,
            now=now or (lambda: self.now + timedelta(seconds=1)),
            monotonic=monotonic or (lambda: self.monotonic_now + 1),
            controller_liveness=controller_liveness,
        )

    def test_capability_encoding_is_canonical(self) -> None:
        encoded = encode_session_capability(self.capability)
        self.assertEqual(43, len(encoded))
        self.assertEqual(self.capability, decode_session_capability(encoded))
        for invalid in ("", encoded + "=", "!" * 43, encode_session_capability(b"d" * 32)[:-1]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                decode_session_capability(invalid)

    def test_active_context_revalidates_capability_package_audit_and_expiry(self) -> None:
        context = self.context()
        grant = context.resolve(self.package_id)
        self.assertEqual(self.archive, grant.archive_path)
        self.assertEqual(self.session_hash, grant.session_id_sha256)

        with self.assertRaises(ToolError) as wrong_package:
            context.resolve("different-package")
        self.assertEqual("PACKAGE_MISMATCH", wrong_package.exception.code)

        with self.assertRaises(ToolError) as wrong_capability:
            self.context(capability=b"x" * 32).resolve(self.package_id)
        self.assertEqual("SESSION_CONFLICT", wrong_capability.exception.code)

        self.store.transition(self.session_hash, "active", "revoking")
        with self.assertRaises(ToolError) as revoked:
            context.resolve(self.package_id)
        self.assertEqual("NO_ACTIVE_PACKAGE", revoked.exception.code)

    def test_footer_blocks_future_content(self) -> None:
        self.audit.append_footer("user_requested")
        with self.assertRaises(ToolError) as raised:
            self.context().resolve(self.package_id)
        self.assertEqual("AUDIT_CHAIN_INVALID", raised.exception.code)

    def test_wall_clock_rollback_cannot_extend_production_idle_or_session_ttl(self) -> None:
        rolled_back_wall = lambda: self.now - timedelta(days=1)
        idle_expired = self.context(
            now=rolled_back_wall,
            monotonic=lambda: self.monotonic_now + 901,
        )
        with self.assertRaises(ToolError) as idle:
            idle_expired.resolve(self.package_id)
        self.assertEqual("IDLE_TIMEOUT", idle.exception.code)

        session_expired = self.context(
            now=rolled_back_wall,
            monotonic=lambda: self.monotonic_now + 3601,
        )
        with self.assertRaises(ToolError) as session:
            session_expired.resolve(self.package_id)
        self.assertEqual("SESSION_EXPIRED", session.exception.code)

        restarted_clock = self.context(
            now=rolled_back_wall,
            monotonic=lambda: self.monotonic_now - 1,
        )
        with self.assertRaises(ToolError) as unsafe:
            restarted_clock.resolve(self.package_id)
        self.assertEqual("RUNTIME_STATE_UNSAFE", unsafe.exception.code)

    def test_runtime_server_lease_is_exclusive_and_recoverable(self) -> None:
        first = RuntimeServerLease(self.store, self.session_hash).acquire()
        try:
            with self.assertRaises(RuntimeStateError) as raised:
                RuntimeServerLease(self.store, self.session_hash).acquire()
            self.assertEqual("SESSION_CONFLICT", raised.exception.code)
        finally:
            first.close()
        second = RuntimeServerLease(self.store, self.session_hash).acquire()
        second.close()

    def test_controller_process_death_releases_liveness_and_denies_future_calls(self) -> None:
        context = multiprocessing.get_context("spawn")
        ready = context.Event()
        process = context.Process(
            target=hold_controller_lease,
            args=(str(self.store.root), self.session_hash, ready),
        )
        process.start()
        try:
            self.assertTrue(ready.wait(5))
            self.assertTrue(controller_lease_is_live(self.store, self.session_hash))
            live = self.context(controller_liveness=controller_lease_is_live)
            self.assertEqual(self.package_id, live.resolve(self.package_id).package_id)
            process.terminate()
            process.join(5)
            self.assertFalse(process.is_alive())
            self.assertFalse(controller_lease_is_live(self.store, self.session_hash))
            with self.assertRaises(ToolError) as raised:
                live.resolve(self.package_id)
            self.assertEqual("NO_ACTIVE_PACKAGE", raised.exception.code)
        finally:
            if process.is_alive():
                process.terminate()
            process.join(5)


if __name__ == "__main__":
    unittest.main()
