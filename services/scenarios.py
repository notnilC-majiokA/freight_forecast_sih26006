"""Scenario builder (SIH26006).

Ties the (placeholder) forecasting and optimiser services together into the
single :class:`ForecastResponse` that the API returns and the results page
renders. This is the one place that knows how a procurement "scenario" is
assembled, and it enforces that the requested trade lane is feasible
(defined by ``data/routes.csv``).
"""
from __future__ import annotations

from datetime import datetime, timezone

from schemas.forecast_schema import ForecastRequest, ForecastResponse, RouteInfo
from services.data_service import data_service
from services.forecasting import generate_forecast, horizon_weeks_for
from services.optimizer import recommend_strategy
from utils.helpers import DEMO_DISCLAIMER


class InfeasibleRouteError(ValueError):
    """Raised when the requested origin x cargo x destination is not an allowed lane."""


# Fallbacks only used if routes.csv is missing/incomplete (keeps the demo alive).
_DEMO_FALLBACK = {
    "distance_nm": {
        "Indonesia": 3200,
        "Australia": 5100,
        "South Africa": 4300,
        "Brazil": 8600,
    },
    "load_port": {
        "Indonesia": "Samarinda",
        "Australia": "Hay Point",
        "South Africa": "Richards Bay",
        "Brazil": "Tubarao",
    },
    "vessel": {"Coking Coal": "Panamax", "Iron Ore": "Capesize", "Limestone": "Supramax"},
    "capacity": {"Panamax": 75000, "Capesize": 170000, "Supramax": 55000, "Handysize": 32000},
}
_DEMO_DESIGN_SPEED_KN = 12.5


def _route_info_from_lane(request: ForecastRequest, lane: dict) -> RouteInfo:
    return RouteInfo(
        route_id=str(lane.get("route_id", "DEMO")),
        origin_region=str(lane["origin_region"]),
        load_port=str(lane["load_port"]),
        destination_port=str(lane["destination_port"]),
        cargo_type=str(lane["cargo_type"]),
        vessel_type=str(lane["vessel_type"]),
        vessel_capacity_tonnes=int(lane["vessel_capacity_tonnes"]),
        approx_distance_nm=int(lane["approx_distance_nm"]),
        estimated_transit_days=float(lane["est_transit_days"]),
        feasible_combination=True,
    )


def _route_info_fallback(request: ForecastRequest) -> RouteInfo:
    region = request.origin_region.value
    cargo = request.cargo_type.value
    vessel = _DEMO_FALLBACK["vessel"].get(cargo, "Panamax")
    distance = _DEMO_FALLBACK["distance_nm"].get(region, 5000)
    return RouteInfo(
        route_id="DEMO-FALLBACK",
        origin_region=region,
        load_port=_DEMO_FALLBACK["load_port"].get(region, "TBD"),
        destination_port=request.destination_port.value,
        cargo_type=cargo,
        vessel_type=vessel,
        vessel_capacity_tonnes=int(_DEMO_FALLBACK["capacity"].get(vessel, 75000)),
        approx_distance_nm=distance,
        estimated_transit_days=round(distance / (_DEMO_DESIGN_SPEED_KN * 24), 1),
        feasible_combination=True,
    )


def _resolve_route(request: ForecastRequest) -> RouteInfo:
    lane = data_service.find_route(
        request.origin_region.value,
        request.cargo_type.value,
        request.destination_port.value,
    )
    if lane is not None:
        return _route_info_from_lane(request, lane)

    # No matching lane. If routes.csv is present, this combination is simply
    # not allowed - tell the user which lanes DO exist for their choice.
    if not data_service.routes.empty:
        alt = data_service.routes_for_origin_cargo(
            request.origin_region.value, request.cargo_type.value
        )
        if alt:
            dests = sorted({str(a["destination_port"]) for a in alt})
            hint = (
                f"{request.origin_region.value} can supply {request.cargo_type.value} "
                f"to: {', '.join(dests)}."
            )
        else:
            same_cargo = data_service.routes[
                data_service.routes["cargo_type"].str.lower()
                == request.cargo_type.value.lower()
            ]
            origins = sorted({str(o) for o in same_cargo["origin_region"].tolist()})
            hint = (
                f"No demo lane carries {request.cargo_type.value} from "
                f"{request.origin_region.value}. Demo origins for "
                f"{request.cargo_type.value}: {', '.join(origins) or 'none'}."
            )
        raise InfeasibleRouteError(
            f"'{request.origin_region.value} -> {request.destination_port.value}' is not "
            f"a feasible lane for {request.cargo_type.value} in the demo route dataset. "
            + hint
        )

    # routes.csv missing entirely - keep the demo usable.
    return _route_info_fallback(request)


def build_forecast_response(request: ForecastRequest) -> ForecastResponse:
    """Assemble a full DEMO scenario response for one procurement request."""
    route_info = _resolve_route(request)
    forecast = generate_forecast(request)
    recommendation, cost_comparison = recommend_strategy(request, forecast, route_info)

    return ForecastResponse(
        disclaimer=DEMO_DISCLAIMER,
        generated_at=datetime.now(timezone.utc),
        request=request,
        horizon_weeks=horizon_weeks_for(int(request.delivery_window_days.value)),
        forecast=forecast,
        recommendation=recommendation,
        cost_comparison=cost_comparison,
        route_info=route_info,
    )
