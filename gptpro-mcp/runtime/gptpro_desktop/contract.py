"""Stable JSON boundary between gptpro and visible ChatGPT Desktop UI automation."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .state import DesktopStateError

DESKTOP_HANDOFF_CONTRACT = "gptpro-desktop-handoff-v1"
DESKTOP_OBSERVATION_CONTRACT = "gptpro-desktop-observation-v1"
EXTRACTION_RULES_VERSION = "chatgpt-desktop-visible-assistant-text-v1"
MAX_RESPONSE_WAIT_SECONDS = 20 * 60
MAX_POLL_SECONDS = 60
SAFE_NONCE = re.compile(r"[0-9a-f]{32}")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request_nonce_for(package_id: str, outbound_sha256: str) -> str:
    return _sha256(
        json.dumps(
            {"package_id": package_id, "outbound_sha256": outbound_sha256},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )[:32]


def build_handoff_plan(*, handoff_dir: Path, verified: dict[str, Any]) -> dict[str, Any]:
    manifest = verified["manifest"]
    state = verified["state"]
    if manifest.get("schema_version") != 4 or manifest.get("transport", {}).get("resolved") != "mcp-research":
        raise DesktopStateError(
            "DESKTOP_HANDOFF_UNSUPPORTED",
            "Desktop collaboration requires a Schema-4 mcp-research package.",
        )
    if manifest.get("delivery", {}).get("channel") != "desktop-ui":
        raise DesktopStateError(
            "DESKTOP_HANDOFF_UNSUPPORTED", "The package is not approved for Desktop UI delivery."
        )
    if state.get("phase") not in {"approved", "submitted", "response_imported", "evaluated"}:
        raise DesktopStateError(
            "DESKTOP_HANDOFF_NOT_APPROVED", "The prepared request is not approved for transmission."
        )
    outbound = verified.get("outbound_artifacts")
    if not isinstance(outbound, list) or len(outbound) != 1:
        raise DesktopStateError(
            "DESKTOP_HANDOFF_INVALID", "Desktop delivery requires exactly one prompt artifact."
        )
    item = outbound[0]
    artifact_key = item.get("artifact")
    filename = manifest.get("artifacts", {}).get(artifact_key)
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise DesktopStateError("DESKTOP_HANDOFF_INVALID", "The outbound prompt is invalid.")
    artifact_path = Path(handoff_dir) / filename
    if not artifact_path.is_file():
        raise DesktopStateError("DESKTOP_HANDOFF_INVALID", "The outbound prompt is missing.")
    actual = artifact_path.read_bytes()
    actual_hash = _sha256(actual)
    if item.get("bytes") != len(actual) or item.get("sha256") != actual_hash:
        raise DesktopStateError("DESKTOP_HANDOFF_INVALID", "The outbound prompt hash is invalid.")
    connector = manifest.get("connector", {})
    nonce = request_nonce_for(str(manifest["package_id"]), actual_hash)
    return {
        "contract": DESKTOP_HANDOFF_CONTRACT,
        "package_id": manifest["package_id"],
        "delivery_channel": "desktop-ui",
        "application": "ChatGPT",
        "chat_surface": "general-chat",
        "visible_mode_required": "Chat",
        "visible_pro_required": True,
        "requested_model": manifest["requested_model"],
        "app_name": connector.get("app_name"),
        "workspace_label": connector.get("workspace_label"),
        "transport": "mcp-research",
        "approval_source": state["approval"].get("approval_source", "exact-package"),
        "request_nonce": nonce,
        "outbound": {"path": str(artifact_path), "bytes": len(actual), "sha256": actual_hash},
        "send_attempt_limit": 1,
        "response_wait": {
            "max_total_seconds": MAX_RESPONSE_WAIT_SECONDS,
            "max_poll_seconds": MAX_POLL_SECONDS,
        },
        "automatic_login": False,
        "local_tool_calls": False,
        "private_desktop_api_used": False,
    }


def _validate_common(plan: dict[str, Any], observation: dict[str, Any], *, stage: str) -> None:
    if observation.get("contract") != DESKTOP_OBSERVATION_CONTRACT:
        raise DesktopStateError(
            "DESKTOP_OBSERVATION_INVALID", "The Desktop observation contract is invalid."
        )
    if observation.get("stage") != stage or observation.get("package_id") != plan.get("package_id"):
        raise DesktopStateError(
            "DESKTOP_OBSERVATION_MISMATCH", "The observation belongs to another stage or request."
        )
    if observation.get("request_nonce") != plan.get("request_nonce"):
        raise DesktopStateError(
            "DESKTOP_OBSERVATION_MISMATCH", "The observation request binding does not match."
        )


def validate_submission_observation(
    plan: dict[str, Any], observation: dict[str, Any]
) -> dict[str, Any]:
    _validate_common(plan, observation, stage="submission")
    status = observation.get("status")
    if status not in {"sent", "not_sent", "ambiguous"}:
        raise DesktopStateError("DESKTOP_OBSERVATION_INVALID", "Submission status is invalid.")
    attempts = observation.get("send_attempts")
    if isinstance(attempts, bool) or not isinstance(attempts, int) or not 0 <= attempts <= 1:
        raise DesktopStateError(
            "DESKTOP_SEND_LIMIT_VIOLATION", "A Desktop handoff may attempt Send at most once."
        )
    if status == "not_sent":
        if attempts != 0:
            raise DesktopStateError(
                "DESKTOP_OBSERVATION_INVALID", "A not-sent observation must have zero Send attempts."
            )
        return {"status": status, "automatic_retry_allowed": True, "resend_allowed": True}
    if attempts != 1:
        raise DesktopStateError(
            "DESKTOP_OBSERVATION_INVALID", "A sent or ambiguous observation requires one Send attempt."
        )
    if status == "ambiguous":
        return {"status": status, "automatic_retry_allowed": False, "resend_allowed": False}
    expected_hash = plan["outbound"]["sha256"]
    if (
        observation.get("application") != "ChatGPT"
        or observation.get("delivery_channel") != "desktop-ui"
        or observation.get("chat_surface") != "general-chat"
        or observation.get("chat_mode_visible") is not True
        or observation.get("pro_visible") is not True
        or observation.get("new_chat_empty_before_send") is not True
        or observation.get("composer_sha256") != expected_hash
        or observation.get("visible_user_turn_sha256") != expected_hash
        or observation.get("observed_model") != plan.get("requested_model")
        or observation.get("observed_app_name") != plan.get("app_name")
        or observation.get("observed_workspace_label") != plan.get("workspace_label")
    ):
        raise DesktopStateError(
            "DESKTOP_SUBMISSION_EVIDENCE_INCOMPLETE",
            "The visible Desktop user turn is not fully bound to the approved request.",
        )
    return {
        "status": "sent",
        "request_nonce": plan["request_nonce"],
        "automatic_retry_allowed": False,
        "resend_allowed": False,
        "outbound_sha256": expected_hash,
        "visible_user_turn_sha256": expected_hash,
        "send_attempts": 1,
    }


def validate_response_observation(
    plan: dict[str, Any], observation: dict[str, Any], *, expected_request_nonce: str
) -> dict[str, Any]:
    _validate_common(plan, observation, stage="response")
    if expected_request_nonce != plan.get("request_nonce"):
        raise DesktopStateError(
            "DESKTOP_OBSERVATION_MISMATCH", "The recorded submission belongs to another request."
        )
    status = observation.get("status")
    if status not in {"complete", "pending", "timed_out", "cancelled", "error"}:
        raise DesktopStateError("DESKTOP_OBSERVATION_INVALID", "Response status is invalid.")
    if observation.get("visible_user_turn_sha256") != plan["outbound"]["sha256"]:
        raise DesktopStateError(
            "DESKTOP_OBSERVATION_MISMATCH", "The response is not bound to the approved user turn."
        )
    if status != "complete":
        return {
            "status": status,
            "request_nonce": plan["request_nonce"],
            "automatic_retry_allowed": False,
            "resend_allowed": False,
            "collection_retry_allowed": status in {"pending", "timed_out"},
        }
    if (
        observation.get("generation_complete") is not True
        or observation.get("stop_button_visible") is not False
        or observation.get("error_card_visible") is not False
        or observation.get("assistant_turn_ordinal") != 1
        or observation.get("copy_action_confirmed") is not True
    ):
        raise DesktopStateError(
            "DESKTOP_RESPONSE_INCOMPLETE", "The next assistant turn is not visibly complete."
        )
    text = observation.get("captured_text")
    if not isinstance(text, str) or not text.strip() or "\x00" in text:
        raise DesktopStateError(
            "DESKTOP_RESPONSE_INVALID", "The captured assistant text is empty or invalid."
        )
    canonical = text.strip() + "\n"
    actual_hash = _sha256(canonical.encode("utf-8"))
    if observation.get("captured_text_sha256") != actual_hash:
        raise DesktopStateError(
            "DESKTOP_RESPONSE_HASH_MISMATCH", "The captured assistant text hash does not match."
        )
    turn_identity = _sha256(
        json.dumps(
            {
                "package_id": plan["package_id"],
                "request_nonce": plan["request_nonce"],
                "visible_user_turn_sha256": plan["outbound"]["sha256"],
                "assistant_turn_ordinal": 1,
                "captured_text_sha256": actual_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    return {
        "status": "complete",
        "request_nonce": plan["request_nonce"],
        "captured_text": canonical,
        "captured_text_sha256": actual_hash,
        "assistant_turn_identity_sha256": turn_identity,
        "extraction_rules_version": EXTRACTION_RULES_VERSION,
        "automatic_retry_allowed": False,
        "resend_allowed": False,
        "collection_retry_allowed": False,
    }


def deterministic_response_wrapper(*, package_id: str, captured_text: str) -> bytes:
    begin = f"BEGIN_GPTPRO_RESPONSE:{package_id}"
    end = f"END_GPTPRO_RESPONSE:{package_id}"
    body = captured_text.strip()
    if not body:
        raise DesktopStateError("DESKTOP_RESPONSE_INVALID", "The response body is empty.")
    if begin in body or end in body:
        raise DesktopStateError(
            "DESKTOP_RESPONSE_MARKER_COLLISION",
            "The captured response contains package markers and cannot be wrapped safely.",
        )
    return f"{begin}\n{body}\n{end}\n".encode("utf-8")
