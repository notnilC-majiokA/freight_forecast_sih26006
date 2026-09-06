"""Pydantic schemas for the /forecast API (SIH26006).

Domain: overseas industrial bulk raw-material imports (coking coal, iron ore,
limestone) to ports on the East Coast of India, for Indian steel plants / PSUs.

These models define the request the frontend sends and the (structured)
response the backend returns. In the current build every number is
SYNTHETIC / DEMONSTRATION DATA - NOT REAL MARKET DATA (see the ``disclaimer``
and ``data_transparency_note`` fields on :class:`ForecastResponse`).

Response shape (all produced by services/ modules, not main.py):

    ForecastResponse
      route_info            - resolved trade lane
      forecast             - ForecastSeries (history + forecast + CI + meta)   [Module A]
      entry_windows        - list[EntryWindow] + recommended_entry             [Module A]
      vessel_options       - list[VesselOption] ("BEST feasible" flagged)      [Module B]
      port_feasibility     - PortFeasibilityResult for the chosen vessel       [Modules C/D]
      contract_strategies  - list[ContractStrategy] (Spot / ST-MVC / MT-MVC)   [Module E]
      idle_analysis        - IdleAnalysis                                      [Module F]
      risk_analysis        - RiskAnalysis                                      [Module G]
      recommendation       - FinalRecommendation (the "what should I do?")     [Engine]
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# --------------------------------------------------------------------------
# Enumerations - the allowed values in one place so the form, the API and the
# services all agree. Feasible *combinations* are defined by data/routes.csv,
# not by these enums (not every origin can supply every cargo to every port).
# The lists are intentionally small for the campus-screening demo; the
# architecture is extensible - add a value here + rows in data/ to grow scope.
# --------------------------------------------------------------------------
class CargoType(str, Enum):
    coking_coal = "Coking Coal"
    iron_ore = "Iron Ore"
    limestone = "Limestone"


class OriginCountry(str, Enum):
    australia = "Australia"
    united_states = "United States"
    mozambique = "Mozambique"
    russia = "Russia"
    indonesia = "Indonesia"


class DestinationPort(str, Enum):
    """East Coast of India discharge ports (per the SIH26006 statement)."""

    paradip = "Paradip"
    visakhapatnam = "Visakhapatnam"
    gangavaram = "Gangavaram"
    gopalpur = "Gopalpur"
    dhamra = "Dhamra"
    sagar_sandheads = "Sagar-Sandheads"
    haldia = "Haldia"


class VesselType(str, Enum):
    handysize = "Handysize"
    supramax = "Supramax"
    panamax = "Panamax"
    capesize = "Capesize"


class VesselPreference(str, Enum):
    """A specific class, or let the optimiser pick the best feasible one."""

    handysize = "Handysize"
    supramax = "Supramax"
    panamax = "Panamax"
    capesize = "Capesize"
    optimize = "Optimize"


class ContractPreference(str, Enum):
    spot = "Spot"
    short_term_mvc = "Short-term MVC"
    medium_term_mvc = "Medium-term MVC"
    compare_all = "Compare All"


class DeliveryWindow(int, Enum):
    """Days from today by which the cargo must arrive at the Indian port."""

    d30 = 30
    d45 = 45
    d60 = 60


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------
class ForecastRequest(BaseModel):
    """Payload accepted by ``POST /forecast`` - one procurement scenario."""

    cargo_type: CargoType = Field(..., description="Bulk raw material to import")
    quantity_tonnes: float = Field(
        ..., gt=0, le=5_000_000,
        description="Total cargo quantity to procure, in metric tonnes",
    )
    origin_country: OriginCountry = Field(..., description="Overseas source country")
    origin_port: Optional[str] = Field(
        default=None,
        description="Optional preferred load port. If omitted or not served, the "
        "lane's default load port is used.",
    )
    destination_port: DestinationPort = Field(
        ..., description="Discharge port on the East Coast of India"
    )
    delivery_window_days: DeliveryWindow = Field(
        ..., description="Delivery deadline: days from today to arrival at the Indian port"
    )
    vessel_preference: VesselPreference = Field(
        default=VesselPreference.optimize,
        description="Force a vessel class, or 'Optimize' to evaluate all feasible classes",
    )
    contract_preference: ContractPreference = Field(
        default=ContractPreference.compare_all,
        description="Which chartering contract strategy to recommend (or compare all)",
    )

    @field_validator("quantity_tonnes")
    @classmethod
    def _round_quantity(cls, value: float) -> float:
        return round(float(value), 3)

    @field_validator("origin_port")
    @classmethod
    def _clean_port(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None

    model_config = {
        "json_schema_extra": {
            "example": {
                "cargo_type": "Coking Coal",
                "quantity_tonnes": 120000,
                "origin_country": "Australia",
                "origin_port": "Hay Point",
                "destination_port": "Paradip",
                "delivery_window_days": 45,
                "vessel_preference": "Optimize",
                "contract_preference": "Compare All",
            }
        }
    }


# --------------------------------------------------------------------------
# Trade lane
# --------------------------------------------------------------------------
class RouteInfo(BaseModel):
    route_id: str
    origin_country: str
    load_port: str
    destination_port: str
    cargo_type: str
    approx_distance_nm: int
    estimated_transit_days: float
    reference_rate_usd_per_tonne: float
    feasible_combination: bool = True
    data_class: str = "SYNTHETIC_DEMO"


# --------------------------------------------------------------------------
# Module A - freight forecast
# --------------------------------------------------------------------------
class HistoricalPoint(BaseModel):
    week_start: date
    rate_usd_per_tonne: float


class ForecastPoint(BaseModel):
    """One weekly point on the freight-rate forecast curve (USD / tonne)."""

    week_index: int = Field(..., description="1-based week offset from the first forecast week")
    week_start: date
    predicted_rate_usd_per_tonne: float
    lower_bound_usd_per_tonne: float
    upper_bound_usd_per_tonne: float
    uncertainty_pct: float = Field(..., description="Half CI width as a % of the point forecast")


class ForecastSeries(BaseModel):
    method: str = Field(..., description="Forecasting approach used for this lane")
    horizon_weeks: int
    history_weeks: int
    historical: List[HistoricalPoint]
    forecast: List[ForecastPoint]
    trend: str = Field(..., description="rising / easing / broadly flat")
    trend_usd_per_week: float
    volatility_pct: float = Field(..., description="Std dev of history as a % of its mean")
    confidence: str = Field(..., description="HIGH / MEDIUM / LOW - heuristic")
    confidence_score: float = Field(..., ge=0, le=1)
    backtest_mape_pct: Optional[float] = Field(
        default=None, description="One-step holdout MAPE on the synthetic history, if computable"
    )
    note: str


class EntryWindow(BaseModel):
    """One candidate market-entry (booking) window - Module A output."""

    label: str
    week_index: int = Field(..., description="0 = now, 1 = week 2, ...")
    week_start: date
    expected_rate_usd_per_tonne: float
    expected_total_cost_usd: float
    cost_per_tonne_usd: float
    forecast_uncertainty_pct: float
    risk_level: str = Field(..., description="LOW / MEDIUM / HIGH - heuristic")
    delivery_feasible: bool
    estimated_delivery_lead_days: float
    recommended: bool
    note: str


# --------------------------------------------------------------------------
# Modules C / D - port + vessel feasibility
# --------------------------------------------------------------------------
class FeasibilityCheck(BaseModel):
    parameter: str
    required: str
    available: str
    passed: bool


class PortFeasibilityCheck(BaseModel):
    port_name: str
    role: str = Field(..., description="load / discharge")
    checks: List[FeasibilityCheck]
    verdict: str = Field(..., description="FEASIBLE / INFEASIBLE")
    reasons: List[str]


class PortFeasibilityResult(BaseModel):
    vessel_type: str
    origin: PortFeasibilityCheck
    destination: PortFeasibilityCheck
    cargo_capacity_tonnes: int
    number_of_voyages: int
    loading_days: float
    discharge_days: float
    turnaround_days: float
    delivery_deadline_days: int
    delivery_feasible: bool
    overall: str = Field(..., description="FEASIBLE / INFEASIBLE")
    reasons: List[str]


# --------------------------------------------------------------------------
# Module B - vessel type optimisation
# --------------------------------------------------------------------------
class VesselOption(BaseModel):
    vessel_type: str
    capacity_tonnes: int
    loa_m: float
    beam_m: float
    laden_draft_m: float
    voyages_required: int
    cargo_per_voyage_tonnes: float
    utilization_pct: float
    origin_port_feasible: bool
    destination_port_feasible: bool
    port_feasibility: str = Field(..., description="FEASIBLE / INFEASIBLE")
    infeasibility_reasons: List[str]
    estimated_turnaround_days: float
    delivery_feasible: bool
    expected_freight_rate_usd_per_tonne: float
    expected_total_cost_usd: float
    operational_risk: str = Field(..., description="LOW / MEDIUM / HIGH - heuristic")
    recommended: bool
    verdict: str = Field(..., description="BEST / Feasible / Infeasible")


# --------------------------------------------------------------------------
# Module E - multiple-voyage contract strategy
# --------------------------------------------------------------------------
class ContractStrategy(BaseModel):
    strategy: str = Field(..., description="Repeated Spot / Short-term MVC / Medium-term MVC")
    contract_duration: str
    vessel_type: str
    number_of_voyages: int
    cargo_per_voyage_tonnes: float
    total_cargo_tonnes: float
    expected_freight_rate_usd_per_tonne: float
    expected_total_cost_usd: float
    expected_utilization_pct: float
    delivery_feasible: bool
    risk_level: str = Field(..., description="LOW / MEDIUM / HIGH - heuristic")
    savings_vs_spot_usd: float
    savings_vs_spot_pct: float
    operational_implications: str
    recommended: bool


# --------------------------------------------------------------------------
# Module F - idle scenario management
# --------------------------------------------------------------------------
class IdleAnalysis(BaseModel):
    vessel_type: str
    expected_idle_days: float
    utilization_pct: float
    next_cargo_opportunity_days: float
    repositioning_required: bool
    ballast_exposure_nm: int
    alternative_employment: str
    idle_risk: str = Field(..., description="LOW / MEDIUM / HIGH - heuristic")
    mitigation: str
    note: str


# --------------------------------------------------------------------------
# Module G - risk mitigation
# --------------------------------------------------------------------------
class RiskComponent(BaseModel):
    name: str
    level: str = Field(..., description="LOW / MEDIUM / HIGH - heuristic")
    score: float = Field(..., ge=0, le=1)
    rationale: str


class RiskAnalysis(BaseModel):
    overall_risk: str = Field(..., description="LOW / MEDIUM / HIGH - heuristic")
    overall_score: float = Field(..., ge=0, le=1)
    components: List[RiskComponent]
    mitigation: List[str]
    note: str = Field(
        default="Model-based / heuristic risk indicators - NOT statistically "
        "validated probabilities."
    )


# --------------------------------------------------------------------------
# Central recommendation engine
# --------------------------------------------------------------------------
class FinalRecommendation(BaseModel):
    headline: str
    contract_strategy: str
    entry_window_label: str
    entry_week_range: str
    origin_country: str
    origin_port: str
    destination_port: str
    cargo_type: str
    vessel_type: str
    number_of_voyages: int
    expected_freight_rate_usd_per_tonne: float
    expected_total_cost_usd: float
    expected_savings_vs_spot_usd: float
    expected_savings_vs_spot_pct: float
    delivery_feasible: bool
    port_feasibility: str = Field(..., description="FEASIBLE / INFEASIBLE")
    idle_risk: str
    market_risk: str
    forecast_confidence: str
    reasons: List[str]


# --------------------------------------------------------------------------
# Top-level response
# --------------------------------------------------------------------------
class ForecastResponse(BaseModel):
    """Payload returned by ``POST /forecast`` and ``GET /api/last-forecast``."""

    disclaimer: str
    data_transparency_note: str
    demo_mode: bool = True
    generated_at: datetime
    request: ForecastRequest
    route_info: RouteInfo
    forecast: ForecastSeries
    entry_windows: List[EntryWindow]
    recommended_entry: EntryWindow
    vessel_options: List[VesselOption]
    port_feasibility: PortFeasibilityResult
    contract_strategies: List[ContractStrategy]
    idle_analysis: IdleAnalysis
    risk_analysis: RiskAnalysis
    recommendation: FinalRecommendation
