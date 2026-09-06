"""Multiple-voyage contract strategy comparison (SIH26006) - Module E.

Compares three ways to lift the same cargo with the same (best feasible) vessel:

    1. Repeated Spot       - re-fix every voyage on the spot market
    2. Short-term MVC      - one short multi-voyage contract of affreightment
    3. Medium-term MVC     - a longer term multi-voyage contract

MVC is NOT hard-coded as cheaper. Each strategy is priced off the SAME forecast
curve; MVC trades a fixture premium / volume position for lower volatility. If
the forecast falls steeply, repeated spot can still win - the numbers decide.

All figures are SYNTHETIC / DEMONSTRATION DATA.
"""
from __future__ import annotations

from schemas.forecast_schema import (
    ContractPreference,
    ContractStrategy,
    ForecastRequest,
    ForecastSeries,
    VesselOption,
)
from services.optimizer import port_call_cost
from utils.helpers import clamp, mean, risk_band

# Demo contract-economics assumptions (synthetic):
_SPOT_VOLATILITY_PREMIUM = 0.03    # spot re-fixing friction / exposure loading
_ST_MVC_FIXTURE_PREMIUM = 0.015    # owner's premium for a short commitment
_ST_MVC_VOLUME_DISCOUNT = 0.045    # schedule certainty / volume rebate
_MT_MVC_FIXTURE_PREMIUM = 0.030    # larger premium for a longer commitment
_MT_MVC_VOLUME_DISCOUNT = 0.070    # bigger volume rebate
_MT_MVC_MARKET_FALL_RISK = 0.02    # being locked in if the market drops


def _strategy_rate_spot(forecast: ForecastSeries, voyages: int) -> float:
    """Spread voyages across the horizon and average their forecast rates."""
    pts = forecast.forecast
    if not pts:
        return 0.0
    step = max(1, len(pts) // max(voyages, 1))
    picks = [pts[min(i * step, len(pts) - 1)].predicted_rate_usd_per_tonne for i in range(voyages)]
    return mean(picks) * (1 + _SPOT_VOLATILITY_PREMIUM)


def compare_contracts(
    request: ForecastRequest,
    forecast: ForecastSeries,
    vessel: VesselOption,
) -> list[ContractStrategy]:
    quantity = float(request.quantity_tonnes)
    voyages = vessel.voyages_required
    parcel = round(quantity / voyages, 1)
    pcc = port_call_cost(vessel.vessel_type, voyages)
    delivery_ok = vessel.delivery_feasible and vessel.port_feasibility == "FEASIBLE"

    horizon_avg = mean([p.predicted_rate_usd_per_tonne for p in forecast.forecast])
    early_avg = mean([p.predicted_rate_usd_per_tonne for p in forecast.forecast[:4]])

    spot_rate = round(_strategy_rate_spot(forecast, voyages), 2)
    st_rate = round(early_avg * (1 + _ST_MVC_FIXTURE_PREMIUM - _ST_MVC_VOLUME_DISCOUNT), 2)
    mt_rate = round(horizon_avg * (1 + _MT_MVC_FIXTURE_PREMIUM - _MT_MVC_VOLUME_DISCOUNT), 2)

    def _row(strategy: str, duration: str, rate: float, risk_score: float,
             implications: str) -> ContractStrategy:
        total = round(rate * quantity + pcc, 2)
        return ContractStrategy(
            strategy=strategy,
            contract_duration=duration,
            vessel_type=vessel.vessel_type,
            number_of_voyages=voyages,
            cargo_per_voyage_tonnes=parcel,
            total_cargo_tonnes=round(quantity, 1),
            expected_freight_rate_usd_per_tonne=rate,
            expected_total_cost_usd=total,
            expected_utilization_pct=vessel.utilization_pct,
            delivery_feasible=delivery_ok,
            risk_level=risk_band(risk_score),
            savings_vs_spot_usd=0.0,
            savings_vs_spot_pct=0.0,
            operational_implications=implications,
            recommended=False,
        )

    spot_risk = 0.62 + (0.08 if voyages >= 3 else 0.0)
    st_risk = 0.42
    # Locked-in for longer: rated Medium/High because a market fall after fixing
    # cannot be recovered.
    mt_risk = 0.67 + _MT_MVC_MARKET_FALL_RISK * 3

    rows = [
        _row("Repeated Spot", f"{voyages} separate fixtures", spot_rate, spot_risk,
             "Maximum flexibility, but every voyage is re-exposed to freight "
             "volatility and vessel availability; highest administrative load."),
        _row("Short-term MVC", "~6-10 weeks", st_rate, st_risk,
             "One contract of affreightment covering all voyages in the entry "
             "window; removes per-voyage volatility, keeps commitment short."),
        _row("Medium-term MVC", "~3-6 months", mt_rate, mt_risk,
             "Lowest unit rate via volume, but locks the position for longer - "
             "downside if the market falls after fixing."),
    ]

    spot_total = rows[0].expected_total_cost_usd
    for r in rows:
        r.savings_vs_spot_usd = round(spot_total - r.expected_total_cost_usd, 2)
        r.savings_vs_spot_pct = round(
            100.0 * (spot_total - r.expected_total_cost_usd) / spot_total, 2
        ) if spot_total else 0.0

    _flag_recommended(rows, request.contract_preference)
    return rows


_RISK_WEIGHT = {"LOW": 0.0, "MEDIUM": 0.5, "HIGH": 1.0}


def _flag_recommended(rows: list[ContractStrategy], preference: ContractPreference) -> None:
    label_map = {
        ContractPreference.spot: "Repeated Spot",
        ContractPreference.short_term_mvc: "Short-term MVC",
        ContractPreference.medium_term_mvc: "Medium-term MVC",
    }
    if preference in label_map:
        target = next((r for r in rows if r.strategy == label_map[preference]), None)
        if target is not None:
            target.recommended = True
            return

    # Compare All -> best expected cost / risk trade-off (cost 0.6, risk 0.4).
    feasible = [r for r in rows if r.delivery_feasible] or rows
    max_cost = max(r.expected_total_cost_usd for r in feasible) or 1.0
    min_cost = min(r.expected_total_cost_usd for r in feasible)
    span = (max_cost - min_cost) or 1.0

    def score(r: ContractStrategy) -> float:
        cost_norm = (r.expected_total_cost_usd - min_cost) / span
        risk_norm = _RISK_WEIGHT.get(r.risk_level, 0.5)
        return 0.6 * cost_norm + 0.4 * risk_norm

    best = min(feasible, key=score)
    best.recommended = True


def recommended_contract(rows: list[ContractStrategy]) -> ContractStrategy:
    return next((r for r in rows if r.recommended), rows[0])
