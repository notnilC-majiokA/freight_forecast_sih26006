"""Freight-rate forecasting service.

STATUS: PLACEHOLDER  ------------------------------------------------------
This module currently returns a deterministic DEMO series so the UI and the
API can be built end to end. **The real forecasting model is not written
yet.** Do not present any output of this module as a real forecast.

TODO (SIH team - the actual project work):
  1. Pull cleaned historical freight rates + bunker prices from
     ``services.data_service`` (real, sourced data - not the demo CSVs).
  2. Feature engineering: seasonality, route, cargo, vessel, bunker cost,
     lag / rolling-mean terms, macro indicators.
  3. Train and back-test candidate models, e.g.:
       * ``statsmodels`` SARIMAX / Exponential Smoothing for the univariate
         rate series per route.
       * ``scikit-learn`` GradientBoostingRegressor / RandomForest for the
         multivariate case.
  4. Produce genuine prediction intervals (e.g. quantile regression or
     model residual bootstrapping).
  5. Persist the chosen model to ``models/`` with ``joblib``.
  6. Replace :func:`generate_forecast` below with real inference, keeping
     the same signature and return type (``list[ForecastPoint]``).
------------------------------------------------------------------------
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import numpy as np

from schemas.forecast_schema import ForecastPoint, ForecastRequest
from utils.helpers import clamp, request_seed, week_starts

# Clearly-synthetic baseline rates (USD / tonne). Used ONLY to make the demo
# curve land in a plausible-looking range. These are not market observations.
_DEMO_BASE_RATE_USD_PER_TONNE = {
    "Coking Coal": 21.0,
    "Iron Ore": 20.0,
    "Limestone": 14.0,
}
# Rough origin-distance effect on the rate to India's East Coast (demo only).
_DEMO_REGION_ADJUSTMENT = {
    "Indonesia": -2.0,
    "Australia": 0.0,
    "South Africa": 1.5,
    "Brazil": 6.0,
}


def horizon_weeks_for(delivery_window_days: int) -> int:
    """How many weekly points to forecast for a given delivery window."""
    return max(4, round(delivery_window_days / 7))


def generate_forecast(
    request: ForecastRequest, today: Optional[date] = None
) -> list[ForecastPoint]:
    """Return a DEMO weekly freight-rate forecast for the requested scenario.

    The series is deterministic in the request fields, so the same form
    input always renders the same chart during development.
    """
    weeks = horizon_weeks_for(int(request.delivery_window_days.value))
    starts = week_starts(weeks, today)

    seed = request_seed(
        request.cargo_type.value,
        request.origin_region.value,
        request.destination_port.value,
        int(request.delivery_window_days.value),
    )
    rng = np.random.default_rng(seed)

    base = _DEMO_BASE_RATE_USD_PER_TONNE.get(request.cargo_type.value, 18.0)
    base += _DEMO_REGION_ADJUSTMENT.get(request.origin_region.value, 0.0)

    # Gentle linear trend + a seasonal-looking wave + small gaussian noise.
    trend = rng.uniform(-0.15, 0.25)
    wave_amplitude = rng.uniform(0.5, 1.5)
    phase = rng.uniform(0.0, 2.0 * np.pi)
    period = max(weeks, 6)

    points: list[ForecastPoint] = []
    for i, start in enumerate(starts):
        seasonal = wave_amplitude * np.sin(phase + i * (2.0 * np.pi / period))
        noise = rng.normal(0.0, 0.35)
        rate = clamp(base + trend * i + seasonal + noise, 5.0, 120.0)
        # Uncertainty band widens further into the horizon.
        spread = 0.8 + 0.06 * i
        points.append(
            ForecastPoint(
                week_index=i,
                week_start=start,
                predicted_rate_usd_per_tonne=round(float(rate), 2),
                lower_bound_usd_per_tonne=round(float(rate - spread), 2),
                upper_bound_usd_per_tonne=round(float(rate + spread), 2),
            )
        )
    return points
