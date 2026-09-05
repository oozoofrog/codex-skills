"""Owner-only state helpers for the normal-Chat Desktop runtime."""

from __future__ import annotations

import hashlib
import fcntl
import json
import os
import secrets
import stat
import sys
from dataclasses import dataclass
from contextlib import contextmanager
from pathlib import Path
from typing import Any


@dataclass
class StateError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def state_root(*, home: Path | None = None, platform_name: str | None = None) -> Path:
    root = Path.home() if home is None else Path(home)
    if not root.is_absolute() or root == Path(root.anchor):
        raise StateError("STATE_HOME_UNSAFE", "The account home directory is invalid.")
    if (platform_name or sys.platform) == "darwin":
        return root / "Library" / "Application Support" / "gptpro" / "desktop" / "v5"
    xdg = os.environ.get("XDG_STATE_HOME", "").strip()
    if xdg:
        candidate = Path(xdg)
        if not candidate.is_absolute():
            raise StateError("STATE_ROOT_UNSAFE", "XDG_STATE_HOME must be absolute.")
        return candidate / "gptpro" / "desktop" / "v5"
    return root / ".local" / "state" / "gptpro" / "desktop" / "v5"


def secure_directory(path: Path, *, create: bool = True) -> Path:
    target = Path(path).expanduser()
    if not target.is_absolute() or target == Path(target.anchor) or ".." in target.parts:
        raise StateError("STATE_PATH_UNSAFE", "Private state paths must be absolute and bounded.")
    if create:
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        metadata = target.lstat()
    except OSError as exc:
        raise StateError("STATE_NOT_FOUND", "The private state directory is unavailable.") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
    ):
        raise StateError("STATE_PATH_UNSAFE", "The private state directory is unsafe.")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        if create:
            os.chmod(target, 0o700)
        else:
            raise StateError("STATE_PERMISSIONS_UNSAFE", "Private state must use mode 0700.")
    return target


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write(path: Path, data: bytes, *, mode: int = 0o600) -> None:
    target = Path(path)
    parent = secure_directory(target.parent)
    if target.exists() or target.is_symlink():
        metadata = target.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
        ):
            raise StateError("STATE_FILE_UNSAFE", "Refusing to replace an unsafe state file.")
    temporary = parent / f".{target.name}.tmp-{secrets.token_hex(8)}"
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            mode,
        )
        os.fchmod(descriptor, mode)
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, target)
        directory_fd = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        raise StateError("STATE_WRITE_FAILED", "Unable to write private state atomically.") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except OSError:
            pass


def write_json(path: Path, value: Any) -> None:
    atomic_write(path, canonical_json_bytes(value) + b"\n")


def read_private(path: Path, *, maximum: int = 16 * 1024 * 1024) -> bytes:
    target = Path(path)
    try:
        metadata = target.lstat()
    except OSError as exc:
        raise StateError("STATE_FILE_MISSING", "The requested private state file is absent.") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_size > maximum
    ):
        raise StateError("STATE_FILE_UNSAFE", "The requested private state file is unsafe.")
    return target.read_bytes()


def read_json(path: Path, *, maximum: int = 16 * 1024 * 1024) -> Any:
    try:
        return json.loads(read_private(path, maximum=maximum))
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise StateError("STATE_JSON_INVALID", "Private state JSON is invalid.") from exc


@contextmanager
def package_lock(handoff: Path):
    """Serialize every package lifecycle mutation across processes."""

    directory = secure_directory(Path(handoff), create=False)
    path = directory / ".consult.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise StateError("PACKAGE_LOCK_UNAVAILABLE", "The package lifecycle lock is unavailable.") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise StateError("PACKAGE_LOCK_UNSAFE", "The package lifecycle lock is unsafe.")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise StateError(
                "PACKAGE_LIFECYCLE_IN_PROGRESS",
                "Another process already owns this exact package lifecycle.",
            ) from exc
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(descriptor)
