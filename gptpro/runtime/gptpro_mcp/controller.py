"""Foreground lifecycle coordinator for one approved Web MCP package.

The caller owns attended Tunnel profile setup, ``doctor`` verification, and
package governance.  This module owns only the short-lived execution boundary:
begin an already-preflighted activation, start exactly one official
``tunnel-client run`` child, require its control-plane-aware health check, and
revoke authorization before stopping that exact child.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .live import (
    ControllerLease,
    RUNTIME_DIRECTORY_ENV,
    SESSION_CAPABILITY_ENV,
    decode_session_capability,
    new_session_capability,
)
from .request_correlation import (
    derive_request_correlation_key,
    unavailable_request_correlation,
)
from .runtime_state import RuntimeStateError, RuntimeStateStore, ensure_private_directory
from .supervisor import ForegroundSupervisor, SupervisorResult
from .tunnel_client import (
    TunnelCheck,
    TunnelClientError,
    TunnelRuntimeFiles,
    prepare_runtime_files,
)

_SHA256 = re.compile(r"[0-9a-f]{64}")
_ERROR_CODE = re.compile(r"[A-Z][A-Z0-9_]{1,63}")
_PROFILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_MAX_UNIX_SOCKET_PATH_BYTES = 100


@dataclass
class ControllerError(Exception):
    """Stable, non-secret lifecycle failure."""

    code: str
    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.code


@dataclass(frozen=True)
class ActiveSession:
    """Non-secret evidence emitted only after activation becomes usable."""

    status: str
    session_id_sha256: str
    control_socket: Path
    control_plane_poll_confirmed: bool


@dataclass(frozen=True)
class ControllerResult:
    """Terminal, non-secret result of one foreground controller run."""

    status: str
    session_id_sha256: str
    stop_reason: str
    control_plane_poll_confirmed: bool
    child_returncode: int | None
    terminated_exact_child: bool
    forced_exact_child: bool
    authorization_revoked: bool
    stopped_recorded: bool
    request_correlation: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ControllerHooks:
    """Governance callbacks supplied by ``gptpro.py``.

    Callbacks should be package-bound closures.  The controller never reads or
    rewrites package receipts itself.
    """

    begin_activation: Callable[[str], Mapping[str, Any]]
    complete_activation: Callable[[str, str], Any]
    fail_activation: Callable[[str, str], None]
    revoke_authorization: Callable[[str], Any]
    record_stopped: Callable[[str, str], None]
    on_active: Callable[[ActiveSession], None] | None = None


class TunnelRuntime(Protocol):
    def spawn_run(
        self,
        profile: str,
        *,
        env: Mapping[str, str],
        runtime_files: TunnelRuntimeFiles,
        extra_env: Mapping[str, str] | None = None,
        profile_dir: Path | None = None,
        cwd: Path | None = None,
        request_correlation_diagnostic: bool = False,
    ) -> subprocess.Popen[bytes]: ...

    def health(
        self,
        files: TunnelRuntimeFiles,
        *,
        env: Mapping[str, str],
        expected_pid: int,
    ) -> TunnelCheck: ...

    def capture_request_correlation(
        self,
        files: TunnelRuntimeFiles,
        *,
        hmac_key: bytes,
    ) -> Mapping[str, Any]: ...


def control_socket_path(runtime_root: Path) -> Path:
    """Return the one deterministic socket for the machine-global active slot."""

    root = ensure_private_directory(Path(runtime_root).expanduser())
    path = root / "control.sock"
    if len(os.fsencode(path)) > _MAX_UNIX_SOCKET_PATH_BYTES:
        raise ControllerError(
            "RUNTIME_STATE_UNSAFE",
            "The private runtime directory is too long for a local control socket.",
        )
    return path


def run_foreground(
    *,
    tunnel_client: TunnelRuntime,
    runtime_store: RuntimeStateStore,
    tunnel_profile: str,
    child_environment: Mapping[str, str],
    hooks: ControllerHooks,
    profile_dir: Path | None = None,
    cwd: Path | None = None,
    ready_timeout: float = 60.0,
    health_poll_interval: float = 0.2,
    stop_timeout: float = 5.0,
    capability_factory: Callable[[], tuple[bytes, str, str]] = new_session_capability,
    runtime_files_factory: Callable[..., TunnelRuntimeFiles] = prepare_runtime_files,
    supervisor_factory: Callable[..., ForegroundSupervisor] = ForegroundSupervisor,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    request_correlation_diagnostic: bool = False,
) -> ControllerResult:
    """Run one approved package until an attended or child-exit stop.

    ``doctor`` and package preflight must already have succeeded.  This function
    never initializes a profile, starts a daemon, discovers a process by name,
    or exposes the transient capability in its result.
    """

    _validate_inputs(
        tunnel_profile=tunnel_profile,
        ready_timeout=ready_timeout,
        health_poll_interval=health_poll_interval,
        stop_timeout=stop_timeout,
        request_correlation_diagnostic=request_correlation_diagnostic,
    )
    environment = dict(child_environment)
    raw_capability, encoded_capability, session_id_sha256 = capability_factory()
    if not isinstance(raw_capability, bytes) or len(raw_capability) != 32:
        raise ControllerError("SESSION_CONFLICT", "The generated session capability is invalid.")
    try:
        decoded_capability = decode_session_capability(encoded_capability)
    except (TypeError, ValueError) as exc:
        raise ControllerError(
            "SESSION_CONFLICT", "The generated session capability is invalid."
        ) from exc
    if (
        decoded_capability != raw_capability
        or not isinstance(session_id_sha256, str)
        or _SHA256.fullmatch(session_id_sha256) is None
        or hashlib.sha256(raw_capability).hexdigest() != session_id_sha256
    ):
        raise ControllerError("SESSION_CONFLICT", "The generated session identity is invalid.")
    request_correlation_key = (
        derive_request_correlation_key(raw_capability)
        if request_correlation_diagnostic
        else None
    )
    del decoded_capability, raw_capability

    begun = False
    activation_completed = False
    failure_attempted = False
    revocation_succeeded = False
    stopped_recorded = False
    process_started = False
    health_confirmed = False
    stop_reason = "controller_exit"
    failure_code = "MCP_ACTIVATION_FAILED"
    audit_header_sha256 = ""
    supervisor_result: SupervisorResult | None = None
    request_correlation_report: Mapping[str, Any] | None = None

    def mark_failed(code: str) -> None:
        nonlocal failure_attempted
        if failure_attempted or not begun or activation_completed:
            return
        failure_attempted = True
        hooks.fail_activation(session_id_sha256, _safe_code(code, "MCP_ACTIVATION_FAILED"))

    controller_lease = ControllerLease(runtime_store, session_id_sha256).acquire()
    try:
        try:
            begin_result = hooks.begin_activation(session_id_sha256)
            begun = True
            audit_header_sha256 = str(begin_result.get("audit_header_sha256", ""))
            if _SHA256.fullmatch(audit_header_sha256) is None:
                raise ControllerError(
                    "AUDIT_CHAIN_INVALID", "Activation did not create a valid audit header."
                )
            _require_runtime_status(runtime_store, session_id_sha256, {"activating"})
        except Exception:
            # A governance callback may have durably begun and then reported a
            # package-side failure.  Detect that exact session so it is denied.
            if not begun:
                begun = _runtime_matches(
                    runtime_store, session_id_sha256, {"activating", "active"}
                )
            raise

        runtime_files = runtime_files_factory(
            runtime_store.root, session_id_sha256=session_id_sha256
        )
        socket_path = control_socket_path(runtime_store.root)

        child_extra_environment = {
            SESSION_CAPABILITY_ENV: encoded_capability,
            RUNTIME_DIRECTORY_ENV: str(runtime_store.root),
        }

        def process_factory() -> subprocess.Popen[bytes]:
            nonlocal failure_code, process_started
            try:
                process = tunnel_client.spawn_run(
                    tunnel_profile,
                    env=environment,
                    runtime_files=runtime_files,
                    extra_env=child_extra_environment,
                    profile_dir=profile_dir,
                    cwd=cwd,
                    request_correlation_diagnostic=request_correlation_diagnostic,
                )
            except Exception as exc:
                failure_code = _exception_code(exc, "TUNNEL_NOT_READY")
                raise
            process_started = True
            return process

        def after_start(process: subprocess.Popen[bytes]) -> None:
            nonlocal activation_completed, failure_code, health_confirmed
            deadline = monotonic() + ready_timeout
            while True:
                if process.poll() is not None:
                    failure_code = "TUNNEL_EXITED"
                    raise ControllerError(
                        failure_code,
                        "The foreground Tunnel process exited before activation completed.",
                    )
                try:
                    check = tunnel_client.health(
                        runtime_files,
                        env=environment,
                        expected_pid=process.pid,
                    )
                except Exception as exc:
                    code = _exception_code(exc, "TUNNEL_NOT_READY")
                    retryable = bool(getattr(exc, "retryable", False)) or code == "TUNNEL_NOT_READY"
                    if not retryable:
                        failure_code = code
                        raise _as_controller_error(exc, code) from None
                    check = None
                if check is not None and check.ok:
                    if not check.control_plane_poll_confirmed:
                        failure_code = "TUNNEL_CONTROL_PLANE_UNCONFIRMED"
                        raise ControllerError(
                            failure_code,
                            "Tunnel health did not confirm a successful control-plane poll.",
                        )
                    if process.poll() is not None:
                        failure_code = "TUNNEL_EXITED"
                        raise ControllerError(
                            failure_code,
                            "The foreground Tunnel process exited during activation.",
                        )
                    health_confirmed = True
                    try:
                        hooks.complete_activation(session_id_sha256, audit_header_sha256)
                        _require_runtime_status(runtime_store, session_id_sha256, {"active"})
                    except Exception as exc:
                        failure_code = _exception_code(exc, "MCP_ACTIVATION_FAILED")
                        raise
                    activation_completed = True
                    if hooks.on_active is not None:
                        hooks.on_active(
                            ActiveSession(
                                status="active",
                                session_id_sha256=session_id_sha256,
                                control_socket=socket_path,
                                control_plane_poll_confirmed=True,
                            )
                        )
                    return
                if check is not None and check.code not in {None, "TUNNEL_NOT_READY"}:
                    failure_code = _safe_code(check.code, "TUNNEL_NOT_READY")
                    raise ControllerError(failure_code, "Tunnel health validation failed.", check.retryable)
                if monotonic() >= deadline:
                    failure_code = "TUNNEL_READY_TIMEOUT"
                    raise ControllerError(
                        failure_code,
                        "The foreground Tunnel did not become ready before the timeout.",
                        retryable=True,
                    )
                sleep(min(health_poll_interval, max(0.0, deadline - monotonic())))

        def revoke_before_terminate(reason: str) -> None:
            nonlocal request_correlation_key, request_correlation_report
            nonlocal revocation_succeeded, stop_reason
            stop_reason = reason
            if activation_completed:
                hooks.revoke_authorization(reason)
                _require_runtime_status(
                    runtime_store, session_id_sha256, {"revoked", "expired", "faulted"}
                )
                revocation_succeeded = True
                if request_correlation_diagnostic:
                    try:
                        if request_correlation_key is None:
                            raise ControllerError(
                                "REQUEST_CORRELATION_KEY_INVALID",
                                "The request-correlation key is unavailable.",
                            )
                        request_correlation_report = tunnel_client.capture_request_correlation(
                            runtime_files,
                            hmac_key=request_correlation_key,
                        )
                    except Exception as exc:
                        request_correlation_report = unavailable_request_correlation(
                            _exception_code(exc, "REQUEST_CORRELATION_UNAVAILABLE")
                        )
                    finally:
                        request_correlation_key = None
            else:
                mark_failed(failure_code)

        supervisor = supervisor_factory(
            process_factory=process_factory,
            control_socket=socket_path,
            session_id_sha256=session_id_sha256,
            revoke_before_terminate=revoke_before_terminate,
            after_start=after_start,
            stop_timeout=stop_timeout,
        )
        supervisor_error: BaseException | None = None
        try:
            supervisor_result = supervisor.run()
        except BaseException as exc:
            supervisor_error = exc

        # Never persist stopped evidence when exact-child cleanup raised or did
        # not produce an observed return code. Authorization may already be
        # denied, but that is distinct from proving process termination.
        if supervisor_error is not None:
            raise supervisor_error
        if supervisor_result is None or supervisor_result.child_returncode is None:
            raise ControllerError(
                "TUNNEL_STOP_UNCONFIRMED",
                "The exact Tunnel child termination could not be confirmed.",
            )

        # The supervisor has now completed revoke-first cleanup and observed
        # the exact child's terminal return code before package evidence is written.
        if activation_completed and revocation_succeeded:
            try:
                hooks.record_stopped(session_id_sha256, stop_reason)
                stopped_recorded = True
            except Exception as exc:
                raise _as_controller_error(exc, "MCP_STOP_RECORD_FAILED") from None
    except BaseException as exc:
        try:
            mark_failed(_exception_code(exc, failure_code))
        except Exception as fail_exc:
            raise _as_controller_error(fail_exc, "MCP_ACTIVATION_FAILED") from None
        if isinstance(exc, KeyboardInterrupt):
            raise
        raise _as_controller_error(exc, failure_code) from None
    finally:
        request_correlation_key = None
        controller_lease.close()

    if supervisor_result is None:
        raise ControllerError("MCP_ACTIVATION_FAILED", "The foreground supervisor did not run.")
    return ControllerResult(
        status="stopped",
        session_id_sha256=session_id_sha256,
        stop_reason=stop_reason,
        control_plane_poll_confirmed=health_confirmed,
        child_returncode=supervisor_result.child_returncode,
        terminated_exact_child=supervisor_result.terminated,
        forced_exact_child=supervisor_result.forced_exact_child,
        authorization_revoked=revocation_succeeded,
        stopped_recorded=stopped_recorded,
        request_correlation=request_correlation_report,
    )


def _validate_inputs(
    *,
    tunnel_profile: str,
    ready_timeout: float,
    health_poll_interval: float,
    stop_timeout: float,
    request_correlation_diagnostic: bool,
) -> None:
    if not isinstance(tunnel_profile, str) or _PROFILE.fullmatch(tunnel_profile) is None:
        raise ControllerError("MCP_INVALID_ARGUMENT", "The Tunnel profile alias is invalid.")
    for value, label in (
        (ready_timeout, "readiness timeout"),
        (health_poll_interval, "health poll interval"),
        (stop_timeout, "stop timeout"),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 300:
            raise ControllerError("MCP_INVALID_ARGUMENT", f"The {label} is invalid.")
    if health_poll_interval > ready_timeout:
        raise ControllerError(
            "MCP_INVALID_ARGUMENT", "The health poll interval exceeds the readiness timeout."
        )
    if not isinstance(request_correlation_diagnostic, bool):
        raise ControllerError(
            "MCP_INVALID_ARGUMENT",
            "The request-correlation diagnostic flag is invalid.",
        )


def _runtime_matches(
    store: RuntimeStateStore, session_id_sha256: str, statuses: set[str]
) -> bool:
    try:
        state = store.read()
    except RuntimeStateError:
        return False
    return bool(
        state is not None
        and state.get("session_id_sha256") == session_id_sha256
        and state.get("status") in statuses
    )


def _require_runtime_status(
    store: RuntimeStateStore, session_id_sha256: str, statuses: set[str]
) -> Mapping[str, Any]:
    try:
        state = store.read()
    except RuntimeStateError as exc:
        raise _as_controller_error(exc, "RUNTIME_STATE_UNSAFE") from None
    if (
        state is None
        or state.get("session_id_sha256") != session_id_sha256
        or state.get("status") not in statuses
    ):
        raise ControllerError(
            "SESSION_CONFLICT", "The machine-global runtime state differs from this controller."
        )
    return state


def _safe_code(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) and _ERROR_CODE.fullmatch(value) else fallback


def _exception_code(exc: BaseException, fallback: str) -> str:
    return _safe_code(getattr(exc, "code", None), fallback)


def _as_controller_error(exc: BaseException, fallback: str) -> ControllerError:
    if isinstance(exc, ControllerError):
        return exc
    code = _exception_code(exc, fallback)
    retryable = bool(getattr(exc, "retryable", False))
    if isinstance(exc, TunnelClientError):
        return ControllerError(code, "The official Tunnel client operation failed.", retryable)
    if isinstance(exc, RuntimeStateError):
        return ControllerError(code, "The private runtime state operation failed.", retryable)
    return ControllerError(code, "The foreground MCP lifecycle operation failed.", retryable)
