"""Data access layer (SIH26006).

Responsibilities:
  * Load the SYNTHETIC / DEMONSTRATION CSV datasets in ``data/`` with pandas.
  * Expose the feasible trade lanes (``data/routes.csv``).
  * Provide small typed read helpers for the other services (ports, vessels,
    historical freight rates, congestion, market indicators, commodity prices).
  * Record every forecast request in a local SQLite database so the admin
    dashboard can show usage stats (created automatically on first run).

Every dataset here is SYNTHETIC / DEMONSTRATION DATA - NOT REAL MARKET DATA.
See README and the header comment in each CSV.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR / "freight_forecast.db"

_CSV = {
    "freight_rates": DATA_DIR / "freight_rates.csv",
    "bunker_prices": DATA_DIR / "bunker_prices.csv",
    "ports": DATA_DIR / "ports.csv",
    "vessels": DATA_DIR / "vessels.csv",
    "routes": DATA_DIR / "routes.csv",
    "congestion": DATA_DIR / "congestion.csv",
    "market_indicators": DATA_DIR / "market_indicators.csv",
    "commodity_prices": DATA_DIR / "commodity_prices.csv",
}


def _read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV if it exists, otherwise return an empty DataFrame."""
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, comment="#", skip_blank_lines=True)
    except Exception:  # pragma: no cover - defensive for malformed demo files
        return pd.DataFrame()


def _split_list(value: Any) -> list[str]:
    """Turn a ';'-separated cell into a clean list of strings."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [part.strip() for part in str(value).split(";") if part.strip()]


class DataService:
    """Thin wrapper around the demo CSV datasets and the request-log database."""

    def __init__(self) -> None:
        self.freight_rates = _read_csv(_CSV["freight_rates"])
        self.bunker_prices = _read_csv(_CSV["bunker_prices"])
        self.ports = _read_csv(_CSV["ports"])
        self.vessels = _read_csv(_CSV["vessels"])
        self.routes = _read_csv(_CSV["routes"])
        self.congestion = _read_csv(_CSV["congestion"])
        self.market_indicators = _read_csv(_CSV["market_indicators"])
        self.commodity_prices = _read_csv(_CSV["commodity_prices"])
        self._init_db()

    # ------------------------------------------------------------------
    # Trade lanes (routes.csv)
    # ------------------------------------------------------------------
    def feasible_routes(self) -> list[dict[str, Any]]:
        df = self.routes
        return [] if df.empty else df.to_dict(orient="records")

    def find_route(
        self, origin_country: str, cargo_type: str, destination_port: str
    ) -> Optional[dict[str, Any]]:
        """Return the matching lane, or ``None`` if the combination is not allowed."""
        df = self.routes
        if df.empty:
            return None
        mask = (
            (df["origin_country"].str.lower() == str(origin_country).lower())
            & (df["cargo_type"].str.lower() == str(cargo_type).lower())
            & (df["destination_port"].str.lower() == str(destination_port).lower())
        )
        match = df[mask]
        return None if match.empty else match.iloc[0].to_dict()

    def routes_for_origin_cargo(
        self, origin_country: str, cargo_type: str
    ) -> list[dict[str, Any]]:
        df = self.routes
        if df.empty:
            return []
        mask = (df["origin_country"].str.lower() == str(origin_country).lower()) & (
            df["cargo_type"].str.lower() == str(cargo_type).lower()
        )
        return df[mask].to_dict(orient="records")

    def origins_for_cargo(self, cargo_type: str) -> list[str]:
        df = self.routes
        if df.empty:
            return []
        sub = df[df["cargo_type"].str.lower() == str(cargo_type).lower()]
        return sorted({str(o) for o in sub["origin_country"].tolist()})

    def route_count(self) -> int:
        return 0 if self.routes.empty else int(self.routes.shape[0])

    # ------------------------------------------------------------------
    # Ports (ports.csv)
    # ------------------------------------------------------------------
    def port(self, port_name: str) -> Optional[dict[str, Any]]:
        df = self.ports
        if df.empty or not port_name:
            return None
        match = df[df["port_name"].str.lower() == str(port_name).lower()]
        if match.empty:
            return None
        row = match.iloc[0].to_dict()
        row["supported_commodities"] = _split_list(row.get("supported_commodities"))
        row["compatible_vessels"] = _split_list(row.get("compatible_vessels"))
        return row

    def load_ports_for_country(self, country: str) -> list[str]:
        df = self.ports
        if df.empty:
            return []
        mask = (df["country"].str.lower() == str(country).lower()) & (df["role"] == "load")
        return sorted(df[mask]["port_name"].astype(str).tolist())

    def discharge_ports(self) -> list[str]:
        df = self.ports
        if df.empty:
            return []
        return sorted(df[df["role"] == "discharge"]["port_name"].astype(str).tolist())

    # ------------------------------------------------------------------
    # Vessels (vessels.csv)
    # ------------------------------------------------------------------
    def vessels_list(self) -> list[dict[str, Any]]:
        df = self.vessels
        if df.empty:
            return []
        out = []
        for row in df.to_dict(orient="records"):
            row["typical_commodities"] = _split_list(row.get("typical_commodities"))
            out.append(row)
        return out

    def vessel(self, vessel_type: str) -> Optional[dict[str, Any]]:
        for row in self.vessels_list():
            if str(row.get("vessel_type", "")).lower() == str(vessel_type).lower():
                return row
        return None

    # ------------------------------------------------------------------
    # Historical freight rates (freight_rates.csv)
    # ------------------------------------------------------------------
    def historical_rates(self, route_id: str) -> list[tuple[str, float]]:
        """``[(week_start_iso, rate), ...]`` sorted by week for one lane."""
        df = self.freight_rates
        if df.empty or "route_id" not in df.columns:
            return []
        sub = df[df["route_id"] == route_id].sort_values("week_start")
        return [
            (str(r["week_start"]), float(r["freight_rate_usd_per_tonne"]))
            for _, r in sub.iterrows()
        ]

    # ------------------------------------------------------------------
    # Congestion (congestion.csv)
    # ------------------------------------------------------------------
    def congestion_for(self, port_name: str) -> dict[str, Any]:
        df = self.congestion
        default = {"port_name": port_name, "congestion_factor": 1.25, "avg_wait_days": 3.0,
                   "trend": "unknown", "data_class": "SYNTHETIC_DEMO"}
        if df.empty or not port_name:
            return default
        match = df[df["port_name"].str.lower() == str(port_name).lower()]
        return default if match.empty else match.iloc[0].to_dict()

    # ------------------------------------------------------------------
    # Market indicators / commodity prices (context only)
    # ------------------------------------------------------------------
    def latest_market_indicator(self) -> dict[str, Any]:
        df = self.market_indicators
        if df.empty:
            return {}
        return df.sort_values("week_start").iloc[-1].to_dict()

    def market_index_series(self) -> list[tuple[str, float]]:
        df = self.market_indicators
        if df.empty or "dry_bulk_index" not in df.columns:
            return []
        sub = df.sort_values("week_start")
        return [(str(r["week_start"]), float(r["dry_bulk_index"])) for _, r in sub.iterrows()]

    def latest_commodity_price(self, commodity: str) -> Optional[float]:
        df = self.commodity_prices
        if df.empty:
            return None
        sub = df[df["commodity"].str.lower() == str(commodity).lower()].sort_values("week_start")
        return None if sub.empty else float(sub.iloc[-1]["price_usd_per_tonne"])

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    def data_last_updated(self) -> Optional[str]:
        stamps = [p.stat().st_mtime for p in _CSV.values() if p.exists()]
        if not stamps:
            return None
        return datetime.fromtimestamp(max(stamps), tz=timezone.utc).isoformat()

    def dataset_summary(self) -> dict[str, int]:
        return {
            name: (0 if getattr(self, name).empty else int(getattr(self, name).shape[0]))
            for name in (
                "routes", "ports", "vessels", "freight_rates", "congestion",
                "market_indicators", "commodity_prices", "bunker_prices",
            )
        }

    # ------------------------------------------------------------------
    # Forecast request log (SQLite)
    # ------------------------------------------------------------------
    def _init_db(self) -> None:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS forecast_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    cargo_type TEXT,
                    quantity_tonnes REAL,
                    delivery_window_days INTEGER,
                    destination_port TEXT,
                    origin_region TEXT,
                    payload TEXT
                )
                """
            )
            conn.commit()

    def log_forecast_request(self, request: dict[str, Any]) -> None:
        """Persist one forecast request. Safe to call from a request handler."""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT INTO forecast_requests
                    (created_at, cargo_type, quantity_tonnes, delivery_window_days,
                     destination_port, origin_region, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    request.get("cargo_type"),
                    float(request.get("quantity_tonnes") or 0),
                    int(request.get("delivery_window_days") or 0),
                    request.get("destination_port"),
                    request.get("origin_country") or request.get("origin_region"),
                    json.dumps(request, default=str),
                ),
            )
            conn.commit()

    def forecast_request_count(self) -> int:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute("SELECT COUNT(*) FROM forecast_requests")
            return int(cur.fetchone()[0])

    def recent_forecast_requests(self, limit: int = 10) -> list[dict[str, Any]]:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                """
                SELECT id, created_at, cargo_type, quantity_tonnes,
                       delivery_window_days, destination_port, origin_region
                FROM forecast_requests
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),),
            )
            return [dict(row) for row in cur.fetchall()]


# Module-level singleton. Import this everywhere:
#     from services.data_service import data_service
data_service = DataService()
