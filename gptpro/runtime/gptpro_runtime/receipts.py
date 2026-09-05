"""Hash-chained package receipt helpers."""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .state import atomic_write, canonical_json_bytes, sha256_bytes


class ReceiptError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash(record: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes({key: value for key, value in record.items() if key != "event_sha256"}))


def _safe_receipt(path: Path) -> None:
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_size > 8 * 1024 * 1024
    ):
        raise ReceiptError("RECEIPT_UNSAFE", "The package receipt is unsafe.")


def load_receipt(path: Path, *, package_id: str | None = None) -> dict[str, Any]:
    try:
        _safe_receipt(path)
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise ReceiptError("RECEIPT_INVALID", "The package receipt cannot be verified.") from exc
    if (
        not isinstance(value, dict)
        or value.get("schema") != "gptpro-consultation-receipt-v1"
        or not isinstance(value.get("package_id"), str)
        or not isinstance(value.get("events"), list)
        or (package_id is not None and value.get("package_id") != package_id)
    ):
        raise ReceiptError("RECEIPT_INVALID", "The package receipt contract is invalid.")
    previous: str | None = None
    for index, event in enumerate(value["events"]):
        if (
            not isinstance(event, dict)
            or event.get("sequence") != index
            or event.get("previous_event_sha256") != previous
            or event.get("event_sha256") != _hash(event)
        ):
            raise ReceiptError("RECEIPT_INVALID", "The package receipt hash chain is invalid.")
        previous = event["event_sha256"]
    if not value["events"] or value["events"][0].get("event") != "prepared":
        raise ReceiptError("RECEIPT_INVALID", "The package receipt has no preparation event.")
    return value


def create_receipt(path: Path, *, package_id: str, manifest_sha256: str, outbound_sha256: str) -> dict[str, Any]:
    if path.exists() or path.is_symlink():
        raise ReceiptError("RECEIPT_ALREADY_EXISTS", "A receipt already exists for this package.")
    event = {
        "sequence": 0,
        "event": "prepared",
        "recorded_at": utc_now(),
        "previous_event_sha256": None,
        "manifest_sha256": manifest_sha256,
        "outbound_sha256": outbound_sha256,
    }
    event["event_sha256"] = _hash(event)
    receipt = {"schema": "gptpro-consultation-receipt-v1", "package_id": package_id, "events": [event]}
    atomic_write(path, canonical_json_bytes(receipt) + b"\n")
    return receipt


def append_receipt(path: Path, package_id: str, event_name: str, fields: dict[str, Any]) -> dict[str, Any]:
    receipt = load_receipt(path, package_id=package_id)
    previous = receipt["events"][-1]["event_sha256"]
    event = {
        "sequence": len(receipt["events"]),
        "event": event_name,
        "recorded_at": utc_now(),
        "previous_event_sha256": previous,
        **fields,
    }
    event["event_sha256"] = _hash(event)
    receipt["events"].append(event)
    atomic_write(path, canonical_json_bytes(receipt) + b"\n")
    return event
