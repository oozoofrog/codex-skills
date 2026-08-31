"""Validate the owner-only local ChatGPT App companion without exposing its ID."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .state import DesktopStateError, read_private_json

DESKTOP_APP_BINDING_CONTRACT = "gptpro-desktop-app-binding-v1"
DESKTOP_APP_KEY = "gpt-pro-collaborator"


def _pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inspect_desktop_app_binding(state_root: Path) -> dict[str, Any]:
    """Return sanitized, observation-only binding readiness."""

    root = Path(state_root)
    binding_path = root / "companion" / "app-binding.json"
    try:
        binding = read_private_json(binding_path)
    except DesktopStateError as exc:
        if exc.code == "DESKTOP_STATE_NOT_FOUND":
            return {"status": "absent", "code": None, "path": str(binding_path)}
        return {"status": "unsafe", "code": exc.code, "path": str(binding_path)}

    expected_keys = {
        "schema",
        "recorded_at",
        "app_key",
        "app_id_sha256",
        "plugin_root",
        "plugin_manifest_sha256",
        "raw_app_id_stored_only_in_private_app_manifest",
    }
    if not isinstance(binding, dict) or set(binding) != expected_keys:
        return {
            "status": "invalid",
            "code": "DESKTOP_APP_BINDING_INVALID",
            "path": str(binding_path),
        }
    plugin_root = root / "companion" / "gptpro-desktop-app"
    if (
        binding.get("schema") != DESKTOP_APP_BINDING_CONTRACT
        or binding.get("app_key") != DESKTOP_APP_KEY
        or binding.get("plugin_root") != str(plugin_root)
        or binding.get("raw_app_id_stored_only_in_private_app_manifest") is not True
        or not isinstance(binding.get("app_id_sha256"), str)
        or not isinstance(binding.get("plugin_manifest_sha256"), str)
    ):
        return {
            "status": "invalid",
            "code": "DESKTOP_APP_BINDING_INVALID",
            "path": str(binding_path),
        }
    try:
        plugin = read_private_json(plugin_root / ".codex-plugin" / "plugin.json")
        app_manifest = read_private_json(plugin_root / ".app.json")
    except DesktopStateError as exc:
        return {"status": "unsafe", "code": exc.code, "path": str(binding_path)}
    app_entry = (
        app_manifest.get("apps", {}).get(DESKTOP_APP_KEY)
        if isinstance(app_manifest, dict)
        else None
    )
    app_id = app_entry.get("id") if isinstance(app_entry, dict) else None
    if (
        not isinstance(plugin, dict)
        or plugin.get("apps") != "./.app.json"
        or _sha256(_pretty_bytes(plugin)) != binding["plugin_manifest_sha256"]
        or not isinstance(app_id, str)
        or not app_id
        or _sha256(app_id.encode("utf-8")) != binding["app_id_sha256"]
    ):
        return {
            "status": "invalid",
            "code": "DESKTOP_APP_BINDING_INVALID",
            "path": str(binding_path),
        }
    return {
        "status": "verified",
        "code": None,
        "path": str(binding_path),
        "contract": DESKTOP_APP_BINDING_CONTRACT,
        "app_id_sha256": binding["app_id_sha256"],
    }
