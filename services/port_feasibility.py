"""Port / vessel feasibility engine (SIH26006) - Modules C & D.

A dedicated module (not logic buried in main.py) that decides whether a given
vessel class can actually serve a lane, checking infrastructure constraints at
BOTH ends plus the delivery-deadline timeline:

    origin (load) port    -> LOA, beam, draft, commodity, vessel-class, handling
    destination (discharge)-> LOA, beam, draft, commodity, vessel-class, handling
    timeline              -> voyages, loading, sea transit, discharge, waiting,
                             laycan buffer -> turnaround vs delivery deadline

Returns a structured FEASIBLE / INFEASIBLE verdict with explicit reasons.

All port particulars are SYNTHETIC / DEMONSTRATION DATA (see data/ports.csv).
"""
from __future__ import annotations

import math
from typing import Any

from schemas.forecast_schema import (
    FeasibilityCheck,
    PortFeasibilityCheck,
    PortFeasibilityResult,
    RouteInfo,
)
from services.data_service import data_service

LAYCAN_BUFFER_DAYS = 5.0          # fixture / laycan / berthing readiness
VOYAGE_STAGGER_DAYS = 3.0         # gap between successive parcels for a multi-voyage lift
DRAFT_SAFETY_MARGIN_M = 0.3       # under-keel / tidal allowance applied to the demo check


def _num(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return default


def _port_checks(
    port: dict[str, Any], role: str, vessel: dict[str, Any], cargo: str
) -> PortFeasibilityCheck:
    loa_ok = _num(vessel, "loa_m") <= _num(port, "max_loa_m")
    beam_ok = _num(vessel, "beam_m") <= _num(port, "max_beam_m")
    draft_ok = _num(vessel, "laden_draft_m") + DRAFT_SAFETY_MARGIN_M <= _num(port, "max_draft_m")
    commodity_ok = cargo in (port.get("supported_commodities") or [])
    vclass_ok = vessel.get("vessel_type") in (port.get("compatible_vessels") or [])
    handling_ok = _num(port, "cargo_handling_rate_tpd") > 0

    checks = [
        FeasibilityCheck(
            parameter="Length overall (LOA)",
            required=f"<= {_num(port, 'max_loa_m'):.0f} m",
            available=f"{_num(vessel, 'loa_m'):.0f} m",
            passed=loa_ok,
        ),
        FeasibilityCheck(
            parameter="Beam",
            required=f"<= {_num(port, 'max_beam_m'):.1f} m",
            available=f"{_num(vessel, 'beam_m'):.1f} m",
            passed=beam_ok,
        ),
        FeasibilityCheck(
            parameter="Laden draft",
            required=f"<= {_num(port, 'max_draft_m'):.1f} m (incl. {DRAFT_SAFETY_MARGIN_M:.1f} m margin)",
            available=f"{_num(vessel, 'laden_draft_m'):.1f} m",
            passed=draft_ok,
        ),
        FeasibilityCheck(
            parameter="Commodity handled",
            required=cargo,
            available=", ".join(port.get("supported_commodities") or []) or "-",
            passed=commodity_ok,
        ),
        FeasibilityCheck(
            parameter="Vessel class accepted",
            required=str(vessel.get("vessel_type")),
            available=", ".join(port.get("compatible_vessels") or []) or "-",
            passed=vclass_ok,
        ),
        FeasibilityCheck(
            parameter="Cargo handling",
            required="> 0 t/day",
            available=f"{_num(port, 'cargo_handling_rate_tpd'):,.0f} t/day",
            passed=handling_ok,
        ),
    ]
    reasons = [
        f"{port.get('port_name')} ({role}): {c.parameter} constraint exceeded "
        f"(needs {c.required}, vessel is {c.available})."
        for c in checks
        if not c.passed
    ]
    verdict = "FEASIBLE" if all(c.passed for c in checks) else "INFEASIBLE"
    return PortFeasibilityCheck(
        port_name=str(port.get("port_name")), role=role, checks=checks,
        verdict=verdict, reasons=reasons,
    )


def _in_port_days(parcel_tonnes: float, vessel_rate_tpd: float, port_rate_tpd: float,
                  congestion_factor: float, wait_days: float) -> float:
    rate = min(r for r in (vessel_rate_tpd, port_rate_tpd) if r > 0)
    working = parcel_tonnes / rate if rate else 0.0
    return round(working * max(congestion_factor, 1.0) + wait_days, 2)


def assess(
    vessel: dict[str, Any],
    origin_port: dict[str, Any],
    dest_port: dict[str, Any],
    route: RouteInfo,
    quantity_tonnes: float,
    delivery_window_days: int,
) -> PortFeasibilityResult:
    """Full FEASIBLE / INFEASIBLE assessment for one vessel class on one lane."""
    cargo = route.cargo_type
    capacity = int(_num(vessel, "capacity_tonnes", 1)) or 1
    voyages = max(1, math.ceil(quantity_tonnes / capacity))
    parcel = quantity_tonnes / voyages

    origin_chk = _port_checks(origin_port, "load", vessel, cargo)
    dest_chk = _port_checks(dest_port, "discharge", vessel, cargo)

    o_cong = data_service.congestion_for(str(origin_port.get("port_name")))
    d_cong = data_service.congestion_for(str(dest_port.get("port_name")))

    loading_days = _in_port_days(
        parcel, _num(vessel, "load_rate_tpd"), _num(origin_port, "cargo_handling_rate_tpd"),
        float(o_cong.get("congestion_factor", 1.25)), float(o_cong.get("avg_wait_days", 3.0)),
    )
    discharge_days = _in_port_days(
        parcel, _num(vessel, "discharge_rate_tpd"), _num(dest_port, "cargo_handling_rate_tpd"),
        float(d_cong.get("congestion_factor", 1.25)), float(d_cong.get("avg_wait_days", 3.0)),
    )

    # Parallel multi-vessel lift: one parcel's timeline + a stagger for the rest.
    stagger = VOYAGE_STAGGER_DAYS * (voyages - 1)
    turnaround = round(
        LAYCAN_BUFFER_DAYS + loading_days + route.estimated_transit_days
        + discharge_days + stagger,
        1,
    )
    delivery_feasible = turnaround <= delivery_window_days

    reasons: list[str] = []
    reasons.extend(origin_chk.reasons)
    reasons.extend(dest_chk.reasons)
    if not delivery_feasible:
        reasons.append(
            f"Delivery deadline: estimated {turnaround:.0f}-day turnaround for "
            f"{voyages} voyage(s) exceeds the {delivery_window_days}-day window."
        )

    ports_ok = origin_chk.verdict == "FEASIBLE" and dest_chk.verdict == "FEASIBLE"
    overall = "FEASIBLE" if (ports_ok and delivery_feasible) else "INFEASIBLE"
    if overall == "FEASIBLE":
        reasons = [
            f"{origin_port.get('port_name')} accepts {vessel.get('vessel_type')} "
            f"(draft/LOA/beam/commodity all within limits).",
            f"{dest_port.get('port_name')} accepts {vessel.get('vessel_type')} "
            f"(draft/LOA/beam/commodity all within limits).",
            f"{voyages} voyage(s); ~{turnaround:.0f}-day turnaround fits the "
            f"{delivery_window_days}-day delivery window.",
        ]

    return PortFeasibilityResult(
        vessel_type=str(vessel.get("vessel_type")),
        origin=origin_chk,
        destination=dest_chk,
        cargo_capacity_tonnes=capacity,
        number_of_voyages=voyages,
        loading_days=loading_days,
        discharge_days=discharge_days,
        turnaround_days=turnaround,
        delivery_deadline_days=int(delivery_window_days),
        delivery_feasible=delivery_feasible,
        overall=overall,
        reasons=reasons,
    )
