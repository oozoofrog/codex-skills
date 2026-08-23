"""Foreground-only ownership and cooperative stop for one tunnel-client process."""

from __future__ import annotations

import json
import os
import re
import selectors
import signal
import socket
import stat
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .runtime_state import RuntimeStateError, ensure_private_directory

_MAX_CONTROL_FRAME_BYTES = 4096


def _recv_json_frame(connection: socket.socket) -> object:
    """Read one bounded newline-delimited JSON frame.

    Newline framing avoids treating an ordinary short ``recv`` as a complete
    request. EOF is accepted for compatibility with a client that half-closes
    its write side after sending one frame.
    """

    payload = bytearray()
    while len(payload) <= _MAX_CONTROL_FRAME_BYTES:
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
        process_factory: Callable[[], subprocess.Popen[bytes]],
        control_socket: Path,
        session_id_sha256: str,
        revoke_before_terminate: Callable[[str], None],
        after_start: Callable[[subprocess.Popen[bytes]], None] | None = None,
        stop_timeout: float = 5.0,
    ) -> None:
        self.process_factory = process_factory
        self.control_socket = Path(control_socket)
        self.session_id_sha256 = _session_hash(session_id_sha256)
        self.revoke_before_terminate = revoke_before_terminate
        self.after_start = after_start
        self.stop_timeout = stop_timeout
        self._stop = threading.Event()
        self._reason = "controller_exit"
        self._listener: socket.socket | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._revoked = False

    def run(self) -> SupervisorResult:
        self._bind_control_socket()
        previous_handlers = self._install_signal_handlers()
        listener_thread = threading.Thread(target=self._serve_control, daemon=True)
        listener_thread.start()
        forced = False
        terminated = False
        revoke_attempted = False
        try:
            self._process = self.process_factory()
            if self.after_start is not None:
                self.after_start(self._process)
            while not self._stop.wait(0.05):
                if self._process.poll() is not None:
                    self._reason = "child_exit"
                    break
        except KeyboardInterrupt:
            self._reason = "user_interrupt"
        finally:
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
                            listener_thread.join(timeout=1.0)
                        finally:
                            self._restore_signal_handlers(previous_handlers)
        return SupervisorResult(
            child_returncode=None if self._process is None else self._process.returncode,
            revoke_attempted=revoke_attempted,
            revoked=self._revoked,
            terminated=terminated,
            forced_exact_child=forced,
        )

    def _install_signal_handlers(self) -> dict[int, object]:
        if threading.current_thread() is not threading.main_thread():
            return {}
        previous: dict[int, object] = {}
        for signum, reason in ((signal.SIGTERM, "signal_term"), (signal.SIGHUP, "signal_hup")):
            previous[signum] = signal.getsignal(signum)

            def handle(received: int, frame: object, *, stop_reason: str = reason) -> None:
                del received, frame
                self.request_local_stop(stop_reason)

            signal.signal(signum, handle)
        return previous

    @staticmethod
    def _restore_signal_handlers(previous: dict[int, object]) -> None:
        for signum, handler in previous.items():
            signal.signal(signum, handler)

    def request_local_stop(self, reason: str = "user_requested") -> None:
        if not isinstance(reason, str) or re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", reason) is None:
            raise ValueError("stop reason is invalid")
        self._reason = reason
        self._stop.set()

    def _bind_control_socket(self) -> None:
        ensure_private_directory(self.control_socket.parent)
        try:
            self.control_socket.lstat()
        except FileNotFoundError:
            pass
        else:
            raise RuntimeStateError("SESSION_CONFLICT", "The supervisor control socket already exists.")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(str(self.control_socket))
            os.chmod(self.control_socket, 0o600, follow_symlinks=False)
            listener.listen(4)
            listener.setblocking(False)
            self._listener = listener
        except Exception:
            listener.close()
            raise

    def _serve_control(self) -> None:
        listener = self._listener
        if listener is None:
            return
        selector = selectors.DefaultSelector()
        selector.register(listener, selectors.EVENT_READ)
        try:
            while not self._stop.is_set():
                for key, _ in selector.select(timeout=0.1):
                    if key.fileobj is not listener:
                        continue
                    try:
                        connection, _ = listener.accept()
                    except OSError:
                        continue
                    with connection:
                        connection.settimeout(1.0)
                        try:
                            request = _recv_json_frame(connection)
                            accepted = (
                                isinstance(request, dict)
                                and request.get("command") == "stop"
                                and request.get("session_id_sha256") == self.session_id_sha256
                            )
                        except (OSError, UnicodeDecodeError, ValueError, RecursionError):
                            accepted = False
                        if accepted:
                            self._reason = "remote_stop"
                            self._stop.set()
                        response = (
                            json.dumps({"accepted": accepted}, separators=(",", ":")) + "\n"
                        ).encode("utf-8")
                        try:
                            connection.sendall(response)
                        except OSError:
                            pass
        finally:
            selector.close()

    def _close_control_socket(self) -> None:
        if self._listener is not None:
            self._listener.close()
            self._listener = None
        try:
            metadata = self.control_socket.lstat()
            if stat.S_ISSOCK(metadata.st_mode) and metadata.st_uid == os.getuid():
                self.control_socket.unlink()
        except FileNotFoundError:
            pass


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
        response = _recv_json_frame(client)
        return isinstance(response, dict) and response.get("accepted") is True
    except (OSError, UnicodeDecodeError, ValueError, RecursionError):
        return False
    finally:
        client.close()
