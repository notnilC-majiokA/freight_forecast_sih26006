"""Risk mitigation engine (SIH26006) - Module G.

Combines the scenario's individual exposures into an overall heuristic risk
indicator plus actionable mitigation. Every score here is a MODEL-BASED /
HEURISTIC indicator on synthetic data - NOT a statistically validated
probability.

Components:
  A. Freight market volatility     (from the forecast history)
  B. Forecast uncertainty          (from the forecast band width)
  C. Origin port congestion        (data/congestion.csv)
  D. Destination port congestion   (data/congestion.csv)
  E. Vessel / port compatibility   (from the feasibility engine)
  F. Delivery pressure             (turnaround vs deadline)
  G. Idle exposure                 (from Module F)
"""
from __future__ import annotations

from schemas.forecast_schema import (
    ContractStrategy,
    EntryWindow,
    ForecastRequest,
    ForecastSeries,
    IdleAnalysis,
    PortFeasibilityResult,
    RiskAnalysis,
    RiskComponent,
    RouteInfo,
    VesselOption,
)
from services.data_service import data_service
from utils.helpers import clamp, mean, risk_band

_LEVEL_SCORE = {"LOW": 0.2, "MEDIUM": 0.5, "HIGH": 0.82}
_COMPONENT_WEIGHTS = {
    "Freight market volatility": 0.20,
    "Forecast uncertainty": 0.18,
    "Origin port congestion": 0.12,
    "Destination port congestion": 0.13,
    "Vessel/port compatibility": 0.15,
    "Delivery pressure": 0.14,
    "Idle exposure": 0.08,
}


def _congestion_component(port_name: str, role: str) -> RiskComponent:
    row = data_service.congestion_for(port_name)
    factor = float(row.get("congestion_factor", 1.25))
    wait = float(row.get("avg_wait_days", 3.0))
    score = clamp((factor - 1.0) / 0.7 * 0.6 + wait / 12.0, 0.0, 1.0)
    return RiskComponent(
        name=f"{role} port congestion",
        level=risk_band(score),
        score=round(score, 2),
        rationale=f"{port_name}: congestion factor {factor:.2f}, ~{wait:.0f}-day "
        f"pre-berth wait ({row.get('trend', 'n/a')}).",
    )


def assess_risk(
    request: ForecastRequest,
    route: RouteInfo,
    forecast: ForecastSeries,
    vessel: VesselOption,
    feasibility: PortFeasibilityResult,
    entry: EntryWindow,
    contract: ContractStrategy,
    idle: IdleAnalysis,
) -> RiskAnalysis:
    window = int(request.delivery_window_days.value)

    # A. market volatility
    vol_score = clamp(forecast.volatility_pct / 12.0, 0.0, 1.0)
    comp_vol = RiskComponent(
        name="Freight market volatility",
        level=risk_band(vol_score),
        score=round(vol_score, 2),
        rationale=f"History volatility {forecast.volatility_pct:.1f}% of mean; "
        f"trend {forecast.trend}.",
    )

    # B. forecast uncertainty (mean band half-width across the horizon)
    unc = mean([p.uncertainty_pct for p in forecast.forecast])
    unc_score = clamp(unc / 14.0, 0.0, 1.0)
    comp_unc = RiskComponent(
        name="Forecast uncertainty",
        level=risk_band(unc_score),
        score=round(unc_score, 2),
        rationale=f"Mean forecast band +/-{unc:.1f}%; backtest MAPE "
        f"{forecast.backtest_mape_pct if forecast.backtest_mape_pct is not None else 'n/a'}%.",
    )

    # C / D. congestion
    comp_oc = _congestion_component(route.load_port, "Origin")
    comp_oc.name = "Origin port congestion"
    comp_dc = _congestion_component(route.destination_port, "Destination")
    comp_dc.name = "Destination port congestion"

    # E. vessel/port compatibility
    if feasibility.overall != "FEASIBLE":
        compat_score = 0.9
        compat_rat = "Recommended vessel is not fully feasible on this lane."
    else:
        margin = min(vessel_draft_margin(vessel, route))
        compat_score = clamp(0.45 - margin / 6.0, 0.05, 0.6)
        compat_rat = (
            f"{vessel.vessel_type} clears both ports; tightest draft margin "
            f"~{margin:.1f} m."
        )
    comp_compat = RiskComponent(
        name="Vessel/port compatibility",
        level=risk_band(compat_score),
        score=round(compat_score, 2),
        rationale=compat_rat,
    )

    # F. delivery pressure
    ratio = feasibility.turnaround_days / window if window else 1.0
    press_score = clamp((ratio - 0.5) / 0.5, 0.0, 1.0)
    comp_press = RiskComponent(
        name="Delivery pressure",
        level=risk_band(press_score),
        score=round(press_score, 2),
        rationale=f"~{feasibility.turnaround_days:.0f}-day turnaround vs "
        f"{window}-day deadline ({ratio * 100:.0f}% of the window used).",
    )

    # G. idle exposure
    idle_score = _LEVEL_SCORE.get(idle.idle_risk, 0.5)
    comp_idle = RiskComponent(
        name="Idle exposure",
        level=idle.idle_risk,
        score=round(idle_score, 2),
        rationale=f"~{idle.expected_idle_days:.0f} expected idle day(s); "
        f"utilisation {idle.utilization_pct:.0f}%.",
    )

    components = [comp_vol, comp_unc, comp_oc, comp_dc, comp_compat, comp_press, comp_idle]
    overall_score = round(
        sum(_COMPONENT_WEIGHTS.get(c.name, 0.1) * c.score for c in components), 2
    )
    overall = risk_band(overall_score)

    mitigation = _mitigation(components, entry, contract, feasibility, idle)

    return RiskAnalysis(
        overall_risk=overall,
        overall_score=overall_score,
        components=components,
        mitigation=mitigation,
    )


def vessel_draft_margin(vessel: VesselOption, route: RouteInfo):
    """Yield the draft margin (m) at origin and destination for the chosen vessel."""
    origin = data_service.port(route.load_port) or {}
    dest = data_service.port(route.destination_port) or {}
    for port in (origin, dest):
        try:
            yield float(port.get("max_draft_m", 99)) - vessel.laden_draft_m
        except (TypeError, ValueError):
            yield 99.0


def _mitigation(
    components: list[RiskComponent],
    entry: EntryWindow,
    contract: ContractStrategy,
    feasibility: PortFeasibilityResult,
    idle: IdleAnalysis,
) -> list[str]:
    out: list[str] = []
    top = sorted(components, key=lambda c: c.score, reverse=True)[:3]
    names = {c.name for c in top}

    if "Freight market volatility" in names or "Forecast uncertainty" in names:
        out.append(
            f"Secure the {contract.strategy} during the {entry.label} entry "
            f"window to cap exposure to later freight volatility."
        )
    if "Destination port congestion" in names or "Origin port congestion" in names:
        out.append(
            "Build congestion buffer into the laycan and pre-advise the "
            "discharge berth; consider a lower-congestion East Coast port if "
            "commercially acceptable."
        )
    if "Delivery pressure" in names:
        out.append(
            "Start chartering earlier or split the parcel across two vessels to "
            "protect the delivery deadline."
        )
    if "Idle exposure" in names or idle.idle_risk == "HIGH":
        out.append(idle.mitigation)
    if feasibility.overall != "FEASIBLE":
        out.append(
            "Re-run with 'Optimize' vessel selection - the current class is not "
            "feasible on this lane."
        )
    if not out:
        out.append("Overall exposure is contained; proceed with the recommended plan.")
    return out
