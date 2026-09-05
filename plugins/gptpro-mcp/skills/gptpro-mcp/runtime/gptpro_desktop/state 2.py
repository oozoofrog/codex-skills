"""Owner-only, machine-global state for the public Desktop-UI workflow."""

from __future__ import annotations

import json
import os
import pwd
import secrets
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass
class DesktopStateError(Exception):
    """Stable and sanitized Desktop workflow failure."""

    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def platform_state_root(
    *,
    platform_name: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Resolve the private state root without creating it."""

    current_platform = platform_name or sys.platform
    values = os.environ if environ is None else environ
    if home is None:
        try:
            home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        except (KeyError, ImportError, TypeError) as exc:
            raise DesktopStateError(
                "DESKTOP_STATE_HOME_UNAVAILABLE",
                "The canonical account home is unavailable.",
            ) from exc
    home = Path(home)
    if not home.is_absolute() or home == Path(home.anchor):
        raise DesktopStateError(
            "DESKTOP_STATE_HOME_UNSAFE", "The canonical account home is invalid."
        )
    if current_platform == "darwin":
        return home / "Library" / "Application Support" / "gptpro" / "desktop" / "v2"
    xdg = values.get("XDG_STATE_HOME", "").strip()
    if xdg:
        xdg_path = Path(xdg)
        if not xdg_path.is_absolute():
            raise DesktopStateError(
                "DESKTOP_STATE_ROOT_UNSAFE", "XDG_STATE_HOME must be absolute."
            )
        return xdg_path / "gptpro" / "desktop" / "v2"
    return home / ".local" / "state" / "gptpro" / "desktop" / "v2"


def _validate_absolute(path: Path) -> Path:
    requested = Path(path).expanduser()
    if (
        not requested.is_absolute()
        or len(requested.parts) <= 1
        or any(part in {"", ".", ".."} for part in requested.parts[1:])
    ):
        raise DesktopStateError(
            "DESKTOP_STATE_PATH_UNSAFE", "Private Desktop-state paths must be absolute."
        )
    return requested


def _open_directory_chain(path: Path, *, create: bool, final_mode: int = 0o700) -> int:
    requested = _validate_absolute(path)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise DesktopStateError(
            "DESKTOP_STATE_UNSUPPORTED", "O_NOFOLLOW is required for private state."
        )
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(requested.anchor, flags | nofollow)
    except OSError as exc:
        raise DesktopStateError(
            "DESKTOP_STATE_PATH_UNSAFE", "Unable to open the filesystem root safely."
        ) from exc
    try:
        for index, component in enumerate(requested.parts[1:], start=1):
            final = index == len(requested.parts) - 1
            try:
                child = os.open(component, flags | nofollow, dir_fd=descriptor)
            except FileNotFoundError:
                if not create:
                    raise DesktopStateError(
                        "DESKTOP_STATE_NOT_FOUND", "The private Desktop-state directory is absent."
                    )
                try:
                    os.mkdir(component, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
                except OSError as exc:
                    raise DesktopStateError(
                        "DESKTOP_STATE_CREATE_FAILED",
                        "Unable to create a private Desktop-state directory.",
                    ) from exc
                try:
                    child = os.open(component, flags | nofollow, dir_fd=descriptor)
                except OSError as exc:
                    raise DesktopStateError(
                        "DESKTOP_STATE_PATH_UNSAFE",
                        "A Desktop-state path contains a link or non-directory component.",
                    ) from exc
                os.fchmod(child, 0o700)
                os.fsync(descriptor)
            except DesktopStateError:
                raise
            except OSError as exc:
                raise DesktopStateError(
                    "DESKTOP_STATE_PATH_UNSAFE",
                    "A Desktop-state path contains a link or non-directory component.",
                ) from exc
            metadata = os.fstat(child)
            if not stat.S_ISDIR(metadata.st_mode):
                os.close(child)
                raise DesktopStateError(
                    "DESKTOP_STATE_PATH_UNSAFE", "A Desktop-state component is not a directory."
                )
            os.close(descriptor)
            descriptor = child
            if final and (
                metadata.st_uid != os.getuid()
                or stat.S_IMODE(os.fstat(descriptor).st_mode) != final_mode
            ):
                raise DesktopStateError(
                    "DESKTOP_STATE_PERMISSIONS_UNSAFE",
                    f"The private Desktop-state directory must be owner-only mode {final_mode:04o}.",
                )
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def secure_directory(path: Path, *, create: bool = True) -> Path:
    descriptor = _open_directory_chain(path, create=create)
    os.close(descriptor)
    return Path(path)


def _validate_private_file(descriptor: int) -> None:
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise DesktopStateError(
            "DESKTOP_STATE_FILE_UNSAFE",
            "Private Desktop-state files must be owner-only regular files with one link.",
        )


def _existing_destination_is_safe(directory: int, name: str) -> None:
    try:
        metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise DesktopStateError(
            "DESKTOP_STATE_FILE_UNSAFE", "Unable to inspect an existing Desktop-state file."
        ) from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise DesktopStateError(
            "DESKTOP_STATE_FILE_UNSAFE", "Refusing to replace an unsafe Desktop-state file."
        )


def atomic_write_private(path: Path, data: bytes) -> None:
    target = _validate_absolute(Path(path))
    directory = _open_directory_chain(target.parent, create=True)
    temp_name = f".{target.name}.tmp-{secrets.token_hex(8)}"
    descriptor = -1
    try:
        _existing_destination_is_safe(directory, target.name)
        descriptor = os.open(
            temp_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW")
            | getattr(os, "O_CLOEXEC", 0),
            0o600,
            dir_fd=directory,
        )
        os.fchmod(descriptor, 0o600)
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temp_name, target.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    except DesktopStateError:
        raise
    except OSError as exc:
        raise DesktopStateError(
            "DESKTOP_STATE_WRITE_FAILED", "Unable to write private Desktop state atomically."
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temp_name, dir_fd=directory)
        except OSError:
            pass
        os.close(directory)


def write_private_json(path: Path, value: Any) -> None:
    atomic_write_private(
        path,
        (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
    )


def read_private_json(path: Path) -> Any:
    target = _validate_absolute(Path(path))
    directory = _open_directory_chain(target.parent, create=False)
    descriptor = -1
    try:
        descriptor = os.open(
            target.name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW") | getattr(os, "O_CLOEXEC", 0),
            dir_fd=directory,
        )
        _validate_private_file(descriptor)
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = -1
            return json.load(handle)
    except FileNotFoundError as exc:
        raise DesktopStateError(
            "DESKTOP_STATE_NOT_FOUND", "The requested Desktop-state file is absent."
        ) from exc
    except DesktopStateError:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise DesktopStateError(
            "DESKTOP_STATE_FILE_UNSAFE", "The Desktop-state file cannot be read safely."
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory)


def list_private_json(directory_path: Path) -> list[tuple[str, Any]]:
    directory = _open_directory_chain(directory_path, create=False)
    try:
        names = sorted(
            name
            for name in os.listdir(directory)
            if name.endswith(".json") and not name.startswith(".")
        )
    except OSError as exc:
        os.close(directory)
        raise DesktopStateError(
            "DESKTOP_STATE_READ_FAILED", "Unable to list private Desktop state."
        ) from exc
    os.close(directory)
    return [(name, read_private_json(Path(directory_path) / name)) for name in names]
