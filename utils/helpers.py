"""Small, pure helper functions shared across the service modules.

Beginner note: keep this file for stateless helpers only (no file I/O, no
database calls, no global state). That makes them trivial to unit-test.
"""
from __future__ import annotations

import hashlib
import math
from datetime import date, timedelta
from typing import Optional


DEMO_DISCLAIMER = (
    "DEMO DATA - NOT REAL MARKET DATA. SIH26006 prototype. Every figure shown "
    "is synthetic and generated only to demonstrate the decision-support "
    "workflow for overseas bulk raw-material procurement to India's East "
    "Coast. It is NOT a real freight-rate forecast and must not be used for "
    "actual vessel chartering or raw-material procurement decisions."
)


def request_seed(*parts: object) -> int:
    """Build a deterministic 32-bit integer seed from request fields.

    A stable seed means the same scenario always produces the same demo
    forecast, which keeps the UI predictable while the team develops it.
    """
    raw = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def next_monday(from_date: Optional[date] = None) -> date:
    """Return the first Monday strictly after ``from_date`` (default: today)."""
    d = from_date or date.today()
    offset = (7 - d.weekday()) % 7
    return d + timedelta(days=offset or 7)


def week_starts(count: int, from_date: Optional[date] = None) -> list[date]:
    """Return ``count`` consecutive Monday dates starting from next Monday."""
    start = next_monday(from_date)
    return [start + timedelta(weeks=i) for i in range(count)]


def voyages_required(quantity_tonnes: float, vessel_capacity_tonnes: float) -> int:
    """How many full voyages of one vessel class are needed for the cargo."""
    if vessel_capacity_tonnes <= 0:
        return 1
    return max(1, math.ceil(quantity_tonnes / vessel_capacity_tonnes))


def format_usd(value: float) -> str:
    return f"${value:,.2f}"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
