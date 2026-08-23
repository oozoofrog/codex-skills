"""Narrow adapter for the documented Secure MCP Tunnel client commands."""

from __future__ import annotations

import base64
import errno
import fcntl
import hashlib
import ipaddress
import json
import os
import re
import selectors
import secrets
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .request_correlation import capture_request_correlation as _capture_request_correlation
from .runtime_state import (
    RuntimeStateError,
    ensure_private_directory,
    fsync_directory,
    open_private_regular,
)

_PROFILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_ENV_NAME = re.compile(r"[A-Z_][A-Z0-9_]{0,127}")
_TUNNEL_ID = re.compile(r"tunnel_[A-Za-z0-9_-]{16,128}")
_RUNTIME_KEY = re.compile(r"sk-[A-Za-z0-9_-]{16,}")
_RAW_SECRET = re.compile(r"(?:\bsk-[A-Za-z0-9_-]{16,}|\btunnel_[A-Za-z0-9_-]{16,128}\b)")
_SECRET_SHAPED_ENV_VALUE = re.compile(
    r"(?:\bsk-[A-Za-z0-9_-]{16,}|\bgh[pousr]_[A-Za-z0-9_]{16,}|"
    r"\bgithub_pat_[A-Za-z0-9_]{16,}|\btunnel_[A-Za-z0-9_-]{16,128}\b)",
    re.IGNORECASE,
)
_SAFE_CHILD_ENV_NAMES = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_COLLATE",
        "LC_CTYPE",
        "LC_MESSAGES",
        "LC_MONETARY",
        "LC_NUMERIC",
        "LC_TIME",
        "TMPDIR",
        "XDG_CONFIG_HOME",
    }
)
_CONTROL_PLANE_KEY_ENV = "CONTROL_PLANE_API_KEY"
_CANONICAL_CONTROL_PLANE_BASE_URL = "https://api.openai.com"
# v0.0.12 treats an explicitly changed but empty flag as unset. A root path is
# non-empty at precedence selection time and normalizes to an empty URL prefix.
_CANONICAL_CONTROL_PLANE_URL_PATH = "/"
_TRUSTED_GPTPRO_CHILD_ENV_NAMES = frozenset(
    {"GPTPRO_MCP_SESSION_CAPABILITY", "GPTPRO_MCP_RUNTIME_DIR"}
)
_SESSION_CAPABILITY = re.compile(r"[A-Za-z0-9_-]{43}")
_PROFILE_KEY = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,127}")
_PROFILE_MAX_BYTES = 64 * 1024
_MAX_UNIX_SOCKET_PATH_BYTES = 100
_MAX_COMMAND_OUTPUT_BYTES = 1024 * 1024
_COMMAND_STOP_GRACE_SECONDS = 1.0
_OFFICIAL_PROFILE_PATHS = frozenset(
    {
        ("config_version",),
        ("control_plane",),
        ("control_plane", "base_url"),
        ("control_plane", "url_path"),
        ("control_plane", "tunnel_id"),
        ("control_plane", "api_key"),
        ("health",),
        ("health", "listen_addr"),
        ("admin_ui",),
        ("admin_ui", "open_browser"),
        ("log",),
        ("log", "level"),
        ("log", "format"),
        ("mcp",),
        ("mcp", "commands"),
        ("mcp", "commands", "channel"),
        ("mcp", "commands", "command"),
    }
)
_OFFICIAL_PROFILE_REQUIRED_SCALARS = frozenset(
    {
        ("config_version",),
        ("control_plane", "base_url"),
        ("control_plane", "url_path"),
        ("control_plane", "tunnel_id"),
        ("control_plane", "api_key"),
        ("health", "listen_addr"),
        ("admin_ui", "open_browser"),
        ("log", "level"),
        ("log", "format"),
        ("mcp", "commands", "channel"),
        ("mcp", "commands", "command"),
    }
)


def _help_has_exact_option(text: str, option: str) -> bool:
    """Match one complete CLI option token, not a longer option prefix."""

    return re.search(
        rf"(?<![A-Za-z0-9_.-]){re.escape(option)}(?![A-Za-z0-9_.-])",
        text,
    ) is not None


@dataclass
class TunnelClientError(Exception):
    code: str
    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return self.code


def validate_control_plane_base_url(raw: str) -> str:
    """Accept only the phase-1 OpenAI control-plane origin, without URL adornments."""

    try:
        parsed = urllib.parse.urlsplit(raw)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise TunnelClientError(
            "CONTROL_PLANE_ENDPOINT_REJECTED", "The control-plane endpoint is invalid."
        ) from exc
    if (
        raw != _CANONICAL_CONTROL_PLANE_BASE_URL
        or parsed.scheme != "https"
        or parsed.netloc != "api.openai.com"
        or parsed.hostname != "api.openai.com"
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != ""
        or parsed.query != ""
        or parsed.fragment != ""
    ):
        raise TunnelClientError(
            "CONTROL_PLANE_ENDPOINT_REJECTED",
            "Only the canonical OpenAI control-plane origin is allowed.",
        )
    return _CANONICAL_CONTROL_PLANE_BASE_URL


def _runtime_control_plane_arguments() -> list[str]:
    return [
        # An explicitly changed empty CA flag makes v0.0.12 use system trust
        # instead of a profile/environment bundle.
        "--ca-bundle",
        "",
        "--control-plane.api-key",
        f"env:{_CONTROL_PLANE_KEY_ENV}",
        "--control-plane.base-url",
        validate_control_plane_base_url(_CANONICAL_CONTROL_PLANE_BASE_URL),
        "--control-plane.url-path",
        _CANONICAL_CONTROL_PLANE_URL_PATH,
    ]


@dataclass(frozen=True)
class TunnelCapabilities:
    binary_sha256: str
    version: str
    quickstart_help: bool
    init_profile: bool
    doctor_profile: bool
    foreground_run: bool
    run_mcp_command_override: bool
    health_require_control_plane_poll: bool
    health_unix_socket: bool
    health_exact_pid: bool
    warn_log_level: bool

    @property
    def supported(self) -> bool:
        return (
            self.quickstart_help
            and self.init_profile
            and self.doctor_profile
            and self.foreground_run
            and self.run_mcp_command_override
            and self.health_require_control_plane_poll
            and self.health_unix_socket
            and self.health_exact_pid
            and self.warn_log_level
        )


@dataclass(frozen=True)
class TunnelCheck:
    ok: bool
    code: str | None
    retryable: bool
    profile_sha256: str
    control_plane_poll_confirmed: bool = False
    tunnel_binding_sha256: str | None = None
    tunnel_binding_matches: bool | None = None
    mcp_target_sha256: str | None = None
    mcp_target_matches: bool | None = None
    profile_binding_verification: str = "unavailable"


@dataclass(frozen=True)
class TunnelInitResult:
    ok: bool
    code: str | None
    retryable: bool
    profile_sha256: str
    profile_dir_sha256: str | None
    mcp_command_sha256: str


@dataclass(frozen=True)
class TunnelProfileInspection:
    ready: bool
    code: str | None
    refresh_required: bool
    safe_to_refresh: bool
    reinit_required: bool
    profile_sha256: str
    profile_dir_sha256: str
    observed_mcp_command_sha256: str
    expected_mcp_command_sha256: str


@dataclass(frozen=True)
class TunnelProfileRefreshResult:
    ok: bool
    previous_profile_sha256: str
    profile_sha256: str
    profile_dir_sha256: str
    mcp_command_sha256: str
    staging_cleanup_complete: bool


class ProfileControllerLease:
    """Machine-global flock serializing profile mutation and foreground use."""

    def __init__(self, runtime_root: Path) -> None:
        self.path = Path(runtime_root) / "profile-controller.lock"
        self._descriptor: int | None = None

    def acquire(self) -> "ProfileControllerLease":
        descriptor = open_private_regular(self.path, flags=os.O_RDWR, create=True)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(descriptor)
            raise RuntimeStateError(
                "PROFILE_OPERATION_CONFLICT",
                "Another profile mutation or foreground controller operation is in progress.",
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

    def __enter__(self) -> "ProfileControllerLease":
        return self.acquire()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        del exc_type, exc, traceback
        self.close()


@dataclass(frozen=True)
class ProfileSecuritySnapshot:
    directory: Path
    path: Path
    sha256: str


@dataclass(frozen=True)
class CommandPathIdentity:
    path: Path
    sha256: str
    device: int
    inode: int


@dataclass(frozen=True)
class LoopbackStatus:
    healthy: bool
    ready: bool
    code: str | None


@dataclass(frozen=True)
class TunnelRuntimeFiles:
    url_file: Path
    pid_file: Path
    socket_file: Path


def prepare_runtime_files(runtime_dir: Path, *, session_id_sha256: str) -> TunnelRuntimeFiles:
    if re.fullmatch(r"[0-9a-f]{64}", session_id_sha256) is None:
        raise TunnelClientError("SESSION_CONFLICT", "The Tunnel session identity is invalid.")
    requested_root = Path(runtime_dir).expanduser()
    if not requested_root.is_absolute():
        raise TunnelClientError("RUNTIME_STATE_UNSAFE", "Tunnel runtime files require an absolute directory.")
    try:
        root = ensure_private_directory(requested_root)
        files = TunnelRuntimeFiles(
            url_file=root / f"health-{session_id_sha256}.url",
            pid_file=root / f"tunnel-{session_id_sha256}.pid",
            socket_file=root / "h.sock",
        )
        for path in (files.url_file, files.pid_file):
            descriptor = open_private_regular(path, flags=os.O_RDWR, create=True)
            os.close(descriptor)
        if len(os.fsencode(files.socket_file)) > _MAX_UNIX_SOCKET_PATH_BYTES:
            raise TunnelClientError(
                "RUNTIME_STATE_UNSAFE",
                "The private runtime directory is too long for the Tunnel health socket.",
            )
        try:
            socket_metadata = files.socket_file.lstat()
        except FileNotFoundError:
            pass
        else:
            if (
                not stat.S_ISSOCK(socket_metadata.st_mode)
                or socket_metadata.st_uid != os.getuid()
                or socket_metadata.st_nlink != 1
                or stat.S_IMODE(socket_metadata.st_mode) & 0o077
            ):
                raise TunnelClientError(
                    "RUNTIME_STATE_UNSAFE", "The existing Tunnel health socket is unsafe."
                )
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            probe.settimeout(0.1)
            try:
                probe.connect(str(files.socket_file))
            except OSError as exc:
                if exc.errno not in {errno.ECONNREFUSED, errno.ENOENT}:
                    raise TunnelClientError(
                        "RUNTIME_STATE_UNSAFE", "Unable to validate the stale Tunnel health socket."
                    ) from exc
                try:
                    files.socket_file.unlink(missing_ok=True)
                except OSError as unlink_error:
                    raise TunnelClientError(
                        "RUNTIME_STATE_UNSAFE", "Unable to retire the stale Tunnel health socket."
                    ) from unlink_error
            else:
                raise TunnelClientError(
                    "SESSION_CONFLICT", "An existing Tunnel health socket is still live."
                )
            finally:
                probe.close()
        fsync_directory(root)
        return files
    except RuntimeStateError as exc:
        raise TunnelClientError(exc.code, "Unable to prepare owner-only Tunnel runtime files.") from exc


def _validate_runtime_files(files: TunnelRuntimeFiles, *, require_socket: bool = False) -> None:
    regular_paths = (Path(files.url_file), Path(files.pid_file))
    socket_path = Path(files.socket_file)
    paths = (*regular_paths, socket_path)
    if any(not path.is_absolute() for path in paths) or len({path.parent for path in paths}) != 1:
        raise TunnelClientError(
            "RUNTIME_STATE_UNSAFE",
            "Tunnel runtime files must share one absolute private directory.",
        )
    if len(os.fsencode(socket_path)) > _MAX_UNIX_SOCKET_PATH_BYTES:
        raise TunnelClientError(
            "RUNTIME_STATE_UNSAFE", "The Tunnel health socket path is too long."
        )
    try:
        ensure_private_directory(socket_path.parent)
        for path in regular_paths:
            descriptor = open_private_regular(path, flags=os.O_RDWR)
            os.close(descriptor)
    except RuntimeStateError as exc:
        raise TunnelClientError(exc.code, "Tunnel runtime files are not owner-only regular files.") from exc
    try:
        metadata = socket_path.lstat()
    except FileNotFoundError:
        if require_socket:
            raise TunnelClientError(
                "TUNNEL_NOT_READY", "The activation-owned Tunnel health socket is unavailable.", True
            )
        return
    except OSError as exc:
        raise TunnelClientError(
            "RUNTIME_STATE_UNSAFE", "Unable to inspect the Tunnel health socket."
        ) from exc
    if require_socket:
        if (
            not stat.S_ISSOCK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise TunnelClientError(
                "RUNTIME_STATE_UNSAFE", "The Tunnel health socket is not activation-owned."
            )
    else:
        raise TunnelClientError(
            "RUNTIME_STATE_UNSAFE", "The activation-owned Tunnel health socket already exists."
        )


def _pid_file_matches_owned_process(path: Path, expected_pid: int) -> bool:
    """Read the private PID file without following links and match one exact child."""

    descriptor = -1
    try:
        descriptor = open_private_regular(Path(path), flags=os.O_RDONLY)
        metadata = os.fstat(descriptor)
        if metadata.st_size > 32:
            raise TunnelClientError(
                "RUNTIME_STATE_UNSAFE", "The Tunnel PID file is unexpectedly large."
            )
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            payload = handle.read(33)
    except RuntimeStateError as exc:
        raise TunnelClientError(exc.code, "The Tunnel PID file is unsafe.") from exc
    except OSError as exc:
        raise TunnelClientError(
            "RUNTIME_STATE_UNSAFE", "The Tunnel PID file cannot be read."
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        observed = payload.decode("ascii").strip()
    except UnicodeDecodeError:
        return False
    return observed == str(expected_pid)


def _profile_directory(path: Path, *, create: bool) -> Path:
    directory = Path(path).expanduser()
    if not directory.is_absolute():
        raise TunnelClientError("RUNTIME_STATE_UNSAFE", "Tunnel profile directories must be absolute.")
    if not create and not directory.exists():
        raise TunnelClientError("TUNNEL_PROFILE_UNSAFE", "The Tunnel profile directory is unavailable.")
    try:
        private = ensure_private_directory(directory)
        _require_replacement_safe_profile_directory(private)
        return private
    except RuntimeStateError as exc:
        raise TunnelClientError(exc.code, "The Tunnel profile directory is unsafe.") from exc


def _require_replacement_safe_profile_directory(path: Path) -> None:
    """Reject profile paths another local account can replace after validation.

    The external Tunnel process reopens ``--profile-dir`` by pathname, so a
    private final directory is insufficient when one of its ancestors can be
    renamed by another account. Walk the already-created absolute chain with
    ``openat``/``O_NOFOLLOW`` and require root/current ownership throughout.
    Group/other-writable parents are accepted only with sticky-directory
    semantics and a root/current-owned child.
    """

    requested = Path(path)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory_flag is None:
        raise TunnelClientError(
            "RUNTIME_STATE_UNSAFE",
            "Replacement-safe Tunnel profile paths require O_NOFOLLOW and O_DIRECTORY.",
        )
    flags = os.O_RDONLY | nofollow | directory_flag | getattr(os, "O_CLOEXEC", 0)
    descriptor = -1
    try:
        descriptor = os.open(requested.anchor, flags)
        for component in requested.parts[1:]:
            parent_metadata = os.fstat(descriptor)
            child = os.open(component, flags, dir_fd=descriptor)
            try:
                child_metadata = os.fstat(child)
                if not stat.S_ISDIR(child_metadata.st_mode):
                    raise TunnelClientError(
                        "RUNTIME_STATE_UNSAFE",
                        "The Tunnel profile path contains a non-directory component.",
                    )
                trusted_owners = {0, os.getuid()}
                parent_writable = bool(stat.S_IMODE(parent_metadata.st_mode) & 0o022)
                sticky_protected = bool(parent_metadata.st_mode & stat.S_ISVTX)
                if parent_metadata.st_uid not in trusted_owners or (
                    parent_writable
                    and not (
                        sticky_protected
                        and child_metadata.st_uid in trusted_owners
                    )
                ):
                    raise TunnelClientError(
                        "RUNTIME_STATE_UNSAFE",
                        "A Tunnel profile ancestor permits replacement by another local account.",
                    )
            except Exception:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
        final_metadata = os.fstat(descriptor)
        if (
            final_metadata.st_uid != os.getuid()
            or stat.S_IMODE(final_metadata.st_mode) != 0o700
        ):
            raise TunnelClientError(
                "RUNTIME_STATE_UNSAFE",
                "The Tunnel profile directory must be owner-only mode 0700.",
            )
    except TunnelClientError:
        raise
    except OSError as exc:
        raise TunnelClientError(
            "RUNTIME_STATE_UNSAFE",
            "The Tunnel profile path changed or contains an unsafe component.",
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _resolved_profile_directory(
    profile_dir: Path | None,
    environ: Mapping[str, str],
    *,
    create: bool = False,
) -> Path:
    if profile_dir is not None:
        return _profile_directory(profile_dir, create=create)
    xdg_config = _safe_environment_value(environ.get("XDG_CONFIG_HOME"))
    if xdg_config is not None:
        base = Path(xdg_config)
        directory = base / "tunnel-client"
    else:
        home = _safe_environment_value(environ.get("HOME"))
        if home is None:
            raise TunnelClientError(
                "RUNTIME_STATE_UNSAFE", "The default Tunnel profile directory is unavailable."
            )
        base = Path(home)
        directory = base / ".config" / "tunnel-client"
    if not base.is_absolute():
        raise TunnelClientError(
            "RUNTIME_STATE_UNSAFE", "The default Tunnel profile directory must be absolute."
        )
    return _profile_directory(directory, create=create)


def _profile(value: str) -> str:
    if not isinstance(value, str) or _PROFILE.fullmatch(value) is None:
        raise TunnelClientError("MCP_INVALID_ARGUMENT", "The Tunnel profile name is invalid.")
    return value


def _profile_identity_sha256(name: str, snapshot: ProfileSecuritySnapshot) -> str:
    payload = (
        b"gptpro-tunnel-profile-v2\0"
        + name.encode("utf-8")
        + b"\0"
        + str(snapshot.path).encode("utf-8")
        + b"\0"
        + snapshot.sha256.encode("ascii")
    )
    return hashlib.sha256(payload).hexdigest()


def _profile_scalar(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith('"'):
        try:
            decoded = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise TunnelClientError(
                "TUNNEL_PROFILE_UNSAFE", "The Tunnel profile has an invalid quoted scalar."
            ) from exc
        if not isinstance(decoded, str):
            raise TunnelClientError(
                "TUNNEL_PROFILE_UNSAFE", "The Tunnel profile scalar must be text."
            )
        return decoded
    if stripped.startswith("'"):
        if len(stripped) < 2 or not stripped.endswith("'"):
            raise TunnelClientError(
                "TUNNEL_PROFILE_UNSAFE", "The Tunnel profile has an invalid quoted scalar."
            )
        return stripped[1:-1].replace("''", "'")
    if " #" in stripped:
        stripped = stripped.split(" #", 1)[0].rstrip()
    if not stripped or any(character in stripped for character in "{}[]&*!|>"):
        raise TunnelClientError(
            "TUNNEL_PROFILE_UNSAFE", "The Tunnel profile uses unsupported YAML syntax."
        )
    return stripped


def _restricted_profile_values(document: str) -> dict[tuple[str, ...], str]:
    """Parse the conservative plain-key YAML subset emitted by official init.

    This is intentionally not a general YAML parser. Advanced YAML constructs
    fail closed so quoted keys, aliases, merges, tags, flow mappings, and block
    scalars cannot hide proxy or trust configuration from the policy check.
    """

    stack: list[tuple[int, str]] = []
    paths: list[tuple[str, ...]] = []
    scalars: dict[tuple[str, ...], str] = {}
    for line_number, raw_line in enumerate(document.splitlines(), start=1):
        if "\t" in raw_line or any(
            ord(character) < 32 and character not in {"\r", "\n"}
            for character in raw_line
        ):
            raise TunnelClientError(
                "TUNNEL_PROFILE_UNSAFE", "The Tunnel profile uses unsupported YAML syntax."
            )
        stripped = raw_line.lstrip(" ")
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(stripped)
        if stripped.startswith(("%", "---", "...", "?", "&", "*", "!", "{", "[", "|", ">")):
            raise TunnelClientError(
                "TUNNEL_PROFILE_UNSAFE", "The Tunnel profile uses unsupported YAML syntax."
            )
        list_item = stripped.startswith("- ")
        if list_item:
            stripped = stripped[2:].lstrip(" ")
        match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_-]{0,127}):(?:[ ](.*))?", stripped)
        if match is None or _PROFILE_KEY.fullmatch(match.group(1)) is None:
            raise TunnelClientError(
                "TUNNEL_PROFILE_UNSAFE",
                f"The Tunnel profile has unsupported structure at line {line_number}.",
            )
        key = match.group(1)
        value = match.group(2)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = tuple(item[1] for item in stack) + (key,)
        if path not in _OFFICIAL_PROFILE_PATHS:
            raise TunnelClientError(
                "TUNNEL_PROFILE_UNSAFE",
                "The Tunnel profile contains a configuration outside the gptpro init profile.",
            )
        if list_item and path != ("mcp", "commands", "channel"):
            raise TunnelClientError(
                "TUNNEL_PROFILE_UNSAFE", "The Tunnel profile has an unsupported list item."
            )
        paths.append(path)
        if value is None or value.strip() == "" or value.lstrip().startswith("#"):
            stack.append((indent, key))
            continue
        if value.lstrip().startswith(("&", "*", "!", "{", "[", "|", ">")):
            raise TunnelClientError(
                "TUNNEL_PROFILE_UNSAFE", "The Tunnel profile uses unsupported YAML syntax."
            )
        if path in scalars:
            raise TunnelClientError(
                "TUNNEL_PROFILE_UNSAFE", "The Tunnel profile contains a duplicate setting."
            )
        scalars[path] = _profile_scalar(value)
    if not paths:
        raise TunnelClientError("TUNNEL_PROFILE_UNSAFE", "The Tunnel profile is empty.")
    return scalars


def _validate_bounded_profile_values(
    scalars: Mapping[tuple[str, ...], str],
) -> None:
    if set(scalars) != _OFFICIAL_PROFILE_REQUIRED_SCALARS:
        raise TunnelClientError(
            "TUNNEL_PROFILE_UNSAFE", "The Tunnel profile differs from the bounded gptpro init shape."
        )
    expected = {
        ("config_version",): "1",
        ("control_plane", "base_url"): _CANONICAL_CONTROL_PLANE_BASE_URL,
        ("control_plane", "url_path"): _CANONICAL_CONTROL_PLANE_URL_PATH,
        ("control_plane", "api_key"): f"env:{_CONTROL_PLANE_KEY_ENV}",
        ("health", "listen_addr"): "127.0.0.1:0",
        ("admin_ui", "open_browser"): "false",
        ("log", "level"): "info",
        ("log", "format"): "json",
        ("mcp", "commands", "channel"): "main",
    }
    if any(scalars.get(path) != value for path, value in expected.items()):
        raise TunnelClientError(
            "TUNNEL_PROFILE_UNSAFE", "The Tunnel profile changes a bounded gptpro setting."
        )
    if _TUNNEL_ID.fullmatch(scalars[("control_plane", "tunnel_id")]) is None:
        raise TunnelClientError(
            "TUNNEL_PROFILE_UNSAFE", "The Tunnel profile has an invalid Tunnel identity."
        )


def _validate_restricted_profile(document: str, *, expected_mcp_command: str) -> None:
    scalars = _restricted_profile_values(document)
    _validate_bounded_profile_values(scalars)
    if scalars.get(("mcp", "commands", "command")) != expected_mcp_command:
        raise TunnelClientError(
            "TUNNEL_PROFILE_UNSAFE", "The Tunnel profile changes the bounded MCP command."
        )


def _read_profile_document(name: str, directory: Path) -> tuple[bytes, str]:
    path = directory / f"{name}.yaml"
    descriptor = -1
    try:
        descriptor = open_private_regular(path, flags=os.O_RDONLY)
        metadata = os.fstat(descriptor)
        if metadata.st_size <= 0 or metadata.st_size > _PROFILE_MAX_BYTES:
            raise TunnelClientError(
                "TUNNEL_PROFILE_UNSAFE", "The Tunnel profile size is outside the safe range."
            )
        chunks: list[bytes] = []
        remaining = _PROFILE_MAX_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(4096, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > _PROFILE_MAX_BYTES:
            raise TunnelClientError(
                "TUNNEL_PROFILE_UNSAFE", "The Tunnel profile size is outside the safe range."
            )
    except TunnelClientError:
        raise
    except RuntimeStateError as exc:
        if isinstance(exc.__cause__, FileNotFoundError):
            raise TunnelClientError(
                "TUNNEL_PROFILE_NOT_FOUND",
                "The requested Tunnel profile does not exist.",
            ) from exc
        raise TunnelClientError(exc.code, "The Tunnel profile file is unsafe.") from exc
    except OSError as exc:
        raise TunnelClientError("TUNNEL_PROFILE_UNSAFE", "Unable to read the Tunnel profile.") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        return payload, payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TunnelClientError("TUNNEL_PROFILE_UNSAFE", "The Tunnel profile is not UTF-8.") from exc


def _profile_security_snapshot(
    name: str,
    directory: Path,
    *,
    expected_mcp_command: str,
) -> ProfileSecuritySnapshot:
    path = directory / f"{name}.yaml"
    payload, document = _read_profile_document(name, directory)
    _validate_restricted_profile(document, expected_mcp_command=expected_mcp_command)
    return ProfileSecuritySnapshot(
        directory=directory,
        path=path,
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _regular_command_path(value: Path | str, *, executable: bool) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
        metadata = path.stat()
    except OSError as exc:
        raise TunnelClientError("RUNTIME_STATE_UNSAFE", "The MCP command path is unavailable.") from exc
    if (
        not path.is_absolute()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid not in {0, os.getuid()}
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or (executable and not os.access(path, os.X_OK))
        or any(ord(character) < 32 for character in str(path))
    ):
        raise TunnelClientError("RUNTIME_STATE_UNSAFE", "The MCP command path is unsafe.")
    return path


def _command_path_identity(value: Path | str, *, executable: bool) -> CommandPathIdentity:
    """Hash one safe command path through the same descriptor used for metadata."""

    path = _regular_command_path(value, executable=executable)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise TunnelClientError("RUNTIME_STATE_UNSAFE", "O_NOFOLLOW is required.")
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0))
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid not in {0, os.getuid()}
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) & 0o022
            or (executable and not os.access(path, os.X_OK))
        ):
            raise TunnelClientError("RUNTIME_STATE_UNSAFE", "The MCP command path is unsafe.")
        digest = hashlib.sha256()
        for chunk in iter(lambda: os.read(descriptor, 1024 * 1024), b""):
            digest.update(chunk)
        after = os.fstat(descriptor)
        current_path = path.lstat()
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(
            getattr(before, field) != getattr(observed, field)
            for observed in (after, current_path)
            for field in stable_fields
        ):
            raise TunnelClientError(
                "MCP_RUNTIME_IDENTITY_CHANGED",
                "The MCP command path changed while its identity was inspected.",
            )
        return CommandPathIdentity(
            path=path,
            sha256=digest.hexdigest(),
            device=before.st_dev,
            inode=before.st_ino,
        )
    except TunnelClientError:
        raise
    except OSError as exc:
        raise TunnelClientError(
            "RUNTIME_STATE_UNSAFE", "Unable to inspect the MCP command path."
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _exact_mcp_command(mcp_script: Path, python_executable: Path | str | None) -> str:
    script = _regular_command_path(mcp_script, executable=False)
    if script.name != "gptpro_mcp.py" or script.parent.name != "scripts":
        raise TunnelClientError("RUNTIME_STATE_UNSAFE", "The MCP command is not the gptpro entrypoint.")
    python = _regular_command_path(python_executable or sys.executable, executable=True)
    # The exact command is part of the approved/receipted MCP target identity.
    # Isolated mode ignores user-site, PYTHONPATH, and PYTHON* environment
    # configuration; -S suppresses sitecustomize; and the explicit /dev/null
    # pycache prefix prevents Python from reading source-adjacent .pyc files.
    return shlex.join(
        [
            str(python),
            "-I",
            "-S",
            "-B",
            f"-Xpycache_prefix={os.devnull}",
            str(script),
            "serve",
        ]
    )


def _bundled_mcp_command() -> str:
    """Return the canonical installed stdio entrypoint, independent of profile state."""

    skill_root = Path(__file__).resolve().parents[2]
    return _exact_mcp_command(skill_root / "scripts" / "gptpro_mcp.py", sys.executable)


def inspect_tunnel_profile(
    profile: str,
    *,
    env: Mapping[str, str],
    mcp_script: Path,
    profile_dir: Path | None = None,
    python_executable: Path | str | None = None,
) -> TunnelProfileInspection:
    """Classify an exact profile or a refreshable interpreter-path-only drift."""

    name = _profile(profile)
    directory = _resolved_profile_directory(profile_dir, env)
    payload, document = _read_profile_document(name, directory)
    scalars = _restricted_profile_values(document)
    _validate_bounded_profile_values(scalars)
    observed_command = scalars[("mcp", "commands", "command")]
    expected_command = _exact_mcp_command(mcp_script, python_executable)
    snapshot = ProfileSecuritySnapshot(
        directory=directory,
        path=directory / f"{name}.yaml",
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    identity = _profile_identity_sha256(name, snapshot)
    common = {
        "profile_sha256": identity,
        "profile_dir_sha256": hashlib.sha256(str(directory).encode("utf-8")).hexdigest(),
        "observed_mcp_command_sha256": hashlib.sha256(
            observed_command.encode("utf-8")
        ).hexdigest(),
        "expected_mcp_command_sha256": hashlib.sha256(
            expected_command.encode("utf-8")
        ).hexdigest(),
    }
    if secrets.compare_digest(observed_command, expected_command):
        return TunnelProfileInspection(
            ready=True,
            code=None,
            refresh_required=False,
            safe_to_refresh=False,
            reinit_required=False,
            **common,
        )
    try:
        observed_arguments = shlex.split(observed_command, posix=True)
        expected_arguments = shlex.split(expected_command, posix=True)
    except ValueError as exc:
        raise TunnelClientError(
            "TUNNEL_PROFILE_UNSAFE", "The Tunnel profile MCP command is malformed."
        ) from exc
    canonical_observed = observed_command == shlex.join(observed_arguments)
    entrypoint = observed_arguments[-2] if len(observed_arguments) >= 2 else ""
    entrypoint_mismatch = (
        len(observed_arguments) == len(expected_arguments)
        and len(observed_arguments) >= 3
        and observed_arguments[:-2] == expected_arguments[:-2]
        and observed_arguments[-1] == expected_arguments[-1]
        and observed_arguments[-2] != expected_arguments[-2]
        and Path(entrypoint).is_absolute()
        and Path(entrypoint).name == "gptpro_mcp.py"
        and Path(entrypoint).parent.name == "scripts"
        and not any(ord(character) < 32 for character in entrypoint)
        and canonical_observed
    )
    if entrypoint_mismatch:
        return TunnelProfileInspection(
            ready=False,
            code="MCP_SKILL_ENTRYPOINT_MISMATCH",
            refresh_required=False,
            safe_to_refresh=False,
            reinit_required=True,
            **common,
        )
    interpreter = observed_arguments[0] if observed_arguments else ""
    refreshable = (
        len(observed_arguments) == len(expected_arguments)
        and len(observed_arguments) >= 2
        and observed_arguments[1:] == expected_arguments[1:]
        and Path(interpreter).is_absolute()
        and not any(ord(character) < 32 for character in interpreter)
        and canonical_observed
    )
    if not refreshable:
        raise TunnelClientError(
            "TUNNEL_PROFILE_UNSAFE",
            "The Tunnel profile differs by more than the pinned Python interpreter path.",
        )
    return TunnelProfileInspection(
        ready=False,
        code="MCP_INTERPRETER_PATH_DRIFT",
        refresh_required=True,
        safe_to_refresh=True,
        reinit_required=False,
        **common,
    )


def _atomic_move_staged_profile(
    source_name: str,
    destination_name: str,
    staging: Path,
    destination: Path,
) -> None:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory_flag is None:
        raise TunnelClientError(
            "RUNTIME_STATE_UNSAFE", "Atomic profile replacement requires safe directory handles."
        )
    flags = os.O_RDONLY | nofollow | directory_flag | getattr(os, "O_CLOEXEC", 0)
    source_descriptor = -1
    destination_descriptor = -1
    try:
        source_descriptor = os.open(staging, flags)
        destination_descriptor = os.open(destination, flags)
        os.replace(
            source_name,
            destination_name,
            src_dir_fd=source_descriptor,
            dst_dir_fd=destination_descriptor,
        )
        os.fsync(source_descriptor)
        os.fsync(destination_descriptor)
    except OSError as exc:
        raise TunnelClientError(
            "TUNNEL_PROFILE_REFRESH_FAILED", "Unable to atomically replace the Tunnel profile."
        ) from exc
    finally:
        if source_descriptor >= 0:
            os.close(source_descriptor)
        if destination_descriptor >= 0:
            os.close(destination_descriptor)


def _write_profile_backup(path: Path, payload: bytes) -> None:
    """Write an owner-only, synced byte-for-byte rollback copy in the stage."""

    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory_flag is None:
        raise TunnelClientError(
            "RUNTIME_STATE_UNSAFE", "Profile rollback requires safe directory handles."
        )
    directory_descriptor = -1
    descriptor = -1
    try:
        directory_descriptor = os.open(
            path.parent,
            os.O_RDONLY | nofollow | directory_flag | getattr(os, "O_CLOEXEC", 0),
        )
        metadata = os.fstat(directory_descriptor)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise TunnelClientError(
                "RUNTIME_STATE_UNSAFE", "The profile refresh stage is not owner-only."
            )
        descriptor = os.open(
            path.name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | nofollow
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=directory_descriptor,
        )
        os.fchmod(descriptor, 0o600)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short profile backup write")
            view = view[written:]
        os.fsync(descriptor)
        os.fsync(directory_descriptor)
    except TunnelClientError:
        raise
    except OSError as exc:
        raise TunnelClientError(
            "TUNNEL_PROFILE_REFRESH_FAILED",
            "Unable to create the byte-for-byte profile rollback copy.",
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if directory_descriptor >= 0:
            os.close(directory_descriptor)


def _cleanup_profile_refresh_stage(staging: Path, *files: Path) -> bool:
    complete = True
    for path in files:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            complete = False
    try:
        staging.rmdir()
    except OSError:
        complete = False
    return complete


def _mcp_target_identity(arguments: list[str]) -> tuple[str, list[str]]:
    if len(arguments) < 3:
        raise ValueError("MCP target is not the exact gptpro stdio command")
    script_index = len(arguments) - 2
    if not Path(arguments[0]).is_absolute() or not Path(arguments[script_index]).is_absolute():
        raise ValueError("MCP target paths are not resolvable")
    interpreter = _command_path_identity(arguments[0], executable=True)
    script = _command_path_identity(arguments[script_index], executable=False)
    normalized_arguments = [*arguments]
    normalized_arguments[0] = str(interpreter.path)
    normalized_arguments[script_index] = str(script.path)
    canonical = json.dumps(
        {
            "identity_version": 2,
            "argv": normalized_arguments,
            "interpreter": {
                "path": str(interpreter.path),
                "sha256": interpreter.sha256,
                "device": interpreter.device,
                "inode": interpreter.inode,
            },
            "script": {
                "path": str(script.path),
                "sha256": script.sha256,
                "device": script.device,
                "inode": script.inode,
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest(), normalized_arguments


def bundled_mcp_target_sha256() -> str:
    """Return the current exact bundled stdio target identity."""

    arguments = shlex.split(_bundled_mcp_command(), posix=True)
    digest, _ = _mcp_target_identity(arguments)
    return digest


def _safe_environment_value(value: object) -> str | None:
    if not isinstance(value, str) or not value or "\x00" in value:
        return None
    if any(ord(character) < 32 for character in value):
        return None
    if _SECRET_SHAPED_ENV_VALUE.search(value):
        return None
    return value


def _minimal_tunnel_environment(
    source: Mapping[str, str] | None = None,
    *,
    include_control_plane_key: bool = False,
    trusted_child_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build the finite environment accepted by an external tunnel-client process."""

    environment = os.environ if source is None else source
    child: dict[str, str] = {}
    for name in _SAFE_CHILD_ENV_NAMES:
        safe = _safe_environment_value(environment.get(name))
        if safe is not None:
            child[name] = safe

    if include_control_plane_key:
        key = environment.get(_CONTROL_PLANE_KEY_ENV)
        if not isinstance(key, str) or _RUNTIME_KEY.fullmatch(key) is None:
            raise TunnelClientError(
                "TUNNEL_AUTH_UNAVAILABLE", "The runtime control-plane key is unavailable."
            )
        child[_CONTROL_PLANE_KEY_ENV] = key

    if trusted_child_environment is not None:
        supplied_names = set(trusted_child_environment)
        if supplied_names != _TRUSTED_GPTPRO_CHILD_ENV_NAMES:
            raise TunnelClientError(
                "RUNTIME_STATE_UNSAFE", "The MCP child capability environment is incomplete or unsafe."
            )
        capability = trusted_child_environment.get("GPTPRO_MCP_SESSION_CAPABILITY")
        runtime_directory = trusted_child_environment.get("GPTPRO_MCP_RUNTIME_DIR")
        if not isinstance(capability, str) or _SESSION_CAPABILITY.fullmatch(capability) is None:
            raise TunnelClientError(
                "RUNTIME_STATE_UNSAFE", "The MCP child session capability is invalid."
            )
        if (
            not isinstance(runtime_directory, str)
            or not runtime_directory
            or not Path(runtime_directory).is_absolute()
            or any(ord(character) < 32 for character in runtime_directory)
        ):
            raise TunnelClientError(
                "RUNTIME_STATE_UNSAFE", "The MCP child runtime directory is invalid."
            )
        child.update(
            {
                "GPTPRO_MCP_SESSION_CAPABILITY": capability,
                "GPTPRO_MCP_RUNTIME_DIR": runtime_directory,
            }
        )
    return child


def _safe_version(raw: str) -> str:
    line = raw.splitlines()[0].strip()[:128] if raw else "unknown"
    if not line or _RAW_SECRET.search(line) or any(ord(char) < 32 for char in line):
        return "unknown"
    return line


def validate_loopback_base_url(raw: str) -> str:
    """Return a normalized explicit loopback admin base URL without redirects."""

    try:
        parsed = urllib.parse.urlsplit(raw)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise TunnelClientError("TUNNEL_ADMIN_URL_REJECTED", "The Tunnel admin URL is invalid.") from exc
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise TunnelClientError(
            "TUNNEL_ADMIN_URL_REJECTED", "The Tunnel admin URL must be credential-free HTTP(S)."
        )
    if parsed.query or parsed.fragment or parsed.path not in {"", "/"} or port is None:
        raise TunnelClientError(
            "TUNNEL_ADMIN_URL_REJECTED",
            "The Tunnel admin URL must be an explicit loopback origin with a port.",
        )
    host = (parsed.hostname or "").casefold().rstrip(".")
    if host == "localhost":
        accepted = True
    else:
        try:
            accepted = ipaddress.ip_address(host).is_loopback
        except ValueError:
            accepted = False
    if not accepted:
        raise TunnelClientError(
            "TUNNEL_ADMIN_URL_REJECTED", "Only an explicit loopback Tunnel admin URL is allowed."
        )
    rendered_host = f"[{host}]" if ":" in host else host
    return f"{parsed.scheme}://{rendered_host}:{port}"


def _unix_health_base_url(socket_path: Path) -> str:
    path = Path(socket_path)
    if not path.is_absolute() or any(ord(character) < 32 for character in str(path)):
        raise TunnelClientError(
            "TUNNEL_ADMIN_URL_REJECTED", "The Tunnel health socket path is invalid."
        )
    encoded = base64.urlsafe_b64encode(str(path).encode("utf-8")).rstrip(b"=").decode("ascii")
    return f"http+unix://{encoded}"


def validate_unix_health_base_url(raw: str, *, expected_socket: Path) -> str:
    """Accept only the official canonical URL for one activation-owned Unix socket."""

    expected = _unix_health_base_url(expected_socket)
    try:
        parsed = urllib.parse.urlsplit(raw)
    except (TypeError, ValueError) as exc:
        raise TunnelClientError("TUNNEL_ADMIN_URL_REJECTED", "The Tunnel admin URL is invalid.") from exc
    if (
        raw != expected
        or parsed.scheme != "http+unix"
        or parsed.netloc == ""
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != ""
        or parsed.query != ""
        or parsed.fragment != ""
    ):
        raise TunnelClientError(
            "TUNNEL_ADMIN_URL_REJECTED",
            "The Tunnel admin URL does not name the activation-owned Unix socket.",
        )
    token = parsed.netloc
    try:
        padding = "=" * ((4 - len(token) % 4) % 4)
        decoded = base64.urlsafe_b64decode((token + padding).encode("ascii"))
    except (UnicodeEncodeError, ValueError) as exc:
        raise TunnelClientError(
            "TUNNEL_ADMIN_URL_REJECTED", "The Tunnel admin Unix socket URL is invalid."
        ) from exc
    if (
        base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != token
        or decoded != str(Path(expected_socket)).encode("utf-8")
    ):
        raise TunnelClientError(
            "TUNNEL_ADMIN_URL_REJECTED",
            "The Tunnel admin URL does not name the activation-owned Unix socket.",
        )
    return expected


def _read_owner_only_file(path: Path, *, maximum: int = 16 * 1024) -> str:
    if not path.is_absolute():
        raise TunnelClientError("TUNNEL_AUTH_UNAVAILABLE", "Secret file references must be absolute.")
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise TunnelClientError("RUNTIME_STATE_UNSAFE", "O_NOFOLLOW is required for secret files.")
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0))
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > maximum
        ):
            raise TunnelClientError(
                "RUNTIME_STATE_UNSAFE", "Secret files must be owner-only regular files with mode 0600."
            )
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(4096, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > maximum:
            raise TunnelClientError("TUNNEL_AUTH_UNAVAILABLE", "The secret file is unexpectedly large.")
        try:
            return payload.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise TunnelClientError("TUNNEL_AUTH_UNAVAILABLE", "The secret file is not UTF-8.") from exc
    except TunnelClientError:
        raise
    except OSError as exc:
        raise TunnelClientError("TUNNEL_AUTH_UNAVAILABLE", "Unable to read the secret reference.") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _resolve_reference(reference: str, environ: Mapping[str, str]) -> str:
    if reference.startswith("env:"):
        name = reference.removeprefix("env:")
        if _ENV_NAME.fullmatch(name) is None:
            raise TunnelClientError("TUNNEL_AUTH_UNAVAILABLE", "The environment reference is invalid.")
        value = environ.get(name, "")
    elif reference.startswith("file:"):
        value = _read_owner_only_file(Path(reference.removeprefix("file:")))
    else:
        raise TunnelClientError(
            "TUNNEL_AUTH_UNAVAILABLE", "Use an env:NAME or file:/absolute/path reference."
        )
    if not value:
        raise TunnelClientError("TUNNEL_AUTH_UNAVAILABLE", "The referenced secret is unavailable.")
    return value


def runtime_key_environment(
    reference: str,
    *,
    environ: Mapping[str, str] | None = None,
    base_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Resolve a transient key and return a child-only environment without printing it."""

    source = os.environ if environ is None else environ
    value = _resolve_reference(reference, source)
    if _RUNTIME_KEY.fullmatch(value) is None:
        raise TunnelClientError("TUNNEL_AUTH_UNAVAILABLE", "The runtime key reference is invalid.")
    base = os.environ if base_environment is None else base_environment
    child = _minimal_tunnel_environment(base)
    child[_CONTROL_PLANE_KEY_ENV] = value
    return child


def tunnel_binding_from_reference(
    package_id: str,
    reference: str,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Hash a transient Tunnel ID with the package without returning the raw identity."""

    if not isinstance(package_id, str) or not package_id:
        raise TunnelClientError("MCP_INVALID_ARGUMENT", "The package identity is invalid.")
    value = _resolve_reference(reference, os.environ if environ is None else environ)
    if _TUNNEL_ID.fullmatch(value) is None:
        raise TunnelClientError("TUNNEL_NOT_ASSOCIATED", "The Tunnel identity reference is invalid.")
    payload = b"gptpro-tunnel-binding-v1\0" + package_id.encode("utf-8") + b"\0" + value.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        del req, fp, code, msg, headers, newurl
        return None


def probe_loopback_admin(base_url: str, *, timeout: float = 2.0) -> LoopbackStatus:
    base = validate_loopback_base_url(base_url)
    opener = urllib.request.build_opener(_NoRedirect)

    def check(path: str) -> bool:
        request = urllib.request.Request(base + path, method="GET")
        try:
            with opener.open(request, timeout=timeout) as response:
                return 200 <= response.status < 300
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            return False

    healthy = check("/healthz")
    ready = check("/readyz") if healthy else False
    return LoopbackStatus(
        healthy=healthy,
        ready=ready,
        code=None if healthy and ready else "TUNNEL_NOT_READY",
    )


def loopback_url_from_file(path: Path, *, expected_socket: Path) -> str:
    descriptor = open_private_regular(Path(path), flags=os.O_RDONLY)
    try:
        metadata = os.fstat(descriptor)
        if metadata.st_size <= 0 or metadata.st_size > 4096:
            raise TunnelClientError("TUNNEL_NOT_READY", "The Tunnel health URL file is unavailable.")
        payload = os.read(descriptor, 4097)
    finally:
        os.close(descriptor)
    try:
        return validate_unix_health_base_url(
            payload.decode("utf-8").strip(), expected_socket=expected_socket
        )
    except UnicodeDecodeError as exc:
        raise TunnelClientError("TUNNEL_NOT_READY", "The Tunnel health URL file is invalid.") from exc


class _BoundedCommandError(Exception):
    """Internal output-limit or timeout failure with no captured child content."""


def _terminate_exact_child(process: subprocess.Popen[bytes]) -> None:
    """Stop and reap only the exact child handle created by this adapter."""

    if process.poll() is not None:
        return
    try:
        process.terminate()
    except OSError:
        pass
    try:
        process.wait(timeout=_COMMAND_STOP_GRACE_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        process.kill()
    except OSError:
        pass
    process.wait(timeout=_COMMAND_STOP_GRACE_SECONDS)


def _collect_bounded_output(
    process: subprocess.Popen[bytes],
    *,
    command: list[str],
    timeout: float,
    output_limit: int,
) -> subprocess.CompletedProcess[str]:
    """Collect stdout and stderr with one shared byte limit and deadline."""

    if timeout <= 0 or output_limit <= 0 or process.stdout is None or process.stderr is None:
        raise _BoundedCommandError("bounded command configuration is invalid")
    selector = selectors.DefaultSelector()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    total = 0
    deadline = time.monotonic() + timeout
    try:
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, data=name)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _BoundedCommandError("command deadline exceeded")
            events = selector.select(timeout=remaining)
            if not events:
                raise _BoundedCommandError("command deadline exceeded")
            for key, _ in events:
                read_limit = min(64 * 1024, output_limit - total + 1)
                try:
                    chunk = os.read(key.fd, read_limit)
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                buffers[str(key.data)].extend(chunk)
                total += len(chunk)
                if total > output_limit:
                    raise _BoundedCommandError("command output limit exceeded")
        remaining = deadline - time.monotonic()
        if remaining <= 0 and process.poll() is None:
            raise _BoundedCommandError("command deadline exceeded")
        try:
            returncode = process.wait(timeout=max(0.0, remaining))
        except subprocess.TimeoutExpired as exc:
            raise _BoundedCommandError("command deadline exceeded") from exc
        return subprocess.CompletedProcess(
            command,
            returncode,
            bytes(buffers["stdout"]).decode("utf-8", errors="replace"),
            bytes(buffers["stderr"]).decode("utf-8", errors="replace"),
        )
    finally:
        selector.close()


class TunnelClient:
    """Feature-probed adapter; it has no daemon, PID, profile deletion, or broad stop API."""

    def __init__(self, binary: Path | str | None = None, *, timeout: float = 10.0) -> None:
        located = str(binary) if binary is not None else shutil.which("tunnel-client")
        if not located:
            raise TunnelClientError("TUNNEL_CLIENT_NOT_FOUND", "The official tunnel-client was not found.")
        try:
            self.binary = Path(located).expanduser().resolve(strict=True)
        except OSError as exc:
            raise TunnelClientError("TUNNEL_CLIENT_NOT_FOUND", "The tunnel-client path is invalid.") from exc
        self.timeout = timeout
        self.binary_sha256, self._binary_device, self._binary_inode = self._inspect_binary()
        self._capabilities: TunnelCapabilities | None = None
        self._verified_profiles: dict[tuple[str, str], tuple[str, str]] = {}

    def _inspect_binary(self) -> tuple[str, int, int]:
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if nofollow is None:
            raise TunnelClientError("TUNNEL_CLIENT_UNSUPPORTED", "O_NOFOLLOW is required.")
        descriptor = -1
        try:
            descriptor = os.open(self.binary, os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0))
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid not in {0, os.getuid()}
                or stat.S_IMODE(metadata.st_mode) & 0o022
            ):
                raise TunnelClientError(
                    "TUNNEL_CLIENT_UNSUPPORTED", "The tunnel-client binary ownership or mode is unsafe."
                )
            digest = hashlib.sha256()
            for chunk in iter(lambda: os.read(descriptor, 1024 * 1024), b""):
                digest.update(chunk)
            return digest.hexdigest(), metadata.st_dev, metadata.st_ino
        except TunnelClientError:
            raise
        except OSError as exc:
            raise TunnelClientError("TUNNEL_CLIENT_UNSUPPORTED", "Unable to inspect tunnel-client.") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def _assert_binary_unchanged(self) -> None:
        digest, device, inode = self._inspect_binary()
        if (
            digest != self.binary_sha256
            or device != self._binary_device
            or inode != self._binary_inode
        ):
            raise TunnelClientError(
                "TUNNEL_CLIENT_UNSUPPORTED",
                "The tunnel-client binary changed after it was selected.",
            )

    def _run(
        self,
        argv: list[str],
        *,
        env: Mapping[str, str] | None = None,
        include_control_plane_key: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        child_env = _minimal_tunnel_environment(
            env, include_control_plane_key=include_control_plane_key
        )
        command = [str(self.binary), *argv]
        process: subprocess.Popen[bytes] | None = None
        try:
            # Keep this identity check adjacent to process creation so a binary that
            # changed after selection or capability probing fails closed.
            self._assert_binary_unchanged()
            process = subprocess.Popen(
                command,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=child_env,
            )
            return _collect_bounded_output(
                process,
                command=command,
                timeout=self.timeout,
                output_limit=_MAX_COMMAND_OUTPUT_BYTES,
            )
        except (KeyboardInterrupt, SystemExit):
            if process is not None:
                try:
                    _terminate_exact_child(process)
                except Exception:
                    pass
            raise
        except Exception:
            if process is not None:
                try:
                    _terminate_exact_child(process)
                except Exception:
                    pass
            raise TunnelClientError(
                "TUNNEL_CLIENT_UNSUPPORTED", "The tunnel-client capability check failed."
            ) from None
        finally:
            if process is not None:
                for stream in (process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()

    def probe(self) -> TunnelCapabilities:
        version = self._run(["--version"])
        quickstart = self._run(["help", "quickstart"])
        init_help = self._run(["init", "--help"])
        doctor_help = self._run(["doctor", "--help"])
        run_help = self._run(["run", "--help"])
        health_help = self._run(["health", "--help"])
        init_text = init_help.stdout + init_help.stderr
        doctor_text = doctor_help.stdout + doctor_help.stderr
        run_text = run_help.stdout + run_help.stderr
        health_text = health_help.stdout + health_help.stderr
        capabilities = TunnelCapabilities(
            binary_sha256=self.binary_sha256,
            version=_safe_version(version.stdout or version.stderr),
            quickstart_help=quickstart.returncode == 0,
            init_profile=init_help.returncode == 0
            and all(
                _help_has_exact_option(init_text, flag)
                for flag in (
                    "--profile",
                    "--profile-dir",
                    "--tunnel-id",
                    "--control-plane-api-key-ref",
                    "--control-plane-base-url",
                    "--control-plane-url-path",
                    "--health-listen-addr",
                    "--mcp-command",
                )
            ),
            doctor_profile=doctor_help.returncode == 0
            and all(
                _help_has_exact_option(doctor_text, flag)
                for flag in (
                    "--profile",
                    "--profile-dir",
                    "--ca-bundle",
                    "--control-plane.api-key",
                    "--control-plane.base-url",
                    "--control-plane.url-path",
                    "--log.file",
                    "--log.level",
                    "--explain",
                    "--json",
                )
            ),
            foreground_run=run_help.returncode == 0
            and all(
                _help_has_exact_option(run_text, flag)
                for flag in (
                    "--profile",
                    "--profile-dir",
                    "--ca-bundle",
                    "--control-plane.api-key",
                    "--control-plane.base-url",
                    "--control-plane.url-path",
                    "--health.listen-addr",
                    "--health.url-file",
                    "--pid.file",
                    "--log.file",
                    "--log.level",
                    "--mcp.max-concurrent-requests",
                )
            ),
            run_mcp_command_override=(
                run_help.returncode == 0
                and _help_has_exact_option(run_text, "--mcp.command")
            ),
            health_require_control_plane_poll=(
                health_help.returncode == 0
                and _help_has_exact_option(health_text, "--require-control-plane-poll")
            ),
            health_unix_socket=(
                run_help.returncode == 0
                and _help_has_exact_option(run_text, "--health.unix-socket")
            ),
            health_exact_pid=(
                health_help.returncode == 0
                and all(
                    _help_has_exact_option(health_text, flag)
                    for flag in ("--url-file", "--pid", "--json")
                )
            ),
            warn_log_level=(
                run_help.returncode == 0
                and _help_has_exact_option(run_text, "--log.level")
            ),
        )
        self._capabilities = capabilities
        return capabilities

    def init_profile_attended(
        self,
        profile: str,
        *,
        env: Mapping[str, str],
        tunnel_id_reference: str,
        control_plane_api_key_reference: str,
        mcp_script: Path,
        profile_dir: Path | None = None,
        python_executable: Path | str | None = None,
    ) -> TunnelInitResult:
        """Run the explicit first-use profile initializer as an attended setup action.

        Activation must never call this method. The raw Tunnel ID is placed only in the
        official init child argv because v0.0.12 requires it; it is not returned here.
        Child output is deliberately discarded so credentials or identifiers printed by
        a dependency cannot escape the wrapper's one-JSON-result contract.
        """

        capabilities = self._capabilities or self.probe()
        if not capabilities.init_profile:
            raise TunnelClientError(
                "TUNNEL_CLIENT_UNSUPPORTED", "The tunnel-client lacks required profile-init flags."
            )
        name = _profile(profile)
        directory = _resolved_profile_directory(profile_dir, env, create=True)
        raw_tunnel_id = _resolve_reference(tunnel_id_reference, env)
        if _TUNNEL_ID.fullmatch(raw_tunnel_id) is None:
            raise TunnelClientError("TUNNEL_NOT_ASSOCIATED", "The Tunnel identity reference is invalid.")
        raw_runtime_key = _resolve_reference(control_plane_api_key_reference, env)
        if _RUNTIME_KEY.fullmatch(raw_runtime_key) is None:
            raise TunnelClientError("TUNNEL_AUTH_UNAVAILABLE", "The runtime key reference is invalid.")
        child_env = _minimal_tunnel_environment(env)
        child_env[_CONTROL_PLANE_KEY_ENV] = raw_runtime_key
        raw_runtime_key = ""
        command = _exact_mcp_command(mcp_script, python_executable)
        argv = [
            str(self.binary),
            "init",
            "--profile",
            name,
            "--profile-dir",
            str(directory),
        ]
        argv.extend(
            [
                "--tunnel-id",
                raw_tunnel_id,
                "--control-plane-api-key-ref",
                f"env:{_CONTROL_PLANE_KEY_ENV}",
                "--control-plane-base-url",
                validate_control_plane_base_url(_CANONICAL_CONTROL_PLANE_BASE_URL),
                "--control-plane-url-path",
                _CANONICAL_CONTROL_PLANE_URL_PATH,
                "--health-listen-addr",
                "127.0.0.1:0",
                "--mcp-command",
                command,
            ]
        )
        self._assert_binary_unchanged()
        try:
            result = subprocess.run(
                argv,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                env=child_env,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TunnelClientError(
                "TUNNEL_PROFILE_INIT_FAILED", "Unable to run the attended Tunnel profile initializer."
            ) from exc
        finally:
            raw_tunnel_id = ""
            child_env.pop(_CONTROL_PLANE_KEY_ENV, None)
        snapshot = (
            _profile_security_snapshot(
                name,
                directory,
                expected_mcp_command=command,
            )
            if result.returncode == 0
            else None
        )
        profile_sha256 = (
            _profile_identity_sha256(name, snapshot)
            if snapshot is not None
            else hashlib.sha256(
                f"gptpro-tunnel-profile-init-failed-v1\0{name}\0{directory}".encode("utf-8")
            ).hexdigest()
        )
        return TunnelInitResult(
            ok=result.returncode == 0,
            code=None if result.returncode == 0 else "TUNNEL_PROFILE_INIT_FAILED",
            retryable=result.returncode != 0,
            profile_sha256=profile_sha256,
            profile_dir_sha256=hashlib.sha256(str(directory).encode("utf-8")).hexdigest(),
            mcp_command_sha256=hashlib.sha256(command.encode("utf-8")).hexdigest(),
        )

    def refresh_profile_attended(
        self,
        profile: str,
        *,
        env: Mapping[str, str],
        tunnel_id_reference: str,
        control_plane_api_key_reference: str,
        mcp_script: Path,
        expected_profile_sha256: str,
        profile_dir: Path | None = None,
        python_executable: Path | str | None = None,
    ) -> TunnelProfileRefreshResult:
        """Replace only an interpreter-path-stale profile through a validated stage."""

        capabilities = self._capabilities or self.probe()
        if not capabilities.init_profile:
            raise TunnelClientError(
                "TUNNEL_CLIENT_UNSUPPORTED", "The tunnel-client lacks required profile-init flags."
            )
        if re.fullmatch(r"[0-9a-f]{64}", expected_profile_sha256) is None:
            raise TunnelClientError(
                "MCP_INVALID_ARGUMENT", "The confirmed current Tunnel profile hash is invalid."
            )
        name = _profile(profile)
        directory = _resolved_profile_directory(profile_dir, env)
        inspection = inspect_tunnel_profile(
            name,
            env=env,
            mcp_script=mcp_script,
            profile_dir=directory,
            python_executable=python_executable,
        )
        if not secrets.compare_digest(inspection.profile_sha256, expected_profile_sha256):
            raise TunnelClientError(
                "TUNNEL_PROFILE_CHANGED", "The Tunnel profile changed after attended inspection."
            )
        if inspection.ready:
            raise TunnelClientError(
                "TUNNEL_PROFILE_CURRENT", "The Tunnel profile already uses the current interpreter."
            )
        if not inspection.refresh_required or not inspection.safe_to_refresh:
            raise TunnelClientError(
                "TUNNEL_PROFILE_UNSAFE", "The Tunnel profile is not safe for interpreter refresh."
            )

        profile_payload, document = _read_profile_document(name, directory)
        current_snapshot = ProfileSecuritySnapshot(
            directory=directory,
            path=directory / f"{name}.yaml",
            sha256=hashlib.sha256(profile_payload).hexdigest(),
        )
        if not secrets.compare_digest(
            _profile_identity_sha256(name, current_snapshot), expected_profile_sha256
        ):
            raise TunnelClientError(
                "TUNNEL_PROFILE_CHANGED", "The Tunnel profile changed before secret resolution."
            )
        scalars = _restricted_profile_values(document)
        _validate_bounded_profile_values(scalars)
        referenced_tunnel_id = _resolve_reference(tunnel_id_reference, env)
        if _TUNNEL_ID.fullmatch(referenced_tunnel_id) is None:
            raise TunnelClientError(
                "TUNNEL_NOT_ASSOCIATED", "The Tunnel identity reference is invalid."
            )
        existing_tunnel_id = scalars[("control_plane", "tunnel_id")]
        if not secrets.compare_digest(referenced_tunnel_id, existing_tunnel_id):
            referenced_tunnel_id = ""
            existing_tunnel_id = ""
            raise TunnelClientError(
                "TUNNEL_NOT_ASSOCIATED",
                "The replacement Tunnel identity differs from the existing profile.",
            )
        expected_tunnel_id_sha256 = hashlib.sha256(
            existing_tunnel_id.encode("utf-8")
        ).hexdigest()
        referenced_tunnel_id = ""
        existing_tunnel_id = ""

        staging = _profile_directory(
            directory / f".gptpro-refresh-{secrets.token_hex(16)}",
            create=True,
        )
        staging_profile = staging / f"{name}.yaml"
        backup_profile = staging / ".previous-profile.yaml"
        replacement_attempted = False
        refreshed: TunnelProfileInspection | None = None
        try:
            initialized = self.init_profile_attended(
                name,
                env=env,
                tunnel_id_reference=tunnel_id_reference,
                control_plane_api_key_reference=control_plane_api_key_reference,
                mcp_script=mcp_script,
                profile_dir=staging,
                python_executable=python_executable,
            )
            if not initialized.ok:
                raise TunnelClientError(
                    "TUNNEL_PROFILE_REFRESH_FAILED",
                    "The official Tunnel profile initializer failed during staged refresh.",
                )
            expected_command = _exact_mcp_command(mcp_script, python_executable)
            _, staged_document = _read_profile_document(name, staging)
            staged_scalars = _restricted_profile_values(staged_document)
            _validate_bounded_profile_values(staged_scalars)
            staged_tunnel_id_sha256 = hashlib.sha256(
                staged_scalars[("control_plane", "tunnel_id")].encode("utf-8")
            ).hexdigest()
            if not secrets.compare_digest(
                staged_tunnel_id_sha256, expected_tunnel_id_sha256
            ):
                raise TunnelClientError(
                    "TUNNEL_NOT_ASSOCIATED",
                    "The staged Tunnel profile changed the existing Tunnel identity.",
                )
            _profile_security_snapshot(
                name,
                staging,
                expected_mcp_command=expected_command,
            )
            latest = inspect_tunnel_profile(
                name,
                env=env,
                mcp_script=mcp_script,
                profile_dir=directory,
                python_executable=python_executable,
            )
            if not secrets.compare_digest(latest.profile_sha256, expected_profile_sha256):
                raise TunnelClientError(
                    "TUNNEL_PROFILE_CHANGED",
                    "The Tunnel profile changed while its replacement was staged.",
                )
            _write_profile_backup(backup_profile, profile_payload)
            replacement_attempted = True
            _atomic_move_staged_profile(
                staging_profile.name,
                f"{name}.yaml",
                staging,
                directory,
            )
            refreshed = inspect_tunnel_profile(
                name,
                env=env,
                mcp_script=mcp_script,
                profile_dir=directory,
                python_executable=python_executable,
            )
            if not refreshed.ready:
                raise TunnelClientError(
                    "TUNNEL_PROFILE_REFRESH_FAILED",
                    "The refreshed Tunnel profile did not bind the current interpreter.",
                )
        except BaseException as failure:
            rollback_error: TunnelClientError | None = None
            if replacement_attempted:
                try:
                    _atomic_move_staged_profile(
                        backup_profile.name,
                        f"{name}.yaml",
                        staging,
                        directory,
                    )
                    restored_payload, _ = _read_profile_document(name, directory)
                    if not secrets.compare_digest(restored_payload, profile_payload):
                        raise TunnelClientError(
                            "TUNNEL_PROFILE_ROLLBACK_FAILED",
                            "The original Tunnel profile bytes were not restored.",
                        )
                except TunnelClientError as exc:
                    rollback_error = exc
            if rollback_error is not None:
                raise TunnelClientError(
                    "TUNNEL_PROFILE_ROLLBACK_FAILED",
                    "The atomic profile refresh failed, its original bytes could not be restored, and the private stage was retained for attended recovery.",
                ) from failure
            if not _cleanup_profile_refresh_stage(
                staging, staging_profile, backup_profile
            ):
                raise TunnelClientError(
                    "TUNNEL_PROFILE_STAGE_CLEANUP_REQUIRED",
                    "The refresh failed and its owner-only private stage could not be removed; attended local cleanup is required before retrying.",
                ) from failure
            raise
        if refreshed is None:
            raise TunnelClientError(
                "TUNNEL_PROFILE_REFRESH_FAILED", "The Tunnel profile refresh produced no result."
            )
        cleanup_complete = _cleanup_profile_refresh_stage(
            staging, staging_profile, backup_profile
        )
        return TunnelProfileRefreshResult(
            ok=True,
            previous_profile_sha256=inspection.profile_sha256,
            profile_sha256=refreshed.profile_sha256,
            profile_dir_sha256=refreshed.profile_dir_sha256,
            mcp_command_sha256=refreshed.expected_mcp_command_sha256,
            staging_cleanup_complete=cleanup_complete,
        )

    def doctor(
        self,
        profile: str,
        *,
        env: Mapping[str, str],
        profile_dir: Path | None = None,
        package_id: str | None = None,
        expected_tunnel_binding_sha256: str | None = None,
        expected_mcp_script: Path | None = None,
        python_executable: Path | str | None = None,
    ) -> TunnelCheck:
        self._assert_binary_unchanged()
        name = _profile(profile)
        directory = _resolved_profile_directory(profile_dir, env)
        expected_command = _exact_mcp_command(
            expected_mcp_script or Path(__file__).resolve().parents[2] / "scripts" / "gptpro_mcp.py",
            python_executable,
        )
        snapshot = _profile_security_snapshot(
            name,
            directory,
            expected_mcp_command=expected_command,
        )
        profile_sha256 = _profile_identity_sha256(name, snapshot)
        latest_snapshot = _profile_security_snapshot(
            name,
            directory,
            expected_mcp_command=expected_command,
        )
        if _profile_identity_sha256(name, latest_snapshot) != profile_sha256:
            raise TunnelClientError(
                "TUNNEL_PROFILE_CHANGED",
                "The Tunnel profile changed during doctor preflight.",
            )
        argv = ["doctor", "--profile", name, "--profile-dir", str(directory)]
        argv.extend(_runtime_control_plane_arguments())
        argv.extend(["--log.file", os.devnull, "--log.level", "warn", "--explain", "--json"])
        result = self._run(argv, env=env, include_control_plane_key=True)
        latest_snapshot = _profile_security_snapshot(
            name,
            directory,
            expected_mcp_command=expected_command,
        )
        if _profile_identity_sha256(name, latest_snapshot) != profile_sha256:
            raise TunnelClientError(
                "TUNNEL_PROFILE_CHANGED",
                "The Tunnel profile changed during doctor preflight.",
            )
        observed_binding: str | None = None
        binding_matches: bool | None = None
        target_digest: str | None = None
        target_matches: bool | None = None
        verification = "unavailable"
        if expected_tunnel_binding_sha256 is not None:
            expected = _hash_or_error(expected_tunnel_binding_sha256)
            if not isinstance(package_id, str) or not package_id:
                raise TunnelClientError("MCP_INVALID_ARGUMENT", "package_id is required for Tunnel binding.")
            if expected_mcp_script is None:
                raise TunnelClientError(
                    "MCP_INVALID_ARGUMENT", "The exact gptpro MCP target is required for profile binding."
                )
            try:
                document = json.loads(result.stdout)
                raw_tunnel_id = _doctor_tunnel_id(document)
                target_digest, target_matches = _doctor_mcp_target_identity(
                    document,
                    expected_mcp_script=expected_mcp_script,
                    python_executable=python_executable,
                )
            except (json.JSONDecodeError, ValueError, RecursionError):
                return TunnelCheck(
                    ok=False,
                    code="TUNNEL_CLIENT_UNSUPPORTED",
                    retryable=False,
                    profile_sha256=profile_sha256,
                )
            observed_binding = hashlib.sha256(
                b"gptpro-tunnel-binding-v1\0"
                + package_id.encode("utf-8")
                + b"\0"
                + raw_tunnel_id.encode("utf-8")
            ).hexdigest()
            raw_tunnel_id = ""
            binding_matches = observed_binding == expected
            verification = (
                "automatic-doctor-json"
                if binding_matches and target_matches
                else "doctor-json-mismatch"
            )
        check = TunnelCheck(
            ok=(
                result.returncode == 0
                and binding_matches is not False
                and target_matches is not False
            ),
            code=(
                None
                if result.returncode == 0
                and binding_matches is not False
                and target_matches is not False
                else "TUNNEL_NOT_ASSOCIATED"
                if binding_matches is False or target_matches is False
                else "TUNNEL_NOT_READY"
            ),
            retryable=result.returncode != 0 and binding_matches is not False and target_matches is not False,
            profile_sha256=profile_sha256,
            tunnel_binding_sha256=observed_binding,
            tunnel_binding_matches=binding_matches,
            mcp_target_sha256=target_digest,
            mcp_target_matches=target_matches,
            profile_binding_verification=verification,
        )
        if check.ok and target_digest is not None and target_matches is True:
            self._verified_profiles[(name, str(directory))] = (profile_sha256, target_digest)
        return check

    def health(
        self,
        files: TunnelRuntimeFiles,
        *,
        env: Mapping[str, str],
        expected_pid: int,
    ) -> TunnelCheck:
        capabilities = self._capabilities or self.probe()
        if (
            not capabilities.health_require_control_plane_poll
            or not capabilities.health_unix_socket
            or not capabilities.health_exact_pid
        ):
            return TunnelCheck(
                ok=False,
                code="TUNNEL_CLIENT_UNSUPPORTED",
                retryable=False,
                profile_sha256=hashlib.sha256(b"health-files").hexdigest(),
            )
        if isinstance(expected_pid, bool) or not isinstance(expected_pid, int) or expected_pid <= 0:
            raise TunnelClientError(
                "TUNNEL_NOT_READY", "The owned Tunnel process identity is invalid."
            )
        _validate_runtime_files(files, require_socket=True)
        loopback_url_from_file(files.url_file, expected_socket=files.socket_file)
        if not _pid_file_matches_owned_process(files.pid_file, expected_pid):
            return TunnelCheck(
                ok=False,
                code="TUNNEL_NOT_READY",
                retryable=True,
                profile_sha256=hashlib.sha256(b"health-files").hexdigest(),
            )
        result = self._run(
            [
                "health",
                "--url-file",
                str(files.url_file),
                "--pid",
                str(expected_pid),
                "--require-control-plane-poll",
                "--json",
            ],
            env=env,
        )
        return TunnelCheck(
            ok=result.returncode == 0,
            code=None if result.returncode == 0 else "TUNNEL_NOT_READY",
            retryable=result.returncode != 0,
            profile_sha256=hashlib.sha256(b"health-files").hexdigest(),
            control_plane_poll_confirmed=result.returncode == 0,
        )

    def spawn_run(
        self,
        profile: str,
        *,
        env: Mapping[str, str],
        runtime_files: TunnelRuntimeFiles,
        extra_env: Mapping[str, str] | None = None,
        profile_dir: Path | None = None,
        cwd: Path | None = None,
        expected_mcp_target_sha256: str | None = None,
        request_correlation_diagnostic: bool = False,
    ) -> subprocess.Popen[bytes]:
        self._assert_binary_unchanged()
        name = _profile(profile)
        capabilities = self._capabilities or self.probe()
        if not capabilities.supported or capabilities.binary_sha256 != self.binary_sha256:
            raise TunnelClientError(
                "TUNNEL_CLIENT_UNSUPPORTED",
                "The tunnel-client lacks required init, doctor, run, or health capabilities.",
            )
        _validate_runtime_files(runtime_files)
        child_env = _minimal_tunnel_environment(
            env,
            include_control_plane_key=True,
            trusted_child_environment=extra_env,
        )
        directory = _resolved_profile_directory(profile_dir, child_env)
        command = _bundled_mcp_command()
        snapshot = _profile_security_snapshot(
            name,
            directory,
            expected_mcp_command=command,
        )
        profile_sha256 = _profile_identity_sha256(name, snapshot)
        verified_profile = self._verified_profiles.get((name, str(directory)))
        if verified_profile is None or verified_profile[0] != profile_sha256:
            raise TunnelClientError(
                "TUNNEL_PROFILE_CHANGED",
                "The Tunnel profile was not verified or changed after doctor preflight.",
            )
        verified_target_sha256 = verified_profile[1]
        if expected_mcp_target_sha256 is not None:
            expected_target = _hash_or_error(expected_mcp_target_sha256)
            if expected_target != verified_target_sha256:
                raise TunnelClientError(
                    "MCP_RUNTIME_IDENTITY_CHANGED",
                    "The approved MCP target differs from the doctor-verified target.",
                )
        argv = [
            str(self.binary),
            "run",
            "--profile",
            name,
            "--profile-dir",
            str(directory),
        ]
        argv.extend(_runtime_control_plane_arguments())
        argv.extend(
            [
                "--health.unix-socket",
                str(runtime_files.socket_file),
                "--health.url-file",
                str(runtime_files.url_file),
                "--pid.file",
                str(runtime_files.pid_file),
                "--log.file",
                os.devnull,
                "--log.level",
                "info" if request_correlation_diagnostic else "warn",
                "--mcp.max-concurrent-requests",
                "1",
                "--mcp.command",
                f"channel=main,command={command}",
            ]
        )
        latest_snapshot = _profile_security_snapshot(
            name,
            directory,
            expected_mcp_command=command,
        )
        if _profile_identity_sha256(name, latest_snapshot) != profile_sha256:
            raise TunnelClientError(
                "TUNNEL_PROFILE_CHANGED",
                "The Tunnel profile changed before foreground execution.",
            )
        self._assert_binary_unchanged()
        # Re-hash the exact interpreter and entrypoint immediately before the
        # tunnel process is created. The Tunnel launches this textual command
        # later, so any same-path replacement since doctor must fail closed.
        if bundled_mcp_target_sha256() != verified_target_sha256:
            raise TunnelClientError(
                "MCP_RUNTIME_IDENTITY_CHANGED",
                "The MCP interpreter or entrypoint changed before foreground execution.",
            )
        try:
            return subprocess.Popen(
                argv,
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=None if cwd is None else str(cwd),
                env=child_env,
                start_new_session=False,
                umask=0o077,
            )
        except OSError as exc:
            raise TunnelClientError("TUNNEL_NOT_READY", "Unable to start tunnel-client foreground run.") from exc

    def capture_request_correlation(
        self,
        runtime_files: TunnelRuntimeFiles,
        *,
        hmac_key: bytes,
    ) -> dict[str, Any]:
        """Read and sanitize one bounded private admin-log snapshot in memory."""

        _validate_runtime_files(runtime_files, require_socket=True)
        loopback_url_from_file(
            runtime_files.url_file,
            expected_socket=runtime_files.socket_file,
        )
        return _capture_request_correlation(
            runtime_files.socket_file,
            hmac_key=hmac_key,
        )


def _hash_or_error(value: str | None) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise TunnelClientError("TUNNEL_NOT_ASSOCIATED", "The Tunnel binding digest is invalid.")
    return value


def _doctor_tunnel_id(document: Any) -> str:
    candidate = _doctor_check_summary(document, "tunnel_id")
    if _TUNNEL_ID.fullmatch(candidate) is None:
        raise ValueError("doctor tunnel identity is missing")
    return candidate


def _doctor_check_summary(document: Any, check_id: str) -> str:
    if not isinstance(document, Mapping) or document.get("result") != "ok":
        raise ValueError("doctor output is not a successful report")
    checks = document.get("checks")
    if not isinstance(checks, list):
        raise ValueError("doctor output has no checks")
    candidates = [
        item.get("summary")
        for item in checks
        if isinstance(item, Mapping)
        and item.get("id") == check_id
        and item.get("status") == "PASS"
    ]
    if len(candidates) != 1 or not isinstance(candidates[0], str) or not candidates[0]:
        raise ValueError(f"doctor {check_id} check is missing")
    return candidates[0]


def _doctor_mcp_target_identity(
    document: Any,
    *,
    expected_mcp_script: Path,
    python_executable: Path | str | None,
) -> tuple[str, bool]:
    summary = _doctor_check_summary(document, "mcp_target")
    try:
        arguments = shlex.split(summary, posix=True)
    except ValueError as exc:
        raise ValueError("doctor MCP target is not a valid command") from exc
    expected_arguments = shlex.split(
        _exact_mcp_command(expected_mcp_script, python_executable), posix=True
    )
    if len(arguments) != len(expected_arguments):
        raise ValueError("doctor MCP target is not the exact gptpro stdio command")
    digest, normalized_arguments = _mcp_target_identity(arguments)
    expected_digest, normalized_expected = _mcp_target_identity(expected_arguments)
    return digest, normalized_arguments == normalized_expected and digest == expected_digest
