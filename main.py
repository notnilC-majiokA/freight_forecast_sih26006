"""FastAPI entry point for the SIH26006 decision-support prototype.

    Intelligent Freight Forecasting & Vessel Chartering Decision Support System
    SIH26006 | Ministry of Steel | Smart India Hackathon 2026

India-centric decision support for overseas industrial bulk raw-material
procurement and vessel chartering to the East Coast of India.

Run locally with:

    uvicorn main:app --reload

Deployed with:

    uvicorn main:app --host 0.0.0.0 --port $PORT

NOTE: every number this app returns is SYNTHETIC / DEMONSTRATION DATA - NOT REAL
MARKET DATA. Forecasts demonstrate the architecture, not market accuracy; risk
and feasibility scores are model-based heuristic indicators. The business logic
lives in services/ (forecasting, port_feasibility, optimizer, contracts, idle,
risk, recommendation, scenarios) - not in this file.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from schemas.forecast_schema import (
    CargoType,
    ContractPreference,
    DeliveryWindow,
    DestinationPort,
    ForecastRequest,
    ForecastResponse,
    OriginCountry,
    VesselPreference,
    VesselType,
)
from services.data_service import data_service
from services.report_generator import forecast_to_csv, forecast_to_pdf
from services.scenarios import InfeasibleRouteError, build_forecast_response
from utils.helpers import DATA_TRANSPARENCY_NOTE

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Intelligent Freight Forecasting & Vessel Chartering DSS",
    description=(
        "SIH26006 | Ministry of Steel | Smart India Hackathon 2026. "
        "Decision support for overseas industrial bulk raw-material procurement "
        "and vessel chartering to India's East Coast. Prototype - SYNTHETIC / "
        "DEMONSTRATION data only."
    ),
    version="0.3.0",
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# In-memory store of the most recent forecast. Single-user demo convenience so
# /results, /export-csv and /export-pdf have data to show. Replace with
# per-session or database storage later.
_LAST_FORECAST: dict[str, Optional[ForecastResponse]] = {"response": None}


# --------------------------------------------------------------------------
# HTML pages
# --------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/results", response_class=HTMLResponse)
async def results(request: Request):
    return templates.TemplateResponse("results.html", {"request": request})


@app.get("/admin", response_class=HTMLResponse)
async def admin(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/options")
async def options():
    """Dropdown values, per-country load ports, and the feasible trade lanes."""
    origin_ports = {
        c.value: data_service.load_ports_for_country(c.value) for c in OriginCountry
    }
    return {
        "demo_mode": True,
        "data_transparency_note": DATA_TRANSPARENCY_NOTE,
        "commodities": [c.value for c in CargoType],
        "origin_countries": [o.value for o in OriginCountry],
        "origin_ports_by_country": origin_ports,
        "destination_ports": [d.value for d in DestinationPort],
        "vessel_types": [v.value for v in VesselType],
        "vessel_preferences": [v.value for v in VesselPreference],
        "contract_preferences": [c.value for c in ContractPreference],
        "delivery_windows": [int(d.value) for d in DeliveryWindow],
        "feasible_lanes": data_service.feasible_routes(),
        "note": "SYNTHETIC / DEMONSTRATION DATA - NOT REAL MARKET DATA",
    }


@app.post("/forecast", response_model=ForecastResponse)
async def forecast(payload: ForecastRequest):
    """Validate the scenario and return the full DEMO decision-support response."""
    try:
        response = build_forecast_response(payload)
    except InfeasibleRouteError as exc:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    _LAST_FORECAST["response"] = response
    try:
        data_service.log_forecast_request(payload.model_dump(mode="json"))
    except Exception:  # request logging must never break the API response
        pass
    return response


@app.get("/api/last-forecast", response_model=ForecastResponse)
async def last_forecast():
    """Return the most recently generated forecast (used by the results page)."""
    response = _LAST_FORECAST["response"]
    if response is None:
        return JSONResponse(
            status_code=404,
            content={"detail": "No forecast generated yet. Submit the scenario on the home page."},
        )
    return response


@app.get("/api/admin/status")
async def admin_status():
    """System-status payload for the admin dashboard."""
    return {
        "demo_mode": True,
        "data_transparency_note": DATA_TRANSPARENCY_NOTE,
        "data_last_updated": data_service.data_last_updated(),
        "route_count": data_service.route_count(),
        "dataset_summary": data_service.dataset_summary(),
        "forecast_request_count": data_service.forecast_request_count(),
        "recent_forecast_requests": data_service.recent_forecast_requests(10),
    }


# --------------------------------------------------------------------------
# Exports
# --------------------------------------------------------------------------
@app.get("/export-csv")
async def export_csv():
    response = _LAST_FORECAST["response"]
    if response is None:
        return JSONResponse(status_code=404, content={"detail": "No forecast to export yet."})
    return Response(
        content=forecast_to_csv(response),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sih26006_chartering_decision_demo.csv"},
    )


@app.get("/export-pdf")
async def export_pdf():
    response = _LAST_FORECAST["response"]
    if response is None:
        return JSONResponse(status_code=404, content={"detail": "No forecast to export yet."})
    return Response(
        content=forecast_to_pdf(response),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=sih26006_chartering_decision_demo.pdf"},
    )
