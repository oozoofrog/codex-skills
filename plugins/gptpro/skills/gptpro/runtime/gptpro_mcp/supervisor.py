"""Foreground-only ownership and cooperative stop for one tunnel-client process."""

from __future__ import annotations

import json
import os
import re
import selectors
import secrets
import signal
import socket
import stat
import struct
import subprocess
import sys
import threading
import time
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, ContextManager

from .runtime_state import RuntimeStateError, ensure_private_directory

_MAX_CONTROL_FRAME_BYTES = 4096
_STOP_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
_CONTROL_SOCKET_PROOF_BYTES = 32
_CONTROL_SOCKET_PROOF_TIMEOUT_SECONDS = 0.5


def block_stop_signals() -> set[signal.Signals] | None:
    """Block lifecycle stop signals and return the caller's prior mask."""

    if threading.current_thread() is not threading.main_thread():
        return None
    pthread_sigmask = getattr(signal, "pthread_sigmask", None)
    if pthread_sigmask is None:
        raise RuntimeStateError(
            "CONTROL_SIGNAL_UNSAFE",
            "The foreground supervisor cannot safely order stop signals.",
        )
    try:
        return pthread_sigmask(signal.SIG_BLOCK, _STOP_SIGNALS)
    except (OSError, ValueError) as exc:
        raise RuntimeStateError(
            "CONTROL_SIGNAL_UNSAFE",
            "The foreground supervisor could not block stop signals.",
        ) from exc


def restore_stop_signal_mask(previous: set[signal.Signals] | None) -> None:
    """Restore a mask returned by :func:`block_stop_signals`."""

    if previous is None:
        return
    try:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)
    except (OSError, ValueError) as exc:
        raise RuntimeStateError(
            "CONTROL_SIGNAL_UNSAFE",
            "The foreground supervisor could not restore its signal mask.",
        ) from exc


def _control_socket_metadata(path: Path) -> os.stat_result:
    """lstat one control-socket name through its already validated parent."""

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    parent_descriptor = os.open(path.parent, flags)
    try:
        return os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
    finally:
        os.close(parent_descriptor)


def _control_socket_peer_pid(connection: socket.socket) -> int:
    """Return the peer PID for a connected local Unix-domain socket."""

    try:
        if sys.platform == "darwin":
            raw = connection.getsockopt(
                getattr(socket, "SOL_LOCAL", 0),
                getattr(socket, "LOCAL_PEERPID", 2),
                struct.calcsize("i"),
            )
            peer_pid = struct.unpack("i", raw)[0]
        elif sys.platform.startswith("linux") and hasattr(socket, "SO_PEERCRED"):
            raw = connection.getsockopt(
                socket.SOL_SOCKET,
                socket.SO_PEERCRED,
                struct.calcsize("3i"),
            )
            peer_pid, _, _ = struct.unpack("3i", raw)
        else:
            raise OSError("Unix peer PID verification is unavailable")
    except (OSError, TypeError, ValueError, struct.error) as exc:
        raise RuntimeStateError(
            "CONTROL_LISTENER_FAILED",
            "The staged supervisor socket peer could not be verified.",
        ) from exc
    if peer_pid <= 0:
        raise RuntimeStateError(
            "CONTROL_LISTENER_FAILED",
            "The staged supervisor socket peer could not be verified.",
        )
    return peer_pid


def _recv_exact(connection: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = connection.recv(remaining)
        if not chunk:
            raise OSError("control socket proof ended early")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _prove_control_socket_listener_path(
    listener: socket.socket,
    path: Path,
) -> None:
    """Prove that ``path`` currently routes to ``listener`` in this process.

    A pathname lstat cannot prove which listening file descriptor owns that
    directory entry.  A same-UID process could replace the staged name between
    bind and the first metadata read.  A bidirectional nonce exchange plus
    peer-PID checks binds the pathname to this exact process/listener before
    its filesystem identity is trusted for publication or cleanup.
    """

    challenge = secrets.token_bytes(_CONTROL_SOCKET_PROOF_BYTES)
    response = secrets.token_bytes(_CONTROL_SOCKET_PROOF_BYTES)
    probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    accepted: socket.socket | None = None
    previous_timeout = listener.gettimeout()
    try:
        listener.settimeout(_CONTROL_SOCKET_PROOF_TIMEOUT_SECONDS)
        probe.settimeout(_CONTROL_SOCKET_PROOF_TIMEOUT_SECONDS)
        probe.connect(str(path))
        accepted, _ = listener.accept()
        accepted.settimeout(_CONTROL_SOCKET_PROOF_TIMEOUT_SECONDS)
        expected_pid = os.getpid()
        if (
            _control_socket_peer_pid(probe) != expected_pid
            or _control_socket_peer_pid(accepted) != expected_pid
        ):
            raise RuntimeStateError(
                "CONTROL_LISTENER_FAILED",
                "The staged supervisor socket was connected by an unexpected process.",
            )
        probe.sendall(challenge)
        if not secrets.compare_digest(_recv_exact(accepted, len(challenge)), challenge):
            raise RuntimeStateError(
                "CONTROL_LISTENER_FAILED",
                "The staged supervisor socket proof did not reach the owned listener.",
            )
        accepted.sendall(response)
        if not secrets.compare_digest(_recv_exact(probe, len(response)), response):
            raise RuntimeStateError(
                "CONTROL_LISTENER_FAILED",
                "The staged supervisor socket proof did not return to the owned client.",
            )
    except RuntimeStateError:
        raise
    except (OSError, TimeoutError) as exc:
        raise RuntimeStateError(
            "CONTROL_LISTENER_FAILED",
            "The staged supervisor socket could not be proven to belong to this listener.",
        ) from exc
    finally:
        if accepted is not None:
            accepted.close()
        probe.close()
        listener.settimeout(previous_timeout)


def _claim_and_unlink_control_socket_if_matches(
    path: Path, identity: tuple[int, int]
) -> bool:
    """Atomically claim and unlink only the expected control-socket inode.

    A plain stat-then-unlink sequence can delete a same-UID replacement that
    appears between those two operations.  Move the current directory entry
    into a fresh private quarantine first, verify the inode actually moved,
    and delete only that claimed inode.  If a replacement won the race, put
    it back with an atomic no-clobber hard link and retain it.
    """

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    parent_descriptor = os.open(path.parent, flags)
    quarantine_name = f".gptpro-control-quarantine-{secrets.token_hex(16)}"
    quarantine_descriptor: int | None = None
    try:
        os.mkdir(quarantine_name, mode=0o700, dir_fd=parent_descriptor)
        quarantine_descriptor = os.open(
            quarantine_name,
            flags,
            dir_fd=parent_descriptor,
        )
        metadata = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        if not (
            stat.S_ISSOCK(metadata.st_mode)
            and metadata.st_uid == os.getuid()
            and (metadata.st_dev, metadata.st_ino) == identity
        ):
            return False

        claim_name = "control.sock"
        os.rename(
            path.name,
            claim_name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=quarantine_descriptor,
        )
        claimed = os.stat(
            claim_name,
            dir_fd=quarantine_descriptor,
            follow_symlinks=False,
        )
        if (
            stat.S_ISSOCK(claimed.st_mode)
            and claimed.st_uid == os.getuid()
            and (claimed.st_dev, claimed.st_ino) == identity
        ):
            os.unlink(claim_name, dir_fd=quarantine_descriptor)
            return True

        # A replacement won between the initial stat and atomic rename.  A
        # hard link restores it only when the original name is still absent;
        # unlike rename, this cannot overwrite a newer entry.
        try:
            os.link(
                claim_name,
                path.name,
                src_dir_fd=quarantine_descriptor,
                dst_dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise RuntimeStateError(
                "CONTROL_SOCKET_CHANGED",
                "The supervisor socket changed repeatedly during cleanup; the claimed entry was preserved in the private runtime directory.",
            ) from exc
        os.unlink(claim_name, dir_fd=quarantine_descriptor)
        return False
    finally:
        if quarantine_descriptor is not None:
            os.close(quarantine_descriptor)
        try:
            os.rmdir(quarantine_name, dir_fd=parent_descriptor)
        except OSError:
            # A non-empty quarantine is intentional fail-closed preservation,
            # never evidence that its contents are safe to delete broadly.
            pass
        os.close(parent_descriptor)


def _recv_json_frame(
    connection: socket.socket, *, total_timeout: float | None = None
) -> object:
    """Read one bounded newline-delimited JSON frame.

    Newline framing avoids treating an ordinary short ``recv`` as a complete
    request. EOF is accepted for compatibility with a client that half-closes
    its write side after sending one frame.
    """

    payload = bytearray()
    deadline = None if total_timeout is None else time.monotonic() + total_timeout
    while len(payload) <= _MAX_CONTROL_FRAME_BYTES:
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("control frame deadline expired")
            current_timeout = connection.gettimeout()
            connection.settimeout(
                remaining
                if current_timeout is None
                else min(current_timeout, remaining)
            )
        chunk = connection.recv(min(1024, _MAX_CONTROL_FRAME_BYTES + 1 - len(payload)))
        if not chunk:
            break
        payload.extend(chunk)
        newline = payload.find(b"\n")
        if newline >= 0:
            if newline > _MAX_CONTROL_FRAME_BYTES:
                raise ValueError("control frame is too large")
            if bytes(payload[newline + 1 :]).strip():
                raise ValueError("control frame has trailing data")
            del payload[newline:]
            break
        if len(payload) > _MAX_CONTROL_FRAME_BYTES:
            raise ValueError("control frame is too large")
    if not payload:
        raise ValueError("control frame is empty or too large")
    return json.loads(bytes(payload).decode("utf-8"))


@dataclass(frozen=True)
class SupervisorResult:
    child_returncode: int | None
    revoke_attempted: bool
    revoked: bool
    terminated: bool
    forced_exact_child: bool


def _session_hash(value: str) -> str:
    import re

    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise RuntimeStateError("SESSION_CONFLICT", "The supervisor session identity is invalid.")
    return value


class ForegroundSupervisor:
    """Own exactly one Popen handle; never discovers or signals by PID/name."""

    def __init__(
        self,
        *,
        process_factory: Callable[
            [set[signal.Signals] | None], subprocess.Popen[bytes]
        ],
        control_socket: Path,
        session_id_sha256: str,
        revoke_before_terminate: Callable[[str], None],
        after_start: Callable[[subprocess.Popen[bytes]], None] | None = None,
        after_terminate: Callable[[SupervisorResult], None] | None = None,
        process_start_guard: Callable[[], ContextManager[bool]] | None = None,
        initial_signal_mask: set[signal.Signals] | None = None,
        owns_initial_signal_mask: bool = False,
        stop_timeout: float = 5.0,
    ) -> None:
        self.process_factory = process_factory
        self.control_socket = Path(control_socket)
        self.session_id_sha256 = _session_hash(session_id_sha256)
        self.revoke_before_terminate = revoke_before_terminate
        self.after_start = after_start
        self.after_terminate = after_terminate
        self.process_start_guard = process_start_guard
        if not isinstance(owns_initial_signal_mask, bool):
            raise RuntimeStateError(
                "CONTROL_SIGNAL_UNSAFE", "The initial signal-mask ownership is invalid."
            )
        self._initial_signal_mask = initial_signal_mask
        self._owns_initial_signal_mask = owns_initial_signal_mask
        self.stop_timeout = stop_timeout
        self._stop = threading.Event()
        # A signal handler can run on the main thread while child creation is
        # in progress.  Re-entrancy lets that handler record a stop without
        # deadlocking, while remote listener stops remain serialized.
        self._activation_publication_lock = threading.RLock()
        self._reason = "controller_exit"
        self._listener: socket.socket | None = None
        self._owns_control_socket = False
        self._control_socket_identity: tuple[int, int] | None = None
        self._connections: set[socket.socket] = set()
        self._connections_lock = threading.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._revoked = False
        self._listener_ready = threading.Event()
        self._listener_closing = threading.Event()
        self._listener_error: RuntimeStateError | None = None
        self._remote_stop_pending = threading.Event()
        self._failure_code: str | None = None
        self._terminal_result: SupervisorResult | None = None

    @property
    def terminal_result(self) -> SupervisorResult | None:
        """Return exact-child cleanup evidence even when ``run`` raised."""

        return self._terminal_result

    @property
    def stop_requested(self) -> bool:
        """Expose the cooperative stop predicate to bounded readiness work."""

        return self._stop.is_set() or self._remote_stop_pending.is_set()

    @property
    def failure_code(self) -> str | None:
        """Expose the stable foreground cause before cleanup callbacks run."""

        return self._failure_code

    def publish_activation_if_running(self, callback: Callable[[], None]) -> bool:
        """Linearize final activation publication before stop acceptance."""

        previous_mask = self._block_stop_signals()
        published = False
        try:
            with self._activation_publication_lock:
                if not self._stop.is_set() and not self._remote_stop_pending.is_set():
                    callback()
                    published = True
        finally:
            self._restore_signal_mask(previous_mask)
        if not published:
            self.settle_pending_remote_stop()
        return published

    def run(self) -> SupervisorResult:
        previous_handlers: dict[int, object] = {}
        listener_thread: threading.Thread | None = None
        listener_started = False
        forced = False
        terminated = False
        revoke_attempted = False
        try:
            try:
                self._bind_control_socket()
                previous_handlers = self._install_signal_handlers()
                # The controller blocks lifecycle signals before the durable
                # activation begin.  Release that inherited gate only after
                # handlers are installed, so a pending SIGTERM/SIGHUP becomes
                # an attended stop and a pending SIGINT enters cleanup instead
                # of orphaning an ``activating`` authorization.
                self._release_initial_signal_mask()
                listener_thread = threading.Thread(
                    target=self._serve_control,
                    name=f"gptpro-control-{self.session_id_sha256[:12]}",
                    daemon=True,
                )
                # The listener inherits a blocked stop-signal mask.  The main
                # thread restores its prior mask immediately, then blocks the
                # same signals only while publishing activation.  This keeps a
                # process signal from being accepted halfway through the
                # persistent activation commit.
                listener_mask = self._block_stop_signals()
                try:
                    listener_thread.start()
                    listener_started = True
                finally:
                    self._restore_signal_mask(listener_mask)
                if not self._listener_ready.wait(timeout=1.0):
                    raise RuntimeStateError(
                        "CONTROL_LISTENER_FAILED",
                        "The local control listener did not become ready.",
                    )
                if not self._start_process_if_running():
                    self.settle_pending_remote_stop()
                    raise RuntimeStateError(
                        "ACTIVATION_CANCELLED",
                        "The foreground activation was stopped before child start.",
                    )
                self.settle_pending_remote_stop()
                if self._stop.is_set():
                    raise RuntimeStateError(
                        "ACTIVATION_CANCELLED",
                        "The foreground activation was stopped during child start.",
                    )
                if self.after_start is not None:
                    self.after_start(self._process)
                while not self._stop.wait(0.05):
                    self._raise_listener_error()
                    if self._seal_child_exit_if_observed():
                        break
                self._raise_listener_error()
            except KeyboardInterrupt:
                # A manually raised KeyboardInterrupt can arrive after a
                # remote/local stop already sealed the terminal cause.  Keep
                # that first cause instead of rewriting the evidence.
                with self._activation_publication_lock:
                    if not self._stop.is_set():
                        self._reason = "user_interrupt"
                        self._failure_code = "ACTIVATION_CANCELLED"
                        self._stop.set()
                raise
            except BaseException as exc:
                raw_code = getattr(exc, "code", None)
                if self._failure_code is None:
                    self._failure_code = (
                        raw_code
                        if isinstance(raw_code, str)
                        and re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", raw_code) is not None
                        else "CONTROL_LISTENER_FAILED"
                        if self._process is None
                        else "MCP_ACTIVATION_FAILED"
                    )
                raise
            finally:
                cleanup_mask: set[signal.Signals] | None = None
                cleanup_mask_error: BaseException | None = None
                try:
                    cleanup_mask = self._block_stop_signals()
                except BaseException as exc:
                    # Signal shielding is required for the ordering guarantee,
                    # but a platform failure must not skip best-effort denial
                    # and exact-child cleanup.  Report it after cleanup unless
                    # a more specific cleanup failure is already propagating.
                    cleanup_mask_error = exc
                try:
                    revoke_attempted = True
                    try:
                        self.revoke_before_terminate(self._reason)
                        self._revoked = True
                    finally:
                        try:
                            process = self._process
                            if process is not None and process.poll() is None:
                                process.terminate()
                                terminated = True
                                try:
                                    process.wait(timeout=self.stop_timeout)
                                except subprocess.TimeoutExpired:
                                    # This is still the exact Popen object created above; no PID lookup or broad kill.
                                    process.kill()
                                    forced = True
                                    process.wait(timeout=self.stop_timeout)
                        finally:
                            try:
                                self._close_control_socket()
                            finally:
                                try:
                                    if listener_started and listener_thread is not None:
                                        listener_thread.join(timeout=1.0)
                                        if listener_thread.is_alive():
                                            raise RuntimeStateError(
                                                "CONTROL_LISTENER_FAILED",
                                                "The local control listener did not stop cleanly.",
                                            )
                                finally:
                                    self._terminal_result = SupervisorResult(
                                        child_returncode=(
                                            None
                                            if self._process is None
                                            else self._process.returncode
                                        ),
                                        revoke_attempted=revoke_attempted,
                                        revoked=self._revoked,
                                        terminated=terminated,
                                        forced_exact_child=forced,
                                    )
                                    try:
                                        if self.after_terminate is not None:
                                            self.after_terminate(self._terminal_result)
                                    finally:
                                        try:
                                            self._restore_signal_handlers(previous_handlers)
                                        finally:
                                            try:
                                                self._restore_signal_mask(cleanup_mask)
                                            finally:
                                                self._release_initial_signal_mask()
                finally:
                    if cleanup_mask_error is not None and sys.exception() is None:
                        raise cleanup_mask_error
        finally:
            self._terminal_result = SupervisorResult(
                child_returncode=None if self._process is None else self._process.returncode,
                revoke_attempted=revoke_attempted,
                revoked=self._revoked,
                terminated=terminated,
                forced_exact_child=forced,
            )
        return self._terminal_result

    def _raise_listener_error(self) -> None:
        if self._listener_error is not None:
            raise self._listener_error

    def _start_process_if_running(self) -> bool:
        """Linearize child creation while the factory restores the child mask."""

        previous_mask = self._block_stop_signals()
        try:
            with self._activation_publication_lock:
                self._raise_listener_error()
                if self._stop.is_set() or self._remote_stop_pending.is_set():
                    return False
                # Keep SIGINT/SIGTERM/SIGHUP blocked in the parent throughout
                # the factory call.  A process signal sent in this interval is
                # therefore accepted only after the exact child handle has
                # been stored.  The factory contract must launch the child
                # with ``previous_mask`` so this temporary gate mask is not
                # inherited by the Tunnel process.
                guard = (
                    nullcontext(True)
                    if self.process_start_guard is None
                    else self.process_start_guard()
                )
                try:
                    # The controller-provided guard holds the cross-process
                    # runtime-state lock from this final authorization check
                    # through exact Popen ownership.  Therefore an external
                    # terminal denial either commits first and prevents spawn,
                    # or commits only after the exact child is already owned.
                    with guard as permitted:
                        if permitted is not True:
                            self._reason = "authorization_denied"
                            self._failure_code = "ACTIVATION_CANCELLED"
                            self._stop.set()
                            return False
                        self._process = self.process_factory(previous_mask)
                except BaseException as exc:
                    raw_code = getattr(exc, "code", None)
                    self._failure_code = self._failure_code or (
                        raw_code
                        if isinstance(raw_code, str)
                        and re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", raw_code) is not None
                        else "TUNNEL_NOT_READY"
                    )
                    raise
                return True
        finally:
            self._restore_signal_mask(previous_mask)

    def _seal_child_exit_if_observed(self) -> bool:
        """Make child exit compete with stop requests at one linearization point."""

        return self.seal_child_exit_if_observed(self._process)

    def settle_pending_remote_stop(self) -> None:
        """Let the listener finish its bounded ack/stop critical section."""

        if not self._remote_stop_pending.is_set() or self._stop.is_set():
            return
        if self._stop.wait(1.1):
            return
        # A valid request was parsed but its bounded acknowledgement path did
        # not finish.  Preserve the stop even when the response was lost.
        self.request_local_stop("remote_stop")

    def seal_child_exit_if_observed(
        self, process: subprocess.Popen[bytes] | None
    ) -> bool:
        """Seal ``child_exit`` for the exact owned process at first observation."""

        previous_mask = self._block_stop_signals()
        try:
            with self._activation_publication_lock:
                if self._stop.is_set():
                    return False
                if process is None or process is not self._process or process.poll() is None:
                    return False
                self._reason = "child_exit"
                self._stop.set()
                return True
        finally:
            self._restore_signal_mask(previous_mask)

    def _install_signal_handlers(self) -> dict[int, object]:
        if threading.current_thread() is not threading.main_thread():
            return {}
        previous: dict[int, object] = {}
        installed: list[int] = []
        try:
            for signum, reason in (
                (signal.SIGTERM, "signal_term"),
                (signal.SIGHUP, "signal_hup"),
            ):
                previous[signum] = signal.getsignal(signum)

                def handle(received: int, frame: object, *, stop_reason: str = reason) -> None:
                    del received, frame
                    self.request_local_stop(stop_reason)

                signal.signal(signum, handle)
                installed.append(signum)
        except BaseException as exc:
            try:
                for signum in reversed(installed):
                    signal.signal(signum, previous[signum])
            except (OSError, ValueError) as restore_exc:
                raise RuntimeStateError(
                    "CONTROL_SIGNAL_UNSAFE",
                    "The foreground supervisor could not restore a partially installed signal handler.",
                ) from restore_exc
            if isinstance(exc, (OSError, ValueError)):
                raise RuntimeStateError(
                    "CONTROL_SIGNAL_UNSAFE",
                    "The foreground supervisor could not install its signal handlers.",
                ) from exc
            raise
        return previous

    @staticmethod
    def _block_stop_signals() -> set[signal.Signals] | None:
        return block_stop_signals()

    @staticmethod
    def _restore_signal_mask(previous: set[signal.Signals] | None) -> None:
        restore_stop_signal_mask(previous)

    def _release_initial_signal_mask(self) -> None:
        if not self._owns_initial_signal_mask:
            return
        try:
            restore_stop_signal_mask(self._initial_signal_mask)
        except RuntimeStateError:
            # A platform restoration failure may be retryable during cleanup.
            raise
        except BaseException:
            # pthread_sigmask completed before Python delivered the pending
            # signal (for example SIGINT -> KeyboardInterrupt).
            self._owns_initial_signal_mask = False
            raise
        else:
            self._owns_initial_signal_mask = False

    def _restore_signal_handlers(self, previous: dict[int, object]) -> None:
        pending = list(previous.items())
        failures: list[BaseException] = []
        # A transient first restore failure must not prevent restoration of the
        # other handler or a second attempt for the first one.
        for _ in range(2):
            if not pending:
                break
            retry: list[tuple[int, object]] = []
            for signum, handler in pending:
                try:
                    signal.signal(signum, handler)
                except (OSError, ValueError) as exc:
                    failures.append(exc)
                    retry.append((signum, handler))
            pending = retry
        if pending:
            self._failure_code = self._failure_code or "CONTROL_SIGNAL_UNSAFE"
            raise RuntimeStateError(
                "CONTROL_SIGNAL_UNSAFE",
                "The foreground supervisor encountered an error while restoring signal handlers.",
            ) from failures[0]

    def request_local_stop(self, reason: str = "user_requested") -> None:
        if not isinstance(reason, str) or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", reason) is None:
            raise ValueError("stop reason is invalid")
        with self._activation_publication_lock:
            if not self._stop.is_set():
                self._reason = reason
                self._stop.set()

    def _bind_control_socket(self) -> None:
        ensure_private_directory(self.control_socket.parent)
        try:
            _control_socket_metadata(self.control_socket)
        except FileNotFoundError:
            pass
        else:
            raise RuntimeStateError("SESSION_CONFLICT", "The supervisor control socket already exists.")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        staging_socket = self.control_socket.with_name(f".{secrets.token_urlsafe(8)}")
        bound_identity: tuple[int, int] | None = None
        published = False
        try:
            listener.bind(str(staging_socket))
            listener.listen(4)
            try:
                metadata = _control_socket_metadata(staging_socket)
            except OSError:
                # Retry once through the parent directory descriptor.  An
                # unverified random staging name is never published as the
                # well-known control socket.
                try:
                    metadata = _control_socket_metadata(staging_socket)
                except OSError as exc:
                    raise RuntimeStateError(
                        "CONTROL_LISTENER_FAILED",
                        "The staged control socket identity could not be verified.",
                    ) from exc
            if not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != os.getuid():
                raise RuntimeStateError(
                    "RUNTIME_STATE_UNSAFE", "The staged supervisor socket is unsafe."
                )
            candidate_identity = (metadata.st_dev, metadata.st_ino)
            _prove_control_socket_listener_path(listener, staging_socket)
            proven_metadata = _control_socket_metadata(staging_socket)
            if (
                not stat.S_ISSOCK(proven_metadata.st_mode)
                or proven_metadata.st_uid != os.getuid()
                or (proven_metadata.st_dev, proven_metadata.st_ino) != candidate_identity
            ):
                raise RuntimeStateError(
                    "CONTROL_SOCKET_CHANGED",
                    "The staged supervisor socket identity changed during listener proof.",
                )
            # Only a pathname that completed the listener proof may become an
            # owned identity and therefore an eligible cleanup target.
            bound_identity = candidate_identity
            os.chmod(staging_socket, 0o600, follow_symlinks=False)
            secured = _control_socket_metadata(staging_socket)
            if (
                not stat.S_ISSOCK(secured.st_mode)
                or secured.st_uid != os.getuid()
                or stat.S_IMODE(secured.st_mode) != 0o600
                or (secured.st_dev, secured.st_ino) != bound_identity
            ):
                raise RuntimeStateError(
                    "RUNTIME_STATE_UNSAFE",
                    "The staged supervisor socket identity changed during setup.",
                )
            directory_flags = (
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_CLOEXEC", 0)
            )
            if hasattr(os, "O_NOFOLLOW"):
                directory_flags |= os.O_NOFOLLOW
            parent_descriptor = os.open(self.control_socket.parent, directory_flags)
            try:
                try:
                    # A same-directory hard link is an atomic no-clobber
                    # publication of the already pinned socket inode.  Never
                    # rename over a control socket that appeared after the
                    # preflight check.
                    os.link(
                        staging_socket.name,
                        self.control_socket.name,
                        src_dir_fd=parent_descriptor,
                        dst_dir_fd=parent_descriptor,
                        follow_symlinks=False,
                    )
                except FileExistsError as exc:
                    raise RuntimeStateError(
                        "SESSION_CONFLICT",
                        "The supervisor control socket appeared during secure publication.",
                    ) from exc
            finally:
                os.close(parent_descriptor)
            published = True
            published_metadata = _control_socket_metadata(self.control_socket)
            staged_metadata = _control_socket_metadata(staging_socket)
            for candidate in (published_metadata, staged_metadata):
                if (
                    not stat.S_ISSOCK(candidate.st_mode)
                    or candidate.st_uid != os.getuid()
                    or stat.S_IMODE(candidate.st_mode) != 0o600
                    or (candidate.st_dev, candidate.st_ino) != bound_identity
                ):
                    raise RuntimeStateError(
                        "CONTROL_SOCKET_CHANGED",
                        "The supervisor socket identity changed during secure publication.",
                    )
            try:
                staging_removed = _claim_and_unlink_control_socket_if_matches(
                    staging_socket, bound_identity
                )
            except FileNotFoundError:
                staging_removed = False
            if not staging_removed:
                raise RuntimeStateError(
                    "CONTROL_SOCKET_CHANGED",
                    "The staged supervisor socket changed before publication completed.",
                )
            final_metadata = _control_socket_metadata(self.control_socket)
            if (
                not stat.S_ISSOCK(final_metadata.st_mode)
                or final_metadata.st_uid != os.getuid()
                or stat.S_IMODE(final_metadata.st_mode) != 0o600
                or (final_metadata.st_dev, final_metadata.st_ino) != bound_identity
            ):
                raise RuntimeStateError(
                    "CONTROL_SOCKET_CHANGED",
                    "The published supervisor socket identity changed during setup.",
                )
            listener.setblocking(False)
            self._listener = listener
            self._owns_control_socket = True
            self._control_socket_identity = bound_identity
        except Exception:
            listener.close()
            if bound_identity is not None:
                for path in (
                    self.control_socket if published else None,
                    staging_socket,
                ):
                    if path is None:
                        continue
                    try:
                        _claim_and_unlink_control_socket_if_matches(path, bound_identity)
                    except FileNotFoundError:
                        pass
            raise

    def _serve_control(self) -> None:
        listener = self._listener
        if listener is None:
            self._listener_error = RuntimeStateError(
                "CONTROL_LISTENER_FAILED", "The local control listener is unavailable."
            )
            self._listener_ready.set()
            return
        selector: selectors.BaseSelector | None = None
        try:
            selector = selectors.DefaultSelector()
            selector.register(listener, selectors.EVENT_READ)
            self._listener_ready.set()
            while not self._stop.is_set():
                for key, _ in selector.select(timeout=0.1):
                    if key.fileobj is not listener:
                        continue
                    try:
                        connection, _ = listener.accept()
                    except OSError:
                        continue
                    if not self._register_control_connection(connection):
                        connection.close()
                        continue
                    try:
                        connection.settimeout(1.0)
                        try:
                            request = _recv_json_frame(connection, total_timeout=1.0)
                            accepted = (
                                isinstance(request, dict)
                                and request.get("command") == "stop"
                                and request.get("session_id_sha256") == self.session_id_sha256
                            )
                        except (OSError, UnicodeDecodeError, ValueError, RecursionError):
                            accepted = False
                        if accepted:
                            self._remote_stop_pending.set()
                        response = (
                            json.dumps({"accepted": accepted}, separators=(",", ":")) + "\n"
                        ).encode("utf-8")
                        if accepted:
                            # The acknowledgement and stop decision share the
                            # same linearization lock as child creation.  If
                            # this block wins first, the factory sees _stop and
                            # no child is launched.  If spawn wins first, the
                            # client cannot observe accepted=true until the
                            # exact Popen handle is owned.  Set _stop only after
                            # the bounded send attempt so cleanup cannot close
                            # this connection between decision and ack.
                            with self._activation_publication_lock:
                                try:
                                    connection.sendall(response)
                                except OSError:
                                    pass
                                if not self._stop.is_set():
                                    self._reason = "remote_stop"
                                    self._stop.set()
                        else:
                            try:
                                connection.sendall(response)
                            except OSError:
                                pass
                    finally:
                        self._unregister_control_connection(connection)
                        connection.close()
        except BaseException:
            if not self._listener_closing.is_set():
                with self._activation_publication_lock:
                    if not self._stop.is_set():
                        self._listener_error = RuntimeStateError(
                            "CONTROL_LISTENER_FAILED",
                            "The local control listener stopped unexpectedly.",
                        )
                        self._failure_code = "CONTROL_LISTENER_FAILED"
                        self._reason = "listener_failure"
                        self._stop.set()
        finally:
            self._listener_ready.set()
            if selector is not None:
                try:
                    selector.close()
                except OSError:
                    pass

    def _close_control_socket(self) -> None:
        self._listener_closing.set()
        self._stop.set()
        with self._connections_lock:
            connections = tuple(self._connections)
            self._connections.clear()
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            connection.close()
        if self._listener is not None:
            try:
                self._listener.close()
            finally:
                self._listener = None
        identity = self._control_socket_identity
        if not self._owns_control_socket or identity is None:
            return
        try:
            _claim_and_unlink_control_socket_if_matches(self.control_socket, identity)
        except FileNotFoundError:
            pass
        finally:
            self._owns_control_socket = False
            self._control_socket_identity = None

    def _register_control_connection(self, connection: socket.socket) -> bool:
        with self._connections_lock:
            if self._listener_closing.is_set():
                return False
            self._connections.add(connection)
            return True

    def _unregister_control_connection(self, connection: socket.socket) -> None:
        with self._connections_lock:
            self._connections.discard(connection)


def request_cooperative_stop(
    control_socket: Path,
    session_id_sha256: str,
    *,
    timeout: float = 2.0,
) -> bool:
    """Ask the foreground owner to stop; never fall back to PID/process-name signaling."""

    session = _session_hash(session_id_sha256)
    path = Path(control_socket)
    try:
        metadata = path.lstat()
    except OSError:
        return False
    if (
        not stat.S_ISSOCK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        return False
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(path))
        client.sendall(
            (
                json.dumps(
                    {"command": "stop", "session_id_sha256": session},
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        )
        response = _recv_json_frame(client, total_timeout=timeout)
        return isinstance(response, dict) and response.get("accepted") is True
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return False
    finally:
        client.close()
