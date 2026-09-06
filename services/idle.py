"""Idle scenario management (SIH26006) - Module F.

Answers: "what if this vessel finishes employment before the next cargo is
ready?" A transparent, rule-based estimate for the prototype - NOT a globally
connected real-time vessel-employment platform.

Drivers (all synthetic demo assumptions):
  * schedule slack between turnaround and the delivery deadline
  * number of voyages (more parcels -> more waiting between them)
  * congestion at both ports (idle time waiting for a berth)
  * contract type (a multi-voyage contract schedules the follow-on cargo;
    repeated spot leaves gaps)
"""
from __future__ import annotations

from schemas.forecast_schema import (
    ContractStrategy,
    ForecastRequest,
    IdleAnalysis,
    RouteInfo,
    VesselOption,
)
from services.data_service import data_service
from utils.helpers import clamp, risk_band

_CONTRACT_IDLE_FACTOR = {
    "Repeated Spot": 1.35,
    "Short-term MVC": 0.85,
    "Medium-term MVC": 0.65,
}


def analyse_idle(
    request: ForecastRequest,
    route: RouteInfo,
    vessel: VesselOption,
    contract: ContractStrategy,
) -> IdleAnalysis:
    window = int(request.delivery_window_days.value)
    voyages = vessel.voyages_required
    turnaround = vessel.estimated_turnaround_days
    slack = max(0.0, window - turnaround)

    o_cong = data_service.congestion_for(route.load_port)
    d_cong = data_service.congestion_for(route.destination_port)
    cong_wait = 0.5 * (float(o_cong.get("avg_wait_days", 3.0)) + float(d_cong.get("avg_wait_days", 3.0)))

    # Base idle: gaps between parcels + half the congestion wait, scaled by the
    # contract type, minus a little if there is generous schedule slack.
    base = (voyages - 1) * 2.2 + 0.5 * cong_wait
    base *= _CONTRACT_IDLE_FACTOR.get(contract.strategy, 1.0)
    if slack > 15:
        base *= 0.8
    expected_idle = round(clamp(base, 0.0, 45.0), 1)

    # Utilisation over the employment period (laden vs laden+idle).
    laden = max(turnaround, 1.0)
    util = round(100.0 * laden / (laden + expected_idle), 1)

    next_cargo = round(clamp(slack + 3.0, 3.0, 40.0), 1)
    distance = route.approx_distance_nm
    repositioning = expected_idle > 7 or contract.strategy == "Repeated Spot"
    ballast_nm = int(distance * (0.35 if repositioning else 0.12))

    score = (
        0.10
        + expected_idle / 22.0
        + (0.18 if repositioning else 0.0)
        + (0.12 if contract.strategy == "Repeated Spot" else 0.0)
        + clamp((cong_wait - 2.0) / 12.0, 0.0, 0.2)
    )
    score = clamp(score, 0.0, 1.0)
    idle_risk = risk_band(score)

    if idle_risk == "LOW":
        mitigation = (
            "Idle exposure is within normal limits - hold the planned charter "
            "commencement."
        )
    elif idle_risk == "MEDIUM":
        mitigation = (
            f"Delay charter commencement by ~1 week, or line up back-haul / "
            f"alternative employment near {route.destination_port} to absorb the "
            f"~{expected_idle:.0f} idle day(s)."
        )
    else:
        mitigation = (
            f"Stagger the {voyages} voyages under a multi-voyage contract and "
            f"secure follow-on employment before fixing; repositioning ballast "
            f"of ~{ballast_nm:,} nm would otherwise be unpaid."
        )

    alt = (
        f"Regional dry-bulk parcels ex East Coast India / Bay of Bengal, or a "
        f"ballast move toward {route.load_port} for the next lift."
    )

    return IdleAnalysis(
        vessel_type=vessel.vessel_type,
        expected_idle_days=expected_idle,
        utilization_pct=util,
        next_cargo_opportunity_days=next_cargo,
        repositioning_required=repositioning,
        ballast_exposure_nm=ballast_nm,
        alternative_employment=alt,
        idle_risk=idle_risk,
        mitigation=mitigation,
        note="Transparent rule-based estimate on synthetic data - not a live "
        "vessel-employment feed.",
    )
