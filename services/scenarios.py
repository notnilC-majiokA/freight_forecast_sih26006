"""Scenario builder / orchestrator (SIH26006).

The one place that assembles a procurement "scenario" end to end. It resolves
the trade lane (enforcing that origin x cargo x destination is feasible per
``data/routes.csv``) and then runs every module in order:

    forecast (A) -> vessels (B) -> entry windows (A) -> port feasibility (C/D)
    -> contract strategies (E) -> idle (F) -> risk (G) -> recommendation

and returns the single :class:`ForecastResponse` the API and results page use.
"""
from __future__ import annotations

from datetime import datetime, timezone

from schemas.forecast_schema import ForecastRequest, ForecastResponse, RouteInfo
from services import contracts as contracts_mod
from services import idle as idle_mod
from services import port_feasibility
from services import risk as risk_mod
from services.data_service import data_service
from services.forecasting import generate_forecast
from services.optimizer import (
    chosen_vessel,
    evaluate_entry_windows,
    evaluate_vessels,
)
from services.recommendation import build_recommendation
from utils.helpers import DATA_TRANSPARENCY_NOTE, DEMO_DISCLAIMER


class InfeasibleRouteError(ValueError):
    """Raised when origin x cargo x destination is not an allowed lane."""


def _resolve_route(request: ForecastRequest) -> RouteInfo:
    lane = data_service.find_route(
        request.origin_country.value,
        request.cargo_type.value,
        request.destination_port.value,
    )
    if lane is None:
        _raise_lane_hint(request)

    return RouteInfo(
        route_id=str(lane.get("route_id", "DEMO")),
        origin_country=str(lane["origin_country"]),
        load_port=str(lane["load_port"]),
        destination_port=str(lane["destination_port"]),
        cargo_type=str(lane["cargo_type"]),
        approx_distance_nm=int(lane["approx_distance_nm"]),
        estimated_transit_days=float(lane["est_transit_days"]),
        reference_rate_usd_per_tonne=float(lane["reference_rate_usd_per_tonne"]),
        feasible_combination=True,
        data_class=str(lane.get("data_class", "SYNTHETIC_DEMO")),
    )


def _raise_lane_hint(request: ForecastRequest) -> None:
    cargo = request.cargo_type.value
    origin = request.origin_country.value
    dest = request.destination_port.value

    alt = data_service.routes_for_origin_cargo(origin, cargo)
    if alt:
        dests = sorted({str(a["destination_port"]) for a in alt})
        hint = f"{origin} can supply {cargo} to: {', '.join(dests)}."
    else:
        origins = data_service.origins_for_cargo(cargo)
        hint = (
            f"No demo lane carries {cargo} from {origin}. Demo origins for "
            f"{cargo}: {', '.join(origins) or 'none'}."
        )
    raise InfeasibleRouteError(
        f"'{origin} -> {dest}' is not a feasible lane for {cargo} in the demo "
        f"route dataset. " + hint
    )


def build_forecast_response(request: ForecastRequest) -> ForecastResponse:
    """Assemble a full DEMO scenario response for one procurement request."""
    route = _resolve_route(request)

    # A - forecast
    forecast = generate_forecast(request, route)

    # B - vessel optimisation (+ pick the best feasible / closest)
    vessel_options = evaluate_vessels(request, route, forecast)
    vessel = chosen_vessel(vessel_options)

    # C / D - port + vessel feasibility for the chosen class
    origin_row = data_service.port(route.load_port) or {"port_name": route.load_port}
    if request.origin_port:
        pref = data_service.port(request.origin_port)
        if pref and str(pref.get("country", "")).lower() == route.origin_country.lower() \
                and pref.get("role") == "load":
            origin_row = pref
    dest_row = data_service.port(route.destination_port) or {"port_name": route.destination_port}
    vrow = data_service.vessel(vessel.vessel_type) or {}
    feasibility = port_feasibility.assess(
        vrow, origin_row, dest_row, route,
        float(request.quantity_tonnes), int(request.delivery_window_days.value),
    )

    # A - entry windows
    entry_windows, recommended_entry = evaluate_entry_windows(
        request, route, forecast, vessel
    )

    # E - contract strategy comparison
    contract_rows = contracts_mod.compare_contracts(request, forecast, vessel)
    contract = contracts_mod.recommended_contract(contract_rows)

    # F - idle scenario
    idle = idle_mod.analyse_idle(request, route, vessel, contract)

    # G - risk
    risk = risk_mod.assess_risk(
        request, route, forecast, vessel, feasibility, recommended_entry, contract, idle
    )

    # Engine - final recommendation
    recommendation = build_recommendation(
        request, route, forecast, vessel, feasibility, recommended_entry,
        contract, idle, risk,
    )

    return ForecastResponse(
        disclaimer=DEMO_DISCLAIMER,
        data_transparency_note=DATA_TRANSPARENCY_NOTE,
        demo_mode=True,
        generated_at=datetime.now(timezone.utc),
        request=request,
        route_info=route,
        forecast=forecast,
        entry_windows=entry_windows,
        recommended_entry=recommended_entry,
        vessel_options=vessel_options,
        port_feasibility=feasibility,
        contract_strategies=contract_rows,
        idle_analysis=idle,
        risk_analysis=risk,
        recommendation=recommendation,
    )
