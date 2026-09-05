"""Govern one approved ChatGPT Desktop consultation."""

from __future__ import annotations

import ctypes
import errno
import fcntl
import json
import os
import plistlib
import shutil
import socket
import stat
import subprocess
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .approvals import ApprovalError, load_state, save_state, verify_active_approval
from .package import verify_package
from .receipts import ReceiptError, append_receipt, load_receipt
from .schema import CHAT_HISTORY_MODE, DELIVERY_CHANNEL
from .state import StateError, atomic_write, package_lock, secure_directory, sha256_bytes, sha256_file, write_json


PARENT_TIMEOUT_GRACE_SECONDS = 5
DEFAULT_CONSULT_TIMEOUT_SECONDS = 45 * 60
PROGRESS_STAGES = {
    "preflight",
    "dispatch_ready",
    "dispatch_authorized",
    "submitted",
    "response_headers",
    "response_stream",
    "stream_handoff",
    "current_branch_proof",
    "response_dom",  # Preserve verification of receipts created by the retired DOM observer.
    "response_readback",
    "complete",
}
CHATGPT_APP = Path("/Applications/ChatGPT.app")
LAUNCHER_NAME = "gptpro Launcher.app"
LAUNCHER_DISPLAY_NAME = "gptpro Launcher"
LAUNCHER_ICON = "gptpro-launcher.icns"
LAUNCHER_BUNDLE_ID = "com.oozoofrog.gptpro-launcher"
LAUNCHER_EXECUTABLE = "gptpro-launcher"
LAUNCHER_VERSION = "0.6.0"
RUNNER_PORT = 9223
RUNNER_ENDPOINT = f"http://127.0.0.1:{RUNNER_PORT}"
RUNNER_PROFILE_RELATIVE = Path("Library/Application Support/gptpro/runner/v1/profile")
RENAME_SWAP = 0x00000002
RENAME_EXCL = 0x00000004
KNOWN_LEGACY_LAUNCHER_SCRIPT_HASHES = {
    "4d618362c8f4f35bc4c4817b32d881119cb939b83fe327088e2ad17410de941c",
}


def _launcher_script() -> bytes:
    script = """#!/bin/zsh
set -eu
umask 077

chatgpt='/Applications/ChatGPT.app'
chatgpt_executable='/Applications/ChatGPT.app/Contents/MacOS/ChatGPT'
runner_root="$HOME/Library/Application Support/gptpro/runner/v1"
runner_profile="$runner_root/profile"
runner_endpoint='http://127.0.0.1:__RUNNER_PORT__'

if [[ ! -d "$chatgpt" ]]; then
  /usr/bin/osascript -e 'display dialog "ChatGPT.app을 /Applications에서 찾을 수 없습니다." buttons {"OK"} default button "OK" with title "gptpro Launcher"' >/dev/null
  exit 2
fi

for path in "$HOME/Library/Application Support/gptpro" "$HOME/Library/Application Support/gptpro/runner" "$runner_root" "$runner_profile"; do
  if [[ -L "$path" ]]; then
    /usr/bin/osascript -e 'display dialog "gptpro Runner 프로필 경로가 심볼릭 링크입니다. 안전을 위해 실행하지 않았습니다." buttons {"OK"} default button "OK" with title "gptpro Launcher"' >/dev/null
    exit 2
  fi
done
/bin/mkdir -p "$runner_profile"
/bin/chmod 700 "$HOME/Library/Application Support/gptpro" "$HOME/Library/Application Support/gptpro/runner" "$runner_root" "$runner_profile"

current_uid=$(/usr/bin/id -u)
if ! process_list=$(/bin/ps -axo uid=,command=); then
  /usr/bin/osascript -e 'display dialog "gptpro Runner 실행 상태를 확인할 수 없습니다. 잠시 후 다시 시도하세요." buttons {"OK"} default button "OK" with title "gptpro Launcher"' >/dev/null
  exit 2
fi
if print -r -- "$process_list" | /usr/bin/awk -v uid="$current_uid" -v executable="$chatgpt_executable" '
  $1 == uid {
    $1 = ""
    sub(/^ +/, "")
    if (index($0, executable " ") == 1 && index($0, "--user-data-dir=" ENVIRON["HOME"] "/Library/Application Support/gptpro/runner/v1/profile") > 0 && index($0, "--remote-debugging-port=__RUNNER_PORT__") > 0) found = 1
  }
  END { exit found ? 0 : 1 }
'; then
  for attempt in {1..20}; do
    if /usr/bin/curl --fail --silent --max-time 1 "$runner_endpoint/json" >/dev/null 2>&1; then
      exit 0
    fi
    /bin/sleep 0.25
  done
  /usr/bin/osascript -e 'display dialog "gptpro Runner 프로세스가 실행 중이지만 준비되지 않았습니다. 해당 Runner 창을 닫은 뒤 다시 시도하세요." buttons {"OK"} default button "OK" with title "gptpro Launcher"' >/dev/null
  exit 2
fi

if /usr/bin/curl --fail --silent --max-time 1 "$runner_endpoint/json" >/dev/null 2>&1; then
  /usr/bin/osascript -e 'display dialog "다른 프로그램이 gptpro Runner 포트를 사용 중입니다. 해당 프로그램을 종료한 뒤 다시 시도하세요." buttons {"OK"} default button "OK" with title "gptpro Launcher"' >/dev/null
  exit 2
fi

exec /usr/bin/open -na "$chatgpt" --args \
  "--user-data-dir=$runner_profile" \
  --remote-debugging-address=127.0.0.1 \
  --remote-debugging-port=__RUNNER_PORT__
"""
    return script.replace("__RUNNER_PORT__", str(RUNNER_PORT)).encode("utf-8")


def _launcher_icon() -> bytes:
    return (Path(__file__).resolve().parents[2] / "assets" / LAUNCHER_ICON).read_bytes()


def _launcher_plist() -> bytes:
    script_hash = sha256_bytes(_launcher_script())
    return plistlib.dumps(
        {
            "CFBundleDevelopmentRegion": "en",
            "CFBundleDisplayName": LAUNCHER_DISPLAY_NAME,
            "CFBundleExecutable": LAUNCHER_EXECUTABLE,
            "CFBundleIdentifier": LAUNCHER_BUNDLE_ID,
            "CFBundleInfoDictionaryVersion": "6.0",
            "CFBundleName": LAUNCHER_DISPLAY_NAME,
            "CFBundleIconFile": LAUNCHER_ICON,
            "CFBundlePackageType": "APPL",
            "CFBundleShortVersionString": LAUNCHER_VERSION,
            "CFBundleVersion": "2",
            "LSMinimumSystemVersion": "13.0",
            "LSUIElement": True,
            "GPTProLauncherManaged": True,
            "GPTProLauncherScriptSHA256": script_hash,
            "GPTProLauncherIconSHA256": sha256_bytes(_launcher_icon()),
            "GPTProRunnerIsolatedProfile": True,
            "GPTProRunnerPort": RUNNER_PORT,
        },
        fmt=plistlib.FMT_XML,
        sort_keys=True,
    )


def _launcher_destination(applications_dir: Path | None = None) -> Path:
    root = (applications_dir or (Path.home() / "Applications")).expanduser().resolve()
    return root / LAUNCHER_NAME


def _launcher_managed(path: Path) -> bool:
    if path.is_symlink() or not path.is_dir():
        return False
    info = path / "Contents" / "Info.plist"
    executable = path / "Contents" / "MacOS" / LAUNCHER_EXECUTABLE
    if info.is_symlink() or executable.is_symlink() or not info.is_file() or not executable.is_file():
        return False
    try:
        value = plistlib.loads(info.read_bytes())
        path_stat = path.stat()
        info_stat = info.stat()
        executable_stat = executable.stat()
        script_hash = sha256_file(executable)
    except (OSError, plistlib.InvalidFileException):
        return False
    recorded_script_hash = value.get("GPTProLauncherScriptSHA256")
    recorded_icon_hash = value.get("GPTProLauncherIconSHA256")
    if recorded_icon_hash is not None:
        resources = path / "Contents" / "Resources"
        icon = resources / LAUNCHER_ICON
        try:
            icon_stat = icon.lstat()
            if (
                resources.is_symlink()
                or not resources.is_dir()
                or value.get("CFBundleIconFile") != LAUNCHER_ICON
                or not stat.S_ISREG(icon_stat.st_mode)
                or icon_stat.st_uid != os.getuid()
                or icon_stat.st_nlink != 1
                or sha256_file(icon) != recorded_icon_hash
            ):
                return False
        except OSError:
            return False
    script_hash_matches = recorded_script_hash == script_hash or (
        recorded_script_hash is None
        and value.get("CFBundleShortVersionString") == "0.5.0"
        and script_hash in KNOWN_LEGACY_LAUNCHER_SCRIPT_HASHES
    )
    return (
        value.get("CFBundleIdentifier") == LAUNCHER_BUNDLE_ID
        and value.get("GPTProLauncherManaged") is True
        and script_hash_matches
        and path_stat.st_uid == os.getuid()
        and info_stat.st_uid == os.getuid()
        and executable_stat.st_uid == os.getuid()
        and stat.S_ISREG(info_stat.st_mode)
        and stat.S_ISREG(executable_stat.st_mode)
        and info_stat.st_nlink == 1
        and executable_stat.st_nlink == 1
    )


def _launcher_current(path: Path) -> bool:
    if not _launcher_managed(path):
        return False
    info = path / "Contents" / "Info.plist"
    executable = path / "Contents" / "MacOS" / LAUNCHER_EXECUTABLE
    try:
        return (
            info.read_bytes() == _launcher_plist()
            and executable.read_bytes() == _launcher_script()
            and executable.stat().st_mode & 0o777 == 0o755
            and (path / "Contents" / "Resources" / LAUNCHER_ICON).read_bytes() == _launcher_icon()
        )
    except OSError:
        return False


def _launcher_identity(path: Path) -> tuple[int, int]:
    value = path.stat(follow_symlinks=False)
    return value.st_dev, value.st_ino


def _renamex(source: Path, destination: Path, flags: int) -> None:
    renamex = ctypes.CDLL(None, use_errno=True).renamex_np
    renamex.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    renamex.restype = ctypes.c_int
    if renamex(os.fsencode(source), os.fsencode(destination), flags) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


def _fsync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _launcher_lock(root: Path):
    lock_path = root / ".gptpro-launcher.lock"
    flags = os.O_CREAT | os.O_RDWR | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise ControllerError("GPTPRO_LAUNCHER_LOCK_UNSAFE", "The launcher lock file could not be opened safely.") from exc
    try:
        os.fchmod(descriptor, 0o600)
        value = os.fstat(descriptor)
        if value.st_uid != os.getuid() or not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
            raise ControllerError("GPTPRO_LAUNCHER_LOCK_UNSAFE", "The launcher lock file is not owner-only and regular.")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ControllerError(
                "GPTPRO_LAUNCHER_BUSY",
                "Another gptpro launcher install or uninstall is in progress.",
                retryable=True,
            ) from exc
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _trash_root(value: Path | None) -> Path:
    trash = (value or (Path.home() / ".Trash")).expanduser().resolve()
    trash.mkdir(parents=True, exist_ok=True, mode=0o700)
    return trash


def _trash_destination(trash: Path) -> Path:
    return trash / f"gptpro Launcher-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.app"


def _require_same_volume(source: Path, trash: Path) -> None:
    if source.stat().st_dev != trash.stat().st_dev:
        raise ControllerError(
            "GPTPRO_LAUNCHER_TRASH_CROSS_VOLUME",
            "The launcher and user Trash are on different filesystems.",
            recovery="Move the launcher to that volume's Trash yourself; gptpro will not copy and delete it.",
        )


def _runner_profile() -> Path:
    return Path.home() / RUNNER_PROFILE_RELATIVE


def _secure_runner_profile() -> Path:
    profile = _runner_profile()
    # Keep every gptpro-owned component private without changing permissions on
    # the user's home, Library, or Application Support directories.
    for directory in (profile.parents[2], profile.parents[1], profile.parent, profile):
        secure_directory(directory)
    return profile


def _runner_state() -> tuple[str, list[int]]:
    try:
        pids = _runner_pids()
    except ControllerError:
        return "unknown", []
    return ("running", pids) if pids else ("not_running", [])


def launcher_status(
    *,
    skill_root: Path | None = None,
    applications_dir: Path | None = None,
) -> dict[str, Any]:
    destination = _launcher_destination(applications_dir)
    exists = destination.exists() or destination.is_symlink()
    managed = _launcher_managed(destination) if exists else False
    process_state, runner_pids = _runner_state()
    port_open = _port_open(RUNNER_PORT)
    doctor_error_code = None
    if process_state == "unknown":
        mode = "process_state_unknown"
    elif process_state == "not_running":
        mode = "port_conflict" if port_open else "stopped"
    elif not port_open:
        mode = "runner_starting"
    else:
        mode = "runner_unverified"
        if skill_root is not None:
            try:
                desktop_doctor(skill_root)
                mode = "runner_verified"
            except ControllerError as exc:
                doctor_error_code = exc.code
    ordinary_running = None
    if process_state != "unknown":
        try:
            ordinary_running = bool(set(_app_pids()) - set(runner_pids))
        except ControllerError:
            ordinary_running = None
    return {
        "ok": True,
        "operation": "launcher-status",
        "path": str(destination),
        "installed": exists,
        "managed_by_gptpro": managed,
        "current": _launcher_current(destination) if managed else False,
        "launcher_expected_display_name": LAUNCHER_DISPLAY_NAME,
        "launcher_expected_icon": LAUNCHER_ICON,
        "runner_native_identity_customized": False,
        "runner_identity_note": "Runner shares the original ChatGPT app's Dock, app switcher, menu and window identity. Launcher branding does not change it.",
        "chatgpt_running": True if process_state == "running" else False if process_state == "not_running" else None,
        "chatgpt_process_state": process_state,
        "chatgpt_mode": mode,
        "runner_running": True if process_state == "running" else False if process_state == "not_running" else None,
        "runner_pids": runner_pids,
        "runner_endpoint": RUNNER_ENDPOINT,
        "runner_profile": str(_runner_profile()),
        "ordinary_chatgpt_running": ordinary_running,
        "ordinary_chatgpt_relaunch_required": False,
        "doctor_error_code": doctor_error_code,
        "cdp_port_open": port_open,
        "automatic_app_termination": False,
        "login_item_installed": False,
    }


def launcher_install(
    *,
    applications_dir: Path | None = None,
    trash_dir: Path | None = None,
) -> dict[str, Any]:
    if not CHATGPT_APP.is_dir():
        raise ControllerError("CHATGPT_APP_NOT_FOUND", "The ChatGPT app is not installed at /Applications/ChatGPT.app.")
    destination = _launcher_destination(applications_dir)
    root = destination.parent
    root.mkdir(parents=True, exist_ok=True, mode=0o755)
    with _launcher_lock(root):
        if destination.exists() or destination.is_symlink():
            if not _launcher_managed(destination):
                raise ControllerError(
                    "GPTPRO_LAUNCHER_CONFLICT",
                    f"A different item already exists at {destination}.",
                    recovery="Move or rename that item yourself, then run launcher-install again.",
                )
            if _launcher_current(destination):
                return {**launcher_status(applications_dir=root), "operation": "launcher-install", "changed": False}

        temporary_root = Path(tempfile.mkdtemp(prefix=".gptpro-launcher-", dir=root))
        staged = temporary_root / LAUNCHER_NAME
        try:
            executable_dir = staged / "Contents" / "MacOS"
            executable_dir.mkdir(parents=True, mode=0o755)
            os.chmod(staged, 0o755)
            os.chmod(staged / "Contents", 0o755)
            info = staged / "Contents" / "Info.plist"
            executable = executable_dir / LAUNCHER_EXECUTABLE
            resources = staged / "Contents" / "Resources"
            resources.mkdir(mode=0o755)
            icon = resources / LAUNCHER_ICON
            icon.write_bytes(_launcher_icon())
            os.chmod(icon, 0o644)
            info.write_bytes(_launcher_plist())
            executable.write_bytes(_launcher_script())
            os.chmod(info, 0o644)
            os.chmod(executable, 0o755)
            if not _launcher_current(staged):
                raise ControllerError("GPTPRO_LAUNCHER_INSTALL_FAILED", "The staged launcher failed its integrity check.")
            for durable_path in (info, executable, icon, resources, executable_dir, staged / "Contents", staged, temporary_root):
                _fsync(durable_path)

            replaced = destination.exists() or destination.is_symlink()
            cleanup_warning = None
            recovery_path = None
            if not replaced:
                try:
                    _renamex(staged, destination, RENAME_EXCL)
                except OSError as exc:
                    if exc.errno == errno.EEXIST:
                        raise ControllerError(
                            "GPTPRO_LAUNCHER_CONFLICT",
                            f"A different item appeared at {destination} during installation.",
                        ) from exc
                    raise
            else:
                trash = _trash_root(trash_dir)
                _require_same_volume(root, trash)
                original_identity = _launcher_identity(destination)
                _renamex(staged, destination, RENAME_SWAP)
                if _launcher_identity(staged) != original_identity or not _launcher_managed(staged) or not _launcher_current(destination):
                    _renamex(staged, destination, RENAME_SWAP)
                    raise ControllerError(
                        "GPTPRO_LAUNCHER_IDENTITY_CHANGED",
                        "The launcher changed during its atomic update.",
                        recovery="Inspect the launcher path and retry only after it is stable.",
                    )
                try:
                    os.replace(staged, _trash_destination(trash))
                except OSError:
                    recovery_path = root / f".gptpro-launcher-recovery-{uuid.uuid4().hex[:8]}.app"
                    os.replace(staged, recovery_path)
                    cleanup_warning = "The new launcher is installed, but the previous managed launcher could not be moved to Trash."

            if not _launcher_current(destination):
                raise ControllerError("GPTPRO_LAUNCHER_INSTALL_FAILED", "The installed launcher failed its integrity check.")
            _fsync(root)
            return {
                **launcher_status(applications_dir=root),
                "operation": "launcher-install",
                "changed": True,
                "replaced_managed_launcher": replaced,
                "cleanup_warning": cleanup_warning,
                "recovery_path": str(recovery_path) if recovery_path else None,
            }
        except ControllerError:
            raise
        except OSError as exc:
            raise ControllerError("GPTPRO_LAUNCHER_INSTALL_FAILED", "The user launcher could not be installed.") from exc
        finally:
            shutil.rmtree(temporary_root, ignore_errors=True)


def launcher_uninstall(
    *,
    applications_dir: Path | None = None,
    trash_dir: Path | None = None,
) -> dict[str, Any]:
    destination = _launcher_destination(applications_dir)
    root = destination.parent
    if not root.is_dir():
        return {"ok": True, "operation": "launcher-uninstall", "path": str(destination), "removed": False}
    with _launcher_lock(root):
        if not (destination.exists() or destination.is_symlink()):
            return {"ok": True, "operation": "launcher-uninstall", "path": str(destination), "removed": False}
        if not _launcher_managed(destination):
            raise ControllerError(
                "GPTPRO_LAUNCHER_CONFLICT",
                f"The item at {destination} is not a gptpro-managed launcher.",
                recovery="Inspect the item yourself. gptpro will not remove it.",
            )
        trash = _trash_root(trash_dir)
        _require_same_volume(root, trash)
        original_identity = _launcher_identity(destination)
        moved = _trash_destination(trash)
        try:
            _renamex(destination, moved, RENAME_EXCL)
        except OSError as exc:
            raise ControllerError("GPTPRO_LAUNCHER_UNINSTALL_FAILED", "The launcher could not be moved to Trash.") from exc
        if _launcher_identity(moved) != original_identity:
            raise ControllerError(
                "GPTPRO_LAUNCHER_IDENTITY_CHANGED",
                "The launcher changed while it was being moved to Trash.",
                recovery="Inspect both the launcher and Trash paths before retrying.",
            )
        return {
            "ok": True,
            "operation": "launcher-uninstall",
            "path": str(destination),
            "removed": True,
            "recoverable_from_trash": True,
            "trashed_path": str(moved),
        }


class ControllerError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        recovery: str = "Run desktop-doctor before deciding whether a new approved consultation is required.",
        submission_state: str = "not_started",
        stage: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.recovery = recovery
        self.submission_state = submission_state
        self.stage = stage


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def node_binary() -> Path:
    candidate = shutil.which("node")
    if not candidate:
        raise ControllerError("NODE_UNAVAILABLE", "Node.js 22 or newer is required.")
    result = subprocess.run(
        [candidate, "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=5,
    )
    try:
        major = int(result.stdout.strip().lstrip("v").split(".", 1)[0])
    except (ValueError, IndexError):
        major = 0
    if result.returncode != 0 or major < 22:
        raise ControllerError("NODE_VERSION_UNSUPPORTED", "Node.js 22 or newer is required.")
    return Path(candidate).resolve()


def node_entrypoint(skill_root: Path) -> Path:
    entrypoint = skill_root / "scripts" / "chatgpt-desktop.js"
    if not entrypoint.is_file():
        raise ControllerError("DESKTOP_RUNTIME_MISSING", "The bundled Desktop runtime is incomplete.")
    return entrypoint


def _safe_env() -> dict[str, str]:
    return {
        "PATH": os.defpath,
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", ""),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
    }


def _runtime_error_value(stderr: str) -> dict[str, Any]:
    try:
        value = json.loads(stderr.strip().splitlines()[-1]).get("error", {})
    except (ValueError, IndexError, AttributeError):
        return {}
    return value if isinstance(value, dict) else {}


def _node_json(skill_root: Path, arguments: list[str], *, timeout: int = 60) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [str(node_binary()), str(node_entrypoint(skill_root)), *arguments],
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            env=_safe_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ControllerError(
            "DESKTOP_RUNTIME_UNAVAILABLE",
            "The bundled Desktop runtime did not complete.",
            retryable=True,
        ) from exc
    if result.returncode != 0:
        error = _runtime_error_value(result.stderr)
        raise ControllerError(
            str(error.get("code", "DESKTOP_RUNTIME_ERROR")),
            str(error.get("message", "The Desktop runtime failed.")),
            retryable=error.get("retryable") is True,
            recovery=str(error.get("recovery", "Run desktop-doctor before retrying.")),
            submission_state=str(error.get("submission_state", "not_started")),
            stage=error.get("stage") if isinstance(error.get("stage"), str) else None,
        )
    try:
        value = json.loads(result.stdout)
    except (ValueError, RecursionError) as exc:
        raise ControllerError("DESKTOP_RUNTIME_PROTOCOL_ERROR", "The Desktop runtime returned invalid JSON.") from exc
    if not isinstance(value, dict):
        raise ControllerError("DESKTOP_RUNTIME_PROTOCOL_ERROR", "The Desktop runtime returned an unsupported result.")
    return value


def desktop_doctor(skill_root: Path, *, endpoint: str | None = None) -> dict[str, Any]:
    arguments = ["probe"]
    if endpoint:
        arguments += ["--endpoint", endpoint]
    result = _node_json(skill_root, arguments, timeout=20)
    if (
        result.get("desktop_bridge") is not True
        or result.get("stream_bridge") is not True
        or result.get("response_stream_supported") is not True
        or result.get("response_readback_supported") is not True
    ):
        raise ControllerError("BRIDGE_UNAVAILABLE", "The required ChatGPT Desktop request/stream bridge is unavailable.")
    if result.get("desktop_environment_readable") is not True:
        raise ControllerError("DESKTOP_CAPABILITY_UNAVAILABLE", "The ChatGPT Desktop environment capability is unavailable.")
    if result.get("device_check_supported") is not True:
        raise ControllerError("DEVICE_CHECK_UNAVAILABLE", "The ChatGPT Desktop DeviceCheck capability is unavailable.")
    if endpoint is None and result.get("isolated_runner") is not True:
        raise ControllerError(
            "GPTPRO_RUNNER_UNVERIFIED",
            "The default Desktop endpoint is not owned by the isolated gptpro Runner profile.",
            recovery="Run desktop-launch or open the installed gptpro Launcher. The ordinary ChatGPT app does not need to be restarted.",
        )
    return {"ok": True, "operation": "desktop-doctor", **result}


def desktop_models(skill_root: Path, *, endpoint: str | None = None) -> dict[str, Any]:
    arguments = ["models"]
    if endpoint:
        arguments += ["--endpoint", endpoint]
    return {"ok": True, "operation": "models", **_node_json(skill_root, arguments, timeout=45)}


def _app_processes() -> list[tuple[int, str]]:
    expected = "/Applications/ChatGPT.app/Contents/MacOS/ChatGPT"
    try:
        result = subprocess.run(
            ["/bin/ps", "-axo", "pid=,uid=,command="],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ControllerError(
            "CHATGPT_PROCESS_STATE_UNKNOWN",
            "The current ChatGPT process state could not be inspected safely.",
            retryable=True,
        ) from exc
    if result.returncode != 0:
        raise ControllerError(
            "CHATGPT_PROCESS_STATE_UNKNOWN",
            "The current ChatGPT process state could not be inspected safely.",
            retryable=True,
        )
    matches: list[tuple[int, str]] = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 2)
        if len(fields) != 3 or not fields[0].isdigit() or not fields[1].isdigit() or int(fields[1]) != os.getuid():
            continue
        if fields[2] == expected or fields[2].startswith(expected + " "):
            matches.append((int(fields[0]), fields[2]))
    return matches


def _app_pids() -> list[int]:
    return [pid for pid, _ in _app_processes()]


def _runner_pids() -> list[int]:
    profile_argument = f"--user-data-dir={_runner_profile()}"
    port_argument = f"--remote-debugging-port={RUNNER_PORT}"
    return [
        pid
        for pid, command in _app_processes()
        if profile_argument in command and port_argument in command
    ]


def _port_open(port: int = RUNNER_PORT) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def desktop_launch(skill_root: Path) -> dict[str, Any]:
    app = CHATGPT_APP
    if not app.is_dir():
        raise ControllerError("CHATGPT_APP_NOT_FOUND", "The ChatGPT app is not installed at /Applications/ChatGPT.app.")
    command = [
        "open",
        "-na",
        str(app),
        "--args",
        f"--user-data-dir={_runner_profile()}",
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={RUNNER_PORT}",
    ]
    runner_pids = _runner_pids()
    if runner_pids:
        if _port_open(RUNNER_PORT):
            return desktop_doctor(skill_root)
        raise ControllerError(
            "GPTPRO_RUNNER_RESTART_REQUIRED",
            "The isolated gptpro Runner process exists without its verified loopback endpoint.",
            recovery="Quit only the dedicated gptpro Runner window, then run desktop-launch again. The ordinary ChatGPT app does not need to be restarted.",
        )
    if _port_open(RUNNER_PORT):
        raise ControllerError(
            "CDP_LISTENER_UNVERIFIED",
            f"Port {RUNNER_PORT} is occupied while no matching isolated gptpro Runner process is running.",
            recovery="Stop or reconfigure the unrelated local listener, then run desktop-launch again.",
        )
    profile = _secure_runner_profile()
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=15)
    if result.returncode != 0:
        raise ControllerError("CHATGPT_LAUNCH_FAILED", "The isolated gptpro Runner instance could not be launched.")
    deadline = time.monotonic() + 30
    last_error: ControllerError | None = None
    while time.monotonic() < deadline:
        if _port_open(RUNNER_PORT):
            try:
                return desktop_doctor(skill_root)
            except ControllerError as exc:
                if exc.code not in {
                    "CDP_UNAVAILABLE",
                    "TARGET_NOT_FOUND",
                    "BRIDGE_UNAVAILABLE",
                    "DESKTOP_CAPABILITY_UNAVAILABLE",
                    "DEVICE_CHECK_UNAVAILABLE",
                }:
                    raise
                last_error = exc
        time.sleep(0.25)
    if last_error:
        raise last_error
    raise ControllerError(
        "CDP_UNAVAILABLE",
        "The isolated gptpro Runner launched but its loopback endpoint did not become ready.",
        retryable=True,
    )


def resolve_model(catalog: dict[str, Any], intent: str, effort: str | None) -> dict[str, Any]:
    models = catalog.get("models") if isinstance(catalog, dict) else None
    if not isinstance(models, list) or not models:
        raise ControllerError("MODEL_CATALOG_FAILED", "The logged-in model catalog is empty.")
    candidates = [item for item in models if item.get("id") == intent]
    if not candidates:
        raise ControllerError(
            "MODEL_NOT_FOUND",
            f"The exact Desktop model ID {intent!r} is not present in the logged-in catalog.",
            recovery="Do not silently select another model. Confirm the account catalog or prepare a newly approved package with an explicit model change.",
        )
    if len(candidates) != 1:
        raise ControllerError("MODEL_AMBIGUOUS", "The exact Desktop model ID appears more than once in the catalog.")
    model = candidates[0]
    efforts = model.get("thinking_efforts") if isinstance(model.get("thinking_efforts"), list) else []
    if effort and effort not in efforts:
        raise ControllerError("MODEL_EFFORT_UNSUPPORTED", "The requested reasoning effort is not supported by the exact Desktop model.")
    return {
        "id": model["id"],
        "name": model.get("name", model["id"]),
        "thinking_effort": effort,
        "catalog_source": "dynamic",
    }


def _wrap_response(package_id: str, text: str) -> str:
    begin = f"BEGIN_GPTPRO_RESPONSE:{package_id}"
    end = f"END_GPTPRO_RESPONSE:{package_id}"
    if begin in text or end in text:
        raise ControllerError(
            "RESPONSE_MARKER_COLLISION",
            "The raw assistant response contains a package marker, so deterministic import was stopped.",
            submission_state="completed",
            recovery="Inspect the saved raw response. Do not resend the consultation automatically.",
        )
    return f"{begin}\n{text.rstrip(chr(10))}\n{end}\n"


def _record_failure(
    handoff: Path,
    manifest: dict[str, Any],
    state: dict[str, Any],
    error: ControllerError,
    submitted: bool,
    last_stage: str,
) -> None:
    if not (submitted or error.submission_state in {"ambiguous", "rejected", "completed"}):
        return
    phase = "submission_rejected" if error.submission_state == "rejected" else "submission_ambiguous"
    state["phase"] = phase
    state["last_submission"] = {
        "status": phase,
        "error_code": error.code,
        "last_stage": last_stage,
        "recorded_at": utc_now(),
        "turn": 1,
    }
    save_state(handoff, state)
    append_receipt(
        handoff / "receipt.json",
        manifest["package_id"],
        phase,
        {
            "error_code": error.code,
            "automatic_retry_allowed": False,
            "channel": DELIVERY_CHANNEL,
            "chat_history_mode": CHAT_HISTORY_MODE,
            "outbound_sha256": manifest["hashes"]["outbound_sha256"],
            "last_stage": last_stage,
            "turn": 1,
        },
    )


def _record_response_capture_failure(
    handoff: Path,
    manifest: dict[str, Any],
    state: dict[str, Any],
    error: ControllerError,
    *,
    raw_path: Path,
) -> None:
    raw_hash = sha256_file(raw_path) if raw_path.is_file() else None
    append_receipt(
        handoff / "receipt.json",
        manifest["package_id"],
        "response_capture_failed",
        {
            "error_code": error.code,
            "raw_response_sha256": raw_hash,
            "channel": DELIVERY_CHANNEL,
            "chat_history_mode": CHAT_HISTORY_MODE,
            "automatic_retry_allowed": False,
            "tool_routes": 0,
        },
    )
    state["phase"] = "response_capture_failed"
    state["last_submission"] = {
        "status": "completed_unimported",
        "error_code": error.code,
        "recorded_at": utc_now(),
    }
    save_state(handoff, state)


def _runtime_error(stderr: str, *, submitted: bool, last_stage: str) -> ControllerError:
    error = _runtime_error_value(stderr)
    child_submission_state = str(error.get("submission_state", "ambiguous" if submitted else "not_started"))
    if submitted and child_submission_state not in {"rejected", "completed"}:
        return ControllerError(
            str(error.get("code", "DESKTOP_RUNTIME_ERROR")),
            str(error.get("message", "The Desktop runtime failed.")),
            retryable=False,
            recovery="Run collect-response. It performs GET readback only and never resends the prompt.",
            submission_state="ambiguous",
            stage=error.get("stage") if isinstance(error.get("stage"), str) else last_stage,
        )
    recovery = str(error.get("recovery", "Run desktop-doctor and inspect the package state."))
    if submitted and child_submission_state == "rejected":
        recovery = "Do not resend this package. Inspect the rejection before preparing and approving a fresh package."
    elif submitted and child_submission_state == "completed":
        recovery = "Inspect the saved response evidence. Do not resend this package."
    return ControllerError(
        str(error.get("code", "DESKTOP_RUNTIME_ERROR")),
        str(error.get("message", "The Desktop runtime failed.")),
        retryable=error.get("retryable") is True and not submitted,
        recovery=recovery,
        submission_state=child_submission_state,
        stage=error.get("stage") if isinstance(error.get("stage"), str) else last_stage,
    )


def _message_id(package_id: str, outbound_sha256: str) -> str:
    material = f"gptpro-message-v1\0{package_id}\0{outbound_sha256}\0turn-1".encode("utf-8")
    return str(uuid.UUID(bytes=bytes.fromhex(sha256_bytes(material))[:16], version=5))


def _has_unfinished_dispatch(handoff: Path, package_id: str) -> bool:
    receipt = load_receipt(handoff / "receipt.json", package_id=package_id)
    started = any(
        event.get("turn") == 1 and event.get("event") in {"submission_dispatching", "submission_dispatched"}
        for event in receipt["events"]
    )
    terminal = any(
        event.get("turn") == 1
        and event.get("event") in {"submission_ambiguous", "submission_rejected", "response_capture_failed", "response_imported"}
        for event in receipt["events"]
    )
    return started and not terminal


def _finalize_response(
    handoff: Path,
    manifest: dict[str, Any],
    state: dict[str, Any],
    complete: dict[str, Any],
    *,
    model: dict[str, Any],
    effort: str | None,
    operation: str,
) -> dict[str, Any]:
    response_dir = secure_directory(handoff / "responses")
    raw_path = response_dir / "response.raw.md"
    wrapped_path = response_dir / "response.md"
    completion_source = complete.get("completion_source")
    accepted_sources = {
        "consult": ("signed-stream-handoff-v1",),
        "collect-response": ("conversation-readback-v1",),
    }
    if not isinstance(completion_source, str) or completion_source not in accepted_sources.get(operation, ()):
        raise ControllerError(
            "RESPONSE_COMPLETION_UNPROVEN",
            "The Desktop runtime did not prove completion through the expected response path.",
            submission_state="ambiguous",
            stage="complete",
        )
    topic_hash = complete.get("stream_handoff_topic_sha256")
    if (
        (completion_source == "signed-stream-handoff-v1" and (
            not isinstance(topic_hash, str)
            or len(topic_hash) != 64
            or any(character not in "0123456789abcdef" for character in topic_hash)
        ))
        or (completion_source != "signed-stream-handoff-v1" and topic_hash is not None)
    ):
        raise ControllerError(
            "RESPONSE_COMPLETION_UNPROVEN",
            "The Desktop runtime returned invalid signed stream-handoff evidence.",
            submission_state="ambiguous",
            stage="complete",
        )
    branch_proof = complete.get("current_branch_proof")
    branch_proof_required = complete.get("current_branch_proof_required")
    tool_candidate = complete.get("tool_route_candidate_observed")
    pre_handoff_assistant = complete.get("pre_handoff_assistant_observed")
    signed_delta_continuation = complete.get("signed_delta_continuation_observed")
    signed_assistant_evidence = complete.get("signed_assistant_evidence")
    invalid_branch_proof = branch_proof not in (None, "authenticated-exact-message-readback-v1")
    if operation == "consult":
        invalid_branch_proof = (
            invalid_branch_proof
            or not isinstance(branch_proof_required, bool)
            or not isinstance(tool_candidate, bool)
            or not isinstance(pre_handoff_assistant, bool)
            or not isinstance(signed_delta_continuation, bool)
        )
        invalid_branch_proof = invalid_branch_proof or branch_proof_required != (
            tool_candidate or pre_handoff_assistant or signed_delta_continuation
        )
        invalid_branch_proof = invalid_branch_proof or (
            branch_proof_required
            and branch_proof != "authenticated-exact-message-readback-v1"
        )
        invalid_branch_proof = invalid_branch_proof or (not branch_proof_required and branch_proof is not None)
        invalid_branch_proof = invalid_branch_proof or (tool_candidate and not branch_proof_required)
        invalid_branch_proof = invalid_branch_proof or signed_assistant_evidence is not True
    else:
        invalid_branch_proof = (
            invalid_branch_proof
            or (tool_candidate is not None and tool_candidate is not False)
            or (pre_handoff_assistant is not None and pre_handoff_assistant is not False)
            or (signed_delta_continuation is not None and signed_delta_continuation is not False)
            or (branch_proof_required is not None and branch_proof_required is not False)
            or branch_proof is not None
            or signed_assistant_evidence is not None
        )
    if invalid_branch_proof:
        raise ControllerError(
            "RESPONSE_COMPLETION_UNPROVEN",
            "The Desktop runtime returned invalid current-branch proof evidence.",
            submission_state="ambiguous",
            stage="complete",
        )
    if type(complete.get("tool_routes")) is not int or complete["tool_routes"] != 0:
        raise ControllerError(
            "UNEXPECTED_TOOL_ROUTE",
            "The Desktop runtime did not prove a zero-tool inline response.",
            submission_state="ambiguous",
            stage="complete",
        )
    conversation_id = complete.get("conversation_id")
    assistant_message_id = complete.get("assistant_message_id")
    parent_message_id = complete.get("parent_message_id")
    if (
        complete.get("done") is not True
        or not isinstance(conversation_id, str)
        or not conversation_id
        or not isinstance(assistant_message_id, str)
        or not assistant_message_id
        or parent_message_id != assistant_message_id
    ):
        raise ControllerError(
            "RESPONSE_COMPLETION_UNPROVEN",
            "The Desktop runtime returned incomplete assistant identity evidence.",
            submission_state="ambiguous",
            stage="complete",
        )
    text = complete.get("text")
    if not isinstance(text, str) or not text.strip():
        error = ControllerError(
            "RESPONSE_EMPTY",
            "The completed assistant turn contained no response text.",
            submission_state="completed",
            stage="complete",
        )
        _record_response_capture_failure(handoff, manifest, state, error, raw_path=raw_path)
        raise error
    atomic_write(raw_path, text.encode("utf-8"))
    try:
        atomic_write(wrapped_path, _wrap_response(manifest["package_id"], text).encode("utf-8"))
    except ControllerError as error:
        _record_response_capture_failure(handoff, manifest, state, error, raw_path=raw_path)
        raise

    receipt_fields = {
        "channel": DELIVERY_CHANNEL,
        "chat_history_mode": CHAT_HISTORY_MODE,
        "backend_model_id": model["id"],
        "thinking_effort": effort,
        "raw_response_sha256": sha256_file(raw_path),
        "wrapped_response_sha256": sha256_file(wrapped_path),
        "runtime_wrapped": True,
        "completion_source": completion_source,
        "stream_handoff_topic_sha256": topic_hash,
        "current_branch_proof": branch_proof,
        "current_branch_proof_required": bool(branch_proof_required),
        "tool_route_candidate_observed": bool(tool_candidate),
        "pre_handoff_assistant_observed": bool(pre_handoff_assistant),
        "signed_delta_continuation_observed": bool(signed_delta_continuation),
        "signed_assistant_evidence": signed_assistant_evidence,
        "conversation_id_sha256": sha256_bytes(conversation_id.encode("utf-8")) if isinstance(conversation_id, str) and conversation_id else None,
        "parent_message_id_sha256": sha256_bytes(parent_message_id.encode("utf-8")) if isinstance(parent_message_id, str) and parent_message_id else None,
        "outbound_sha256": manifest["hashes"]["outbound_sha256"],
        "turn": 1,
        "response_file": wrapped_path.name,
        "tool_routes": 0,
    }
    append_receipt(handoff / "receipt.json", manifest["package_id"], "response_captured", receipt_fields)
    append_receipt(
        handoff / "receipt.json",
        manifest["package_id"],
        "response_imported",
        {"wrapped_response_sha256": receipt_fields["wrapped_response_sha256"], "turn": 1},
    )
    state["phase"] = "imported"
    state["response_count"] = 1
    state["last_submission"] = {"status": "completed", "turn": 1, "recorded_at": utc_now()}
    save_state(handoff, state)
    return {
        "ok": True,
        "operation": operation,
        "package_id": manifest["package_id"],
        "phase": "imported",
        "model": model,
        "response_file": str(wrapped_path),
        "raw_response_file": str(raw_path),
        "receipt": str(handoff / "receipt.json"),
        "outbound_sha256": manifest["hashes"]["outbound_sha256"],
        "completion_source": completion_source,
        "current_branch_proof": branch_proof,
        "current_branch_proof_required": bool(branch_proof_required),
        "tool_route_candidate_observed": bool(tool_candidate),
        "pre_handoff_assistant_observed": bool(pre_handoff_assistant),
        "signed_delta_continuation_observed": bool(signed_delta_continuation),
        "signed_assistant_evidence": signed_assistant_evidence,
        "tool_routes": 0,
        "advisory_only": True,
        "desktop_session": {
            "chatgpt_mode": "isolated_runner_may_still_be_active",
            "automatic_shutdown": False,
            "next_action": "The ordinary ChatGPT app is unaffected. Quit only the dedicated gptpro Runner window when no more consultations are needed.",
        },
    }


def _run_consultation_locked(skill_root: Path, handoff: Path, *, timeout_seconds: int) -> dict[str, Any]:
    active = verify_active_approval(handoff)
    verified = active["verified"]
    manifest = verified["manifest"]
    state = active["state"]
    if (
        state.get("phase") in {"dispatching", "submission_ambiguous", "submission_rejected", "response_capture_failed"}
        or _has_unfinished_dispatch(handoff, manifest["package_id"])
    ):
        raise ControllerError(
            "SUBMISSION_STATE_UNSAFE",
            "This package has an unresolved prior submission and cannot be resent.",
            recovery="Inspect the normal Chat conversation or prepare and approve a fresh package. Do not resend this package.",
        )
    if (
        state.get("phase") != "approved"
        or state.get("response_count") != 0
        or state.get("last_submission") is not None
    ):
        raise ControllerError(
            "PACKAGE_ALREADY_SUBMITTED",
            "This package has already entered a submission lifecycle and cannot be resent.",
            recovery="Inspect the normal Chat conversation or prepare and approve a fresh package. Do not resend this package.",
        )

    catalog = desktop_models(skill_root)
    effort = manifest["model_intent"].get("thinking_effort")
    model = resolve_model(catalog, manifest["model_intent"]["requested"], effort)
    if state.get("resolved_model") is not None and state.get("resolved_model") != model:
        raise ControllerError("MODEL_BINDING_CHANGED", "The exact package was previously bound to another Desktop model.")
    state["resolved_model"] = model
    save_state(handoff, state)

    outbound = handoff / "outbound.md"
    system_prompt = handoff / "system-prompt.md"
    if (
        not outbound.is_file()
        or not system_prompt.is_file()
        or sha256_file(outbound) != manifest["hashes"]["outbound_sha256"]
        or outbound.stat().st_size != manifest["disclosure"]["outbound_bytes"]
    ):
        raise ControllerError("PACKAGE_TAMPERED", "The approved outbound artifact changed after approval.")

    message_id = _message_id(manifest["package_id"], manifest["hashes"]["outbound_sha256"])
    command = [
        str(node_binary()),
        str(node_entrypoint(skill_root)),
        "ask",
        "--prompt-file",
        str(outbound),
        "--system-prompt-file",
        str(system_prompt),
        "--model",
        model["id"],
        "--history-mode",
        CHAT_HISTORY_MODE,
        "--timeout-seconds",
        str(timeout_seconds),
        "--message-id",
        message_id,
        "--events-jsonl",
    ]
    if effort:
        command += ["--thinking-effort", effort]

    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
        env=_safe_env(),
    )
    if process.stdin is None or process.stdout is None or process.stderr is None:
        process.kill()
        raise ControllerError("DESKTOP_RUNTIME_UNAVAILABLE", "The Desktop controller pipes are unavailable.")

    stderr_parts: list[str] = []
    stderr_thread = threading.Thread(target=lambda: stderr_parts.append(process.stderr.read()), daemon=True)
    stderr_thread.start()
    dispatch_authorized = False
    submitted = False
    complete: dict[str, Any] | None = None
    last_stage = "preflight"
    deadline_reached = threading.Event()

    def stop_child_at_deadline() -> None:
        deadline_reached.set()
        try:
            if process.poll() is None:
                process.kill()
        except OSError:
            pass

    watchdog = threading.Timer(
        max(0.001, float(timeout_seconds) + PARENT_TIMEOUT_GRACE_SECONDS),
        stop_child_at_deadline,
    )
    watchdog.daemon = True
    watchdog.start()
    try:
        for line in process.stdout:
            try:
                event = json.loads(line)
            except ValueError as exc:
                raise ControllerError(
                    "DESKTOP_RUNTIME_PROTOCOL_ERROR",
                    "The Desktop runtime emitted invalid JSONL.",
                    submission_state="ambiguous" if dispatch_authorized else "not_started",
                    stage=last_stage,
                ) from exc
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                raise ControllerError(
                    "DESKTOP_RUNTIME_PROTOCOL_ERROR",
                    "The Desktop runtime emitted an unsupported JSONL event.",
                    submission_state="ambiguous" if dispatch_authorized else "not_started",
                    stage=last_stage,
                )

            if event["type"] == "progress":
                stage = event.get("stage")
                if not isinstance(stage, str) or stage not in PROGRESS_STAGES:
                    raise ControllerError(
                        "DESKTOP_RUNTIME_PROTOCOL_ERROR",
                        "The Desktop runtime emitted an invalid progress stage.",
                        submission_state="ambiguous" if dispatch_authorized else "not_started",
                        stage=last_stage,
                    )
                last_stage = stage
                continue
            if event["type"] == "dispatch_ready":
                last_stage = "dispatch_ready"
                expected_prompt_sha256 = sha256_file(outbound)
                expected_prompt_bytes = outbound.stat().st_size
                if (
                    dispatch_authorized
                    or submitted
                    or event.get("prompt_sha256") != expected_prompt_sha256
                    or event.get("prompt_bytes") != expected_prompt_bytes
                    or event.get("system_prompt_sha256") != manifest["hashes"]["system_prompt_sha256"]
                    or event.get("state_sha256") is not None
                    or event.get("backend_model_id") != model["id"]
                    or event.get("thinking_effort") != effort
                    or event.get("history_mode") != CHAT_HISTORY_MODE
                    or event.get("message_id") != message_id
                    or not isinstance(event.get("dispatch_token"), str)
                    or not event["dispatch_token"]
                ):
                    raise ControllerError(
                        "DISPATCH_ARTIFACT_MISMATCH",
                        "The Desktop runtime bytes or delivery binding differ from the approved package.",
                        stage=last_stage,
                    )
                state = verify_active_approval(handoff)["state"]
                if state.get("phase") != "approved":
                    raise ControllerError(
                        "SUBMISSION_STATE_UNSAFE",
                        "The package state changed before dispatch authorization.",
                        stage=last_stage,
                    )
                state["phase"] = "dispatching"
                state["last_submission"] = {
                    "status": "dispatching",
                    "recorded_at": utc_now(),
                    "turn": 1,
                    "message_id_sha256": sha256_bytes(message_id.encode("utf-8")),
                }
                try:
                    save_state(handoff, state)
                    append_receipt(
                        handoff / "receipt.json",
                        manifest["package_id"],
                        "submission_dispatching",
                        {
                            "channel": DELIVERY_CHANNEL,
                            "chat_history_mode": CHAT_HISTORY_MODE,
                            "backend_model_id": model["id"],
                            "thinking_effort": effort,
                            "prompt_sha256": expected_prompt_sha256,
                            "prompt_bytes": expected_prompt_bytes,
                            "system_prompt_sha256": manifest["hashes"]["system_prompt_sha256"],
                            "message_id_sha256": sha256_bytes(message_id.encode("utf-8")),
                            "turn": 1,
                        },
                    )
                except (ApprovalError, ReceiptError, StateError) as exc:
                    raise ControllerError(
                        "DISPATCH_EVIDENCE_WRITE_FAILED",
                        "The no-resend boundary could not be recorded, so the Desktop POST was not authorized.",
                        recovery="Run diagnostic-status. Do not reuse this package if its phase is dispatching.",
                        stage=last_stage,
                    ) from exc
                dispatch_authorized = True
                last_stage = "dispatch_authorized"
                try:
                    process.stdin.write(json.dumps({"type": "dispatch_authorized", "dispatch_token": event["dispatch_token"]}) + "\n")
                    process.stdin.flush()
                except (BrokenPipeError, OSError) as exc:
                    raise ControllerError(
                        "SUBMISSION_AMBIGUOUS",
                        "The child dispatch acknowledgement failed after the durable dispatch boundary was recorded.",
                        submission_state="ambiguous",
                        stage=last_stage,
                    ) from exc
                finally:
                    try:
                        process.stdin.close()
                    except OSError:
                        pass
                continue
            if event["type"] == "submitted":
                last_stage = "submitted"
                request_id = event.get("request_id")
                if not dispatch_authorized or submitted or not isinstance(request_id, str) or not request_id:
                    raise ControllerError(
                        "DESKTOP_RUNTIME_PROTOCOL_ERROR",
                        "The Desktop runtime returned invalid dispatch evidence.",
                        submission_state="ambiguous",
                        stage=last_stage,
                    )
                submitted = True
                request_hash = sha256_bytes(request_id.encode("utf-8"))
                append_receipt(
                    handoff / "receipt.json",
                    manifest["package_id"],
                    "submission_dispatched",
                    {
                        "channel": DELIVERY_CHANNEL,
                        "chat_history_mode": CHAT_HISTORY_MODE,
                        "backend_model_id": model["id"],
                        "thinking_effort": effort,
                        "request_id_sha256": request_hash,
                        "outbound_sha256": manifest["hashes"]["outbound_sha256"],
                        "outbound_bytes": outbound.stat().st_size,
                        "turn": 1,
                    },
                )
                state["phase"] = "submitted"
                state["last_submission"] = {
                    "status": "dispatched",
                    "request_id_sha256": request_hash,
                    "recorded_at": utc_now(),
                    "turn": 1,
                }
                save_state(handoff, state)
                continue
            if event["type"] == "complete":
                last_stage = "complete"
                if not submitted or complete is not None:
                    raise ControllerError(
                        "DESKTOP_RUNTIME_PROTOCOL_ERROR",
                        "The Desktop runtime returned invalid completion evidence.",
                        submission_state="ambiguous",
                        stage=last_stage,
                    )
                complete = event
                continue
            raise ControllerError(
                "DESKTOP_RUNTIME_PROTOCOL_ERROR",
                "The Desktop runtime emitted an unexpected event type.",
                submission_state="ambiguous" if dispatch_authorized else "not_started",
                stage=last_stage,
            )

        return_code = process.wait(timeout=10)
        stderr_thread.join()
        error_text = "".join(stderr_parts)
        if deadline_reached.is_set():
            raise ControllerError(
                "TIMEOUT",
                f"The Desktop consultation exceeded its single overall deadline at stage {last_stage}.",
                retryable=not dispatch_authorized,
                recovery=(
                    "Inspect the normal Chat conversation. Do not resend this package automatically."
                    if dispatch_authorized
                    else "Run desktop-doctor, then retry only while the exact approval remains valid."
                ),
                submission_state="ambiguous" if dispatch_authorized else "not_started",
                stage=last_stage,
            )
        if return_code != 0 or complete is None:
            raise _runtime_error(error_text, submitted=dispatch_authorized, last_stage=last_stage)
    except KeyboardInterrupt:
        error = ControllerError(
            "CANCELLED",
            "The Desktop consultation was cancelled by the operator.",
            retryable=not dispatch_authorized,
            recovery=(
                "Inspect the normal Chat conversation. Do not resend this package automatically."
                if dispatch_authorized
                else "Retry only while the exact approval remains valid."
            ),
            submission_state="ambiguous" if dispatch_authorized else "not_started",
            stage=last_stage,
        )
        _record_failure(handoff, manifest, state, error, dispatch_authorized, last_stage)
        raise error
    except ControllerError as error:
        _record_failure(handoff, manifest, state, error, dispatch_authorized, error.stage or last_stage)
        raise
    except (OSError, subprocess.SubprocessError) as exc:
        error = ControllerError(
            "SUBMISSION_AMBIGUOUS" if dispatch_authorized else "DESKTOP_RUNTIME_UNAVAILABLE",
            "The Desktop runtime process ended unexpectedly.",
            submission_state="ambiguous" if dispatch_authorized else "not_started",
            stage=last_stage,
        )
        _record_failure(handoff, manifest, state, error, dispatch_authorized, last_stage)
        raise error from exc
    finally:
        watchdog.cancel()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        stderr_thread.join(timeout=1)

    assert complete is not None
    try:
        return _finalize_response(
            handoff,
            manifest,
            state,
            complete,
            model=model,
            effort=effort,
            operation="consult",
        )
    except ControllerError as error:
        if error.submission_state == "ambiguous":
            _record_failure(handoff, manifest, state, error, True, error.stage or "complete")
        raise


def run_consultation(
    skill_root: Path,
    handoff_value: Path,
    *,
    timeout_seconds: int = DEFAULT_CONSULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    handoff = Path(handoff_value).expanduser().resolve()
    verify_package(handoff)
    with package_lock(handoff):
        return _run_consultation_locked(skill_root, handoff, timeout_seconds=timeout_seconds)


def _run_collection_locked(skill_root: Path, handoff: Path, *, timeout_seconds: int) -> dict[str, Any]:
    verified = verify_package(handoff)
    manifest = verified["manifest"]
    state = load_state(handoff, manifest["package_id"])
    if state.get("phase") in {"imported", "evaluated"} or state.get("response_count") != 0:
        raise ControllerError(
            "RESPONSE_ALREADY_IMPORTED",
            "This package already has an imported response.",
            recovery="Use status and the saved response file; do not collect or resend it again.",
        )
    if state.get("phase") not in {"dispatching", "submitted", "submission_ambiguous", "response_capture_failed"}:
        raise ControllerError(
            "RESPONSE_COLLECTION_NOT_AVAILABLE",
            "Response collection requires a package with a durable submitted request.",
            recovery="Do not use collect-response before submission evidence exists.",
        )

    receipt = load_receipt(handoff / "receipt.json", package_id=manifest["package_id"])
    dispatching = [event for event in receipt["events"] if event.get("event") == "submission_dispatching" and event.get("turn") == 1]
    dispatched = [event for event in receipt["events"] if event.get("event") == "submission_dispatched" and event.get("turn") == 1]
    if len(dispatching) != 1 or len(dispatched) > 1:
        raise ControllerError(
            "RESPONSE_COLLECTION_EVIDENCE_INVALID",
            "The package does not contain exactly one durable Desktop dispatch boundary.",
            recovery="Do not resend this package; inspect its receipt independently.",
            submission_state="ambiguous",
        )
    message_id = _message_id(manifest["package_id"], manifest["hashes"]["outbound_sha256"])
    if dispatching[0].get("message_id_sha256") != sha256_bytes(message_id.encode("utf-8")):
        raise ControllerError(
            "RESPONSE_COLLECTION_EVIDENCE_INVALID",
            "The deterministic Desktop message ID does not match the dispatch receipt.",
            recovery="Do not resend or collect this package; inspect its receipt independently.",
            submission_state="ambiguous",
        )
    model = state.get("resolved_model")
    if (
        not isinstance(model, dict)
        or model.get("id") != dispatching[0].get("backend_model_id")
        or (dispatched and dispatched[0].get("backend_model_id") != dispatching[0].get("backend_model_id"))
    ):
        raise ControllerError(
            "RESPONSE_COLLECTION_EVIDENCE_INVALID",
            "The resolved Desktop model does not match the dispatch receipt.",
            recovery="Do not resend this package; inspect its state and receipt independently.",
            submission_state="ambiguous",
        )
    outbound = handoff / "outbound.md"
    if (
        not outbound.is_file()
        or sha256_file(outbound) != manifest["hashes"]["outbound_sha256"]
        or outbound.stat().st_size != manifest["disclosure"]["outbound_bytes"]
    ):
        raise ControllerError("PACKAGE_TAMPERED", "The approved outbound artifact changed after dispatch.", submission_state="ambiguous")

    command = [
        str(node_binary()),
        str(node_entrypoint(skill_root)),
        "collect",
        "--prompt-file",
        str(outbound),
        "--timeout-seconds",
        str(timeout_seconds),
        "--message-id",
        message_id,
        "--not-before",
        str(dispatching[0]["recorded_at"]),
        "--events-jsonl",
    ]
    try:
        result = subprocess.run(
            command,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(1, timeout_seconds) + PARENT_TIMEOUT_GRACE_SECONDS,
            check=False,
            env=_safe_env(),
        )
    except subprocess.TimeoutExpired as exc:
        raise ControllerError(
            "RESPONSE_COLLECTION_TIMEOUT",
            "Authenticated response readback did not complete before its deadline.",
            retryable=True,
            recovery="Retry collect-response. It performs GET readback only and never resends the prompt.",
            submission_state="ambiguous",
            stage="response_readback",
        ) from exc
    except OSError as exc:
        raise ControllerError(
            "DESKTOP_RUNTIME_UNAVAILABLE",
            "The Desktop response collector could not be started.",
            retryable=True,
            recovery="Run desktop-doctor, then retry collect-response without resending the prompt.",
            submission_state="ambiguous",
            stage="response_readback",
        ) from exc

    complete: dict[str, Any] | None = None
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError as exc:
            raise ControllerError(
                "DESKTOP_RUNTIME_PROTOCOL_ERROR",
                "The Desktop response collector emitted invalid JSONL.",
                submission_state="ambiguous",
                stage="response_readback",
            ) from exc
        if (
            not isinstance(event, dict)
            or not isinstance(event.get("type"), str)
            or event["type"] not in {"progress", "complete"}
        ):
            raise ControllerError(
                "DESKTOP_RUNTIME_PROTOCOL_ERROR",
                "The Desktop response collector emitted an unexpected event.",
                submission_state="ambiguous",
                stage="response_readback",
            )
        if event["type"] == "progress":
            if not isinstance(event.get("stage"), str) or event["stage"] not in {"response_readback", "complete"}:
                raise ControllerError(
                    "DESKTOP_RUNTIME_PROTOCOL_ERROR",
                    "The Desktop response collector emitted an invalid progress stage.",
                    submission_state="ambiguous",
                    stage="response_readback",
                )
            continue
        if complete is not None:
            raise ControllerError(
                "DESKTOP_RUNTIME_PROTOCOL_ERROR",
                "The Desktop response collector emitted more than one completion.",
                submission_state="ambiguous",
                stage="complete",
            )
        complete = event
    if result.returncode != 0 or complete is None:
        raise _runtime_error(result.stderr, submitted=True, last_stage="response_readback")
    return _finalize_response(
        handoff,
        manifest,
        state,
        complete,
        model=model,
        effort=manifest["model_intent"].get("thinking_effort"),
        operation="collect-response",
    )


def collect_response(
    skill_root: Path,
    handoff_value: Path,
    *,
    timeout_seconds: int = 10 * 60,
) -> dict[str, Any]:
    handoff = Path(handoff_value).expanduser().resolve()
    verify_package(handoff)
    with package_lock(handoff):
        return _run_collection_locked(skill_root, handoff, timeout_seconds=timeout_seconds)


def record_evaluation(handoff_value: Path, *, verdict: str, summary: str) -> dict[str, Any]:
    if verdict not in {"accepted", "partially-accepted", "rejected"}:
        raise ControllerError("EVALUATION_INVALID", "The evaluation verdict is invalid.")
    if not isinstance(summary, str) or not summary.strip() or len(summary.encode("utf-8")) > 64 * 1024:
        raise ControllerError("EVALUATION_INVALID", "The independent evaluation summary is empty or too large.")
    initial = verify_package(handoff_value)
    handoff = Path(initial["handoff_dir"])
    with package_lock(handoff):
        verified = verify_package(handoff)
        manifest = verified["manifest"]
        state = load_state(handoff, manifest["package_id"])
        if state.get("phase") not in {"imported", "evaluated"}:
            raise ControllerError("PACKAGE_PHASE_INVALID", "A completed imported response is required before evaluation.")
        evaluation = {
            "schema": "gptpro-independent-evaluation-v1",
            "package_id": manifest["package_id"],
            "verdict": verdict,
            "summary": summary,
            "recorded_at": utc_now(),
            "advice_was_independently_verified": True,
        }
        path = handoff / "evaluation.json"
        write_json(path, evaluation)
        append_receipt(
            handoff / "receipt.json",
            manifest["package_id"],
            "evaluated",
            {"verdict": verdict, "evaluation_sha256": sha256_file(path)},
        )
        state["phase"] = "evaluated"
        save_state(handoff, state)
    return {
        "ok": True,
        "operation": "record-evaluation",
        "package_id": manifest["package_id"],
        "phase": "evaluated",
        "verdict": verdict,
        "evaluation_file": str(path),
    }
