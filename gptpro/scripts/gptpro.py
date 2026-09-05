#!/usr/bin/env python3
"""Governed ChatGPT Pro consultation through the private macOS Electron bridge."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from runtime.gptpro_runtime.approvals import (  # noqa: E402
    ApprovalError,
    apply_standing,
    approve_exact,
    create_standing,
    list_standing,
    load_state,
    revoke_standing,
)
from runtime.gptpro_runtime.controller import (  # noqa: E402
    ControllerError,
    DEFAULT_CONSULT_TIMEOUT_SECONDS,
    collect_response,
    desktop_doctor,
    desktop_launch,
    desktop_models,
    launcher_install,
    launcher_status,
    launcher_uninstall,
    record_evaluation,
    run_consultation,
)
from runtime.gptpro_runtime.package import PackageError, prepare_package, verify_package  # noqa: E402
from runtime.gptpro_runtime.receipts import ReceiptError, load_receipt  # noqa: E402
from runtime.gptpro_runtime.schema import (  # noqa: E402
    CHAT_HISTORY_MODE,
    CONTEXT_TRANSPORT,
    DEFAULT_MODEL_ID,
    INLINE_FORMAT,
    MAX_OUTBOUND_BYTES,
    RUNTIME_VERSION as VERSION,
)
from runtime.gptpro_runtime.state import StateError, secure_directory, state_root  # noqa: E402


LEGACY_COMMANDS = {
    "mcp-activate",
    "mcp-stop",
    "mcp-status",
    "mcp-recover",
    "mcp-research",
    "desktop-plan",
    "collect",
    "browser-plan",
    "human-handoff",
}


class CliError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        recovery: str = "Correct the reported condition and prepare a new approval if disclosure changes.",
        submission_state: str = "not_started",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.recovery = recovery
        self.submission_state = submission_state
        self.details = details or {}


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliError(
            "GPTPRO_ARGUMENT_ERROR",
            message,
            recovery="Run gptpro.py --help and correct the command arguments.",
        )


def error_format(argv: list[str]) -> str:
    for index, value in enumerate(argv):
        if value == "--error-format" and index + 1 < len(argv):
            return argv[index + 1]
        if value.startswith("--error-format="):
            return value.split("=", 1)[1]
    return "text"


def operation_name(argv: list[str]) -> str:
    skip = False
    for value in argv:
        if skip:
            skip = False
            continue
        if value == "--error-format":
            skip = True
            continue
        if value.startswith("--error-format=") or value.startswith("-"):
            continue
        return value
    return "unknown"


def normalize_error(error: Exception, operation: str) -> CliError:
    if isinstance(error, CliError):
        return error
    if isinstance(error, (PackageError, ApprovalError, ControllerError)):
        return CliError(
            getattr(error, "code", f"GPTPRO_{operation.upper().replace('-', '_')}_FAILED"),
            getattr(error, "message", str(error)),
            retryable=getattr(error, "retryable", False),
            recovery=getattr(error, "recovery", "Correct the reported condition before retrying."),
            submission_state=getattr(error, "submission_state", "not_started"),
            details={"last_stage": error.stage} if isinstance(getattr(error, "stage", None), str) else None,
        )
    if isinstance(error, (StateError, ReceiptError)):
        return CliError(getattr(error, "code", "GPTPRO_STATE_INVALID"), getattr(error, "message", str(error)))
    return CliError(
        "GPTPRO_INTERNAL_ERROR",
        "gptpro encountered an unexpected internal error.",
        recovery="Run diagnostic-status and report the sanitized error code. Do not resend an uncertain consultation.",
        submission_state="unknown",
    )


def emit_error(error: CliError, *, operation: str, json_mode: bool) -> int:
    exit_code = 2 if error.code != "GPTPRO_INTERNAL_ERROR" else 3
    envelope = {
        "ok": False,
        "operation": operation,
        "exit_code": exit_code,
        "error": {
            "code": error.code,
            "message": error.message,
            "automatic_retry_allowed": error.retryable and error.submission_state == "not_started",
            "recovery": error.recovery,
            "submission_state": error.submission_state,
            "sanitized": True,
        },
        **error.details,
    }
    if json_mode:
        print(json.dumps(envelope, ensure_ascii=False, sort_keys=True), file=sys.stderr)
    else:
        print(f"오류: {error.code} — {error.message}", file=sys.stderr)
        print(f"실패 단계: {operation}", file=sys.stderr)
        print(f"기대한 결과/관찰: 작업 완료 / {error.message}", file=sys.stderr)
        print(f"전송 상태: {error.submission_state}", file=sys.stderr)
        print("승인·저장소 변경: 오류 증거만으로 새 승인이나 tracked 파일 변경을 단정하지 않습니다.", file=sys.stderr)
        print("package/Tunnel 상태: Electron package 상태는 diagnostic-status로 확인하며 Tunnel은 v0.6에서 사용하지 않습니다.", file=sys.stderr)
        print(f"자동 재시도: {'가능' if envelope['error']['automatic_retry_allowed'] else '불가'}", file=sys.stderr)
        print(f"다음 조치: {error.recovery}", file=sys.stderr)
    return exit_code


def emit(value: dict[str, Any], *, compact: bool = False) -> int:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=None if compact else 2))
    return 0


def add_selection(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", required=True)
    parser.add_argument("--mode", required=True, choices=("plan", "ask", "review", "debug", "architecture"))
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--file-list")
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--supplement", action="append", default=[])
    parser.add_argument("--allow-untracked", action="store_true")
    task = parser.add_mutually_exclusive_group(required=True)
    task.add_argument("--task")
    task.add_argument("--task-file")
    parser.add_argument("--model-intent", default=DEFAULT_MODEL_ID)
    parser.add_argument("--thinking-effort")


def task_text(args: argparse.Namespace) -> str:
    if args.task is not None:
        return args.task
    try:
        return Path(args.task_file).expanduser().resolve().read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CliError("TASK_FILE_INVALID", "The task file cannot be read as strict UTF-8.") from exc


def prepare_from_args(args: argparse.Namespace) -> dict[str, Any]:
    return prepare_package(
        repo_value=Path(args.repo),
        mode=args.mode,
        task=task_text(args),
        includes=args.include,
        file_list=Path(args.file_list).expanduser().resolve() if args.file_list else None,
        excludes=args.exclude,
        supplements=args.supplement,
        allow_untracked=args.allow_untracked,
        model_intent=args.model_intent,
        thinking_effort=args.thinking_effort,
    )


def capabilities() -> dict[str, Any]:
    return {
        "contract": "gptpro-component-capabilities-v1",
        "component": "gptpro",
        "version": VERSION,
        "schema_version": 6,
        "features": [
            "schema-6-inline-immutable-snapshot",
            "desktop-electron-private-runtime",
            "dynamic-model-catalog",
            "single-message-inline-context",
            "machine-global-standing-approval-v4",
            "signed-stream-handoff-v1",
            "authenticated-exact-message-branch-proof",
            "authenticated-exact-message-readback-recovery",
            "deterministic-response-import",
            "macos-user-launcher",
        ],
        "delivery_channels": ["desktop-electron"],
        "context_transports": [CONTEXT_TRANSPORT],
        "inline_format": INLINE_FORMAT,
        "max_outbound_bytes": MAX_OUTBOUND_BYTES,
        "default_model_id": DEFAULT_MODEL_ID,
        "chat_history_mode": CHAT_HISTORY_MODE,
        "response_collection": {
            "primary": "signed-stream-handoff-v1",
            "conditional_branch_proof": "authenticated-exact-message-readback-v1",
            "conditional_branch_proof_get_only": True,
            "conditional_branch_proof_timeout_seconds": 30,
            "conditional_branch_proof_when": [
                "tool-route-candidate",
                "pre-handoff-assistant-evidence",
                "signed-delta-continuation",
            ],
            "direct_completion_fallback": False,
            "recovery": "conversation-readback-v1",
            "collect_response_get_only": True,
            "collect_response_role": "recovery-only",
        },
        "tools_enabled": False,
        "local_functions": False,
        "server_tool_fallback": False,
        "mcp_runtime": False,
        "browser_delivery": False,
        "computer_use": False,
        "secure_mcp_tunnel": False,
        "electron_private_api": True,
        "minimum_node_major": 22,
    }


def diagnostic_status(handoff_value: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": True,
        "operation": "diagnostic-status",
        "observation_only": True,
        "channel": "desktop-electron",
        "tunnel": {"applicable": False, "status": "removed-from-v0.5"},
        "mutations_performed": False,
    }
    if not handoff_value:
        result["package"] = {"availability": "not_provided"}
        return result
    handoff = Path(handoff_value).expanduser().resolve()
    try:
        verified = verify_package(handoff)
        package_id = verified.get("package_id") or verified.get("manifest", {}).get("package_id")
        state = load_state(handoff, package_id)
        approval = state.get("approval")
        result["package"] = {
            "availability": "verified",
            "schema_version": 6,
            "package_id": package_id,
            "phase": state.get("phase"),
            "approval": "recorded" if isinstance(approval, dict) else "not_recorded",
            "submission": (state.get("last_submission") or {}).get("status", "not_recorded"),
            "response_count": state.get("response_count", 0),
            "transport": CONTEXT_TRANSPORT,
            "channel": "desktop-electron",
            "chat_history_mode": verified["manifest"]["delivery"]["chat_history_mode"],
        }
    except Exception as exc:
        error = normalize_error(exc, "diagnostic-status")
        result["package"] = {"availability": "unavailable", "code": error.code}
    return result


def status(handoff_value: str) -> dict[str, Any]:
    verified = verify_package(Path(handoff_value))
    handoff = Path(verified["handoff_dir"])
    manifest = verified["manifest"]
    state = load_state(handoff, manifest["package_id"])
    receipt = load_receipt(handoff / "receipt.json", package_id=manifest["package_id"])
    return {
        "ok": True,
        "operation": "status",
        "package_id": manifest["package_id"],
        "schema_version": 6,
        "phase": state.get("phase"),
        "revision": state.get("revision"),
        "approval": state.get("approval"),
        "last_submission": state.get("last_submission"),
        "response_count": state.get("response_count"),
        "receipt_events": [event["event"] for event in receipt["events"]],
        "context_transport": CONTEXT_TRANSPORT,
        "delivery_channel": "desktop-electron",
        "outbound_sha256": manifest["hashes"]["outbound_sha256"],
        "outbound_bytes": manifest["disclosure"]["outbound_bytes"],
        "inline_format": INLINE_FORMAT,
        "chat_history_mode": manifest.get("delivery", {}).get("chat_history_mode", "unspecified-legacy"),
        "tunnel_applicable": False,
    }


def parser() -> argparse.ArgumentParser:
    root = JsonArgumentParser(description=__doc__)
    root.add_argument("--error-format", choices=("text", "json"), default="text")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("capabilities").add_argument("--json", action="store_true")
    commands.add_parser("init").add_argument("--json", action="store_true")
    doctor = commands.add_parser("desktop-doctor")
    doctor.add_argument("--endpoint")
    doctor.add_argument("--json", action="store_true")
    launch = commands.add_parser("desktop-launch")
    launch.add_argument("--json", action="store_true")
    commands.add_parser("launcher-install").add_argument("--json", action="store_true")
    commands.add_parser("launcher-status").add_argument("--json", action="store_true")
    commands.add_parser("launcher-uninstall").add_argument("--json", action="store_true")
    models = commands.add_parser("models")
    models.add_argument("--endpoint")
    models.add_argument("--json", action="store_true")
    prepare = commands.add_parser("prepare")
    add_selection(prepare)
    prepare.add_argument("--json", action="store_true")
    verify = commands.add_parser("verify")
    verify.add_argument("--handoff-dir", required=True)
    verify.add_argument("--json", action="store_true")
    stat = commands.add_parser("status")
    stat.add_argument("--handoff-dir", required=True)
    stat.add_argument("--json", action="store_true")
    diagnostic = commands.add_parser("diagnostic-status")
    diagnostic.add_argument("--handoff-dir")
    diagnostic.add_argument("--json", action="store_true")
    approve = commands.add_parser("approve")
    approve.add_argument("--handoff-dir", required=True)
    approve.add_argument("--confirm-transmission", action="store_true")
    approve.add_argument("--confirm-disclosure", action="store_true")
    approve.add_argument("--expires-minutes", type=int, default=120)
    approve.add_argument("--json", action="store_true")
    standing = commands.add_parser("standing-approval-create")
    standing.add_argument("--handoff-dir", required=True)
    standing.add_argument("--confirm-transmission", action="store_true")
    standing.add_argument("--confirm-disclosure", action="store_true")
    standing.add_argument("--expires-hours", type=int, default=24)
    standing.add_argument("--mode", action="append", choices=("plan", "ask", "review", "debug", "architecture"))
    standing.add_argument("--json", action="store_true")
    commands.add_parser("standing-approval-list").add_argument("--json", action="store_true")
    revoke = commands.add_parser("standing-approval-revoke")
    revoke.add_argument("--approval-id", required=True)
    revoke.add_argument("--json", action="store_true")
    consult = commands.add_parser("consult")
    consult.add_argument("--handoff-dir")
    consult.add_argument("--standing-approval")
    consult.add_argument("--use-standing-approval", action="store_true")
    consult.add_argument("--timeout-seconds", type=int, default=DEFAULT_CONSULT_TIMEOUT_SECONDS)
    consult.add_argument("--json", action="store_true")
    consult.add_argument("--repo")
    consult.add_argument("--mode", choices=("plan", "ask", "review", "debug", "architecture"))
    consult.add_argument("--include", action="append", default=[])
    consult.add_argument("--file-list")
    consult.add_argument("--exclude", action="append", default=[])
    consult.add_argument("--supplement", action="append", default=[])
    consult.add_argument("--allow-untracked", action="store_true")
    consult.add_argument("--task")
    consult.add_argument("--task-file")
    consult.add_argument("--model-intent", default=DEFAULT_MODEL_ID)
    consult.add_argument("--thinking-effort")
    collect = commands.add_parser("collect-response")
    collect.add_argument("--handoff-dir", required=True)
    collect.add_argument("--timeout-seconds", type=int, default=10 * 60)
    collect.add_argument("--json", action="store_true")
    evaluation = commands.add_parser("record-evaluation")
    evaluation.add_argument("--handoff-dir", required=True)
    evaluation.add_argument("--verdict", required=True, choices=("accepted", "partially-accepted", "rejected"))
    evaluation.add_argument("--summary", required=True)
    evaluation.add_argument("--json", action="store_true")
    return root


def run(args: argparse.Namespace) -> dict[str, Any]:
    command = args.command
    if command == "capabilities":
        return capabilities()
    if command == "init":
        root = secure_directory(state_root())
        secure_directory(root / "workspaces")
        secure_directory(root / "approvals")
        return {"ok": True, "operation": "init", "state_root": str(root), "mode": "0700", "version": VERSION}
    if command == "desktop-doctor":
        return desktop_doctor(SKILL_ROOT, endpoint=args.endpoint)
    if command == "desktop-launch":
        return desktop_launch(SKILL_ROOT)
    if command == "launcher-install":
        return launcher_install()
    if command == "launcher-status":
        return launcher_status(skill_root=SKILL_ROOT)
    if command == "launcher-uninstall":
        return launcher_uninstall()
    if command == "models":
        return desktop_models(SKILL_ROOT, endpoint=args.endpoint)
    if command == "prepare":
        return prepare_from_args(args)
    if command == "verify":
        return verify_package(Path(args.handoff_dir))
    if command == "status":
        return status(args.handoff_dir)
    if command == "diagnostic-status":
        return diagnostic_status(args.handoff_dir)
    if command == "approve":
        return approve_exact(Path(args.handoff_dir), confirm_transmission=args.confirm_transmission, confirm_disclosure=args.confirm_disclosure, expires_minutes=args.expires_minutes)
    if command == "standing-approval-create":
        return create_standing(Path(args.handoff_dir), confirm_transmission=args.confirm_transmission, confirm_disclosure=args.confirm_disclosure, expires_hours=args.expires_hours, modes=args.mode)
    if command == "standing-approval-list":
        return list_standing()
    if command == "standing-approval-revoke":
        return revoke_standing(args.approval_id)
    if command == "consult":
        prepared: dict[str, Any] | None = None
        if args.handoff_dir:
            handoff = Path(args.handoff_dir)
        else:
            required = {"--repo": args.repo, "--mode": args.mode}
            missing = [name for name, value in required.items() if not value]
            if missing or bool(args.task) == bool(args.task_file):
                raise CliError("GPTPRO_ARGUMENT_ERROR", "consult requires --handoff-dir or a complete --repo/--mode/--task selection.")
            prepared = prepare_from_args(args)
            handoff = Path(prepared["handoff_dir"])
        verified = verify_package(handoff)
        state = load_state(Path(verified["handoff_dir"]), verified["manifest"]["package_id"])
        if state.get("phase") == "prepared":
            if args.use_standing_approval or args.standing_approval:
                try:
                    apply_standing(handoff, approval_id=args.standing_approval)
                except ApprovalError as exc:
                    raise CliError(
                        exc.code,
                        exc.message,
                        recovery=exc.recovery,
                        details={"prepared_package": prepared or {"handoff_dir": str(handoff), "package_id": verified["manifest"]["package_id"]}, "prompt_sent": False},
                    ) from exc
            else:
                raise CliError(
                    "APPROVAL_REQUIRED",
                    "The prepared Schema-6 package has no exact or matching standing approval.",
                    recovery="Review the displayed package hashes and scope, then run approve or standing-approval-create. No prompt was sent.",
                    details={"prepared_package": prepared or {"handoff_dir": str(handoff), "package_id": verified["manifest"]["package_id"]}, "prompt_sent": False},
                )
        return run_consultation(SKILL_ROOT, handoff, timeout_seconds=args.timeout_seconds)
    if command == "collect-response":
        return collect_response(SKILL_ROOT, Path(args.handoff_dir), timeout_seconds=args.timeout_seconds)
    if command == "record-evaluation":
        return record_evaluation(Path(args.handoff_dir), verdict=args.verdict, summary=args.summary)
    raise CliError("GPTPRO_ARGUMENT_ERROR", f"Unsupported command: {command}")


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    operation = operation_name(raw)
    json_mode = error_format(raw) == "json"
    try:
        if operation in LEGACY_COMMANDS:
            raise CliError(
                "GPTPRO_LEGACY_TRANSPORT_REMOVED",
                "Browser, Computer Use, custom ChatGPT App, Developer Mode, Secure MCP Tunnel, MCP, and local-function commands are not part of gptpro v0.6.",
                recovery="Use desktop-doctor, models, and a newly approved Schema-6 inline desktop-electron consultation.",
            )
        args = parser().parse_args(raw)
        return emit(run(args), compact=False)
    except Exception as exc:
        return emit_error(normalize_error(exc, operation), operation=operation, json_mode=json_mode)


if __name__ == "__main__":
    raise SystemExit(main())
