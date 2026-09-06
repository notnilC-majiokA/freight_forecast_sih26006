"""Pydantic schemas for the /forecast API (SIH26006).

Domain: overseas bulk raw-material imports (coking coal, iron ore, limestone)
to ports on the East Coast of India, for Indian steel plants / PSUs.

These models define the request the frontend sends and the response the
backend returns. In the current build every number is DEMO DATA - NOT REAL
MARKET DATA (see the ``disclaimer`` field on :class:`ForecastResponse`).
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import List

from pydantic import BaseModel, Field, field_validator


# --------------------------------------------------------------------------
# Enumerations - the allowed values in one place so the form, the API and the
# services all agree. Feasible *combinations* are defined by data/routes.csv,
# not by these enums (not every origin can supply every cargo).
# --------------------------------------------------------------------------
class CargoType(str, Enum):
    coking_coal = "Coking Coal"
    iron_ore = "Iron Ore"
    limestone = "Limestone"


class DeliveryWindow(int, Enum):
    """Days from today by which the cargo must arrive at the Indian port."""

    d30 = 30
    d45 = 45
    d60 = 60


class DestinationPort(str, Enum):
    """East Coast of India discharge ports. Add more East Coast ports here."""

    paradip = "Paradip"
    visakhapatnam = "Visakhapatnam"
    kolkata_haldia = "Kolkata/Haldia"


class OriginRegion(str, Enum):
    """Overseas bulk raw-material source regions."""

    australia = "Australia"
    brazil = "Brazil"
    south_africa = "South Africa"
    indonesia = "Indonesia"


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------
class ForecastRequest(BaseModel):
    """Payload accepted by ``POST /forecast`` - one procurement scenario."""

    cargo_type: CargoType = Field(..., description="Bulk raw material to import")
    quantity_tonnes: float = Field(
        ...,
        gt=0,
        le=5_000_000,
        description="Total cargo quantity to procure, in metric tonnes",
    )
    delivery_window_days: DeliveryWindow = Field(
        ..., description="Delivery deadline: days from today to arrival at the Indian port"
    )
    destination_port: DestinationPort = Field(
        ..., description="Discharge port on the East Coast of India"
    )
    origin_region: OriginRegion = Field(
        ..., description="Preferred overseas load region"
    )

    @field_validator("quantity_tonnes")
    @classmethod
    def _round_quantity(cls, value: float) -> float:
        return round(float(value), 3)

    model_config = {
        "json_schema_extra": {
            "example": {
                "cargo_type": "Coking Coal",
                "quantity_tonnes": 150000,
                "delivery_window_days": 45,
                "destination_port": "Paradip",
                "origin_region": "Australia",
            }
        }
    }


# --------------------------------------------------------------------------
# Response building blocks
# --------------------------------------------------------------------------
class ForecastPoint(BaseModel):
    """One weekly point on the freight-rate forecast curve (USD / tonne)."""

    week_index: int = Field(..., description="0-based week offset from today")
    week_start: date
    predicted_rate_usd_per_tonne: float
    lower_bound_usd_per_tonne: float
    upper_bound_usd_per_tonne: float


class Recommendation(BaseModel):
    """The recommended chartering strategy shown to the procurement user.

    This is the *lowest expected-cost feasible strategy*, not merely the week
    with the lowest predicted rate.
    """

    # Timing
    chartering_week_index: int
    chartering_week_start: date
    estimated_delivery_lead_days: float
    delivery_deadline_days: int
    within_delivery_window: bool

    # Route
    origin_region: str
    load_port: str
    destination_port: str

    # Vessel / voyages
    vessel_type: str
    vessel_capacity_tonnes: int
    number_of_voyages: int
    cargo_quantity_tonnes: float

    # Cost
    expected_freight_rate_usd_per_tonne: float
    total_expected_freight_cost_usd: float
    expected_savings_vs_booking_now_usd: float

    # Explanation
    confidence: str = Field(..., description="High / Medium / Low")
    confidence_score: float = Field(..., ge=0, le=1)
    justification: str
    feasibility_notes: List[str] = Field(default_factory=list)


class CostComparisonRow(BaseModel):
    label: str
    freight_rate_usd_per_tonne: float
    total_freight_cost_usd: float
    delta_vs_recommended_usd: float


class RouteInfo(BaseModel):
    route_id: str
    origin_region: str
    load_port: str
    destination_port: str
    cargo_type: str
    vessel_type: str
    vessel_capacity_tonnes: int
    approx_distance_nm: int
    estimated_transit_days: float
    feasible_combination: bool = True


class ForecastResponse(BaseModel):
    """Payload returned by ``POST /forecast`` and ``GET /api/last-forecast``."""

    disclaimer: str
    generated_at: datetime
    request: ForecastRequest
    horizon_weeks: int
    forecast: List[ForecastPoint]
    recommendation: Recommendation
    cost_comparison: List[CostComparisonRow]
    route_info: RouteInfo
