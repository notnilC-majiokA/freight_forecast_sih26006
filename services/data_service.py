"""Data access layer (SIH26006).

Responsibilities:
  * Load the DEMO CSV datasets in ``data/`` with pandas.
  * Expose the feasible trade lanes (``data/routes.csv``) - which
    origin x cargo x destination x vessel combinations are allowed.
  * Provide small read helpers for the other services.
  * Record every forecast request in a local SQLite database so the admin
    dashboard can show usage stats (created automatically on first run).

Every dataset here is DEMO DATA - NOT REAL MARKET DATA. See README.
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

FREIGHT_RATES_CSV = DATA_DIR / "freight_rates.csv"
BUNKER_PRICES_CSV = DATA_DIR / "bunker_prices.csv"
PORTS_CSV = DATA_DIR / "ports.csv"
VESSELS_CSV = DATA_DIR / "vessels.csv"
ROUTES_CSV = DATA_DIR / "routes.csv"


def _read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV if it exists, otherwise return an empty DataFrame."""
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, comment="#", skip_blank_lines=True)
    except Exception:  # pragma: no cover - defensive for malformed demo files
        return pd.DataFrame()


class DataService:
    """Thin wrapper around the DEMO CSV datasets and the request-log database."""

    def __init__(self) -> None:
        self.freight_rates = _read_csv(FREIGHT_RATES_CSV)
        self.bunker_prices = _read_csv(BUNKER_PRICES_CSV)
        self.ports = _read_csv(PORTS_CSV)
        self.vessels = _read_csv(VESSELS_CSV)
        self.routes = _read_csv(ROUTES_CSV)
        self._init_db()

    # ------------------------------------------------------------------
    # Reference-data helpers
    # ------------------------------------------------------------------
    def load_ports(self) -> pd.DataFrame:
        return self.ports

    def load_vessels(self) -> pd.DataFrame:
        return self.vessels

    def load_routes(self) -> pd.DataFrame:
        return self.routes

    def destination_ports(self) -> list[str]:
        df = self.ports
        if df.empty or "role" not in df.columns:
            return []
        return sorted(df[df["role"] == "discharge"]["port_name"].astype(str).tolist())

    def vessel_capacity(self, vessel_type: str) -> Optional[int]:
        df = self.vessels
        if df.empty or "vessel_type" not in df.columns:
            return None
        match = df[df["vessel_type"].str.lower() == str(vessel_type).lower()]
        if match.empty or "capacity_tonnes" not in match.columns:
            return None
        return int(match.iloc[0]["capacity_tonnes"])

    # ------------------------------------------------------------------
    # Feasible trade lanes (routes.csv)
    # ------------------------------------------------------------------
    def feasible_routes(self) -> list[dict[str, Any]]:
        """All allowed trade lanes as a list of plain dicts."""
        df = self.routes
        if df.empty:
            return []
        return df.to_dict(orient="records")

    def find_route(
        self,
        origin_region: str,
        cargo_type: str,
        destination_port: str,
        vessel_type: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Return the matching lane, or ``None`` if the combination is not allowed."""
        df = self.routes
        if df.empty:
            return None
        mask = (
            (df["origin_region"].str.lower() == str(origin_region).lower())
            & (df["cargo_type"].str.lower() == str(cargo_type).lower())
            & (df["destination_port"].str.lower() == str(destination_port).lower())
        )
        if vessel_type is not None and "vessel_type" in df.columns:
            mask &= df["vessel_type"].str.lower() == str(vessel_type).lower()
        match = df[mask]
        return None if match.empty else match.iloc[0].to_dict()

    def routes_for_origin_cargo(
        self, origin_region: str, cargo_type: str
    ) -> list[dict[str, Any]]:
        df = self.routes
        if df.empty:
            return []
        mask = (df["origin_region"].str.lower() == str(origin_region).lower()) & (
            df["cargo_type"].str.lower() == str(cargo_type).lower()
        )
        return df[mask].to_dict(orient="records")

    def route_count(self) -> int:
        """Number of feasible trade lanes in the demo dataset."""
        if not self.routes.empty:
            return int(self.routes.shape[0])
        df = self.freight_rates
        if df.empty:
            return 0
        keys = [
            c
            for c in ("origin_region", "destination_port", "cargo_type", "vessel_type")
            if c in df.columns
        ]
        return int(df.drop_duplicates(subset=keys).shape[0]) if keys else 0

    def data_last_updated(self) -> Optional[str]:
        """ISO timestamp of the most recently modified dataset file."""
        files = [
            FREIGHT_RATES_CSV,
            BUNKER_PRICES_CSV,
            PORTS_CSV,
            VESSELS_CSV,
            ROUTES_CSV,
        ]
        stamps = [f.stat().st_mtime for f in files if f.exists()]
        if not stamps:
            return None
        return datetime.fromtimestamp(max(stamps), tz=timezone.utc).isoformat()

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
                    request.get("origin_region"),
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
