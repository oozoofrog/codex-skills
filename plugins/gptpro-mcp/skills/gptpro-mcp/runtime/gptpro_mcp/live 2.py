"""Production authorization bridge for one foreground read-only MCP session.

This module deliberately knows nothing about ChatGPT credentials or Tunnel
profiles.  The governance script supplies package verification callbacks while
the foreground controller supplies one random capability through the child
environment.  Repository content remains unavailable unless both bindings and
the package-local audit still verify.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import math
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .analysis import AnalysisLedger
from .audit import AuditLog
from .authorization import AuthorizationGrant
from .clock import parse_utc
from .errors import ToolError
from .runtime_state import RuntimeStateError, RuntimeStateStore, open_private_regular

SESSION_CAPABILITY_ENV = "GPTPRO_MCP_SESSION_CAPABILITY"
RUNTIME_DIRECTORY_ENV = "GPTPRO_MCP_RUNTIME_DIR"
PARENT_SHUTDOWN_CONTRACT_ENV = "GPTPRO_MCP_PARENT_SHUTDOWN_CONTRACT"
_CAPABILITY_BYTES = 32
PackageLoader = Callable[[Path], dict[str, Any]]
BindingValidator = Callable[[dict[str, Any], dict[str, Any], str], None]
AuditFactory = Callable[[dict[str, Any], str], AuditLog]
AnalysisFactory = Callable[[dict[str, Any], str], AnalysisLedger]
Now = Callable[[], datetime]
Monotonic = Callable[[], float]
ControllerLiveness = Callable[[RuntimeStateStore, str], bool]


def encode_session_capability(value: bytes) -> str:
    """Return the canonical unpadded base64url form used only in child env."""

    if not isinstance(value, bytes) or len(value) != _CAPABILITY_BYTES:
        raise ValueError("session capability must contain exactly 32 random bytes")
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def decode_session_capability(value: str) -> bytes:
    """Decode a canonical 256-bit capability without accepting aliases."""

    if not isinstance(value, str) or len(value) != 43:
        raise ValueError("session capability is invalid")
    try:
        raw = base64.b64decode(value + "=", altchars=b"-_", validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("session capability is invalid") from exc
    if len(raw) != _CAPABILITY_BYTES or encode_session_capability(raw) != value:
        raise ValueError("session capability is invalid")
    return raw


def new_session_capability() -> tuple[bytes, str, str]:
    """Create raw, encoded, and hashed forms; only the hash may be persisted."""

    raw = secrets.token_bytes(_CAPABILITY_BYTES)
    encoded = encode_session_capability(raw)
    digest = hashlib.sha256(raw).hexdigest()
    return raw, encoded, digest


@dataclass(frozen=True)
class _ResolvedContext:
    grant: AuthorizationGrant
    audit: AuditLog
    analysis: AnalysisLedger | None


class ActiveRuntimeContext:
    """AuthorizationProvider and DisclosureCommitter backed by durable state."""

    def __init__(
        self,
        *,
        runtime_store: RuntimeStateStore,
        session_capability: bytes,
        package_loader: PackageLoader,
        binding_validator: BindingValidator,
        audit_factory: AuditFactory,
        analysis_factory: AnalysisFactory | None = None,
        now: Now | None = None,
        monotonic: Monotonic | None = None,
        controller_liveness: ControllerLiveness | None = None,
    ) -> None:
        if not isinstance(session_capability, bytes) or len(session_capability) != _CAPABILITY_BYTES:
            raise ValueError("session capability must contain exactly 32 bytes")
        self.runtime_store = runtime_store
        self._session_capability = session_capability
        self._session_id_sha256 = hashlib.sha256(session_capability).hexdigest()
        self._package_loader = package_loader
        self._binding_validator = binding_validator
        self._audit_factory = audit_factory
        self._analysis_factory = analysis_factory
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic or time.monotonic
        self._controller_liveness = controller_liveness or controller_lease_is_live

    def resolve(self, package_id: str) -> AuthorizationGrant:
        return self._resolve_context(package_id).grant

    def resolve_analysis_ledger(self, grant: AuthorizationGrant) -> AnalysisLedger:
        current = self._resolve_context(grant.package_id)
        if self._grant_identity(current.grant) != self._grant_identity(grant):
            raise ToolError("CONTENT_DRIFT", "The active analysis authorization changed.")
        if current.analysis is None:
            raise ToolError(
                "ANALYSIS_LEDGER_UNAVAILABLE",
                "The active package has no approved analysis ledger.",
            )
        return current.analysis

    def commit_before_return(
        self,
        *,
        grant: AuthorizationGrant,
        tool: str,
        request_id_sha256: str,
        arguments_sha256: str,
        audit_metadata: dict[str, Any],
        calls_used: int,
        disclosed_bytes: int,
    ) -> None:
        current = self._resolve_context(grant.package_id)
        if self._grant_identity(current.grant) != self._grant_identity(grant):
            raise ToolError(
                "CONTENT_DRIFT",
                "The active authorization changed before disclosure could be committed.",
                recovery="Discard this result and activate a new approved package session.",
            )
        current.audit.commit_before_return(
            grant=current.grant,
            tool=tool,
            request_id_sha256=request_id_sha256,
            arguments_sha256=arguments_sha256,
            audit_metadata=audit_metadata,
            calls_used=calls_used,
            disclosed_bytes=disclosed_bytes,
        )

    def record_rejection(
        self,
        *,
        grant: AuthorizationGrant,
        tool: str,
        request_id_sha256: str,
        arguments_sha256: str,
        error_code: str,
        calls_used: int,
    ) -> None:
        """Record a zero-disclosure rejection while authorization is still valid."""

        current = self._resolve_context(grant.package_id)
        if self._grant_identity(current.grant) != self._grant_identity(grant):
            raise ToolError("CONTENT_DRIFT", "The active authorization changed during the call.")
        try:
            current.audit.append_rejection(
                tool=tool,
                request_id_sha256=request_id_sha256,
                arguments_sha256=arguments_sha256,
                error_code=error_code,
                calls_used=calls_used,
            )
        except ValueError as exc:
            raise ToolError(
                "AUDIT_WRITE_FAILED",
                "The rejected call could not be durably audited.",
                recovery="Revoke this session and activate a new approved package session.",
            ) from exc

    def _resolve_context(self, package_id: str) -> _ResolvedContext:
        if not isinstance(package_id, str) or not package_id:
            raise ToolError("MCP_INVALID_ARGUMENT", "The package identity is invalid.")
        try:
            with self.runtime_store.locked() as transaction:
                state = transaction.read()
                if state is None or state.get("status") != "active":
                    raise ToolError(
                        "NO_ACTIVE_PACKAGE",
                        "No approved repository package is active.",
                        recovery="Activate the exact approved package before calling content tools.",
                    )
                persisted_session = str(state.get("session_id_sha256", ""))
                if not secrets.compare_digest(persisted_session, self._session_id_sha256):
                    raise ToolError(
                        "SESSION_CONFLICT",
                        "The MCP process capability does not match the active session.",
                        recovery="Stop this process and activate a new approved package session.",
                    )
                if not self._controller_liveness(self.runtime_store, self._session_id_sha256):
                    raise ToolError(
                        "NO_ACTIVE_PACKAGE",
                        "The attended foreground controller is no longer live.",
                        recovery="Revoke this orphaned session before preparing a new package.",
                    )
                if state.get("package_id") != package_id:
                    raise ToolError(
                        "PACKAGE_MISMATCH",
                        "The requested package is not the active approved package.",
                        recovery="Use the package ID from the approved prompt.",
                    )
                handoff_dir = self._handoff_dir(state)
                verified = self._package_loader(handoff_dir)
                self._binding_validator(verified, state, self._session_id_sha256)
                self._validate_verified_paths(verified, handoff_dir)
                audit = self._audit_factory(verified, self._session_id_sha256)
                summary = audit.verify()
                if summary.footer or summary.header_sha256 != state.get("audit_header_sha256"):
                    raise ToolError(
                        "AUDIT_CHAIN_INVALID",
                        "The disclosure audit does not match the active authorization.",
                        recovery="Revoke this session and inspect its audit evidence.",
                    )
                analysis: AnalysisLedger | None = None
                if int(verified.get("schema_version", 0)) == 4:
                    if self._analysis_factory is None:
                        raise ToolError(
                            "ANALYSIS_LEDGER_UNAVAILABLE",
                            "The schema-4 analysis provider is unavailable.",
                        )
                    analysis = self._analysis_factory(verified, self._session_id_sha256)
                    analysis_summary = analysis.verify()
                    if (
                        analysis_summary.closed
                        or analysis_summary.header_sha256 != state.get("analysis_header_sha256")
                    ):
                        raise ToolError(
                            "ANALYSIS_LEDGER_INVALID",
                            "The analysis ledger does not match the active authorization.",
                        )
                monotonic_now = self._monotonic_now()
                activated_monotonic = self._state_monotonic(state, "activated_monotonic")
                expires_monotonic = self._state_monotonic(state, "expires_monotonic")
                last_activity_monotonic = self._state_monotonic(
                    state, "last_activity_monotonic"
                )
                if (
                    monotonic_now < activated_monotonic
                    or monotonic_now < last_activity_monotonic
                ):
                    raise ToolError(
                        "RUNTIME_STATE_UNSAFE",
                        "The monotonic runtime clock moved behind persisted session state.",
                        recovery="Revoke this session and activate a new approved package.",
                    )
                if monotonic_now >= expires_monotonic:
                    raise ToolError(
                        "SESSION_EXPIRED",
                        "The approved package session has expired.",
                        recovery="Stop this session and activate a newly approved package.",
                    )
                expires_at = parse_utc(str(state.get("expires_at", "")))
                activated_at = parse_utc(str(state.get("activated_at", "")))
                idle_ttl = state.get("idle_ttl_seconds")
                if isinstance(idle_ttl, bool) or not isinstance(idle_ttl, int) or idle_ttl <= 0:
                    raise ToolError("PACKAGE_TAMPERED", "The approved idle timeout is invalid.")
                idle_deadline_monotonic = min(
                    expires_monotonic, last_activity_monotonic + idle_ttl
                )
                if monotonic_now >= idle_deadline_monotonic:
                    raise ToolError(
                        "IDLE_TIMEOUT",
                        "The approved package session reached its idle timeout.",
                        recovery="Stop this session and activate a newly approved package.",
                    )
                effective_now = max(
                    self._aware_now(),
                    activated_at
                    + timedelta(seconds=monotonic_now - activated_monotonic),
                )
                idle_expires_at = min(
                    expires_at,
                    activated_at
                    + timedelta(
                        seconds=last_activity_monotonic
                        - activated_monotonic
                        + idle_ttl
                    ),
                )
                manifest = verified.get("manifest")
                if not isinstance(manifest, dict):
                    raise ToolError("PACKAGE_TAMPERED", "The approved package manifest is invalid.")
                grant = AuthorizationGrant(
                    package_id=package_id,
                    manifest=manifest,
                    archive_path=Path(verified["archive_path"]),
                    archive_sha256=str(state["archive_sha256"]),
                    manifest_sha256=str(state["manifest_sha256"]),
                    session_id_sha256=self._session_id_sha256,
                    session_nonce=self._session_capability,
                    expires_at=expires_at,
                    idle_expires_at=idle_expires_at,
                )
                grant.validate(package_id, now=effective_now)
                current = _ResolvedContext(grant=grant, audit=audit, analysis=analysis)
                return current
        except ToolError:
            raise
        except RuntimeStateError as exc:
            raise ToolError(
                exc.code,
                "The private MCP authorization state is unavailable.",
                retryable=exc.retryable,
                recovery="Stop this session and activate a new approved package session.",
            ) from exc
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise ToolError(
                "PACKAGE_TAMPERED",
                "The active approved package could not be revalidated.",
                recovery="Revoke this session and prepare a new approved package.",
            ) from exc
        except Exception as exc:
            # Governance errors may contain absolute local paths.  Do not reflect them.
            raise ToolError(
                "PACKAGE_TAMPERED",
                "The active approved package could not be revalidated.",
                recovery="Revoke this session and prepare a new approved package.",
            ) from exc

    def _handoff_dir(self, state: Mapping[str, Any]) -> Path:
        raw = state.get("handoff_dir")
        if not isinstance(raw, str):
            raise ToolError("RUNTIME_STATE_UNSAFE", "The active handoff location is invalid.")
        path = Path(raw)
        if not path.is_absolute():
            raise ToolError("RUNTIME_STATE_UNSAFE", "The active handoff location is invalid.")
        resolved = path.resolve(strict=True)
        if resolved != path or not resolved.is_dir():
            raise ToolError("RUNTIME_STATE_UNSAFE", "The active handoff location is unsafe.")
        metadata = resolved.lstat()
        if metadata.st_uid != os.getuid() or metadata.st_mode & 0o022:
            raise ToolError("RUNTIME_STATE_UNSAFE", "The active handoff directory is not owner-controlled.")
        return resolved

    @staticmethod
    def _validate_verified_paths(verified: Mapping[str, Any], handoff_dir: Path) -> None:
        manifest_path = Path(verified.get("manifest_path", ""))
        archive_path = Path(verified.get("archive_path", ""))
        if manifest_path.parent.resolve(strict=True) != handoff_dir:
            raise ToolError("PACKAGE_TAMPERED", "The verified manifest escaped its handoff directory.")
        if archive_path.parent.resolve(strict=True) != handoff_dir:
            raise ToolError("PACKAGE_TAMPERED", "The verified archive escaped its handoff directory.")

    def _aware_now(self) -> datetime:
        value = self._now()
        if not isinstance(value, datetime) or value.tzinfo is None:
            raise ToolError("RUNTIME_STATE_UNSAFE", "The runtime clock is invalid.")
        return value.astimezone(timezone.utc)

    def _monotonic_now(self) -> float:
        value = self._monotonic()
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ToolError("RUNTIME_STATE_UNSAFE", "The monotonic runtime clock is invalid.")
        return float(value)

    @staticmethod
    def _state_monotonic(state: Mapping[str, Any], key: str) -> float:
        value = state.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ToolError("RUNTIME_STATE_UNSAFE", "The persisted monotonic session bound is invalid.")
        return float(value)

    @staticmethod
    def _grant_identity(grant: AuthorizationGrant) -> tuple[str, ...]:
        return (
            grant.package_id,
            grant.session_id_sha256,
            grant.manifest_sha256,
            grant.archive_sha256,
        )


class RuntimeServerLease:
    """Hold a non-blocking per-session flock for the stdio server lifetime."""

    def __init__(self, runtime_store: RuntimeStateStore, session_id_sha256: str) -> None:
        if not isinstance(session_id_sha256, str) or len(session_id_sha256) != 64:
            raise ValueError("session hash is invalid")
        try:
            int(session_id_sha256, 16)
        except ValueError as exc:
            raise ValueError("session hash is invalid") from exc
        self.path = runtime_store.root / f"server-{session_id_sha256}.lock"
        self._descriptor: int | None = None

    def acquire(self) -> "RuntimeServerLease":
        descriptor = open_private_regular(self.path, flags=os.O_RDWR, create=True)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(descriptor)
            raise RuntimeStateError(
                "SESSION_CONFLICT", "Another MCP server already owns this active session."
            ) from exc
        self._descriptor = descriptor
        return self

    def close(self) -> None:
        if self._descriptor is None:
            return
        try:
            fcntl.flock(self._descriptor, fcntl.LOCK_UN)
        finally:
            os.close(self._descriptor)
            self._descriptor = None

    def __enter__(self) -> "RuntimeServerLease":
        return self.acquire()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        del exc_type, exc, traceback
        self.close()


class ControllerLease:
    """CLOEXEC flock proving the attended foreground controller is alive."""

    def __init__(self, runtime_store: RuntimeStateStore, session_id_sha256: str) -> None:
        _validate_session_hash(session_id_sha256)
        self.path = runtime_store.root / f"controller-{session_id_sha256}.lock"
        self._descriptor: int | None = None

    def acquire(self) -> "ControllerLease":
        return self._acquire(create=True)

    def acquire_existing(self) -> "ControllerLease":
        """Acquire only a pre-existing safe lease file; never infer absence as unlocked."""

        return self._acquire(create=False)

    def _acquire(self, *, create: bool) -> "ControllerLease":
        descriptor = open_private_regular(self.path, flags=os.O_RDWR, create=create)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(descriptor)
            raise RuntimeStateError(
                "SESSION_CONFLICT", "Another controller already owns this session."
            ) from exc
        self._descriptor = descriptor
        return self

    def close(self) -> None:
        if self._descriptor is None:
            return
        try:
            fcntl.flock(self._descriptor, fcntl.LOCK_UN)
        finally:
            os.close(self._descriptor)
            self._descriptor = None

    def __enter__(self) -> "ControllerLease":
        return self.acquire()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        del exc_type, exc, traceback
        self.close()


def controller_lease_is_live(
    runtime_store: RuntimeStateStore, session_id_sha256: str
) -> bool:
    """Fail closed unless another process still holds the exact controller flock."""

    _validate_session_hash(session_id_sha256)
    path = runtime_store.root / f"controller-{session_id_sha256}.lock"
    try:
        descriptor = open_private_regular(path, flags=os.O_RDWR)
    except RuntimeStateError:
        return False
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        else:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            return False
    finally:
        os.close(descriptor)


def _validate_session_hash(value: str) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("session hash is invalid")
    try:
        int(value, 16)
    except ValueError as exc:
        raise ValueError("session hash is invalid") from exc
