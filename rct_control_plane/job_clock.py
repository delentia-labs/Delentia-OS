"""Fail closed on a worker's unstable clock; never repair timestamps silently."""
from __future__ import annotations

import math
import sqlite3
from typing import Callable

CLOCK_TOLERANCE_SECONDS = 2.0


class LeaseClock:
    def __init__(self, wall: float, monotonic: Callable[[], float] | None):
        self.monotonic = monotonic
        self.origin_wall = self.last_wall = float(wall)
        self.origin_mono = monotonic() if monotonic is not None else None
        self.fault = False
        self.check(wall)

    def check(self, wall: float) -> float:
        wall = float(wall)
        invalid = not math.isfinite(wall) or wall < self.last_wall - CLOCK_TOLERANCE_SECONDS
        if self.monotonic is not None:
            assert self.origin_mono is not None
            mono = self.monotonic()
            expected = self.origin_wall + mono - self.origin_mono
            invalid = invalid or not math.isfinite(mono) or abs(wall - expected) > CLOCK_TOLERANCE_SECONDS
        self.fault = self.fault or invalid
        if self.fault:
            raise sqlite3.OperationalError('worker clock unstable; stop worker and inspect before restart')
        self.last_wall = max(self.last_wall, wall)
        return wall
