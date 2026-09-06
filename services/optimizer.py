"""Vessel chartering / bulk-procurement optimiser (SIH26006).

Given a forecast rate curve for a feasible trade lane, choose the
**lowest expected-cost feasible chartering strategy** for importing the
cargo to the East Coast of India within the delivery deadline.

STATUS: PLACEHOLDER  ------------------------------------------------------
The search here is a transparent brute-force over chartering weeks with
simple feasibility checks (delivery deadline, vessel capacity -> number of
voyages, port/vessel compatibility already encoded in data/routes.csv).
**No mathematical program is solved yet.**

TODO (SIH team - the actual project work):
  * Replace this with a mixed-integer program (``PuLP``) that optimises
    jointly over:
        - chartering week
        - overseas origin / load port
        - Indian destination port
        - vessel type and vessel capacity
        - number of voyages
        - cargo quantity split across voyages
    minimising expected total freight cost subject to:
        - delivery deadline (charter lead time + transit + laycan)
        - vessel capacity vs cargo quantity
        - port / vessel compatibility (draft limits)
        - laycan spacing / vessel availability
  * Fold in forecast uncertainty (robust or scenario-based objective).
  * Keep the same return contract as :func:`recommend_strategy` below.
------------------------------------------------------------------------
"""
from __future__ import annotations

from schemas.forecast_schema import (
    CostComparisonRow,
    ForecastPoint,
    ForecastRequest,
    Recommendation,
    RouteInfo,
)
from utils.helpers import voyages_required

# Demo-only cost adders so that "number of voyages" and timing actually
# influence the objective. Not real figures.
_DEMO_PORT_CALL_COST_USD_PER_VOYAGE = 60_000.0
# Extra calendar days on top of pure sea transit: loading laycan + berthing
# + discharge readiness. Demo constant.
_DEMO_LAYCAN_BUFFER_DAYS = 6.0
# Days between successive ship arrivals when several vessels are chartered for
# one parcel (they load/sail in parallel, not one after another). Demo constant.
_DEMO_VOYAGE_STAGGER_DAYS = 5.0

_CONFIDENCE_BANDS = ((0.75, "High"), (0.5, "Medium"), (0.0, "Low"))


def _confidence_from_spread(points: list[ForecastPoint]) -> tuple[str, float]:
    """Derive a rough confidence label from how wide the demo bands are."""
    if not points:
        return "Low", 0.4
    relative_widths = [
        (p.upper_bound_usd_per_tonne - p.lower_bound_usd_per_tonne)
        / p.predicted_rate_usd_per_tonne
        for p in points
        if p.predicted_rate_usd_per_tonne > 0
    ]
    avg_rel = sum(relative_widths) / len(relative_widths) if relative_widths else 0.5
    score = max(0.3, min(0.95, 1.0 - avg_rel * 3.0))
    for threshold, label in _CONFIDENCE_BANDS:
        if score >= threshold:
            return label, round(score, 2)
    return "Low", round(score, 2)


def _lead_days(week_index: int, route: RouteInfo, voyages: int) -> float:
    """Estimated days from today to full-cargo delivery for a given charter week.

    Assumes vessels for a multi-voyage parcel are chartered in parallel, so the
    last cargo arrives a few staggered days after the first (not a serial
    round-trip per voyage).
    """
    charter_offset = week_index * 7.0
    one_way = route.estimated_transit_days + _DEMO_LAYCAN_BUFFER_DAYS
    stagger = max(0, voyages - 1) * _DEMO_VOYAGE_STAGGER_DAYS
    return round(charter_offset + one_way + stagger, 1)


def _total_cost(rate_usd_per_tonne: float, quantity: float, voyages: int) -> float:
    return rate_usd_per_tonne * quantity + voyages * _DEMO_PORT_CALL_COST_USD_PER_VOYAGE


def recommend_strategy(
    request: ForecastRequest,
    forecast: list[ForecastPoint],
    route: RouteInfo,
) -> tuple[Recommendation, list[CostComparisonRow]]:
    """Return the lowest expected-cost feasible strategy + a comparison table."""
    if not forecast:
        raise ValueError("forecast series is empty - cannot build a recommendation")

    quantity = float(request.quantity_tonnes)
    deadline = int(request.delivery_window_days.value)
    capacity = int(route.vessel_capacity_tonnes) or 1
    voyages = voyages_required(quantity, capacity)

    # Score every candidate chartering week.
    candidates = []
    for point in forecast:
        lead = _lead_days(point.week_index, route, voyages)
        cost = _total_cost(point.predicted_rate_usd_per_tonne, quantity, voyages)
        candidates.append(
            {
                "point": point,
                "lead_days": lead,
                "within_window": lead <= deadline,
                "total_cost": cost,
            }
        )

    feasible = [c for c in candidates if c["within_window"]]
    pool = feasible if feasible else candidates
    best = min(pool, key=lambda c: c["total_cost"])

    # "Book now" baseline = charter in the first forecast week.
    book_now = candidates[0]
    savings_vs_now = round(book_now["total_cost"] - best["total_cost"], 2)

    label, score = _confidence_from_spread(forecast)

    # ---- Feasibility notes & human-readable justification ----
    notes: list[str] = []
    notes.append(
        f"Vessel/port compatibility: {route.vessel_type} accepted at "
        f"{route.destination_port} (encoded in routes.csv)."
    )
    notes.append(
        f"Cargo {quantity:,.0f} t / {route.vessel_type} capacity "
        f"{capacity:,} t -> {voyages} voyage(s)."
    )
    if feasible:
        notes.append(
            f"{len(feasible)} of {len(candidates)} chartering weeks deliver "
            f"within the {deadline}-day deadline."
        )
    else:
        notes.append(
            f"No chartering week meets the {deadline}-day deadline in this DEMO "
            f"scenario; showing the lowest expected-cost option instead."
        )

    point = best["point"]
    if feasible:
        justification = (
            f"Among {len(feasible)} feasible chartering week(s) for {request.cargo_type.value} "
            f"from {route.origin_region} ({route.load_port}) to {route.destination_port} "
            f"by {route.vessel_type}, week {point.week_index + 1} "
            f"({point.week_start.isoformat()}) has the lowest expected total freight "
            f"cost (${best['total_cost']:,.0f}) while still delivering in about "
            f"{best['lead_days']:.0f} days, within the {deadline}-day deadline, using "
            f"{voyages} voyage(s). Expected saving versus chartering now is "
            f"${max(savings_vs_now, 0):,.0f}."
        )
    else:
        justification = (
            f"No chartering week fully satisfies the {deadline}-day delivery deadline "
            f"for this lane in the DEMO data. Week {point.week_index + 1} "
            f"({point.week_start.isoformat()}) is the lowest expected-cost option "
            f"(${best['total_cost']:,.0f}, ~{best['lead_days']:.0f} days to delivery). "
            f"Consider a wider delivery window or a nearer origin such as Indonesia."
        )

    recommendation = Recommendation(
        chartering_week_index=point.week_index,
        chartering_week_start=point.week_start,
        estimated_delivery_lead_days=best["lead_days"],
        delivery_deadline_days=deadline,
        within_delivery_window=bool(best["within_window"]),
        origin_region=route.origin_region,
        load_port=route.load_port,
        destination_port=route.destination_port,
        vessel_type=route.vessel_type,
        vessel_capacity_tonnes=capacity,
        number_of_voyages=voyages,
        cargo_quantity_tonnes=round(quantity, 3),
        expected_freight_rate_usd_per_tonne=round(point.predicted_rate_usd_per_tonne, 2),
        total_expected_freight_cost_usd=round(best["total_cost"], 2),
        expected_savings_vs_booking_now_usd=round(max(savings_vs_now, 0.0), 2),
        confidence=label,
        confidence_score=score,
        justification=justification,
        feasibility_notes=notes,
    )

    # ---- Cost comparison table ----
    avg_rate = sum(p.predicted_rate_usd_per_tonne for p in forecast) / len(forecast)
    avg_cost = _total_cost(avg_rate, quantity, voyages)
    worst_pool = feasible if feasible else candidates
    worst = max(worst_pool, key=lambda c: c["total_cost"])

    comparison = [
        CostComparisonRow(
            label=f"Charter now - week 1 ({book_now['point'].week_start.isoformat()})",
            freight_rate_usd_per_tonne=round(book_now["point"].predicted_rate_usd_per_tonne, 2),
            total_freight_cost_usd=round(book_now["total_cost"], 2),
            delta_vs_recommended_usd=round(book_now["total_cost"] - best["total_cost"], 2),
        ),
        CostComparisonRow(
            label=(
                f"Recommended - week {point.week_index + 1} "
                f"({point.week_start.isoformat()})"
            ),
            freight_rate_usd_per_tonne=round(point.predicted_rate_usd_per_tonne, 2),
            total_freight_cost_usd=round(best["total_cost"], 2),
            delta_vs_recommended_usd=0.0,
        ),
        CostComparisonRow(
            label="Delivery-window average week",
            freight_rate_usd_per_tonne=round(avg_rate, 2),
            total_freight_cost_usd=round(avg_cost, 2),
            delta_vs_recommended_usd=round(avg_cost - best["total_cost"], 2),
        ),
        CostComparisonRow(
            label=(
                f"Most expensive {'feasible ' if feasible else ''}week - week "
                f"{worst['point'].week_index + 1}"
            ),
            freight_rate_usd_per_tonne=round(worst["point"].predicted_rate_usd_per_tonne, 2),
            total_freight_cost_usd=round(worst["total_cost"], 2),
            delta_vs_recommended_usd=round(worst["total_cost"] - best["total_cost"], 2),
        ),
    ]

    return recommendation, comparison
