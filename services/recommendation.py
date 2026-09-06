"""Central recommendation engine (SIH26006).

Combines every module's output into the single "what should I do?" answer:
forecast + entry timing + vessel optimisation + port feasibility + contract
strategy + delivery deadline + idle risk + market risk.

All figures are SYNTHETIC / DEMONSTRATION DATA.
"""
from __future__ import annotations

from schemas.forecast_schema import (
    ContractStrategy,
    EntryWindow,
    FinalRecommendation,
    ForecastRequest,
    ForecastSeries,
    IdleAnalysis,
    PortFeasibilityResult,
    RiskAnalysis,
    RouteInfo,
    VesselOption,
)
from services.optimizer import entry_week_range_label


def build_recommendation(
    request: ForecastRequest,
    route: RouteInfo,
    forecast: ForecastSeries,
    vessel: VesselOption,
    feasibility: PortFeasibilityResult,
    entry: EntryWindow,
    contract: ContractStrategy,
    idle: IdleAnalysis,
    risk: RiskAnalysis,
) -> FinalRecommendation:
    week_range = entry_week_range_label(entry)
    feasible = vessel.port_feasibility == "FEASIBLE" and vessel.delivery_feasible

    if feasible:
        headline = (
            f"{contract.strategy}: {route.origin_country} -> {route.destination_port}, "
            f"{route.cargo_type}, {vessel.vessel_type}, {vessel.voyages_required} voyage(s); "
            f"enter market {week_range}."
        )
    else:
        headline = (
            f"No fully feasible plan on {route.origin_country} -> "
            f"{route.destination_port} for {route.cargo_type} within "
            f"{request.delivery_window_days.value} days - review the flags below."
        )

    reasons: list[str] = []
    # 1 - timing
    reasons.append(
        f"Forecast ({forecast.method.split(';')[0].strip()}) shows a {forecast.trend} "
        f"market; lowest expected freight is around {week_range} at about "
        f"${entry.expected_rate_usd_per_tonne:,.1f}/t."
    )
    # 2 - vessel feasibility
    if feasible:
        reasons.append(
            f"{vessel.vessel_type} satisfies origin and destination infrastructure "
            f"limits (LOA/beam/draft/commodity) and is the lowest expected-cost "
            f"feasible class at {vessel.utilization_pct:.0f}% utilisation."
        )
    else:
        reasons.append(
            f"{vessel.vessel_type} is the closest option but is flagged "
            f"{vessel.port_feasibility}: "
            + ("; ".join(vessel.infeasibility_reasons[:2]) or "see feasibility section")
            + "."
        )
    # 3 - delivery
    reasons.append(
        f"Estimated {feasibility.turnaround_days:.0f}-day turnaround for "
        f"{feasibility.number_of_voyages} voyage(s) "
        + ("fits" if feasibility.delivery_feasible else "does NOT fit")
        + f" the {feasibility.delivery_deadline_days}-day delivery window."
    )
    # 4 - contract
    if contract.strategy == "Repeated Spot":
        reasons.append(
            "Repeated spot is preferred here: the forecast does not justify a "
            "fixture premium for a multi-voyage contract."
        )
    else:
        reasons.append(
            f"{contract.strategy} reduces repeated spot-market exposure for an "
            f"expected saving of {contract.savings_vs_spot_pct:.1f}% "
            f"(~${contract.savings_vs_spot_usd:,.0f}) vs re-fixing every voyage."
        )
    # 5 - idle / risk
    reasons.append(
        f"Idle exposure is {idle.idle_risk} (~{idle.expected_idle_days:.0f} day(s)); "
        f"overall market risk is {risk.overall_risk}. {risk.mitigation[0]}"
    )

    return FinalRecommendation(
        headline=headline,
        contract_strategy=contract.strategy,
        entry_window_label=entry.label,
        entry_week_range=week_range,
        origin_country=route.origin_country,
        origin_port=route.load_port,
        destination_port=route.destination_port,
        cargo_type=route.cargo_type,
        vessel_type=vessel.vessel_type,
        number_of_voyages=vessel.voyages_required,
        expected_freight_rate_usd_per_tonne=contract.expected_freight_rate_usd_per_tonne,
        expected_total_cost_usd=contract.expected_total_cost_usd,
        expected_savings_vs_spot_usd=contract.savings_vs_spot_usd,
        expected_savings_vs_spot_pct=contract.savings_vs_spot_pct,
        delivery_feasible=feasibility.delivery_feasible,
        port_feasibility=feasibility.overall,
        idle_risk=idle.idle_risk,
        market_risk=risk.overall_risk,
        forecast_confidence=forecast.confidence,
        reasons=reasons,
    )
