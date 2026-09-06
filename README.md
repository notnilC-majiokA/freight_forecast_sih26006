# Intelligent Freight Forecasting & Vessel Chartering Decision Support System

**SIH 2026 &middot; Problem Statement SIH26006 &middot; Ministry of Steel**

**SIH26006 | Ministry of Steel | Smart India Hackathon 2026**

_India-centric decision support for overseas industrial bulk raw-material
procurement and vessel chartering to India's East Coast._

A decision-support tool for **Indian steel plants / PSUs** importing bulk raw
materials (coking coal, iron ore, limestone) from overseas to East Coast Indian
ports. For one procurement scenario it answers **what** to charter, **where**
from/to, **when** to enter the market, **how** to contract it, and **why** the
plan is optimal &mdash; identifying the **lowest expected-cost feasible
strategy**, not a guaranteed minimum future freight.

That is **not** the same as "lowest predicted freight rate" or "cheapest
vessel": the recommended plan must also satisfy the delivery deadline, vessel
capacity / number of voyages, and origin **and** destination port
infrastructure limits (LOA, beam, draft, cargo handling, commodity).

This is a domain-specific tool for one Ministry of Steel use case &mdash; not a
generic global shipping/logistics platform.

---

## Prototype capabilities (current build)

The `POST /forecast` API and the results dashboard walk a scenario through eight
modular stages (business logic lives in `services/`, not `main.py`):

| Stage | Module | What it does |
|-------|--------|--------------|
| A | `forecasting.py` | 8-week weekly freight-rate forecast with a confidence band, trend, volatility, heuristic confidence label and a one-step-holdout backtest MAPE. Blends a moving average with Holt's linear exponential smoothing over synthetic lane history. |
| A | `optimizer.py` (`evaluate_entry_windows`) | Market-entry timing &mdash; scores booking windows (Now, Week 2 … Week 6) on expected rate, expected total cost, $/tonne, forecast uncertainty, risk and delivery feasibility, and picks a recommended **entry window** (e.g. "Week 3–Week 4"). |
| B | `optimizer.py` (`evaluate_vessels`) | Vessel-type optimisation across Handysize / Supramax / Panamax / Capesize &mdash; capacity, voyages, utilisation, feasibility, turnaround, expected cost, operational risk. Recommends the **best _feasible_ vessel**, never an infeasible one. |
| C | `data/ports.csv` | Structured origin + destination port infrastructure (LOA, beam, draft, handling rate, supported commodities, compatible vessels, congestion, turnaround) &mdash; clearly labelled synthetic/demo. |
| D | `port_feasibility.py` | Dedicated FEASIBLE / INFEASIBLE engine checking both port ends + the delivery timeline, with explicit reasons on failure. |
| E | `contracts.py` | Repeated Spot vs Short-term MVC vs Medium-term MVC &mdash; each priced off the **same** forecast (MVC is not hard-coded cheaper); recommends the best expected cost/risk trade-off. |
| F | `idle.py` | Rule-based idle-scenario estimate: expected idle days, utilisation, repositioning/ballast exposure, idle-risk band and mitigation. |
| G | `risk.py` | Heuristic risk engine &mdash; market volatility, forecast uncertainty, origin/destination congestion, vessel/port compatibility, delivery pressure, idle exposure &rarr; overall LOW/MEDIUM/HIGH + actionable mitigation. |
| &mdash; | `recommendation.py` | Central engine combining all of the above into one "what should I do?" recommendation with a 5-point explanation. |

Exports (`/export-csv`, `/export-pdf`) carry the full decision: scenario,
forecast, entry window, vessel, voyages, contract strategy, expected
cost/savings, port feasibility, idle risk, market risk, forecast confidence and
the decision explanation.

**Not implemented:** interactive multi-scenario what-if analysis, a trained ML
forecasting model, and a formal (PuLP) mixed-integer optimiser &mdash; the
forecasting and optimisation code here demonstrate the **architecture** on
synthetic data.

### Data transparency

**The prototype uses synthetic/demo market and infrastructure data. Production
deployment would integrate validated historical, port and licensed market
data.** Every freight rate, port dimension, congestion figure and index level in
`data/` is fabricated (each CSV is headed `SYNTHETIC / DEMONSTRATION DATA`) and
every response carries this notice. Forecasts demonstrate the architecture, not
real market accuracy; risk and feasibility scores are **model-based heuristic
indicators, not statistically validated probabilities**. Do not use any output
for real procurement or chartering decisions.

**Scope (intentionally limited for campus screening; architecture is extensible)**

| Dimension        | Values                                                                          |
|------------------|--------------------------------------------------------------------------------|
| Commodities      | Coking Coal, Iron Ore, Limestone                                              |
| Origin countries | Australia, United States, Mozambique, Russia, Indonesia                      |
| East Coast ports | Paradip, Visakhapatnam, Gangavaram, Gopalpur, Dhamra, Sagar-Sandheads, Haldia |
| Vessel classes   | Handysize, Supramax, Panamax, Capesize                                       |
| Feasible lanes   | `data/routes.csv` (29 demo lanes) &mdash; not every origin supplies every cargo to every port |

Add a value to the relevant enum in `schemas/forecast_schema.py` + rows in
`data/` to widen scope without restructuring the app.

---

## Tech stack

| Layer      | Choice                                                        |
|------------|--------------------------------------------------------------|
| Backend    | Python 3.12, FastAPI, Uvicorn                               |
| Templating | Jinja2                                                      |
| Frontend   | HTML5, CSS3, Bootstrap 5, vanilla JavaScript (ES6+), Chart.js |
| Data       | pandas, numpy                                              |
| Forecasting | Moving average + Holt's linear exponential smoothing (numpy) |
| Reporting  | ReportLab (PDF), csv (CSV)                                  |
| Storage    | SQLite (request log, auto-created) + CSV datasets          |
| Planned    | scikit-learn / statsmodels (real forecasting), PuLP (formal optimiser), joblib (saved models in `models/`) &mdash; listed in `requirements.txt`, not yet imported |

Bootstrap and Chart.js are loaded from a CDN, so an internet connection is
needed the first time you open the pages.

---

## Project structure

```
freight_forecast_sih26006/
│
├── main.py                     # FastAPI app: routes, static mount, templates
├── requirements.txt
├── README.md
├── .gitignore
│
├── templates/                  # Jinja2 templates
│   ├── index.html              # scenario input form + decision-flow overview
│   ├── results.html            # 9-section decision dashboard + forecast chart
│   └── admin.html              # system-status + dataset row counts
│
├── static/
│   ├── css/style.css           # project theme + decision-dashboard components
│   ├── js/
│   │   ├── index.js            # populate selects from /api/options, POST /forecast
│   │   ├── results.js          # render all 9 sections + Chart.js forecast chart
│   │   └── admin.js            # fetch + render /api/admin/status
│   └── assets/                 # images / logos (empty for now)
│
├── render.yaml                 # Render deployment blueprint
│
├── data/                       # SYNTHETIC / DEMONSTRATION DATA - NOT REAL
│   ├── routes.csv              # feasible trade lanes (origin x cargo x destination)
│   ├── freight_rates.csv       # fabricated weekly rates per lane (forecast history)
│   ├── bunker_prices.csv       # fabricated bunker prices
│   ├── ports.csv               # origin + East Coast ports: LOA/beam/draft/handling/...
│   ├── vessels.csv             # vessel classes: capacity, LOA, beam, draft, load rates
│   ├── congestion.csv          # demo port-congestion factors + wait days
│   ├── market_indicators.csv   # demo BDI-style dry-bulk index + sub-indices
│   └── commodity_prices.csv    # demo delivered commodity price levels (context only)
│
├── models/                     # trained ML models will be saved here (planned)
│
├── services/
│   ├── data_service.py         # load all CSVs, lane lookup, port/vessel helpers, SQLite log
│   ├── forecasting.py          # Module A - 8-week forecast (MA + Holt), band, backtest
│   ├── optimizer.py            # Modules A/B - entry-window scoring + vessel optimisation
│   ├── port_feasibility.py     # Modules C/D - FEASIBLE/INFEASIBLE engine (both port ends)
│   ├── contracts.py            # Module E - Spot vs short/medium-term MVC comparison
│   ├── idle.py                 # Module F - idle-scenario estimate + mitigation
│   ├── risk.py                 # Module G - heuristic risk engine + mitigation
│   ├── recommendation.py       # central engine - the "what should I do?" answer
│   ├── scenarios.py            # orchestrates all modules -> ForecastResponse
│   └── report_generator.py     # CSV + PDF (ReportLab) exports of the full decision
│
├── schemas/
│   └── forecast_schema.py      # Pydantic request / response models (all modules)
│
└── utils/
    └── helpers.py              # pure helpers: seeding, dates, stats, forecasting math
```

---

## Setup

You need **Python 3.10 or newer**. Check with `python --version`.
If Python is not installed, get it from <https://www.python.org/downloads/>
(on Windows, tick *"Add python.exe to PATH"* in the installer).

### 1. Create and activate a virtual environment

**Windows (PowerShell):**
```powershell
cd path\to\freight_forecast_sih26006
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
If PowerShell blocks the activation script, run once:
`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

**macOS / Linux:**
```bash
cd path/to/freight_forecast_sih26006
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the application

```bash
uvicorn main:app --reload
```

Then open:

| Page            | URL                                |
|-----------------|------------------------------------|
| Dashboard       | http://127.0.0.1:8000/             |
| Last result     | http://127.0.0.1:8000/results      |
| Admin status    | http://127.0.0.1:8000/admin        |
| Health check    | http://127.0.0.1:8000/health       |
| Interactive API | http://127.0.0.1:8000/docs         |

---

## Sharing a temporary demo link

To let teammates or judges open your running dev server over the internet
without deploying, run it on all interfaces and put a tunnel in front of it:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
# in a second terminal:
cloudflared tunnel --url http://localhost:8000   # prints a temporary https://<...>.trycloudflare.com URL
```

No code changes are needed — the frontend uses relative API URLs. The link is
temporary, dies when you stop the tunnel or the server, and exposes an app with
**no authentication**, so only share it deliberately and stop the tunnel when
the demo is over. All figures remain labelled **DEMO DATA – NOT REAL MARKET
DATA**. Do not add a wide-open `CORSMiddleware`: the pages and API are served
from the same origin, so it is not needed.

---

## API

| Method | Path                   | Purpose                                            |
|--------|------------------------|---------------------------------------------------|
| GET    | `/`                    | Render `index.html`                               |
| GET    | `/results`             | Render `results.html`                             |
| GET    | `/admin`               | Render `admin.html`                               |
| GET    | `/health`              | `{"status": "ok"}`                                |
| GET    | `/api/options`         | Select values (commodities, origin countries, per-country load ports, destination ports, vessel + contract options, delivery windows) + feasible trade lanes |
| POST   | `/forecast`            | Validate scenario (Pydantic) → full DEMO decision JSON; `422` if the lane is not feasible |
| GET    | `/api/last-forecast`   | Most recent decision (used by the results page)   |
| GET    | `/api/admin/status`    | System-status JSON + dataset row counts           |
| GET    | `/export-csv`          | Last decision as CSV                              |
| GET    | `/export-pdf`          | Last decision as a ReportLab PDF                  |

### Example `POST /forecast` body

```json
{
  "cargo_type": "Coking Coal",
  "quantity_tonnes": 120000,
  "origin_country": "Australia",
  "origin_port": "Hay Point",
  "destination_port": "Paradip",
  "delivery_window_days": 45,
  "vessel_preference": "Optimize",
  "contract_preference": "Compare All"
}
```

`origin_port`, `vessel_preference` (`Optimize` or a class) and
`contract_preference` (`Compare All`, `Spot`, `Short-term MVC`,
`Medium-term MVC`) are optional. If `origin_country` × `cargo_type` ×
`destination_port` is not a lane in `data/routes.csv`, `/forecast` returns `422`
with a message listing the lanes that *do* exist. The response contains the
forecast, entry windows, vessel options, port feasibility, contract strategies,
idle analysis, risk analysis and the final recommendation.

The most recent decision is held **in memory** so `/results`, `/export-csv` and
`/export-pdf` have something to show. Restarting the server clears it. This is a
deliberate single-user demo simplification.

---

## What the student team builds next

1. **`services/forecasting.py`** – replace the MA + Holt baseline with a real
   trained model (statsmodels SARIMA and/or scikit-learn / gradient boosting),
   with genuine prediction intervals, saved to `models/` via joblib. Source real
   historical Indian import freight and bunker data first.
2. **`services/optimizer.py` / `contracts.py`** – replace the transparent scans
   with a PuLP mixed-integer program optimising jointly over entry week, origin,
   destination port, vessel type/capacity, number of voyages, cargo split and
   contract structure, subject to the delivery deadline, capacity and port
   draft/LOA/beam constraints.
3. Swap the `SYNTHETIC / DEMONSTRATION` CSVs in `data/` (rates, ports,
   congestion, indices) for validated, licensed, sourced datasets and document
   their provenance.
4. Calibrate the heuristic risk / idle scores against historical outcomes, or
   replace them with statistical models.
5. Add tests (`pytest`) for the schemas and each service module.

Not in scope yet (intentionally): authentication / login, a database admin UI,
multi-scenario what-if comparison, any extra web framework.
