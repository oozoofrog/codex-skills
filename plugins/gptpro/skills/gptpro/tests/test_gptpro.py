from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(SKILL_ROOT))

from runtime.gptpro_runtime import approvals, controller, package  # noqa: E402
from runtime.gptpro_runtime.approvals import ApprovalError  # noqa: E402
from runtime.gptpro_runtime.package import PackageError, SelectedFile  # noqa: E402
from runtime.gptpro_runtime.receipts import ReceiptError, load_receipt  # noqa: E402
from runtime.gptpro_runtime.schema import (  # noqa: E402
    CHAT_HISTORY_MODE,
    CONTEXT_TRANSPORT,
    DEFAULT_MODEL_ID,
    DELIVERY_CHANNEL,
    INLINE_FORMAT,
    MAX_OUTBOUND_BYTES,
)
from runtime.gptpro_runtime.state import read_json, sha256_bytes, sha256_file, write_json  # noqa: E402


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout.strip()


class PackageCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        os.chmod(self.root, 0o700)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "Test")
        git(self.repo, "config", "user.email", "test@example.com")
        (self.repo / "README.md").write_text("# 프로젝트\n\nneedle line\n", encoding="utf-8")
        (self.repo / "src").mkdir()
        (self.repo / "src" / "main.py").write_text("print('hello')", encoding="utf-8")
        git(self.repo, "add", "README.md", "src/main.py")
        git(self.repo, "commit", "-qm", "initial")
        self.state = self.root / "state"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def prepare(self, **overrides):
        values = {
            "repo_value": self.repo,
            "mode": "review",
            "task": "현재 변경을 검토해주세요.\n\n```python\nprint('검토')\n```",
            "includes": ["README.md", "src/**"],
            "file_list": None,
            "excludes": [],
            "supplements": [],
            "allow_untracked": False,
            "model_intent": DEFAULT_MODEL_ID,
            "thinking_effort": None,
            "root": self.state,
        }
        values.update(overrides)
        return package.prepare_package(**values)

    def test_prepare_schema6_builds_exact_inline_artifacts(self) -> None:
        prepared = self.prepare()
        handoff = Path(prepared["handoff_dir"])
        verified = package.verify_package(handoff)
        manifest = verified["manifest"]
        self.assertEqual(6, manifest["schema_version"])
        self.assertEqual(CONTEXT_TRANSPORT, manifest["context_transport"])
        self.assertEqual("desktop-electron", manifest["delivery"]["channel"])
        self.assertEqual(CHAT_HISTORY_MODE, manifest["delivery"]["chat_history_mode"])
        self.assertEqual(INLINE_FORMAT, manifest["disclosure"]["inline_format"])
        self.assertEqual(MAX_OUTBOUND_BYTES, manifest["disclosure"]["max_outbound_bytes"])
        self.assertEqual(
            sha256_bytes("현재 변경을 검토해주세요.\n\n```python\nprint('검토')\n```".encode("utf-8")),
            manifest["task_sha256"],
        )
        self.assertEqual(["README.md", "src/main.py"], [item["path"] for item in manifest["files"]])
        for name in ("prompt.md", "system-prompt.md", "outbound.md", "manifest.json"):
            self.assertEqual(0o600, (handoff / name).stat().st_mode & 0o777)
        self.assertFalse((handoff / "context.zip").exists())
        outbound = (handoff / "outbound.md").read_bytes()
        self.assertEqual(prepared["outbound_sha256"], sha256_bytes(outbound))
        self.assertEqual(prepared["outbound_bytes"], len(outbound))
        self.assertIn("현재 변경을 검토해주세요.".encode(), outbound)
        self.assertIn((self.repo / "README.md").read_bytes(), outbound)
        self.assertIn((self.repo / "src/main.py").read_bytes(), outbound)
        self.assertIn(b'"kind":"repository_file"', outbound)
        self.assertNotIn(b"local_function", outbound)
        self.assertEqual(0o700, handoff.stat().st_mode & 0o777)

    def test_inline_preserves_raw_newlines_and_orders_file_diff_supplement(self) -> None:
        (self.repo / "README.md").write_bytes("첫 줄\r\n둘째 줄\n".encode("utf-8"))
        supplement = self.root / "참고.md"
        supplement.write_bytes("# 참고\n\n```swift\nlet 값 = 1\n```".encode("utf-8"))
        prepared = self.prepare(supplements=[f"design={supplement}"])
        handoff = Path(prepared["handoff_dir"])
        outbound = (handoff / "outbound.md").read_bytes()
        raw_readme = (self.repo / "README.md").read_bytes()
        raw_source = (self.repo / "src/main.py").read_bytes()
        raw_supplement = supplement.read_bytes()
        self.assertIn(raw_readme, outbound)
        self.assertIn(raw_source, outbound)
        self.assertIn(raw_supplement, outbound)
        self.assertLess(outbound.index(b'"path":"README.md"'), outbound.index(b'"path":"src/main.py"'))
        self.assertLess(outbound.index(b'"kind":"repository_file"'), outbound.index(b'"kind":"git_diff"'))
        self.assertLess(outbound.index(b'"kind":"git_diff"'), outbound.index(b'"kind":"supplement"'))
        package.verify_package(handoff)

    def test_outbound_rebuild_detects_tampering(self) -> None:
        prepared = self.prepare()
        handoff = Path(prepared["handoff_dir"])
        outbound = handoff / "outbound.md"
        outbound.write_bytes(outbound.read_bytes() + b"tampered")
        os.chmod(outbound, 0o600)
        manifest = read_json(handoff / "manifest.json")
        manifest["hashes"]["outbound_sha256"] = sha256_file(outbound)
        manifest["disclosure"]["outbound_bytes"] = outbound.stat().st_size
        write_json(handoff / "manifest.json", manifest)
        with self.assertRaises(PackageError) as raised:
            package.verify_package(handoff)
        self.assertEqual("PACKAGE_TAMPERED", raised.exception.code)

    def test_inline_limit_accepts_exactly_256k_and_rejects_one_more_byte(self) -> None:
        package_id = "20260902T000000Z-review-deadbeef"
        prompt = b"task\n"
        size = MAX_OUTBOUND_BYTES - 1024
        while True:
            data = b"x" * size
            item = SelectedFile("large.txt", data, sha256_bytes(data), True)
            outbound = package.build_outbound(
                package_id=package_id,
                prompt=prompt,
                files=[item],
                diff=b"",
                supplements=[],
            )
            delta = MAX_OUTBOUND_BYTES - len(outbound)
            if delta == 0:
                break
            size += delta
        self.assertEqual(MAX_OUTBOUND_BYTES, len(outbound))
        larger = b"x" * (size + 1)
        with self.assertRaises(PackageError) as raised:
            package.build_outbound(
                package_id=package_id,
                prompt=prompt,
                files=[SelectedFile("large.txt", larger, sha256_bytes(larger), True)],
                diff=b"",
                supplements=[],
            )
        self.assertEqual("INLINE_CONTEXT_LIMIT_EXCEEDED", raised.exception.code)

    def test_inline_boundary_collision_fails_before_package_directory(self) -> None:
        fixed_id = "20260902T000000Z-review-deadbeef"
        boundary = package.inline_boundary(fixed_id).decode("ascii")
        fixed_now = package.datetime(2026, 9, 2, tzinfo=package.timezone.utc)
        before = list(self.state.rglob("*")) if self.state.exists() else []
        with mock.patch.object(package, "datetime") as fake_datetime:
            fake_datetime.now.return_value = fixed_now
            with (
                mock.patch.object(package.os, "urandom", return_value=bytes.fromhex("deadbeef")),
                self.assertRaises(PackageError) as raised,
            ):
                self.prepare(task=f"review {boundary}")
        self.assertEqual("INLINE_BOUNDARY_COLLISION", raised.exception.code)
        after = list(self.state.rglob("*")) if self.state.exists() else []
        self.assertEqual(before, after)

    def test_prepare_requires_directed_selection_and_exact_literal(self) -> None:
        with self.assertRaises(PackageError) as raised:
            self.prepare(includes=[])
        self.assertEqual("SELECTION_REQUIRED", raised.exception.code)
        nested = self.repo / "docs"
        nested.mkdir()
        (nested / "README.md").write_text("nested\n", encoding="utf-8")
        git(self.repo, "add", "docs/README.md")
        git(self.repo, "commit", "-qm", "nested")
        manifest = package.verify_package(Path(self.prepare(includes=["README.md"])["handoff_dir"]))["manifest"]
        self.assertEqual(["README.md"], [item["path"] for item in manifest["files"]])

    def test_secret_unsafe_path_untracked_and_supplement_policy(self) -> None:
        (self.repo / "notes.md").write_text("untracked\n", encoding="utf-8")
        with self.assertRaises(PackageError) as untracked:
            self.prepare(includes=["notes.md"])
        self.assertEqual("SELECTION_EMPTY", untracked.exception.code)
        manifest = package.verify_package(Path(self.prepare(includes=["notes.md"], allow_untracked=True)["handoff_dir"]))["manifest"]
        self.assertFalse(manifest["files"][0]["tracked"])
        (self.repo / "src" / "main.py").write_text("api_key='abcdefghijklmnopqrstuv'\n", encoding="utf-8")
        with self.assertRaises(PackageError) as secret:
            self.prepare()
        self.assertEqual("SECRET_DETECTED", secret.exception.code)
        (self.repo / "src" / "main.py").write_text("safe\n", encoding="utf-8")
        (self.repo / ".env").write_text("SAFE=placeholder\n", encoding="utf-8")
        with self.assertRaises(PackageError) as unsafe:
            self.prepare(includes=[".env"], allow_untracked=True)
        self.assertEqual("SECRET_PATH_REJECTED", unsafe.exception.code)
        relative = self.root / "relative.txt"
        relative.write_text("safe\n", encoding="utf-8")
        with self.assertRaises(PackageError) as supplement:
            self.prepare(supplements=["note=relative.txt"])
        self.assertEqual("SUPPLEMENT_INVALID", supplement.exception.code)

    def test_package_symlink_and_permissions_fail_closed(self) -> None:
        fresh = Path(self.prepare()["handoff_dir"])
        link = self.root / "handoff-link"
        link.symlink_to(fresh, target_is_directory=True)
        with self.assertRaises(PackageError) as linked:
            package.verify_package(link)
        self.assertEqual("PACKAGE_UNSAFE", linked.exception.code)
        os.chmod(fresh / "outbound.md", 0o644)
        with self.assertRaises(PackageError) as permissions:
            package.verify_package(fresh)
        self.assertEqual("PACKAGE_UNSAFE", permissions.exception.code)

    def test_exact_approval_v2_binds_inline_model_and_system_prompt(self) -> None:
        prepared = self.prepare(includes=["README.md"])
        handoff = Path(prepared["handoff_dir"])
        result = approvals.approve_exact(
            handoff,
            confirm_transmission=True,
            confirm_disclosure=True,
            expires_minutes=60,
        )
        approval = result["approval"]
        self.assertEqual("exact-package-v2", approval["type"])
        self.assertEqual(prepared["outbound_sha256"], approval["outbound_sha256"])
        self.assertEqual(DEFAULT_MODEL_ID, approval["model_intent"]["requested"])
        self.assertEqual(INLINE_FORMAT, approval["inline_format"])
        approvals.verify_active_approval(handoff)
        manifest = read_json(handoff / "manifest.json")
        manifest["hashes"]["system_prompt_sha256"] = "0" * 64
        write_json(handoff / "manifest.json", manifest)
        with self.assertRaises((PackageError, ApprovalError)):
            approvals.verify_active_approval(handoff)

    def test_standing_v4_matches_only_bounded_scope_and_v3_is_ignored(self) -> None:
        first = Path(self.prepare(includes=["src/**"])["handoff_dir"])
        created = approvals.create_standing(
            first,
            confirm_transmission=True,
            confirm_disclosure=True,
            expires_hours=24,
            modes=["review"],
            root=self.state,
        )
        self.assertTrue(created["approval_id"].startswith("desktop-v4-"))
        second = Path(self.prepare(includes=["src/**"])["handoff_dir"])
        applied = approvals.apply_standing(second, approval_id=created["approval_id"], root=self.state)
        self.assertTrue(applied["matched"])
        outside = Path(self.prepare(includes=["README.md"])["handoff_dir"])
        with self.assertRaises(ApprovalError) as raised:
            approvals.apply_standing(outside, approval_id=created["approval_id"], root=self.state)
        self.assertEqual("APPROVAL_REQUIRED", raised.exception.code)
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "README.md").write_text("nested\n", encoding="utf-8")
        git(self.repo, "add", "docs/README.md")
        git(self.repo, "commit", "-qm", "nested readme")
        nested = Path(self.prepare(includes=["docs/README.md"])["handoff_dir"])
        with self.assertRaises(ApprovalError) as nested_error:
            approvals.apply_standing(nested, approval_id=created["approval_id"], root=self.state)
        self.assertEqual("APPROVAL_REQUIRED", nested_error.exception.code)
        old = approvals.approvals_root(self.state) / "desktop-v3-old.json"
        write_json(old, {"schema": "gptpro-standing-approval-v3"})
        self.assertNotIn(old, approvals.standing_files(self.state))

    def test_schema5_cannot_be_approved_as_schema6(self) -> None:
        prepared = self.prepare()
        handoff = Path(prepared["handoff_dir"])
        manifest = read_json(handoff / "manifest.json")
        manifest["schema_version"] = 5
        write_json(handoff / "manifest.json", manifest)
        with self.assertRaises(PackageError) as raised:
            approvals.approve_exact(handoff, confirm_transmission=True, confirm_disclosure=True)
        self.assertEqual("SCHEMA_VERSION_UNSUPPORTED", raised.exception.code)

    def test_exact_approval_rejects_bound_outbound_byte_tampering(self) -> None:
        handoff = Path(self.prepare()["handoff_dir"])
        approvals.approve_exact(
            handoff,
            confirm_transmission=True,
            confirm_disclosure=True,
            expires_minutes=60,
        )
        state = read_json(handoff / "state.json")
        state["approval"]["outbound_bytes"] -= 1
        write_json(handoff / "state.json", state)
        with self.assertRaises(ApprovalError) as raised:
            approvals.verify_active_approval(handoff)
        self.assertEqual("APPROVAL_INVALID", raised.exception.code)

    def test_state_revision_compare_and_swap_rejects_stale_writer(self) -> None:
        handoff = Path(self.prepare()["handoff_dir"])
        package_id = read_json(handoff / "manifest.json")["package_id"]
        first = approvals.load_state(handoff, package_id)
        stale = approvals.load_state(handoff, package_id)
        first["phase"] = "approved"
        approvals.save_state(handoff, first)
        stale["phase"] = "submitted"
        with self.assertRaises(ApprovalError) as raised:
            approvals.save_state(handoff, stale)
        self.assertEqual("STATE_REVISION_CONFLICT", raised.exception.code)
        self.assertEqual("approved", approvals.load_state(handoff, package_id)["phase"])


class RecordingInput(io.StringIO):
    def close(self) -> None:
        self.final_value = super().getvalue()
        super().close()

    def getvalue(self) -> str:
        return self.final_value if self.closed else super().getvalue()


class FakeProcess:
    def __init__(self, lines: list[dict], *, return_code: int = 0, error: dict | None = None) -> None:
        self.lines = list(lines)
        self.stdout = io.StringIO("".join(json.dumps(item) + "\n" for item in lines))
        self.stdin = RecordingInput()
        self.stderr = io.StringIO(json.dumps({"ok": False, "error": error}) + "\n" if error else "")
        self.return_code = return_code
        self.killed = False

    def bind(self, command, **_kwargs):
        lines = list(self.lines)
        if any(item.get("type") == "submitted" for item in lines) and not any(item.get("type") == "dispatch_ready" for item in lines):
            prompt = Path(command[command.index("--prompt-file") + 1])
            system = Path(command[command.index("--system-prompt-file") + 1])
            state_path = Path(command[command.index("--state-file") + 1]) if "--state-file" in command else None
            effort = command[command.index("--thinking-effort") + 1] if "--thinking-effort" in command else None
            ready = {
                "type": "dispatch_ready",
                "dispatch_token": "test-dispatch-token",
                "prompt_sha256": sha256_file(prompt),
                "prompt_bytes": prompt.stat().st_size,
                "system_prompt_sha256": sha256_file(system),
                "state_sha256": sha256_file(state_path) if state_path else None,
                "backend_model_id": command[command.index("--model") + 1],
                "thinking_effort": effort,
                "history_mode": command[command.index("--history-mode") + 1],
                "message_id": command[command.index("--message-id") + 1],
            }
            lines.insert(0, ready)
        self.stdout = io.StringIO("".join(json.dumps(item) + "\n" for item in lines))
        return self

    def wait(self, timeout=None):
        return self.return_code

    def poll(self):
        return self.return_code

    def terminate(self):
        return None

    def kill(self):
        self.killed = True
        if self.return_code is None:
            self.return_code = -9


class ControllerCase(PackageCase):
    def approved(self) -> tuple[dict, Path]:
        prepared = self.prepare(includes=["README.md"])
        handoff = Path(prepared["handoff_dir"])
        approvals.approve_exact(handoff, confirm_transmission=True, confirm_disclosure=True, expires_minutes=60)
        return prepared, handoff

    @staticmethod
    def catalog() -> dict:
        return {
            "models": [
                {
                    "id": DEFAULT_MODEL_ID,
                    "name": "GPT-5.6 Pro",
                    "thinking_efforts": ["high"],
                    "capabilities": {"server_tools": True},
                }
            ]
        }

    def run_fake(self, handoff: Path, fake: FakeProcess):
        with (
            mock.patch.object(controller, "desktop_models", return_value=self.catalog()),
            mock.patch.object(controller, "node_binary", return_value=Path("/usr/bin/node")),
            mock.patch.object(controller, "node_entrypoint", return_value=Path("/tmp/chatgpt-desktop.js")),
            mock.patch.object(controller.subprocess, "Popen", side_effect=fake.bind) as popen,
        ):
            result = controller.run_consultation(SKILL_ROOT, handoff)
        return result, popen

    def test_model_resolution_is_exact_and_does_not_require_tools(self) -> None:
        resolved = controller.resolve_model(self.catalog(), DEFAULT_MODEL_ID, None)
        self.assertEqual(DEFAULT_MODEL_ID, resolved["id"])
        with self.assertRaises(controller.ControllerError) as wrong:
            controller.resolve_model(self.catalog(), "GPT-5.6 Pro", None)
        self.assertEqual("MODEL_NOT_FOUND", wrong.exception.code)
        with self.assertRaises(controller.ControllerError) as effort:
            controller.resolve_model(self.catalog(), DEFAULT_MODEL_ID, "unsupported")
        self.assertEqual("MODEL_EFFORT_UNSUPPORTED", effort.exception.code)

    def test_completed_response_imports_without_tool_evidence_and_binds_outbound(self) -> None:
        prepared, handoff = self.approved()
        fake = FakeProcess(
            [
                {"type": "submitted", "request_id": "request-1"},
                {
                    "type": "complete",
                    "text": "README.md의 needle을 확인했습니다.",
                    "conversation_id": "conversation",
                    "parent_message_id": "message",
                    "assistant_message_id": "message",
                    "tool_routes": 0,
                    "done": True,
                    "completion_source": "signed-stream-handoff-v1",
                    "stream_handoff_topic_sha256": "a" * 64,
                    "current_branch_proof": "authenticated-exact-message-readback-v1",
                    "current_branch_proof_required": True,
                    "tool_route_candidate_observed": True,
                    "pre_handoff_assistant_observed": False,
                    "signed_delta_continuation_observed": False,
                    "signed_assistant_evidence": True,
                    "sources": [],
                },
            ]
        )
        result, popen = self.run_fake(handoff, fake)
        self.assertEqual("imported", result["phase"])
        self.assertEqual(0, result["tool_routes"])
        self.assertEqual(prepared["outbound_sha256"], result["outbound_sha256"])
        command = popen.call_args.args[0]
        self.assertEqual(
            (handoff / "outbound.md").resolve(),
            Path(command[command.index("--prompt-file") + 1]).resolve(),
        )
        self.assertNotIn("--tools-file", command)
        self.assertNotIn("--protocol", command)
        receipt = load_receipt(handoff / "receipt.json", package_id=prepared["package_id"])
        dispatched = next(item for item in receipt["events"] if item["event"] == "submission_dispatched")
        self.assertEqual(prepared["outbound_sha256"], dispatched["outbound_sha256"])
        self.assertEqual(prepared["outbound_bytes"], dispatched["outbound_bytes"])
        self.assertTrue((handoff / "responses" / "response.raw.md").is_file())
        self.assertTrue((handoff / "responses" / "response.md").is_file())
        dispatching = next(item for item in receipt["events"] if item["event"] == "submission_dispatching")
        self.assertEqual(prepared["outbound_sha256"], dispatching["prompt_sha256"])
        self.assertLess(dispatching["sequence"], dispatched["sequence"])
        captured = next(item for item in receipt["events"] if item["event"] == "response_captured")
        self.assertEqual("signed-stream-handoff-v1", captured["completion_source"])
        self.assertEqual("a" * 64, captured["stream_handoff_topic_sha256"])
        self.assertEqual("authenticated-exact-message-readback-v1", captured["current_branch_proof"])
        self.assertTrue(captured["current_branch_proof_required"])
        self.assertTrue(captured["tool_route_candidate_observed"])
        self.assertTrue(captured["signed_assistant_evidence"])
        self.assertTrue(fake.stdin.getvalue().endswith("\n"))
        self.assertTrue(fake.stdin.closed)

    def test_child_stderr_is_drained_before_stdout_eof(self) -> None:
        _, handoff = self.approved()
        read_started = controller.threading.Event()

        class CoordinatedStderr(io.StringIO):
            def read(self, *args, **kwargs):
                read_started.set()
                return super().read(*args, **kwargs)

        class ExitAfterStderrDrain:
            def __iter__(self):
                return self

            def __next__(self):
                if not read_started.wait(1):
                    raise AssertionError("stderr was not drained concurrently")
                raise StopIteration

        class StderrProcess(FakeProcess):
            def bind(self, command, **kwargs):
                super().bind(command, **kwargs)
                self.stdout = ExitAfterStderrDrain()
                self.stderr = CoordinatedStderr(json.dumps({
                    "ok": False,
                    "error": {"code": "CHILD_TERMINAL_ERROR", "message": "terminal error"},
                }) + "\n")
                return self

        fake = StderrProcess([], return_code=3)
        with (
            mock.patch.object(controller, "desktop_models", return_value=self.catalog()),
            mock.patch.object(controller, "node_binary", return_value=Path("/usr/bin/node")),
            mock.patch.object(controller, "node_entrypoint", return_value=Path("/tmp/chatgpt-desktop.js")),
            mock.patch.object(controller.subprocess, "Popen", side_effect=fake.bind),
            self.assertRaises(controller.ControllerError) as raised,
        ):
            controller.run_consultation(SKILL_ROOT, handoff)
        self.assertEqual("CHILD_TERMINAL_ERROR", raised.exception.code)

    def test_signed_stream_handoff_progress_is_accepted(self) -> None:
        _, handoff = self.approved()
        fake = FakeProcess([
            {"type": "submitted", "request_id": "request-1"},
            {"type": "progress", "stage": "stream_handoff"},
            {"type": "progress", "stage": "current_branch_proof"},
            {"type": "complete", "text": "완료", "conversation_id": "c", "parent_message_id": "m", "assistant_message_id": "m", "tool_routes": 0, "done": True, "completion_source": "signed-stream-handoff-v1", "stream_handoff_topic_sha256": "a" * 64, "current_branch_proof": "authenticated-exact-message-readback-v1", "current_branch_proof_required": True, "tool_route_candidate_observed": False, "pre_handoff_assistant_observed": True, "signed_delta_continuation_observed": False, "signed_assistant_evidence": True},
        ])
        result, _ = self.run_fake(handoff, fake)
        self.assertEqual("imported", result["phase"])
        self.assertTrue(result["current_branch_proof_required"])
        self.assertTrue(result["pre_handoff_assistant_observed"])

    def test_thinking_effort_is_forwarded_to_the_exact_runtime_model(self) -> None:
        prepared = self.prepare(includes=["README.md"], thinking_effort="high")
        handoff = Path(prepared["handoff_dir"])
        approvals.approve_exact(handoff, confirm_transmission=True, confirm_disclosure=True, expires_minutes=60)
        fake = FakeProcess([
            {"type": "submitted", "request_id": "request-1"},
            {"type": "complete", "text": "완료", "conversation_id": "c", "parent_message_id": "m", "assistant_message_id": "m", "tool_routes": 0, "done": True, "completion_source": "signed-stream-handoff-v1", "stream_handoff_topic_sha256": "a" * 64, "current_branch_proof_required": False, "tool_route_candidate_observed": False, "pre_handoff_assistant_observed": False, "signed_delta_continuation_observed": False, "signed_assistant_evidence": True},
        ])
        _, popen = self.run_fake(handoff, fake)
        command = popen.call_args.args[0]
        self.assertEqual("high", command[command.index("--thinking-effort") + 1])

    def test_runtime_byte_mismatch_fails_before_durable_dispatch(self) -> None:
        _, handoff = self.approved()
        fake = FakeProcess([{"type": "dispatch_ready", "prompt_sha256": "0" * 64}])
        with (
            mock.patch.object(controller, "desktop_models", return_value=self.catalog()),
            mock.patch.object(controller, "node_binary", return_value=Path("/usr/bin/node")),
            mock.patch.object(controller, "node_entrypoint", return_value=Path("/tmp/chatgpt-desktop.js")),
            mock.patch.object(controller.subprocess, "Popen", side_effect=fake.bind),
            self.assertRaises(controller.ControllerError) as raised,
        ):
            controller.run_consultation(SKILL_ROOT, handoff)
        self.assertEqual("DISPATCH_ARTIFACT_MISMATCH", raised.exception.code)
        self.assertEqual("approved", read_json(handoff / "state.json")["phase"])
        self.assertNotIn("submission_dispatching", [item["event"] for item in load_receipt(handoff / "receipt.json")["events"]])

    def test_dispatch_evidence_write_failure_never_authorizes_post(self) -> None:
        _, handoff = self.approved()
        fake = FakeProcess([{"type": "submitted", "request_id": "must-not-send"}])
        with (
            mock.patch.object(controller, "desktop_models", return_value=self.catalog()),
            mock.patch.object(controller, "node_binary", return_value=Path("/usr/bin/node")),
            mock.patch.object(controller, "node_entrypoint", return_value=Path("/tmp/chatgpt-desktop.js")),
            mock.patch.object(controller.subprocess, "Popen", side_effect=fake.bind),
            mock.patch.object(
                controller,
                "append_receipt",
                side_effect=ReceiptError("RECEIPT_WRITE_FAILED", "receipt unavailable"),
            ),
            self.assertRaises(controller.ControllerError) as raised,
        ):
            controller.run_consultation(SKILL_ROOT, handoff)
        self.assertEqual("DISPATCH_EVIDENCE_WRITE_FAILED", raised.exception.code)
        self.assertEqual("", fake.stdin.getvalue())
        self.assertEqual("dispatching", read_json(handoff / "state.json")["phase"])
        with self.assertRaises(controller.ControllerError) as second:
            controller.run_consultation(SKILL_ROOT, handoff)
        self.assertEqual("SUBMISSION_STATE_UNSAFE", second.exception.code)

    def test_durable_dispatch_receipt_blocks_resend_even_if_state_is_stale(self) -> None:
        _, handoff = self.approved()
        manifest = read_json(handoff / "manifest.json")
        from runtime.gptpro_runtime.receipts import append_receipt
        append_receipt(
            handoff / "receipt.json",
            manifest["package_id"],
            "submission_dispatching",
            {"turn": 1},
        )
        with self.assertRaises(controller.ControllerError) as raised:
            controller.run_consultation(SKILL_ROOT, handoff)
        self.assertEqual("SUBMISSION_STATE_UNSAFE", raised.exception.code)

    def test_post_dispatch_ambiguity_is_terminal_and_never_retried(self) -> None:
        _, handoff = self.approved()
        fake = FakeProcess(
            [{"type": "submitted", "request_id": "request-1"}],
            return_code=3,
            error={
                "code": "SUBMISSION_AMBIGUOUS",
                "message": "ambiguous",
                "retryable": False,
                "recovery": "inspect",
                "submission_state": "ambiguous",
            },
        )
        with (
            mock.patch.object(controller, "desktop_models", return_value=self.catalog()),
            mock.patch.object(controller, "node_binary", return_value=Path("/usr/bin/node")),
            mock.patch.object(controller, "node_entrypoint", return_value=Path("/tmp/chatgpt-desktop.js")),
            mock.patch.object(controller.subprocess, "Popen", side_effect=fake.bind),
            self.assertRaises(controller.ControllerError) as raised,
        ):
            controller.run_consultation(SKILL_ROOT, handoff)
        self.assertEqual("SUBMISSION_AMBIGUOUS", raised.exception.code)
        self.assertEqual("submission_ambiguous", read_json(handoff / "state.json")["phase"])
        with self.assertRaises(controller.ControllerError) as second:
            controller.run_consultation(SKILL_ROOT, handoff)
        self.assertEqual("SUBMISSION_STATE_UNSAFE", second.exception.code)

    def test_collect_response_recovers_exact_submitted_package_without_post(self) -> None:
        prepared, handoff = self.approved()
        fake = FakeProcess(
            [{"type": "submitted", "request_id": "request-1"}],
            return_code=3,
            error={
                "code": "TIMEOUT",
                "message": "stream did not terminate",
                "retryable": False,
                "recovery": "collect only",
                "submission_state": "ambiguous",
            },
        )
        with self.assertRaises(controller.ControllerError):
            self.run_fake(handoff, fake)
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="".join(
                json.dumps(item) + "\n"
                for item in [
                    {"type": "progress", "stage": "response_readback"},
                    {"type": "progress", "stage": "complete"},
                    {
                        "type": "complete",
                        "text": "회수 완료",
                        "conversation_id": "conversation",
                        "parent_message_id": "assistant",
                        "assistant_message_id": "assistant",
                        "tool_routes": 0,
                        "done": True,
                        "completion_source": "conversation-readback-v1",
                    },
                ]
            ),
            stderr="",
        )
        with (
            mock.patch.object(controller, "node_binary", return_value=Path("/usr/bin/node")),
            mock.patch.object(controller, "node_entrypoint", return_value=Path("/tmp/chatgpt-desktop.js")),
            mock.patch.object(controller.subprocess, "run", return_value=completed) as run,
        ):
            result = controller.collect_response(SKILL_ROOT, handoff, timeout_seconds=30)
        self.assertEqual("imported", result["phase"])
        self.assertEqual("conversation-readback-v1", result["completion_source"])
        command = run.call_args.args[0]
        self.assertIn("collect", command)
        self.assertIn("--not-before", command)
        self.assertNotIn("ask", command)
        self.assertNotIn("--model", command)
        self.assertEqual(prepared["outbound_sha256"], result["outbound_sha256"])
        receipt = load_receipt(handoff / "receipt.json", package_id=prepared["package_id"])
        captured = next(item for item in receipt["events"] if item["event"] == "response_captured")
        self.assertEqual("conversation-readback-v1", captured["completion_source"])
        with self.assertRaises(controller.ControllerError) as second:
            controller.collect_response(SKILL_ROOT, handoff)
        self.assertEqual("RESPONSE_ALREADY_IMPORTED", second.exception.code)

    def test_collect_response_recovers_dispatch_authorized_crash_window_without_post(self) -> None:
        prepared, handoff = self.approved()
        manifest = read_json(handoff / "manifest.json")
        state = read_json(handoff / "state.json")
        model = self.catalog()["models"][0]
        message_id = controller._message_id(prepared["package_id"], prepared["outbound_sha256"])
        state["phase"] = "dispatching"
        state["resolved_model"] = model
        state["last_submission"] = {
            "status": "dispatching",
            "recorded_at": controller.utc_now(),
            "turn": 1,
            "message_id_sha256": sha256_bytes(message_id.encode("utf-8")),
        }
        approvals.save_state(handoff, state)
        from runtime.gptpro_runtime.receipts import append_receipt
        dispatching = append_receipt(
            handoff / "receipt.json",
            prepared["package_id"],
            "submission_dispatching",
            {
                "channel": DELIVERY_CHANNEL,
                "chat_history_mode": CHAT_HISTORY_MODE,
                "backend_model_id": model["id"],
                "thinking_effort": None,
                "prompt_sha256": prepared["outbound_sha256"],
                "prompt_bytes": prepared["outbound_bytes"],
                "system_prompt_sha256": manifest["hashes"]["system_prompt_sha256"],
                "message_id_sha256": sha256_bytes(message_id.encode("utf-8")),
                "turn": 1,
            },
        )
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="\n".join([
                json.dumps({"type": "progress", "stage": "response_readback"}),
                json.dumps({
                    "type": "complete",
                    "text": "crash-window recovery",
                    "conversation_id": "conversation",
                    "parent_message_id": "assistant",
                    "assistant_message_id": "assistant",
                    "tool_routes": 0,
                    "done": True,
                    "completion_source": "conversation-readback-v1",
                }),
            ]) + "\n",
            stderr="",
        )
        with (
            mock.patch.object(controller, "node_binary", return_value=Path("/usr/bin/node")),
            mock.patch.object(controller, "node_entrypoint", return_value=Path("/tmp/chatgpt-desktop.js")),
            mock.patch.object(controller.subprocess, "run", return_value=completed) as run,
        ):
            result = controller.collect_response(SKILL_ROOT, handoff, timeout_seconds=30)
        self.assertEqual("imported", result["phase"])
        command = run.call_args.args[0]
        self.assertEqual(dispatching["recorded_at"], command[command.index("--not-before") + 1])
        events = load_receipt(handoff / "receipt.json")["events"]
        self.assertNotIn("submission_dispatched", [event["event"] for event in events])

    def test_primary_consultation_rejects_recovery_readback_source(self) -> None:
        _, handoff = self.approved()
        fake = FakeProcess(
            [
                {"type": "submitted", "request_id": "request-1"},
                {
                    "type": "complete",
                    "text": "완료",
                    "conversation_id": "conversation",
                    "parent_message_id": "assistant",
                    "tool_routes": 0,
                    "completion_source": "conversation-readback-fallback-v1",
                },
            ]
        )
        with self.assertRaises(controller.ControllerError) as raised:
            self.run_fake(handoff, fake)
        self.assertEqual("RESPONSE_COMPLETION_UNPROVEN", raised.exception.code)

    def test_primary_consultation_rejects_manual_collect_source(self) -> None:
        _, handoff = self.approved()
        fake = FakeProcess(
            [
                {"type": "submitted", "request_id": "request-1"},
                {
                    "type": "complete",
                    "text": "완료",
                    "conversation_id": "conversation",
                    "parent_message_id": "assistant",
                    "tool_routes": 0,
                    "completion_source": "conversation-readback-v1",
                },
            ]
        )
        with self.assertRaises(controller.ControllerError) as raised:
            self.run_fake(handoff, fake)
        self.assertEqual("RESPONSE_COMPLETION_UNPROVEN", raised.exception.code)

    def test_signed_stream_completion_requires_topic_hash_evidence(self) -> None:
        _, handoff = self.approved()
        fake = FakeProcess(
            [
                {"type": "submitted", "request_id": "request-1"},
                {
                    "type": "complete",
                    "text": "완료",
                    "conversation_id": "conversation",
                    "parent_message_id": "assistant",
                    "tool_routes": 0,
                    "completion_source": "signed-stream-handoff-v1",
                    "stream_handoff_topic_sha256": None,
                },
            ]
        )
        with self.assertRaises(controller.ControllerError) as raised:
            self.run_fake(handoff, fake)
        self.assertEqual("RESPONSE_COMPLETION_UNPROVEN", raised.exception.code)

    def test_current_branch_proof_is_valid_only_for_signed_completion(self) -> None:
        _, handoff = self.approved()
        fake = FakeProcess(
            [
                {"type": "submitted", "request_id": "request-1"},
                {
                    "type": "complete",
                    "text": "완료",
                    "conversation_id": "conversation",
                    "parent_message_id": "assistant",
                    "tool_routes": 0,
                    "completion_source": "direct-desktop-stream-v1",
                    "stream_handoff_topic_sha256": None,
                    "current_branch_proof": "authenticated-exact-message-readback-v1",
                },
            ]
        )
        with self.assertRaises(controller.ControllerError) as raised:
            self.run_fake(handoff, fake)
        self.assertEqual("RESPONSE_COMPLETION_UNPROVEN", raised.exception.code)

    def test_parent_requires_signed_provenance_candidate_equivalence_and_identity(self) -> None:
        base = {
            "type": "complete",
            "text": "완료",
            "conversation_id": "RAW_CONVERSATION_SENTINEL",
            "parent_message_id": "RAW_ASSISTANT_SENTINEL",
            "assistant_message_id": "RAW_ASSISTANT_SENTINEL",
            "tool_routes": 0,
            "done": True,
            "completion_source": "signed-stream-handoff-v1",
            "stream_handoff_topic_sha256": "a" * 64,
            "current_branch_proof": None,
            "current_branch_proof_required": False,
            "tool_route_candidate_observed": False,
            "pre_handoff_assistant_observed": False,
            "signed_delta_continuation_observed": False,
            "signed_assistant_evidence": True,
            "topic_id": "RAW_TOPIC_SENTINEL",
            "websocket_url": "wss://ws.chatgpt.com/RAW_SIGNED_URL_SENTINEL",
        }
        for change in (
            {"tool_route_candidate_observed": True},
            {"completion_source": []},
            {"pre_handoff_assistant_observed": True},
            {"signed_delta_continuation_observed": True},
            {"current_branch_proof": "authenticated-exact-message-readback-v1"},
            {"current_branch_proof_required": True},
            {"signed_assistant_evidence": False},
            {"assistant_message_id": ""},
            {"done": False},
        ):
            _, handoff = self.approved()
            fake = FakeProcess([{"type": "submitted", "request_id": "request-1"}, {**base, **change}])
            with self.assertRaises(controller.ControllerError) as raised:
                self.run_fake(handoff, fake)
            self.assertEqual("RESPONSE_COMPLETION_UNPROVEN", raised.exception.code)
            self.assertEqual("submission_ambiguous", read_json(handoff / "state.json")["phase"])
            receipt = load_receipt(handoff / "receipt.json")
            self.assertEqual("submission_ambiguous", receipt["events"][-1]["event"])
            self.assertFalse(receipt["events"][-1]["automatic_retry_allowed"])
            serialized_receipt = json.dumps(receipt)
            for sentinel in (
                "RAW_CONVERSATION_SENTINEL",
                "RAW_ASSISTANT_SENTINEL",
                "RAW_TOPIC_SENTINEL",
                "RAW_SIGNED_URL_SENTINEL",
            ):
                self.assertNotIn(sentinel, serialized_receipt)

        for tool_routes in (False, 0.0, "0", None, [], {}):
            _, handoff = self.approved()
            fake = FakeProcess([
                {"type": "submitted", "request_id": "request-1"},
                {**base, "tool_routes": tool_routes},
            ])
            with self.assertRaises(controller.ControllerError) as raised:
                self.run_fake(handoff, fake)
            self.assertEqual("UNEXPECTED_TOOL_ROUTE", raised.exception.code)
            self.assertEqual("submission_ambiguous", read_json(handoff / "state.json")["phase"])

    def test_parent_deadline_marks_dispatched_submission_ambiguous(self) -> None:
        _, handoff = self.approved()

        class PendingProcess(FakeProcess):
            def __init__(self) -> None:
                super().__init__([
                    {"type": "submitted", "request_id": "request-1"},
                    {"type": "progress", "stage": "response_stream"},
                ])
                self.return_code = None

            def terminate(self):
                self.return_code = -15

        class ImmediateTimer:
            def __init__(self, interval, function) -> None:
                self.function = function
                self.daemon = False

            def start(self) -> None:
                self.function()

            def cancel(self) -> None:
                return None

        fake = PendingProcess()
        with (
            mock.patch.object(controller, "desktop_models", return_value=self.catalog()),
            mock.patch.object(controller, "node_binary", return_value=Path("/usr/bin/node")),
            mock.patch.object(controller, "node_entrypoint", return_value=Path("/tmp/chatgpt-desktop.js")),
            mock.patch.object(controller.subprocess, "Popen", side_effect=fake.bind),
            mock.patch.object(controller.threading, "Timer", ImmediateTimer),
            self.assertRaises(controller.ControllerError) as raised,
        ):
            controller.run_consultation(SKILL_ROOT, handoff, timeout_seconds=1)
        self.assertEqual("TIMEOUT", raised.exception.code)
        self.assertTrue(fake.killed)
        self.assertEqual("submission_ambiguous", read_json(handoff / "state.json")["phase"])
        receipt = load_receipt(handoff / "receipt.json")
        self.assertEqual("TIMEOUT", receipt["events"][-1]["error_code"])
        self.assertEqual("response_stream", receipt["events"][-1]["last_stage"])

    def test_child_failure_after_dispatch_cannot_recommend_resend(self) -> None:
        _, handoff = self.approved()
        fake = FakeProcess(
            [{"type": "submitted", "request_id": "request-1"}],
            return_code=3,
            error={
                "code": "TIMEOUT",
                "message": "child timeout",
                "retryable": True,
                "submission_state": "not_started",
                "recovery": "Retry the consultation.",
                "stage": "current_branch_proof",
            },
        )
        with self.assertRaises(controller.ControllerError) as raised:
            self.run_fake(handoff, fake)
        self.assertEqual("TIMEOUT", raised.exception.code)
        self.assertFalse(raised.exception.retryable)
        self.assertEqual("ambiguous", raised.exception.submission_state)
        self.assertEqual("current_branch_proof", raised.exception.stage)
        self.assertIn("collect-response", raised.exception.recovery)
        self.assertNotIn("Retry the consultation", raised.exception.recovery)
        self.assertEqual("submission_ambiguous", read_json(handoff / "state.json")["phase"])
        receipt = load_receipt(handoff / "receipt.json")
        self.assertFalse(receipt["events"][-1]["automatic_retry_allowed"])
        self.assertEqual("current_branch_proof", receipt["events"][-1]["last_stage"])

        for child_state in ("rejected", "completed"):
            error = controller._runtime_error(
                json.dumps({
                    "error": {
                        "code": "CHILD_ERROR",
                        "message": "child error",
                        "retryable": True,
                        "submission_state": child_state,
                        "recovery": "Run desktop-doctor before retrying.",
                    }
                }),
                submitted=True,
                last_stage="submitted",
            )
            self.assertFalse(error.retryable)
            self.assertEqual(child_state, error.submission_state)
            self.assertIn("Do not resend this package", error.recovery)
            self.assertNotIn("before retrying", error.recovery)

    def test_operator_interrupt_after_dispatch_is_sanitized_and_recorded(self) -> None:
        _, handoff = self.approved()

        class InterruptingOutput:
            def __init__(self, lines: list[str]) -> None:
                self.lines = iter(lines)

            def __iter__(self):
                return self

            def __next__(self):
                try:
                    return next(self.lines)
                except StopIteration:
                    raise KeyboardInterrupt

        class InterruptProcess(FakeProcess):
            def __init__(self) -> None:
                super().__init__([{"type": "submitted", "request_id": "request-1"}])
                self.return_code = None

            def bind(self, command, **kwargs):
                super().bind(command, **kwargs)
                self.stdout = InterruptingOutput(self.stdout.readlines())
                return self

        fake = InterruptProcess()
        with (
            mock.patch.object(controller, "desktop_models", return_value=self.catalog()),
            mock.patch.object(controller, "node_binary", return_value=Path("/usr/bin/node")),
            mock.patch.object(controller, "node_entrypoint", return_value=Path("/tmp/chatgpt-desktop.js")),
            mock.patch.object(controller.subprocess, "Popen", side_effect=fake.bind),
            self.assertRaises(controller.ControllerError) as raised,
        ):
            controller.run_consultation(SKILL_ROOT, handoff)
        self.assertEqual("CANCELLED", raised.exception.code)
        self.assertEqual("submission_ambiguous", read_json(handoff / "state.json")["phase"])
        receipt = load_receipt(handoff / "receipt.json")
        self.assertEqual("CANCELLED", receipt["events"][-1]["error_code"])

    def test_pre_dispatch_failure_does_not_mutate_approval_phase(self) -> None:
        _, handoff = self.approved()
        fake = FakeProcess(
            [],
            return_code=3,
            error={
                "code": "DEVICE_CHECK_UNAVAILABLE",
                "message": "no challenge",
                "retryable": False,
                "recovery": "doctor",
                "submission_state": "not_started",
            },
        )
        with (
            mock.patch.object(controller, "desktop_models", return_value=self.catalog()),
            mock.patch.object(controller, "node_binary", return_value=Path("/usr/bin/node")),
            mock.patch.object(controller, "node_entrypoint", return_value=Path("/tmp/chatgpt-desktop.js")),
            mock.patch.object(controller.subprocess, "Popen", side_effect=fake.bind),
            self.assertRaises(controller.ControllerError),
        ):
            controller.run_consultation(SKILL_ROOT, handoff)
        self.assertEqual("approved", read_json(handoff / "state.json")["phase"])

    def test_marker_collision_preserves_raw_and_blocks_resend(self) -> None:
        prepared, handoff = self.approved()
        marker = f"BEGIN_GPTPRO_RESPONSE:{prepared['package_id']}"
        fake = FakeProcess(
            [
                {"type": "submitted", "request_id": "request-1"},
                {"type": "complete", "text": f"collision {marker}", "conversation_id": "c", "parent_message_id": "m", "assistant_message_id": "m", "tool_routes": 0, "done": True, "completion_source": "signed-stream-handoff-v1", "stream_handoff_topic_sha256": "a" * 64, "current_branch_proof_required": False, "tool_route_candidate_observed": False, "pre_handoff_assistant_observed": False, "signed_delta_continuation_observed": False, "signed_assistant_evidence": True},
            ]
        )
        with self.assertRaises(controller.ControllerError) as raised:
            self.run_fake(handoff, fake)
        self.assertEqual("RESPONSE_MARKER_COLLISION", raised.exception.code)
        self.assertEqual("response_capture_failed", read_json(handoff / "state.json")["phase"])
        self.assertTrue((handoff / "responses" / "response.raw.md").is_file())

    def test_duplicate_submitted_event_is_protocol_error(self) -> None:
        _, handoff = self.approved()
        fake = FakeProcess(
            [
                {"type": "submitted", "request_id": "request-1"},
                {"type": "submitted", "request_id": "request-2"},
            ]
        )
        with self.assertRaises(controller.ControllerError) as raised:
            self.run_fake(handoff, fake)
        self.assertEqual("DESKTOP_RUNTIME_PROTOCOL_ERROR", raised.exception.code)
        self.assertEqual("submission_ambiguous", read_json(handoff / "state.json")["phase"])

    def test_non_string_child_progress_stage_is_protocol_error(self) -> None:
        _, handoff = self.approved()
        fake = FakeProcess([
            {"type": "submitted", "request_id": "request-1"},
            {"type": "progress", "stage": []},
        ])
        with self.assertRaises(controller.ControllerError) as raised:
            self.run_fake(handoff, fake)
        self.assertEqual("DESKTOP_RUNTIME_PROTOCOL_ERROR", raised.exception.code)
        self.assertEqual("submission_ambiguous", read_json(handoff / "state.json")["phase"])
        self.assertEqual("submitted", load_receipt(handoff / "receipt.json")["events"][-1]["last_stage"])

    def test_nonzero_tool_route_is_never_imported(self) -> None:
        _, handoff = self.approved()
        fake = FakeProcess(
            [
                {"type": "submitted", "request_id": "request-1"},
                {"type": "complete", "text": "tool answer", "conversation_id": "c", "parent_message_id": "m", "assistant_message_id": "m", "tool_routes": 1, "done": True, "completion_source": "signed-stream-handoff-v1", "stream_handoff_topic_sha256": "a" * 64, "current_branch_proof_required": False, "tool_route_candidate_observed": False, "pre_handoff_assistant_observed": False, "signed_delta_continuation_observed": False, "signed_assistant_evidence": True},
            ]
        )
        with self.assertRaises(controller.ControllerError) as raised:
            self.run_fake(handoff, fake)
        self.assertEqual("UNEXPECTED_TOOL_ROUTE", raised.exception.code)
        self.assertEqual("submission_ambiguous", read_json(handoff / "state.json")["phase"])
        self.assertFalse((handoff / "responses" / "response.raw.md").exists())

    def test_desktop_doctor_and_launch_fail_closed(self) -> None:
        base = {
            "desktop_bridge": True,
            "stream_bridge": True,
            "response_stream_supported": True,
            "response_readback_supported": True,
            "desktop_environment_readable": True,
            "device_check_supported": True,
            "isolated_runner": True,
        }
        with mock.patch.object(controller, "_node_json", return_value=base):
            self.assertTrue(controller.desktop_doctor(SKILL_ROOT)["ok"])
        with (
            mock.patch.object(controller, "_node_json", return_value={**base, "response_readback_supported": False}),
            self.assertRaises(controller.ControllerError) as unavailable,
        ):
            controller.desktop_doctor(SKILL_ROOT)
        self.assertEqual("BRIDGE_UNAVAILABLE", unavailable.exception.code)
        with (
            mock.patch.object(controller.Path, "is_dir", return_value=True),
            mock.patch.object(controller, "_runner_pids", return_value=[]),
            mock.patch.object(controller, "_port_open", return_value=True),
            mock.patch.object(controller.subprocess, "run") as launch,
            self.assertRaises(controller.ControllerError) as raised,
        ):
            controller.desktop_launch(SKILL_ROOT)
        self.assertEqual("CDP_LISTENER_UNVERIFIED", raised.exception.code)
        launch.assert_not_called()

    def test_user_launcher_install_status_and_trash_uninstall(self) -> None:
        applications = self.root / "Applications"
        fake_chatgpt = self.root / "ChatGPT.app"
        fake_chatgpt.mkdir()
        trash = self.root / ".Trash"
        with (
            mock.patch.object(controller, "CHATGPT_APP", fake_chatgpt),
            mock.patch.object(controller, "_runner_pids", return_value=[]),
            mock.patch.object(controller, "_app_pids", return_value=[]),
            mock.patch.object(controller, "_port_open", return_value=False),
        ):
            installed = controller.launcher_install(applications_dir=applications)
            self.assertTrue(installed["changed"])
            self.assertTrue(installed["current"])
            launcher = applications / controller.LAUNCHER_NAME
            executable = launcher / "Contents" / "MacOS" / controller.LAUNCHER_EXECUTABLE
            self.assertEqual(0o755, executable.stat().st_mode & 0o777)
            script = executable.read_text(encoding="utf-8")
            self.assertIn("--remote-debugging-address=127.0.0.1", script)
            self.assertIn("--remote-debugging-port=9223", script)
            self.assertIn("--user-data-dir=$runner_profile", script)
            self.assertIn("if ! process_list=", script)
            self.assertNotIn("ChatGPT가 일반 모드로 실행 중", script)
            self.assertNotIn("kill ", script)
            self.assertNotIn("Login Item", script)

            unchanged = controller.launcher_install(applications_dir=applications)
            self.assertFalse(unchanged["changed"])
            self.assertTrue(controller.launcher_status(applications_dir=applications)["current"])

            updated_script = controller._launcher_script() + b"\n# test update\n"
            with mock.patch.object(controller, "_launcher_script", return_value=updated_script):
                updated = controller.launcher_install(applications_dir=applications, trash_dir=trash)
                self.assertTrue(updated["changed"])
                self.assertTrue(updated["replaced_managed_launcher"])
                self.assertEqual(updated_script, executable.read_bytes())
                self.assertEqual(1, len(list(trash.glob("gptpro Launcher-*.app"))))

                with controller._launcher_lock(applications):
                    with self.assertRaises(controller.ControllerError) as busy:
                        controller.launcher_install(applications_dir=applications, trash_dir=trash)
                self.assertEqual("GPTPRO_LAUNCHER_BUSY", busy.exception.code)

                removed = controller.launcher_uninstall(applications_dir=applications, trash_dir=trash)
                self.assertTrue(removed["removed"])
                self.assertFalse(launcher.exists())
                self.assertTrue(Path(removed["trashed_path"]).is_dir())

    def test_user_launcher_refuses_foreign_item_and_status_does_not_create(self) -> None:
        applications = self.root / "Applications"
        fake_chatgpt = self.root / "ChatGPT.app"
        fake_chatgpt.mkdir()
        with (
            mock.patch.object(controller, "CHATGPT_APP", fake_chatgpt),
            mock.patch.object(controller, "_runner_pids", return_value=[]),
            mock.patch.object(controller, "_app_pids", return_value=[]),
            mock.patch.object(controller, "_port_open", return_value=False),
        ):
            status = controller.launcher_status(applications_dir=applications)
            self.assertFalse(status["installed"])
            self.assertFalse(applications.exists())
            foreign = applications / controller.LAUNCHER_NAME
            foreign.mkdir(parents=True)
            (foreign / "foreign.txt").write_text("do not replace", encoding="utf-8")
            with self.assertRaises(controller.ControllerError) as raised:
                controller.launcher_install(applications_dir=applications)
            self.assertEqual("GPTPRO_LAUNCHER_CONFLICT", raised.exception.code)
            self.assertEqual("do not replace", (foreign / "foreign.txt").read_text(encoding="utf-8"))

    def test_launcher_status_preserves_unknown_process_state(self) -> None:
        with (
            mock.patch.object(controller, "_runner_pids", side_effect=controller.ControllerError("CHATGPT_PROCESS_STATE_UNKNOWN", "unknown")),
            mock.patch.object(controller, "_port_open", return_value=False),
        ):
            status = controller.launcher_status(applications_dir=self.root / "Applications")
        self.assertIsNone(status["chatgpt_running"])
        self.assertEqual("unknown", status["chatgpt_process_state"])
        self.assertEqual("process_state_unknown", status["chatgpt_mode"])

    def test_desktop_launch_starts_isolated_runner_without_inspecting_ordinary_app(self) -> None:
        fake_chatgpt = self.root / "ChatGPT.app"
        fake_chatgpt.mkdir()
        profile = self.root / "runner" / "v1" / "profile"
        completed = subprocess.CompletedProcess([], 0, "", "")
        doctor = {
            "ok": True,
            "isolated_runner": True,
            "desktop_bridge": True,
            "stream_bridge": True,
            "response_readback_supported": True,
            "desktop_environment_readable": True,
            "device_check_supported": True,
        }
        with (
            mock.patch.object(controller, "CHATGPT_APP", fake_chatgpt),
            mock.patch.object(controller, "_runner_profile", return_value=profile),
            mock.patch.object(controller, "_runner_pids", return_value=[]),
            mock.patch.object(controller, "_port_open", side_effect=[False, True]),
            mock.patch.object(controller.subprocess, "run", return_value=completed) as launch,
            mock.patch.object(controller, "desktop_doctor", return_value=doctor),
        ):
            result = controller.desktop_launch(SKILL_ROOT)
        self.assertTrue(result["ok"])
        command = launch.call_args.args[0]
        self.assertIn(f"--user-data-dir={profile}", command)
        self.assertIn("--remote-debugging-port=9223", command)
        self.assertNotIn("kill", command)

    def test_runner_profile_secures_only_gptpro_owned_directories(self) -> None:
        profile = self.root / "Library" / "Application Support" / "gptpro" / "runner" / "v1" / "profile"
        (self.root / "Library" / "Application Support").mkdir(parents=True)
        with mock.patch.object(controller, "_runner_profile", return_value=profile):
            self.assertEqual(profile, controller._secure_runner_profile())
        for directory in (profile.parents[2], profile.parents[1], profile.parent, profile):
            self.assertEqual(0o700, directory.stat().st_mode & 0o777)
        self.assertNotEqual(0o700, (self.root / "Library" / "Application Support").stat().st_mode & 0o777)

    def test_launcher_status_distinguishes_runner_from_ordinary_chatgpt(self) -> None:
        with (
            mock.patch.object(controller, "_runner_pids", return_value=[222]),
            mock.patch.object(controller, "_app_pids", return_value=[111, 222]),
            mock.patch.object(controller, "_port_open", return_value=True),
        ):
            status = controller.launcher_status(applications_dir=self.root / "Applications")
        self.assertTrue(status["runner_running"])
        self.assertTrue(status["ordinary_chatgpt_running"])
        self.assertFalse(status["ordinary_chatgpt_relaunch_required"])

    def test_evaluation_remains_separate(self) -> None:
        _, handoff = self.approved()
        state = read_json(handoff / "state.json")
        state["phase"] = "imported"
        state["response_count"] = 1
        write_json(handoff / "state.json", state)
        result = controller.record_evaluation(
            handoff,
            verdict="partially-accepted",
            summary="첫 번째 지적만 현재 파일에서 재현됨",
        )
        self.assertEqual("evaluated", result["phase"])


if __name__ == "__main__":
    unittest.main()
