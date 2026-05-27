# FreshOps Analytics — Developer Guide

KTP prototype for lean waste and efficiency analytics in a fresh produce packing operation.
Built in collaboration between **Anglia Ruskin University (ARU)** and **Wealmoor Ltd**.

---

## Project files

| File | Purpose |
|---|---|
| `generate_data.py` | Creates `freshops.db` — 90-day simulation of packing operations with a lean intervention at day 45 |
| `lean_analysis.py` | Python query layer — seven functions that return `pd.DataFrame` results from `freshops.db` |
| `sql_queries.sql` | Eight standalone SQL queries for ad-hoc analysis and Power BI import |
| `dashboard.py` | Plotly Dash app — five-tab interactive dashboard served at `http://localhost:8050` |
| `freshops.db` | SQLite database produced by `generate_data.py` — do not commit to version control |
| `requirements.txt` | Python dependencies: `dash`, `plotly`, `pandas`, `numpy` |

### Running the project

```bash
cd freshops-analytics
pip install -r requirements.txt
python3 generate_data.py    # creates freshops.db
python3 lean_analysis.py    # prints full analysis summary
python3 dashboard.py        # starts Dash app at http://127.0.0.1:8050
```

---

## Database schema

All tables live in `freshops.db` (SQLite). The simulation covers 2024-01-01 to 2024-03-30 (90 days).
The lean intervention is modelled at **day 45 (2024-02-15)** — OEE components, on-time delivery, and waste
event frequency all improve gradually from that date.

### `products`
Eight subtropical/tropical items packed at the facility.

| Column | Type | Notes |
|---|---|---|
| `product_id` | INTEGER PK | 1–8 |
| `name` | TEXT | Mango, Avocado, Aubergine, Papaya, Passion Fruit, Sweet Potato, Okra, Plantain |
| `species` | TEXT | Latin binomial |
| `category` | TEXT | Tropical / Subtropical / Mediterranean |
| `price_per_kg` | REAL | GBP — used to cost waste events |
| `avg_weight_kg` | REAL | Per unit — used to convert units lost to kg |

### `waste_categories`
The seven TIMWOOD lean waste types.

| Column | Type | Notes |
|---|---|---|
| `category_id` | INTEGER PK | 1–7 |
| `name` | TEXT | Transport, Inventory, Motion, Waiting, Overproduction, Overprocessing, Defects |
| `description` | TEXT | Plain-English definition in packing context |

### `production_runs`
One row per shift per line per day — 810 rows total (3 lines × 3 shifts × 90 days).

| Column | Type | Notes |
|---|---|---|
| `run_id` | INTEGER PK | |
| `run_date` | TEXT | ISO 8601 |
| `line` | TEXT | Line 1 / Line 2 / Line 3 |
| `shift` | TEXT | Morning / Afternoon / Night |
| `product_id` | INTEGER FK | |
| `planned_units` | INTEGER | Customer-demand-driven target |
| `actual_units` | INTEGER | `planned × performance × (run_time / planned_duration)` |
| `good_units` | INTEGER | `actual × quality` |
| `cycle_time_seconds` | REAL | Target seconds per unit — `(planned_duration × 60) / planned_units` |
| `planned_duration_mins` | INTEGER | Always 480 (8-hour shift) |
| `run_time_mins` | REAL | `planned_duration × availability` |
| `availability` | REAL | 0–1, improves post day 45 |
| `performance` | REAL | 0–1, improves post day 45 |
| `quality` | REAL | 0–1, improves post day 45 |
| `oee` | REAL | `availability × performance × quality` |

Pre-intervention OEE baseline ≈ 56.6%. Post-intervention average ≈ 67.9%.

### `waste_events`
Waste incidents linked to production runs — 1,859 rows across 90 days.

| Column | Type | Notes |
|---|---|---|
| `event_id` | INTEGER PK | |
| `event_date` | TEXT | ISO 8601 |
| `run_id` | INTEGER FK | Links to `production_runs` |
| `product_id` | INTEGER FK | |
| `category_id` | INTEGER FK | TIMWOOD category |
| `units_lost` | INTEGER | |
| `weight_lost_kg` | REAL | `units_lost × avg_weight_kg` |
| `cost_gbp` | REAL | `weight_lost_kg × price_per_kg` |
| `root_cause` | TEXT | Free-text root cause string (26 distinct causes) |

Defect events (category 7) are always generated — they account for 66.5% of total waste cost (£132k/90d).

### `transport_logs`
Inbound delivery records — 264 rows (2–4 deliveries per day).

| Column | Type | Notes |
|---|---|---|
| `log_id` | INTEGER PK | |
| `log_date` | TEXT | ISO 8601 |
| `product_id` | INTEGER FK | |
| `origin` | TEXT | Kenya, South Africa, Spain, Peru, Dominican Republic, Ghana, Jamaica |
| `supplier` | TEXT | Named supplier within origin |
| `units_received` | INTEGER | |
| `weight_kg` | REAL | |
| `lead_time_days` | INTEGER | Pre-intervention avg 4.8d → post avg 3.8d |
| `on_time` | INTEGER | 0 or 1 — pre 72.2%, post 84.7% |
| `co2_kg_per_kg_product` | REAL | Air freight (Kenya, Ghana) ≈ 3.1, sea (South Africa) ≈ 1.85, road (Spain) ≈ 0.42 |
| `total_co2_kg` | REAL | `weight_kg × co2_kg_per_kg_product` |
| `cost_gbp` | REAL | Inbound landed cost |

---

## lean_analysis.py — API reference

All functions accept a `sqlite3.Connection` and return a `pd.DataFrame`.
Open a connection with the `_connect()` context manager:

```python
import lean_analysis

with lean_analysis._connect() as conn:
    df = lean_analysis.weekly_oee(conn)
```

| Function | Returns | Key columns |
|---|---|---|
| `weekly_oee(conn)` | 13 rows | `week`, `availability_pct`, `performance_pct`, `quality_pct`, `oee_pct` |
| `throughput_by_product(conn)` | 8 rows | `product`, `planned_units`, `good_units`, `yield_pct`, `defect_rate_pct` |
| `waste_pareto(conn)` | 7 rows | `category`, `cost_gbp`, `cost_pct`, `cumulative_pct` |
| `weekly_waste_cost(conn)` | 13 rows | `week`, `waste_cost_gbp`, `events` |
| `root_cause_frequency(conn)` | 30 rows | `root_cause`, `timwood_category`, `frequency`, `total_cost_gbp` |
| `vsm_metrics(conn)` | 6 rows | `metric`, `value`, `description` — takt time, cycle time, CO₂ intensity, etc. |
| `before_after_comparison(conn)` | Transposed DF | Index = metric names, columns = `Before` / `After` / `Δ (After − Before)` |

---

## Dashboard tabs

The Dash app (`dashboard.py`) pre-loads all data at startup and renders static figures — no callbacks required.
All figures use the green/teal palette (`P` dict at the top of the file).

### Tab 1 — OEE & Production
- **Weekly OEE line chart**: four traces (Availability, Performance, Quality, OEE composite) with pre/post
  shading and a world-class 85% reference line. Intervention marker at week 6.5.
- **Throughput stacked bar**: good units vs defect/loss units per product, sorted ascending. Yield % annotated.

### Tab 2 — Waste & TIMWOOD
- **Pareto bar + cumulative line** (dual y-axis): waste cost by TIMWOOD category with 80% threshold.
- **Weekly waste cost area chart**: total waste spend per week with intervention marker.
- **Root cause horizontal bar**: top 15 by cost, coloured by TIMWOOD category, frequency count labelled.

### Tab 3 — Value Stream Map
- **6-stage SVG flow** (Plotly shapes + annotations): Inbound Transport → Goods Receiving →
  Grading & QC Incoming → Packing Lines → Despatch & QC → Outbound Delivery.
  Each stage shows the key metric, before→after values, and a ▲/▼ percentage-change arrow
  in green (improvement) or red (regression). Push arrows connect stages.
- **VSM metrics table**: takt time, actual cycle time, transport lead time, value-add ratio, process quality, CO₂ intensity.

### Tab 4 — Transport & CO₂
- **On-time delivery bar**: per origin, RAG coloured (green ≥ 80%, amber ≥ 70%, red < 70%), 85% target line.
- **Lead time bar with error bars**: average ± min/max range per origin.
- **CO₂ dual-axis chart**: total CO₂ (bars) and intensity kg/kg (diamond markers) per origin.

### Tab 5 — Lean Scorecard
- **Six indicator tiles** (`go.Indicator`): OEE, Yield, On-Time, Lead Time, Waste Cost, Waste Events —
  each showing post-intervention value with delta vs pre-intervention baseline.
- **Grouped before/after bar**: six % KPIs side-by-side.
- **Waste cost delta bar**: change in waste cost per TIMWOOD category (After − Before), green if reduction.

---

## Lean methods used

### OEE (Overall Equipment Effectiveness)
Calculated as `Availability × Performance × Quality`:
- **Availability** = `run_time_mins / planned_duration_mins` — downtime, changeovers, waiting.
- **Performance** = `actual_units / (planned_units × availability)` — speed losses, minor stops.
- **Quality** = `good_units / actual_units` — defects, rework, rejects.

World-class benchmark is 85%. Pre-intervention baseline in this simulation is ~56.6%, rising to ~67.9%
post-intervention — consistent with a first lean programme on a mid-maturity packing line.

### TIMWOOD (7 Wastes)
Each waste event is classified against one of the seven lean waste types:

| Code | Waste | Packing-line manifestation |
|---|---|---|
| T | Transport | Double-handling at intake bay, poor routing from cold store to line |
| I | Inventory | FIFO not followed, overstock of slow-moving SKUs |
| M | Motion | Long walks for packaging materials, no shadow boards at stations |
| W | Waiting | Changeover delays, waiting for QC sign-off, label stock outages |
| O | Overproduction | Packing to forecast when order is subsequently cut |
| O | Overprocessing | Redundant inspection steps, manual recount after auto-weigh |
| D | Defects | Bruising on belt, temperature excursions, seal failures, mislabels |

Defects dominate (66.5% of waste cost) in the simulation — consistent with fresh produce where quality
failures are high-value and often irreversible. The lean intervention reduces total waste events by 22%
and total waste cost by £27.6k across the 45-day post period.

### VSM (Value Stream Map)
The simplified 6-stage VSM in Tab 3 maps the physical flow from supplier to customer:

```
Supplier → [Inbound Transport] → [Goods Receiving] → [Grading & QC]
        → [Packing Lines] → [Despatch & QC] → [Outbound Delivery] → Customer
```

Key VSM metrics surfaced:
- **Takt time** (6.34 s/unit) — rate customer demand requires.
- **Actual cycle time** (7.52 s/unit) — real production rate; currently 19% over takt.
- **Value-add ratio** ≈ OEE (62.2%) — proportion of available time adding value.
- **Transport lead time** (4.3 days average) — inbound supply chain lag.
- **CO₂ intensity** (2.40 kg/kg) — weighted average across all origins; air freight routes dominate.

Closing the takt/cycle gap is the primary lever for throughput improvement once OEE reaches ~75%.

---

## Scaling to a real Wealmoor ERP integration (KTP roadmap)

The prototype uses SQLite with simulated data. The path to a production system involves three layers:

### 1. Data integration
Replace `generate_data.py` with live connectors:

| Data source | Integration approach |
|---|---|
| Packing line PLC / SCADA | OPC-UA or Modbus reader → time-series DB (InfluxDB or TimescaleDB) |
| ERP (SAP / Sage / Dynamics) | REST API or direct DB read for planned orders, BOM, stock levels |
| WMS / goods-in system | Webhook or scheduled ETL for transport logs, lead times, supplier data |
| Quality management system | API pull for defect codes, inspection results, repack records |
| Cold chain sensors | IoT gateway → temperature/humidity events mapped to production runs |

The `production_runs`, `waste_events`, and `transport_logs` table schemas are designed to receive
real data with minimal change — column names and types align with common ERP field naming conventions.

### 2. Analytics layer
`lean_analysis.py` is already ERP-agnostic (pure SQL on any relational DB). To scale:
- Swap `sqlite3.connect("freshops.db")` for a `psycopg2` / `pyodbc` connection string pointing
  to the production database.
- Move the `_connect()` context manager to a shared `db.py` config module with environment-variable
  credentials (`DB_HOST`, `DB_USER`, `DB_PASS`).
- Add shift-level granularity queries for real-time OEE monitoring (5-minute rolling window).
- Parameterise the intervention date — in production this becomes a configurable "baseline period"
  set per site or per improvement programme.

### 3. Dashboard and reporting
`dashboard.py` runs today as a local Dash app. For Wealmoor production:
- **Hosting**: Deploy to Azure App Service or AWS Elastic Beanstalk behind the company VPN.
  Dash is a standard Flask app — a `Procfile` or Docker container is all that is needed.
- **Authentication**: Add `dash-auth` or integrate with Active Directory via `msal`.
- **Live data**: Convert static figure functions to `@callback` functions triggered by a
  `dcc.Interval` component (e.g. 60-second refresh for shift OEE, daily refresh for waste trends).
- **Power BI**: `sql_queries.sql` Query 8 (weekly KPI scorecard) is designed for direct import.
  Point Power BI Desktop at the production PostgreSQL connection and schedule a daily refresh.
- **Alerts**: Add a threshold-check job (cron or Azure Function) that fires a Teams/email alert
  when OEE drops below 60% or waste cost exceeds a configurable weekly limit.

### 4. KTP-specific considerations
- **Shift handover reports**: The before/after comparison logic (`CASE WHEN run_date < ?`) can be
  parameterised to generate daily or weekly handover PDFs using `plotly.io.write_image`.
- **Operator-facing kiosk**: Strip Tab 5 (Lean Scorecard) into a standalone single-page app on a
  locked-down tablet mounted at each packing line — showing live OEE, waste events this shift,
  and the top root cause.
- **Supplier scorecard**: Tab 4 (Transport & CO₂) maps directly to a quarterly supplier review
  pack. The CO₂ intensity data supports Wealmoor's scope-3 emissions reporting obligations.
- **Continuous improvement tracking**: Replace the hardcoded `INTERVENTION_DATE = "2024-02-15"`
  with a `lean_programmes` table that records each kaizen event, its start date, target KPI,
  and owner — enabling multi-programme before/after comparisons over time.
