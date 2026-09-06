# Intelligent Freight Forecasting & Vessel Chartering Decision Support System

**SIH 2026 &middot; Problem Statement SIH26006 &middot; Ministry of Steel**

**SIH26006 | Ministry of Steel | Smart India Hackathon 2026**

_AI-assisted decision support for overseas bulk raw-material procurement and
vessel chartering to India's East Coast._

A decision-support tool for **Indian steel plants / PSUs** importing bulk raw
materials (coking coal, iron ore, limestone) from overseas to East Coast Indian
ports. For a procurement scenario it searches:

```
Overseas Origin x Cargo Type x East Coast Indian Port x Vessel Type x Chartering Week
        -> lowest expected-cost feasible strategy
```

That is **not** the same as "lowest predicted freight rate": the recommended
strategy must also satisfy the delivery deadline, vessel capacity / number of
voyages, and port/vessel compatibility.

This is a domain-specific tool for one Ministry of Steel use case &mdash; not a
generic global shipping/logistics platform.

---

## Prototype capabilities (current build)

- **Freight-rate forecasting** &mdash; weekly USD/tonne curve with lower/upper
  bounds across the delivery horizon _(placeholder model &mdash; synthetic
  series, not a real forecast)_.
- **Vessel feasibility check** &mdash; cargo quantity vs vessel-class capacity
  &rarr; number of voyages; origin &times; cargo &times; port &times; vessel
  compatibility enforced from `data/routes.csv`.
- **Expected-cost calculation** &mdash; total expected freight cost
  (rate &times; quantity + per-voyage port-call cost) for every candidate
  chartering week.
- **Charter-strategy comparison** &mdash; charter-now vs recommended vs
  delivery-window-average vs most-expensive week.
- **Book-now vs wait analysis** &mdash; expected saving from chartering in the
  recommended week instead of now.
- **Recommendation** &mdash; lowest expected-cost _feasible_ strategy (timing,
  route, vessel, voyages) with a plain-language justification and a
  Low/Medium/High confidence label.
- **Exports** &mdash; download the recommendation and forecast curve as CSV or
  as a PDF (ReportLab).

Not implemented yet: interactive what-if scenario analysis, a trained ML
forecasting model, and the PuLP optimisation model (see
[What the student team builds next](#what-the-student-team-builds-next)).

**Current prototype uses synthetic/demo data where real licensed market data is
unavailable.** All figures are labelled `DEMO DATA - NOT REAL MARKET DATA` in the
UI, the API, the exports and the CSV files. The synthetic freight rates are
**not** real-world market data and must not be used for actual procurement or
chartering decisions.

**Scope of the demo dataset**

| Dimension        | Demo values                                                    |
|------------------|---------------------------------------------------------------|
| Cargo            | Coking Coal, Iron Ore, Limestone                             |
| East Coast ports | Paradip, Visakhapatnam, Kolkata/Haldia (add more later)      |
| Overseas origins | Australia, Brazil, South Africa, Indonesia                   |
| Feasible lanes   | `data/routes.csv` &mdash; not every origin supplies every cargo |

---

## Current status: architecture prototype (DEMO data only)

> **The ML forecasting model and the optimisation model are NOT built yet.**
>
> This repository currently contains the full application skeleton: FastAPI
> backend, Jinja2 + Bootstrap frontend, service modules, Pydantic schemas and
> export (PDF / CSV) plumbing.
>
> - `services/forecasting.py` and `services/optimizer.py` are **clean
>   placeholders** with `TODO` notes describing the real work. The optimiser
>   already does a transparent brute-force feasibility search (deadline,
>   capacity -> voyages, port/vessel compatibility); the real version will be a
>   PuLP mixed-integer program.
> - Every number the app returns is **synthetic**, labelled
>   `DEMO DATA - NOT REAL MARKET DATA` in the UI, the API responses, the PDF/CSV
>   exports and the CSV files.
> - **No real freight-rate data is included.** The CSVs in `data/` are
>   fabricated placeholders so the UI has something to render. Do not use them
>   for analysis, model training, benchmarking, or any real decision.

---

## Tech stack

| Layer      | Choice                                                        |
|------------|--------------------------------------------------------------|
| Backend    | Python 3.10+, FastAPI, Uvicorn                              |
| Templating | Jinja2                                                      |
| Frontend   | HTML5, CSS3, Bootstrap 5, vanilla JavaScript (ES6+), Chart.js |
| Data / ML  | pandas, numpy, scikit-learn, statsmodels (planned)         |
| Optimiser  | PuLP (planned)                                             |
| Reporting  | ReportLab (PDF), csv (CSV)                                  |
| Storage    | SQLite (request log, auto-created) + CSV datasets          |
| ML models  | joblib (planned, saved to `models/`)                       |

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
│   ├── index.html              # dashboard + scenario input form
│   ├── results.html            # forecast + recommendation + charts + export
│   └── admin.html              # system-status dashboard
│
├── static/
│   ├── css/style.css           # project theme on top of Bootstrap
│   ├── js/
│   │   ├── index.js            # form validation, POST /forecast, redirect
│   │   ├── results.js          # render results, draw Chart.js chart
│   │   └── admin.js            # fetch + render /api/admin/status
│   └── assets/                 # images / logos (empty for now)
│
├── data/                       # DEMO DATA - NOT REAL MARKET DATA
│   ├── routes.csv              # feasible trade lanes (origin x cargo x port x vessel)
│   ├── freight_rates.csv       # fabricated weekly rates per lane
│   ├── bunker_prices.csv
│   ├── ports.csv               # East Coast discharge ports + overseas load ports
│   └── vessels.csv             # vessel classes + capacity + draft
│
├── models/                     # trained ML models will be saved here
│
├── services/
│   ├── data_service.py         # load CSVs, feasible-lane lookup, SQLite log
│   ├── forecasting.py          # PLACEHOLDER - demo weekly rate series
│   ├── optimizer.py            # PLACEHOLDER - lowest expected-cost feasible strategy
│   ├── scenarios.py            # resolves the lane, assembles ForecastResponse
│   └── report_generator.py     # CSV + PDF (ReportLab) exports
│
├── schemas/
│   └── forecast_schema.py      # Pydantic request / response models
│
└── utils/
    └── helpers.py              # small pure helpers (seeding, dates, format)
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
| GET    | `/api/options`         | Dropdown values + feasible trade lanes (routes.csv) |
| POST   | `/forecast`            | Validate scenario (Pydantic) → DEMO strategy JSON; `422` if the lane is not feasible |
| GET    | `/api/last-forecast`   | Most recent recommendation (used by the results page) |
| GET    | `/api/admin/status`    | System-status JSON for the admin dashboard        |
| GET    | `/export-csv`          | Last recommendation as CSV                        |
| GET    | `/export-pdf`          | Last recommendation as a ReportLab PDF            |

### Example `POST /forecast` body

```json
{
  "cargo_type": "Coking Coal",
  "quantity_tonnes": 150000,
  "delivery_window_days": 45,
  "destination_port": "Paradip",
  "origin_region": "Australia"
}
```

If the requested `origin_region` x `cargo_type` x `destination_port` is not a
lane in `data/routes.csv`, `/forecast` returns `422` with a message listing the
lanes that *do* exist for that choice.

The most recent recommendation is held **in memory** so `/results`,
`/export-csv` and `/export-pdf` have something to show. Restarting the server
clears it. This is a deliberate single-user demo simplification.

---

## What the student team builds next

1. **`services/forecasting.py`** – replace the demo series with a real trained
   model (statsmodels SARIMAX and/or scikit-learn regressors), with genuine
   prediction intervals, saved to `models/` via joblib. Source real historical
   Indian import freight and bunker data first.
2. **`services/optimizer.py`** – replace the brute-force feasibility search with
   a PuLP mixed-integer program optimising jointly over chartering week,
   overseas origin, Indian destination port, vessel type/capacity, number of
   voyages and cargo split, minimising expected total freight cost subject to
   the delivery deadline, capacity and port/vessel draft constraints.
3. Swap the `DEMO DATA` CSVs in `data/` (including `routes.csv`) for validated,
   sourced datasets and document their provenance.
4. Add tests (`pytest`) for the schemas and services.

Not in scope yet (intentionally): authentication / login, a database admin UI,
any extra web framework.
