"""Small, pure helper functions shared across the service modules.

Beginner note: keep this file for stateless helpers only (no file I/O, no
database calls, no global state). That makes them trivial to unit-test.
"""
from __future__ import annotations

import hashlib
import math
from datetime import date, timedelta
from typing import Optional, Sequence


DEMO_DISCLAIMER = (
    "SYNTHETIC / DEMONSTRATION DATA - NOT REAL MARKET DATA. SIH26006 prototype. "
    "Every figure shown is synthetic and generated only to demonstrate the "
    "decision-support workflow for overseas bulk raw-material procurement to "
    "India's East Coast. It is NOT a real freight-rate forecast and must not be "
    "used for actual vessel chartering or raw-material procurement decisions."
)

DATA_TRANSPARENCY_NOTE = (
    "Prototype uses synthetic/demo market and infrastructure data. Production "
    "deployment would integrate validated historical, port and licensed market "
    "data. Forecasts demonstrate the architecture, not real market accuracy. "
    "Risk and feasibility scores are model-based heuristic indicators, not "
    "statistically validated probabilities."
)


# --------------------------------------------------------------------------
# Determinism / seeding
# --------------------------------------------------------------------------
def request_seed(*parts: object) -> int:
    """Build a deterministic 32-bit integer seed from request fields.

    A stable seed means the same scenario always produces the same demo
    forecast, which keeps the UI predictable while the team develops it.
    """
    raw = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------
def next_monday(from_date: Optional[date] = None) -> date:
    """Return the first Monday strictly after ``from_date`` (default: today)."""
    d = from_date or date.today()
    offset = (7 - d.weekday()) % 7
    return d + timedelta(days=offset or 7)


def week_starts(count: int, from_date: Optional[date] = None) -> list[date]:
    """Return ``count`` consecutive Monday dates starting from next Monday."""
    start = next_monday(from_date)
    return [start + timedelta(weeks=i) for i in range(count)]


# --------------------------------------------------------------------------
# Chartering arithmetic
# --------------------------------------------------------------------------
def voyages_required(quantity_tonnes: float, vessel_capacity_tonnes: float) -> int:
    """How many full voyages of one vessel class are needed for the cargo."""
    if vessel_capacity_tonnes <= 0:
        return 1
    return max(1, math.ceil(quantity_tonnes / vessel_capacity_tonnes))


def utilisation_pct(quantity_tonnes: float, vessel_capacity_tonnes: float, voyages: int) -> float:
    """Average deadweight utilisation across the planned voyages, as a percent."""
    if vessel_capacity_tonnes <= 0 or voyages <= 0:
        return 0.0
    return round(100.0 * quantity_tonnes / (vessel_capacity_tonnes * voyages), 1)


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------
def format_usd(value: float) -> str:
    return f"${value:,.2f}"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# --------------------------------------------------------------------------
# Lightweight statistics / forecasting primitives
# --------------------------------------------------------------------------
def mean(values: Sequence[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def stdev(values: Sequence[float]) -> float:
    """Population standard deviation (0.0 for < 2 points)."""
    values = list(values)
    if len(values) < 2:
        return 0.0
    mu = mean(values)
    return math.sqrt(sum((v - mu) ** 2 for v in values) / len(values))


def moving_average(values: Sequence[float], window: int) -> float:
    """Mean of the last ``window`` values (or all of them if fewer)."""
    values = list(values)
    if not values:
        return 0.0
    window = max(1, min(window, len(values)))
    return mean(values[-window:])


def linear_trend(values: Sequence[float]) -> float:
    """Ordinary least-squares slope per step over the series (0.0 if < 2 points)."""
    values = list(values)
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx, my = mean(xs), mean(values)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, values)) / denom


def holt_linear(values: Sequence[float], alpha: float = 0.5, beta: float = 0.3) -> tuple[float, float]:
    """Holt's linear (double) exponential smoothing.

    Returns ``(level, trend)`` after the last observation, so the h-step-ahead
    point forecast is ``level + h * trend``.
    """
    values = list(values)
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return values[0], 0.0
    level = values[0]
    trend = values[1] - values[0]
    for v in values[1:]:
        prev_level = level
        level = alpha * v + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
    return level, trend


def mape(actual: Sequence[float], predicted: Sequence[float]) -> Optional[float]:
    """Mean absolute percentage error (percent), or ``None`` if not computable."""
    pairs = [(a, p) for a, p in zip(actual, predicted) if a not in (0, 0.0)]
    if not pairs:
        return None
    return round(100.0 * mean([abs(a - p) / abs(a) for a, p in pairs]), 2)


# --------------------------------------------------------------------------
# Heuristic risk bands (model-based indicators, not probabilities)
# --------------------------------------------------------------------------
def risk_band(score: float) -> str:
    """Map a 0..1 heuristic risk score to LOW / MEDIUM / HIGH."""
    if score >= 0.66:
        return "HIGH"
    if score >= 0.36:
        return "MEDIUM"
    return "LOW"


def confidence_band(score: float) -> str:
    """Map a 0..1 confidence score to LOW / MEDIUM / HIGH."""
    if score >= 0.7:
        return "HIGH"
    if score >= 0.45:
        return "MEDIUM"
    return "LOW"
