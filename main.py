"""FastAPI entry point for the SIH26006 decision-support prototype.

    Intelligent Freight Forecasting & Vessel Chartering Decision Support System
    SIH26006 | Ministry of Steel | Smart India Hackathon 2026

AI-assisted decision support for overseas bulk raw-material procurement and
vessel chartering to India's East Coast.

Run locally with:

    uvicorn main:app --reload

Then open http://127.0.0.1:8000/ in a browser.

NOTE: every number this app returns today is DEMO DATA - NOT REAL MARKET DATA,
produced by placeholder services. See services/forecasting.py and
services/optimizer.py for the real work that still has to be done.
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
    DestinationPort,
    ForecastRequest,
    ForecastResponse,
    OriginRegion,
)
from services.data_service import data_service
from services.report_generator import forecast_to_csv, forecast_to_pdf
from services.scenarios import InfeasibleRouteError, build_forecast_response

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="Intelligent Freight Forecasting & Vessel Chartering DSS",
    description=(
        "SIH26006 | Ministry of Steel | Smart India Hackathon 2026. "
        "Decision support for overseas bulk raw-material procurement and vessel "
        "chartering to India's East Coast. Prototype - DEMO data only."
    ),
    version="0.2.0",
)

# Serve CSS / JS / images from /static, and load Jinja2 templates.
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# In-memory store of the most recent forecast. This is a single-user demo
# convenience so /results, /export-csv and /export-pdf have data to show.
# Replace with per-session or database storage later.
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
    """Dropdown values + the feasible trade lanes (from data/routes.csv)."""
    return {
        "demo_mode": True,
        "cargo_types": [c.value for c in CargoType],
        "origin_regions": [o.value for o in OriginRegion],
        "destination_ports": [d.value for d in DestinationPort],
        "feasible_lanes": data_service.feasible_routes(),
        "note": "DEMO DATA - NOT REAL MARKET DATA",
    }


@app.post("/forecast", response_model=ForecastResponse)
async def forecast(payload: ForecastRequest):
    """Validate the scenario and return the DEMO lowest expected-cost strategy."""
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
        "data_last_updated": data_service.data_last_updated(),
        "route_count": data_service.route_count(),
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
        headers={"Content-Disposition": "attachment; filename=sih26006_chartering_strategy_demo.csv"},
    )


@app.get("/export-pdf")
async def export_pdf():
    response = _LAST_FORECAST["response"]
    if response is None:
        return JSONResponse(status_code=404, content={"detail": "No forecast to export yet."})
    return Response(
        content=forecast_to_pdf(response),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=sih26006_chartering_strategy_demo.pdf"},
    )
