"""Public Desktop-UI handoff boundary for gptpro."""

from .approval import (
    DESKTOP_APPROVAL_CONTRACT,
    build_desktop_approval,
    desktop_approval_digest,
    list_desktop_approvals,
    load_desktop_approval,
    match_desktop_approval,
    revoke_desktop_approval,
    store_desktop_approval,
    validate_desktop_approval,
)
from .contract import (
    DESKTOP_HANDOFF_CONTRACT,
    DESKTOP_OBSERVATION_CONTRACT,
    build_handoff_plan,
    deterministic_response_wrapper,
    request_nonce_for,
    validate_response_observation,
    validate_submission_observation,
)
from .binding import (
    DESKTOP_APP_BINDING_CONTRACT,
    inspect_desktop_app_binding,
)
from .state import (
    DesktopStateError,
    atomic_write_private,
    list_private_json,
    platform_state_root,
    read_private_json,
    secure_directory,
    write_private_json,
)

__all__ = [
    "DESKTOP_APPROVAL_CONTRACT",
    "DESKTOP_APP_BINDING_CONTRACT",
    "DESKTOP_HANDOFF_CONTRACT",
    "DESKTOP_OBSERVATION_CONTRACT",
    "DesktopStateError",
    "atomic_write_private",
    "build_desktop_approval",
    "build_handoff_plan",
    "desktop_approval_digest",
    "deterministic_response_wrapper",
    "list_desktop_approvals",
    "list_private_json",
    "load_desktop_approval",
    "inspect_desktop_app_binding",
    "match_desktop_approval",
    "platform_state_root",
    "read_private_json",
    "request_nonce_for",
    "revoke_desktop_approval",
    "secure_directory",
    "store_desktop_approval",
    "validate_desktop_approval",
    "validate_response_observation",
    "validate_submission_observation",
    "write_private_json",
]
