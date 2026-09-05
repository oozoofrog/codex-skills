"""Schema-6 inline Desktop consultation constants."""

from __future__ import annotations

CHAT_HISTORY_MODE = "normal"
CONTEXT_TRANSPORT = "inline-immutable-snapshot"
DELIVERY_CHANNEL = "desktop-electron"
INLINE_FORMAT = "gptpro-inline-context-v1"
MAX_OUTBOUND_BYTES = 256 * 1024
DEFAULT_MODEL_ID = "gpt-5-6-pro"

__all__ = [
    "CHAT_HISTORY_MODE",
    "CONTEXT_TRANSPORT",
    "DEFAULT_MODEL_ID",
    "DELIVERY_CHANNEL",
    "INLINE_FORMAT",
    "MAX_OUTBOUND_BYTES",
]
