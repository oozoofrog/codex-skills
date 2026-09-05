from __future__ import annotations

import hashlib
import json
import stat
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
import sys

if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from runtime.gptpro_desktop.approval import (
    build_desktop_approval,
    load_desktop_approval,
    match_desktop_approval,
    revoke_desktop_approval,
    store_desktop_approval,
)
from runtime.gptpro_desktop.contract import (
    DESKTOP_OBSERVATION_CONTRACT,
    build_handoff_plan,
    deterministic_response_wrapper,
    validate_response_observation,
    validate_submission_observation,
)
from runtime.gptpro_desktop.binding import (
    DESKTOP_APP_BINDING_CONTRACT,
    inspect_desktop_app_binding,
)
from runtime.gptpro_desktop.state import DesktopStateError, write_private_json


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class DesktopWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="gptpro-desktop-workflow-")
        self.root = Path(self.temporary.name).resolve()
        self.handoff = self.root / "handoff"
        self.handoff.mkdir()
        self.prompt = b"# Review\n\nInspect `src/main.py`.\n"
        (self.handoff / "prompt.md").write_bytes(self.prompt)
        self.connector = {
            "type": "secure-mcp-tunnel",
            "tunnel_profile_alias": "personal-read-only",
            "tunnel_profile_sha256": sha256(b"profile"),
            "app_name": "gptpro",
            "workspace_label": "Personal",
        }
        self.manifest = {
            "schema_version": 4,
            "package_id": "desktop-fixture",
            "mode": "review",
            "task": "Review the selected code.",
            "requested_model": "ChatGPT Pro",
            "transport": {
                "requested": "mcp-research",
                "resolved": "mcp-research",
                "outbound_artifacts": [
                    {
                        "role": "message",
                        "artifact": "prompt",
                        "bytes": len(self.prompt),
                        "sha256": sha256(self.prompt),
                    }
                ],
            },
            "delivery": {"channel": "desktop-ui", "approval_required": True},
            "connector": dict(self.connector),
            "artifacts": {"prompt": "prompt.md"},
            "files": [{"path": "src/main.py", "size": 12, "sha256": sha256(b"source")}],
            "git": {"dirty_paths": []},
            "totals": {"included_files": 1, "included_bytes": 12},
            "limits": {"max_file_bytes": 1024},
            "mcp_disclosure": {
                "limits": {
                    "max_tool_calls": 20,
                    "max_bytes_returned": 65536,
                    "max_search_matches": 50,
                }
            },
            "supplements": [],
        }
        self.verified = {
            "manifest": self.manifest,
            "state": {
                "phase": "approved",
                "approval": {"approval_source": "exact-package"},
            },
            "outbound_artifacts": self.manifest["transport"]["outbound_artifacts"],
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def approval(self, *, allow_dirty: bool = False) -> dict:
        return build_desktop_approval(
            name="personal-default",
            approved_by="test-user",
            source={
                "package_id": "source-package",
                "manifest_sha256": sha256(b"manifest"),
                "approval_event_sha256": sha256(b"approval"),
            },
            connector=self.connector,
            requested_model="ChatGPT Pro",
            allowed_modes=["review", "architecture"],
            path_patterns=["src/**"],
            allow_dirty=allow_dirty,
            limits={
                "max_task_bytes": 4096,
                "max_files": 10,
                "max_bytes": 65536,
                "max_file_bytes": 4096,
                "mcp_limits": {
                    "max_tool_calls": 40,
                    "max_bytes_returned": 131072,
                    "max_search_matches": 100,
                },
            },
            valid_for_seconds=3600,
        )

    def submission(self, plan: dict, *, status: str = "sent") -> dict:
        return {
            "contract": DESKTOP_OBSERVATION_CONTRACT,
            "stage": "submission",
            "package_id": plan["package_id"],
            "request_nonce": plan["request_nonce"],
            "status": status,
            "send_attempts": 1 if status != "not_sent" else 0,
            "application": "ChatGPT",
            "delivery_channel": "desktop-ui",
            "chat_surface": "general-chat",
            "chat_mode_visible": True,
            "pro_visible": True,
            "new_chat_empty_before_send": True,
            "composer_sha256": plan["outbound"]["sha256"],
            "visible_user_turn_sha256": plan["outbound"]["sha256"],
            "observed_model": plan["requested_model"],
            "observed_app_name": plan["app_name"],
            "observed_workspace_label": plan["workspace_label"],
        }

    def test_handoff_is_desktop_schema4_and_hash_bound(self) -> None:
        plan = build_handoff_plan(handoff_dir=self.handoff, verified=self.verified)
        self.assertEqual("desktop-ui", plan["delivery_channel"])
        self.assertEqual("general-chat", plan["chat_surface"])
        self.assertEqual(sha256(self.prompt), plan["outbound"]["sha256"])
        self.assertEqual(1, plan["send_attempt_limit"])
        self.assertFalse(plan["private_desktop_api_used"])

    def test_app_binding_is_verified_without_exposing_raw_app_id(self) -> None:
        state_root = self.root / "desktop-state"
        plugin_root = state_root / "companion" / "gptpro-desktop-app"
        app_id = "app-private-fixture-id"
        plugin = {"name": "gptpro-desktop-app", "apps": "./.app.json"}
        app_manifest = {
            "apps": {"gpt-pro-collaborator": {"id": app_id, "category": "Developer Tools"}}
        }
        write_private_json(plugin_root / ".codex-plugin" / "plugin.json", plugin)
        write_private_json(plugin_root / ".app.json", app_manifest)
        binding = {
            "schema": DESKTOP_APP_BINDING_CONTRACT,
            "recorded_at": "2026-08-30T00:00:00Z",
            "app_key": "gpt-pro-collaborator",
            "app_id_sha256": sha256(app_id.encode("utf-8")),
            "plugin_root": str(plugin_root),
            "plugin_manifest_sha256": sha256(
                (json.dumps(plugin, sort_keys=True, indent=2) + "\n").encode("utf-8")
            ),
            "raw_app_id_stored_only_in_private_app_manifest": True,
        }
        write_private_json(state_root / "companion" / "app-binding.json", binding)
        observed = inspect_desktop_app_binding(state_root)
        self.assertEqual("verified", observed["status"])
        self.assertNotIn(app_id, json.dumps(observed, sort_keys=True))

        app_manifest["apps"]["gpt-pro-collaborator"]["id"] = "changed"
        write_private_json(plugin_root / ".app.json", app_manifest)
        self.assertEqual("invalid", inspect_desktop_app_binding(state_root)["status"])

    def test_submission_requires_exact_visible_turn_and_never_auto_resends(self) -> None:
        plan = build_handoff_plan(handoff_dir=self.handoff, verified=self.verified)
        sent = validate_submission_observation(plan, self.submission(plan))
        self.assertFalse(sent["automatic_retry_allowed"])
        ambiguous = validate_submission_observation(
            plan, self.submission(plan, status="ambiguous")
        )
        self.assertFalse(ambiguous["resend_allowed"])
        invalid = self.submission(plan)
        invalid["send_attempts"] = 2
        with self.assertRaises(DesktopStateError) as raised:
            validate_submission_observation(plan, invalid)
        self.assertEqual("DESKTOP_SEND_LIMIT_VIOLATION", raised.exception.code)

    def test_response_is_next_complete_turn_and_wrapped_deterministically(self) -> None:
        plan = build_handoff_plan(handoff_dir=self.handoff, verified=self.verified)
        text = "검토 결과입니다.\n"
        response = {
            "contract": DESKTOP_OBSERVATION_CONTRACT,
            "stage": "response",
            "package_id": plan["package_id"],
            "request_nonce": plan["request_nonce"],
            "status": "complete",
            "visible_user_turn_sha256": plan["outbound"]["sha256"],
            "generation_complete": True,
            "stop_button_visible": False,
            "error_card_visible": False,
            "assistant_turn_ordinal": 1,
            "copy_action_confirmed": True,
            "captured_text": text,
            "captured_text_sha256": sha256(text.encode("utf-8")),
        }
        captured = validate_response_observation(
            plan, response, expected_request_nonce=plan["request_nonce"]
        )
        wrapper = deterministic_response_wrapper(
            package_id=plan["package_id"], captured_text=captured["captured_text"]
        )
        self.assertEqual(
            b"BEGIN_GPTPRO_RESPONSE:desktop-fixture\n"
            + text.encode("utf-8")
            + b"END_GPTPRO_RESPONSE:desktop-fixture\n",
            wrapper,
        )

    def test_pending_response_cannot_authorize_resend(self) -> None:
        plan = build_handoff_plan(handoff_dir=self.handoff, verified=self.verified)
        pending = {
            "contract": DESKTOP_OBSERVATION_CONTRACT,
            "stage": "response",
            "package_id": plan["package_id"],
            "request_nonce": plan["request_nonce"],
            "status": "pending",
            "visible_user_turn_sha256": plan["outbound"]["sha256"],
        }
        result = validate_response_observation(
            plan, pending, expected_request_nonce=plan["request_nonce"]
        )
        self.assertTrue(result["collection_retry_allowed"])
        self.assertFalse(result["resend_allowed"])

    def test_machine_global_approval_is_not_repository_bound(self) -> None:
        profile = self.approval()
        first = match_desktop_approval(profile, manifest=self.manifest)
        second_manifest = json.loads(json.dumps(self.manifest))
        second_manifest["repository"] = {"root_identity_sha256": sha256(b"another-repo")}
        second = match_desktop_approval(profile, manifest=second_manifest)
        self.assertEqual("all-local-git", first["repository_scope"])
        self.assertEqual(first["profile_sha256"], second["profile_sha256"])

    def test_selected_untracked_file_is_never_covered_by_standing_approval(self) -> None:
        profile = self.approval(allow_dirty=True)
        manifest = json.loads(json.dumps(self.manifest))
        manifest["files"] = [{"path": "src/new.py", "size": 4, "sha256": sha256(b"new\n")}]
        manifest["git"]["dirty_paths"] = [{"status": "??", "path": "src/new.py"}]
        with self.assertRaises(DesktopStateError) as raised:
            match_desktop_approval(profile, manifest=manifest)
        self.assertEqual("DESKTOP_APPROVAL_UNTRACKED_FILE", raised.exception.code)

    def test_approval_store_is_owner_only_and_revocation_is_persistent(self) -> None:
        state_root = self.root / "state"
        path = store_desktop_approval(self.approval(), state_root=state_root)
        self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))
        self.assertEqual(0o700, stat.S_IMODE(path.parent.stat().st_mode))
        self.assertEqual("personal-default", load_desktop_approval("personal-default", state_root=state_root)["name"])
        revoked = revoke_desktop_approval("personal-default", state_root=state_root)
        self.assertIsNotNone(revoked["revoked_at"])
        with self.assertRaises(DesktopStateError) as raised:
            match_desktop_approval(revoked, manifest=self.manifest)
        self.assertEqual("DESKTOP_APPROVAL_REVOKED", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
