"""Vessel-type optimisation + market-entry timing (SIH26006) - Modules B & A.

Module B - vessel optimisation
    Evaluate every vessel class (Handysize / Supramax / Panamax / Capesize) for
    the scenario. A class is only a candidate if the port/vessel feasibility
    engine says FEASIBLE at both ends AND the delivery deadline is achievable.
    The recommendation is the "BEST feasible vessel" (lowest expected cost among
    the feasible set), NOT simply the cheapest $/tonne.

Module A - market-entry timing
    Score booking windows (Now, Week 2 ... Week 6) on the forecast curve:
    expected rate, expected total cost, $/tonne, forecast uncertainty, risk and
    delivery feasibility - then pick an entry WINDOW rather than pretending to
    know the exact future low.

All figures are SYNTHETIC / DEMONSTRATION DATA.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from schemas.forecast_schema import (
    EntryWindow,
    ForecastRequest,
    ForecastSeries,
    RouteInfo,
    VesselOption,
    VesselPreference,
)
from services import port_feasibility
from services.data_service import data_service
from utils.helpers import clamp, mean, risk_band, utilisation_pct, voyages_required

# Demo-only $/tonne multipliers by class: smaller ships cost more per tonne but
# reach draft-restricted ports; bigger ships are cheaper per tonne where they fit.
_CLASS_RATE_FACTOR = {
    "Handysize": 1.18,
    "Supramax": 1.08,
    "Panamax": 1.00,
    "Capesize": 0.90,
}
# Demo per-voyage fixed port/agency/dues cost by class (USD).
_PORT_CALL_COST = {
    "Handysize": 35_000.0,
    "Supramax": 45_000.0,
    "Panamax": 60_000.0,
    "Capesize": 95_000.0,
}
_VESSEL_ORDER = ["Handysize", "Supramax", "Panamax", "Capesize"]
_ENTRY_LABELS = ["Now", "Week 2", "Week 3", "Week 4", "Week 5", "Week 6"]


def port_call_cost(vessel_type: str, voyages: int) -> float:
    return _PORT_CALL_COST.get(vessel_type, 55_000.0) * voyages


# --------------------------------------------------------------------------
# Module B - vessel optimisation
# --------------------------------------------------------------------------
def _origin_port_row(request: ForecastRequest, route: RouteInfo) -> dict[str, Any]:
    """User's preferred load port if it serves the country, else the lane default."""
    if request.origin_port:
        p = data_service.port(request.origin_port)
        if p and str(p.get("country", "")).lower() == request.origin_country.value.lower() \
                and p.get("role") == "load":
            return p
    return data_service.port(route.load_port) or {"port_name": route.load_port}


def _operational_risk(voyages: int, turnaround: float, window: int, util: float,
                      draft_margin: float) -> tuple[str, float]:
    score = 0.18
    if voyages >= 3:
        score += 0.26
    elif voyages == 2:
        score += 0.12
    ratio = turnaround / window if window else 1.0
    if ratio > 0.85:
        score += 0.22
    elif ratio > 0.70:
        score += 0.11
    if util < 55:
        score += 0.14
    if draft_margin < 1.0:
        score += 0.12
    score = clamp(score, 0.0, 1.0)
    return risk_band(score), round(score, 2)


def evaluate_vessels(
    request: ForecastRequest, route: RouteInfo, forecast: ForecastSeries
) -> list[VesselOption]:
    """Return one VesselOption per class, with exactly one flagged as BEST
    (unless nothing is feasible)."""
    quantity = float(request.quantity_tonnes)
    window = int(request.delivery_window_days.value)
    forecast_avg = mean([p.predicted_rate_usd_per_tonne for p in forecast.forecast])

    origin_row = _origin_port_row(request, route)
    dest_row = data_service.port(route.destination_port) or {"port_name": route.destination_port}

    options: list[VesselOption] = []
    for vtype in _VESSEL_ORDER:
        vrow = data_service.vessel(vtype)
        if not vrow:
            continue
        capacity = int(vrow.get("capacity_tonnes", 1)) or 1
        voyages = voyages_required(quantity, capacity)
        parcel = round(quantity / voyages, 1)
        util = utilisation_pct(quantity, capacity, voyages)

        feas = port_feasibility.assess(vrow, origin_row, dest_row, route, quantity, window)

        rate = round(forecast_avg * _CLASS_RATE_FACTOR.get(vtype, 1.0), 2)
        total = round(rate * quantity + port_call_cost(vtype, voyages), 2)

        draft_margin = min(
            float(origin_row.get("max_draft_m", 99)) - float(vrow.get("laden_draft_m", 0)),
            float(dest_row.get("max_draft_m", 99)) - float(vrow.get("laden_draft_m", 0)),
        )
        op_risk, _ = _operational_risk(
            voyages, feas.turnaround_days, window, util, draft_margin
        )

        options.append(
            VesselOption(
                vessel_type=vtype,
                capacity_tonnes=capacity,
                loa_m=float(vrow.get("loa_m", 0)),
                beam_m=float(vrow.get("beam_m", 0)),
                laden_draft_m=float(vrow.get("laden_draft_m", 0)),
                voyages_required=voyages,
                cargo_per_voyage_tonnes=parcel,
                utilization_pct=util,
                origin_port_feasible=feas.origin.verdict == "FEASIBLE",
                destination_port_feasible=feas.destination.verdict == "FEASIBLE",
                port_feasibility=feas.overall,
                infeasibility_reasons=[] if feas.overall == "FEASIBLE" else feas.reasons,
                estimated_turnaround_days=feas.turnaround_days,
                delivery_feasible=feas.delivery_feasible,
                expected_freight_rate_usd_per_tonne=rate,
                expected_total_cost_usd=total,
                operational_risk=op_risk,
                recommended=False,
                verdict="Feasible" if feas.overall == "FEASIBLE" else "Infeasible",
            )
        )

    _flag_best(options, request)
    return options


def _flag_best(options: list[VesselOption], request: ForecastRequest) -> None:
    feasible = [o for o in options if o.port_feasibility == "FEASIBLE" and o.delivery_feasible]
    pref = request.vessel_preference

    chosen: Optional[VesselOption] = None
    if pref != VesselPreference.optimize:
        forced = next((o for o in feasible if o.vessel_type == pref.value), None)
        if forced is not None:
            chosen = forced
        # forced choice infeasible -> fall through to best feasible (never
        # recommend an infeasible vessel)
    if chosen is None and feasible:
        chosen = min(feasible, key=lambda o: o.expected_total_cost_usd)

    if chosen is not None:
        chosen.recommended = True
        chosen.verdict = "BEST"


def chosen_vessel(options: list[VesselOption]) -> VesselOption:
    """The recommended option, or the least-broken one if nothing is feasible."""
    best = next((o for o in options if o.recommended), None)
    if best is not None:
        return best
    # Nothing feasible: prefer the cheapest that at least clears both ports,
    # else the cheapest overall.
    ports_ok = [o for o in options if o.origin_port_feasible and o.destination_port_feasible]
    pool = ports_ok or options
    return min(pool, key=lambda o: o.expected_total_cost_usd)


# --------------------------------------------------------------------------
# Module A - market-entry timing
# --------------------------------------------------------------------------
def _window_risk(uncertainty_pct: float, week_index: int, delivery_slack: float) -> str:
    score = 0.15 + uncertainty_pct / 25.0 + 0.05 * week_index
    if delivery_slack < 5:
        score += 0.25
    elif delivery_slack < 12:
        score += 0.10
    return risk_band(clamp(score, 0.0, 1.0))


def evaluate_entry_windows(
    request: ForecastRequest,
    route: RouteInfo,
    forecast: ForecastSeries,
    vessel: VesselOption,
) -> tuple[list[EntryWindow], EntryWindow]:
    quantity = float(request.quantity_tonnes)
    window = int(request.delivery_window_days.value)
    voyages = vessel.voyages_required
    pcc = port_call_cost(vessel.vessel_type, voyages)
    turnaround = vessel.estimated_turnaround_days
    pts = forecast.forecast

    rows: list[EntryWindow] = []
    for idx, label in enumerate(_ENTRY_LABELS):
        pt = pts[min(idx, len(pts) - 1)]
        rate = pt.predicted_rate_usd_per_tonne
        total = round(rate * quantity + pcc, 2)
        cpt = round(total / quantity, 2)
        lead = round(idx * 7 + turnaround, 1)
        slack = window - lead
        feasible = lead <= window
        rows.append(
            EntryWindow(
                label=label,
                week_index=idx,
                week_start=pt.week_start,
                expected_rate_usd_per_tonne=rate,
                expected_total_cost_usd=total,
                cost_per_tonne_usd=cpt,
                forecast_uncertainty_pct=pt.uncertainty_pct,
                risk_level=_window_risk(pt.uncertainty_pct, idx, slack),
                delivery_feasible=feasible,
                estimated_delivery_lead_days=lead,
                recommended=False,
                note="",
            )
        )

    feasible_rows = [r for r in rows if r.delivery_feasible]
    pool = feasible_rows or rows
    best = min(pool, key=lambda r: r.expected_total_cost_usd)
    best.recommended = True

    lo = best.week_index
    hi = min(lo + 1, len(_ENTRY_LABELS) - 1)
    lo_lbl = "Now" if lo == 0 else f"Week {lo + 1}"
    hi_lbl = f"Week {hi + 1}"
    best.note = (
        f"Forecast indicates the lowest expected freight around {lo_lbl}-{hi_lbl} "
        f"while still delivering within the {window}-day window."
        if best.delivery_feasible
        else f"No booking window fully meets the {window}-day deadline on this "
        f"lane; this is the lowest expected-cost option."
    )
    for r in rows:
        if not r.recommended and r.delivery_feasible:
            r.note = "Delivery-feasible; higher expected cost than the recommended window."
        elif not r.recommended:
            r.note = f"Estimated {r.estimated_delivery_lead_days:.0f}-day lead exceeds the deadline."
    return rows, best


def entry_week_range_label(best: EntryWindow) -> str:
    lo = best.week_index
    hi = min(lo + 1, len(_ENTRY_LABELS) - 1)
    lo_lbl = "Now" if lo == 0 else f"Week {lo + 1}"
    return f"{lo_lbl}–Week {hi + 1}"


# Backwards-compatible name kept for any external import.
__all__ = [
    "evaluate_vessels",
    "evaluate_entry_windows",
    "chosen_vessel",
    "entry_week_range_label",
    "port_call_cost",
    "voyages_required",
]
