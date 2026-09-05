"""Cross-process serialization for package lifecycle state and receipts."""

from __future__ import annotations

import fcntl
import hashlib
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .runtime_state import RuntimeStateError, ensure_private_directory, open_private_regular


_registry_guard = threading.Lock()
_thread_locks: dict[str, threading.RLock] = {}
_local = threading.local()


def _canonical_handoff(handoff_dir: Path) -> Path:
    try:
        path = Path(handoff_dir).expanduser().resolve(strict=True)
        metadata = path.stat()
    except OSError as exc:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE", "The package lifecycle directory is unavailable."
        ) from exc
    if not path.is_dir() or metadata.st_uid != os.getuid() or metadata.st_mode & 0o022:
        raise RuntimeStateError(
            "RUNTIME_STATE_UNSAFE",
            "The package lifecycle directory must be owned by the current user and not writable by others.",
        )
    return path


def package_lock_path(handoff_dir: Path) -> Path:
    """Return an owner-only lock outside the immutable package artifact set."""

    canonical = _canonical_handoff(handoff_dir)
    lock_root = ensure_private_directory(canonical.parent / ".gptpro-lifecycle-locks")
    identity = hashlib.sha256(str(canonical).encode("utf-8")).hexdigest()
    return lock_root / f"{identity}.lock"


@contextmanager
def package_lifecycle_lock(
    handoff_dir: Path, *, timeout: float = 5.0
) -> Iterator[None]:
    """Acquire the package lock, re-entrantly within one thread.

    Lifecycle code must acquire this lock before the machine-global runtime lock
    and before the disclosure-audit lock. Tool execution never acquires this
    package lock, so this ordering cannot invert the global->audit tool path.
    """

    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("package lifecycle lock timeout must be positive")
    path = package_lock_path(handoff_dir)
    key = str(path)
    with _registry_guard:
        thread_lock = _thread_locks.setdefault(key, threading.RLock())

    with thread_lock:
        depths = getattr(_local, "depths", None)
        if depths is None:
            depths = {}
            _local.depths = depths
        if depths.get(key, 0):
            depths[key] += 1
            try:
                yield
            finally:
                depths[key] -= 1
            return

        descriptor = open_private_regular(path, flags=os.O_RDWR, create=True)
        deadline = time.monotonic() + float(timeout)
        try:
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise RuntimeStateError(
                            "LOCK_TIMEOUT",
                            "The package lifecycle lock is busy.",
                            retryable=True,
                        )
                    time.sleep(0.02)
            depths[key] = 1
            try:
                yield
            finally:
                depths.pop(key, None)
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
