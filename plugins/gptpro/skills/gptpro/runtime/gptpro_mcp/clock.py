"""Conservative UTC and monotonic clocks for bounded MCP sessions."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable


def parse_utc(value: str) -> datetime:
    """Parse one timezone-aware ISO-8601 value and normalize it to UTC."""

    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be a non-empty string")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Clock:
    """Injectable process clock that never extends a session on wall-clock rollback."""

    wall: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    monotonic: Callable[[], float] = time.monotonic

    def anchor(self) -> "ClockAnchor":
        wall = self.wall()
        if wall.tzinfo is None:
            raise ValueError("wall clock must be timezone-aware")
        return ClockAnchor(
            clock=self,
            wall_at_anchor=wall.astimezone(timezone.utc),
            monotonic_at_anchor=self.monotonic(),
        )


@dataclass(frozen=True)
class ClockAnchor:
    clock: Clock
    wall_at_anchor: datetime
    monotonic_at_anchor: float

    def effective_now(self, *, persisted_floor: datetime | None = None) -> datetime:
        wall = self.clock.wall()
        if wall.tzinfo is None:
            raise ValueError("wall clock must be timezone-aware")
        elapsed = max(0.0, self.clock.monotonic() - self.monotonic_at_anchor)
        monotonic_wall = self.wall_at_anchor + timedelta(seconds=elapsed)
        candidates = [wall.astimezone(timezone.utc), monotonic_wall]
        if persisted_floor is not None:
            if persisted_floor.tzinfo is None:
                raise ValueError("persisted floor must be timezone-aware")
            candidates.append(persisted_floor.astimezone(timezone.utc))
        return max(candidates)
