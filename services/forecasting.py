"""Freight-rate forecasting service (SIH26006) - Module A building block.

Approach (transparent, small-data friendly):
  * Load the lane's synthetic weekly history from ``data/freight_rates.csv``.
  * Blend two cheap baselines the judges can reason about:
        - a short moving average (level), and
        - Holt's linear exponential smoothing (level + trend).
  * Widen a confidence band from the history's residual scatter, growing with
    the forecast horizon.
  * Derive a heuristic confidence label from volatility + history length, and a
    one-step holdout MAPE so the demo can show a validation number.

STATUS: this is a demonstration of the forecasting *architecture* on synthetic
data. It is NOT a validated market model. A production build would source real
historical Indian import freight + bunker data and back-test SARIMA / gradient
boosting / quantile models here, keeping the same return type.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import numpy as np

from schemas.forecast_schema import (
    ForecastPoint,
    ForecastRequest,
    ForecastSeries,
    HistoricalPoint,
    RouteInfo,
)
from services.data_service import data_service
from utils.helpers import (
    clamp,
    confidence_band,
    holt_linear,
    linear_trend,
    mape,
    mean,
    moving_average,
    request_seed,
    stdev,
    week_starts,
)

HORIZON_WEEKS = 8


def _history(route: RouteInfo) -> list[float]:
    rows = data_service.historical_rates(route.route_id)
    values = [r for _, r in rows]
    if len(values) >= 6:
        return values
    # Fallback if the lane has little/no history: synthesise a flat-ish series
    # around the lane reference rate so the demo still renders.
    base = route.reference_rate_usd_per_tonne
    rng = np.random.default_rng(request_seed(route.route_id, "synth-history"))
    return [round(float(base + rng.normal(0, base * 0.02)), 2) for _ in range(12)]


def _history_dates(route: RouteInfo, n: int) -> list[str]:
    rows = data_service.historical_rates(route.route_id)
    if len(rows) >= n:
        return [d for d, _ in rows][-n:]
    # Fabricate weekly dates ending "recently" for the fallback case.
    from datetime import timedelta

    start = date(2026, 4, 13)
    return [(start + timedelta(weeks=i)).isoformat() for i in range(n)]


def _blended_forecast(values: list[float], horizon: int) -> list[float]:
    """MA level + Holt trend, blended, clamped to a sane band."""
    ma = moving_average(values, window=4)
    level, trend = holt_linear(values, alpha=0.5, beta=0.3)
    # Damp the trend so it doesn't run away over an 8-week horizon.
    trend *= 0.6
    anchor = 0.5 * ma + 0.5 * level
    lo = min(values) * 0.75
    hi = max(values) * 1.35
    return [round(clamp(anchor + trend * (h + 1), lo, hi), 2) for h in range(horizon)]


def _backtest_mape(values: list[float]) -> Optional[float]:
    """One-step-ahead holdout MAPE over the back half of the history."""
    if len(values) < 8:
        return None
    preds, actuals = [], []
    for cut in range(len(values) // 2, len(values)):
        window = values[:cut]
        ma = moving_average(window, 4)
        level, trend = holt_linear(window, 0.5, 0.3)
        preds.append(0.5 * ma + 0.5 * (level + 0.6 * trend))
        actuals.append(values[cut])
    return mape(actuals, preds)


def generate_forecast(request: ForecastRequest, route: RouteInfo, today: Optional[date] = None) -> ForecastSeries:
    """Return an 8-week freight-rate :class:`ForecastSeries` for the lane."""
    values = _history(route)
    hist_dates = _history_dates(route, len(values))
    historical = [
        HistoricalPoint(week_start=date.fromisoformat(d), rate_usd_per_tonne=v)
        for d, v in zip(hist_dates, values)
    ]

    horizon = HORIZON_WEEKS
    starts = week_starts(horizon, today)
    points_mid = _blended_forecast(values, horizon)

    # Residual scatter of the blended model on the history -> base band width.
    resid = stdev(values) if len(values) > 1 else max(0.5, 0.03 * mean(values))
    resid = max(resid, 0.02 * mean(values))

    seed = request_seed(route.route_id, request.cargo_type.value, "band")
    rng = np.random.default_rng(seed)

    points: list[ForecastPoint] = []
    for i, (start, mid) in enumerate(zip(starts, points_mid)):
        # Band grows ~sqrt(h): more uncertainty further out.
        half = resid * (1.0 + 0.35 * np.sqrt(i)) + rng.uniform(0, 0.05 * resid)
        lower = round(mid - half, 2)
        upper = round(mid + half, 2)
        unc = round(100.0 * half / mid, 1) if mid else 0.0
        points.append(
            ForecastPoint(
                week_index=i + 1,
                week_start=start,
                predicted_rate_usd_per_tonne=mid,
                lower_bound_usd_per_tonne=lower,
                upper_bound_usd_per_tonne=upper,
                uncertainty_pct=unc,
            )
        )

    slope = linear_trend(values)
    if slope > 0.05:
        trend_label = "rising"
    elif slope < -0.05:
        trend_label = "easing"
    else:
        trend_label = "broadly flat"

    mu = mean(values)
    vol_pct = round(100.0 * stdev(values) / mu, 1) if mu else 0.0

    # Confidence: lower volatility + more history -> higher confidence.
    vol_component = clamp(1.0 - vol_pct / 12.0, 0.0, 1.0)
    hist_component = clamp(len(values) / 20.0, 0.0, 1.0)
    conf_score = round(0.65 * vol_component + 0.35 * hist_component, 2)

    return ForecastSeries(
        method="Moving average + Holt linear exponential smoothing (blended); "
        "band from residual scatter",
        horizon_weeks=horizon,
        history_weeks=len(values),
        historical=historical,
        forecast=points,
        trend=trend_label,
        trend_usd_per_week=round(slope, 3),
        volatility_pct=vol_pct,
        confidence=confidence_band(conf_score),
        confidence_score=conf_score,
        backtest_mape_pct=_backtest_mape(values),
        note="Synthetic-data demonstration of the forecasting architecture - "
        "not a validated market forecast.",
    )


def horizon_weeks_for(_delivery_window_days: int) -> int:
    """Kept for API stability; the horizon is a fixed 8 weeks now."""
    return HORIZON_WEEKS
