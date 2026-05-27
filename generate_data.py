"""
generate_data.py — FreshOps Analytics seed script
Simulates 90 days of fresh produce packing operations for a SQLite database.
A lean intervention at day 45 drives gradual OEE improvement through to day 90.
"""

import sqlite3
import random
import os
from datetime import date, timedelta

DB_PATH = "freshops.db"
START_DATE = date(2024, 1, 1)
NUM_DAYS = 90
INTERVENTION_DAY = 45
SEED = 42

random.seed(SEED)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def gauss(mu, sigma, lo, hi):
    return clamp(random.gauss(mu, sigma), lo, hi)


def lerp(a, b, t):
    return a + (b - a) * t


def post_intervention_progress(day_idx):
    """0.0 on intervention day, 1.0 on final day."""
    if day_idx < INTERVENTION_DAY:
        return 0.0
    return (day_idx - INTERVENTION_DAY) / (NUM_DAYS - INTERVENTION_DAY)


def oee_component(day_idx, pre_mu, post_mu, sigma_pre, sigma_post, lo, hi):
    """Sample an OEE component with gradual improvement after the intervention."""
    t = post_intervention_progress(day_idx)
    mu = lerp(pre_mu, post_mu, t)
    sigma = lerp(sigma_pre, sigma_post, t)
    return gauss(mu, sigma, lo, hi)


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

PRODUCTS = [
    # (product_id, name, species, category, price_per_kg, avg_weight_kg)
    (1, "Mango",        "Mangifera indica",       "Tropical",      2.50, 0.45),
    (2, "Avocado",      "Persea americana",        "Subtropical",   3.20, 0.25),
    (3, "Aubergine",    "Solanum melongena",       "Mediterranean", 1.80, 0.35),
    (4, "Papaya",       "Carica papaya",           "Tropical",      2.10, 0.80),
    (5, "Passion Fruit","Passiflora edulis",       "Tropical",      4.50, 0.08),
    (6, "Sweet Potato", "Ipomoea batatas",         "Subtropical",   1.20, 0.30),
    (7, "Okra",         "Abelmoschus esculentus",  "Tropical",      3.80, 0.02),
    (8, "Plantain",     "Musa paradisiaca",        "Tropical",      1.60, 0.25),
]

WASTE_CATEGORIES = [
    # (category_id, name, description)
    (1, "Transport",       "Unnecessary movement of goods or materials within the facility"),
    (2, "Inventory",       "Excess stock, raw materials, or WIP beyond immediate need"),
    (3, "Motion",          "Unnecessary movement of people or equipment on the packing floor"),
    (4, "Waiting",         "Idle time from equipment downtime, changeovers, or missing materials"),
    (5, "Overproduction",  "Packing more units than current customer orders require"),
    (6, "Overprocessing",  "More handling or process steps than product or customer specification requires"),
    (7, "Defects",         "Units requiring rework, repack, or disposal due to quality failure"),
]

LINES = ["Line 1", "Line 2", "Line 3"]
SHIFTS = ["Morning", "Afternoon", "Night"]

# Products typically run on each line (70% of the time; remainder is random)
LINE_PRODUCT_BIAS = {
    "Line 1": [1, 2, 5],   # premium/fragile: mango, avocado, passion fruit
    "Line 2": [3, 4, 8],   # mid-tier: aubergine, papaya, plantain
    "Line 3": [6, 7],       # bulk root/pod: sweet potato, okra
}

# (origin, co2_kg_per_kg_product)  — air freight >> sea >> road
PRODUCT_ORIGINS = {
    1: [("Kenya",             3.10), ("South Africa", 1.85), ("Peru",             2.20)],
    2: [("South Africa",      1.85), ("Peru",         2.20), ("Kenya",            3.10)],
    3: [("Spain",             0.42)],
    4: [("Dominican Republic",2.75), ("Ghana",        2.95)],
    5: [("Kenya",             3.10), ("Jamaica",      2.60)],
    6: [("Jamaica",           2.60), ("Dominican Republic", 2.75)],
    7: [("Ghana",             2.95), ("Kenya",        3.10)],
    8: [("Dominican Republic",2.75), ("Jamaica",      2.60)],
}

SUPPLIERS = {
    "Kenya":             ["Kakuzi PLC", "Flamingo Horticulture", "East African Growers"],
    "South Africa":      ["Cape Fresh Farms", "Dole SA", "Freshworld SA"],
    "Spain":             ["Frutas Marisa", "Grupo Agroponiente"],
    "Peru":              ["AgroHana", "Lima Fresh Export", "Camposol"],
    "Dominican Republic":["Tropical Exports DR", "Caribbean Fresh"],
    "Ghana":             ["Volta Fresh", "GOPDC"],
    "Jamaica":           ["Island Fresh Co.", "Caribbean Harvest"],
}

# Root causes indexed by TIMWOOD category_id
ROOT_CAUSES = {
    1: [
        "Forklift congestion in cold store aisle",
        "Double-handling at intake bay",
        "No direct routing from ambient store to Line 3",
        "Staging pallets blocking floor lanes",
    ],
    2: [
        "Overstock of slow-moving SKU from weekend",
        "FIFO discipline not followed on avocado batch",
        "Excess WIP accumulation between grading and packing stations",
        "Supplier delivered early — no space allocated",
    ],
    3: [
        "Long walks to retrieve packaging materials from far store",
        "No shadow boards at packing stations — tools misplaced",
        "Equipment sited away from point of use",
        "Operatives crossing lines to fetch labels",
    ],
    4: [
        "Line changeover delay — cleaning not pre-staged",
        "Waiting for QC sign-off on incoming batch",
        "Label stock replenishment delay mid-shift",
        "Chiller door held open — temperature recovery wait",
        "Weighscale recalibration pause",
    ],
    5: [
        "Packed to forecast; order cut late by customer",
        "Weekend overrun not absorbed by Monday orders",
        "Batch size not aligned to order quantity",
    ],
    6: [
        "Double inspection step not required per customer spec",
        "Manual recount after auto-weigh — redundant",
        "Excess trimming beyond specification tolerance",
        "Unnecessary rewrap applied before despatch",
    ],
    7: [
        "Ripeness out of spec on arrival — supplier deviation",
        "Mechanical bruising from worn conveyor belt section",
        "Incorrect label applied — full repack required",
        "Temperature excursion in transport — chilling failure",
        "Dropped units during manual transfer between lines",
        "Pack integrity failure — seal not meeting spec",
    ],
}


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE products (
    product_id          INTEGER PRIMARY KEY,
    name                TEXT    NOT NULL,
    species             TEXT,
    category            TEXT,
    price_per_kg        REAL,
    avg_weight_kg       REAL
);

CREATE TABLE waste_categories (
    category_id         INTEGER PRIMARY KEY,
    name                TEXT    NOT NULL,
    description         TEXT
);

CREATE TABLE production_runs (
    run_id              INTEGER PRIMARY KEY,
    run_date            TEXT    NOT NULL,
    line                TEXT    NOT NULL,
    shift               TEXT    NOT NULL,
    product_id          INTEGER NOT NULL,
    planned_units       INTEGER,
    actual_units        INTEGER,
    good_units          INTEGER,
    cycle_time_seconds  REAL,
    planned_duration_mins INTEGER,
    run_time_mins       REAL,
    availability        REAL,
    performance         REAL,
    quality             REAL,
    oee                 REAL,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE waste_events (
    event_id            INTEGER PRIMARY KEY,
    event_date          TEXT    NOT NULL,
    run_id              INTEGER,
    product_id          INTEGER NOT NULL,
    category_id         INTEGER NOT NULL,
    units_lost          INTEGER,
    weight_lost_kg      REAL,
    cost_gbp            REAL,
    root_cause          TEXT,
    FOREIGN KEY (run_id)      REFERENCES production_runs(run_id),
    FOREIGN KEY (product_id)  REFERENCES products(product_id),
    FOREIGN KEY (category_id) REFERENCES waste_categories(category_id)
);

CREATE TABLE transport_logs (
    log_id                  INTEGER PRIMARY KEY,
    log_date                TEXT    NOT NULL,
    product_id              INTEGER NOT NULL,
    origin                  TEXT    NOT NULL,
    supplier                TEXT,
    units_received          INTEGER,
    weight_kg               REAL,
    lead_time_days          INTEGER,
    on_time                 INTEGER,
    co2_kg_per_kg_product   REAL,
    total_co2_kg            REAL,
    cost_gbp                REAL,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);
"""


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def generate_production_and_waste(cur):
    product_dict = {p[0]: p for p in PRODUCTS}

    run_id = 0
    event_id = 0

    for day_idx in range(NUM_DAYS):
        run_date = (START_DATE + timedelta(days=day_idx)).isoformat()

        for line in LINES:
            for shift in SHIFTS:
                run_id += 1
                biased_products = LINE_PRODUCT_BIAS[line]
                product_id = (
                    random.choice(biased_products)
                    if random.random() < 0.72
                    else random.randint(1, 8)
                )
                _, _, _, _, price_per_kg, avg_weight_kg = product_dict[product_id]

                planned_units = int(gauss(4600, 420, 2800, 6800))
                planned_duration = 480  # minutes per shift

                # OEE components
                # Pre-intervention baseline: ~0.78 avail, ~0.82 perf, ~0.91 quality → OEE ≈ 58%
                # Post-intervention target:  ~0.90 avail, ~0.93 perf, ~0.97 quality → OEE ≈ 81%
                availability = oee_component(day_idx,
                    pre_mu=0.78, post_mu=0.90,
                    sigma_pre=0.04, sigma_post=0.025,
                    lo=0.58, hi=0.97)

                performance = oee_component(day_idx,
                    pre_mu=0.82, post_mu=0.93,
                    sigma_pre=0.04, sigma_post=0.025,
                    lo=0.62, hi=0.98)

                quality = oee_component(day_idx,
                    pre_mu=0.91, post_mu=0.97,
                    sigma_pre=0.02, sigma_post=0.012,
                    lo=0.78, hi=0.999)

                # Night shift carries a small efficiency penalty
                if shift == "Night":
                    availability *= gauss(0.965, 0.018, 0.92, 1.00)
                    quality      *= gauss(0.975, 0.012, 0.94, 1.00)

                availability = clamp(availability, 0.50, 0.97)
                performance  = clamp(performance,  0.55, 0.98)
                quality      = clamp(quality,      0.75, 0.999)

                oee = availability * performance * quality

                run_time   = planned_duration * availability
                actual_units = int(planned_units * performance * (run_time / planned_duration))
                good_units   = int(actual_units * quality)
                cycle_time   = (planned_duration * 60) / planned_units  # seconds per unit

                cur.execute("""
                    INSERT INTO production_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    run_id, run_date, line, shift, product_id,
                    planned_units, actual_units, good_units,
                    round(cycle_time, 3), planned_duration, round(run_time, 1),
                    round(availability, 4), round(performance, 4),
                    round(quality, 4), round(oee, 4),
                ))

                # --- Defect waste (category 7) always derived from quality loss ---
                defect_units = actual_units - good_units
                if defect_units > 0:
                    event_id += 1
                    weight = round(defect_units * avg_weight_kg, 2)
                    cost   = round(weight * price_per_kg, 2)
                    cause  = random.choice(ROOT_CAUSES[7])
                    cur.execute("""
                        INSERT INTO waste_events VALUES (?,?,?,?,?,?,?,?,?)
                    """, (event_id, run_date, run_id, product_id, 7,
                          defect_units, weight, cost, cause))

                # --- Additional TIMWOOD waste events (fewer after intervention) ---
                n_extra_weights = (
                    [0.08, 0.38, 0.37, 0.17] if day_idx < INTERVENTION_DAY
                    else [0.28, 0.44, 0.22, 0.06]
                )
                n_extra = random.choices([0, 1, 2, 3], weights=n_extra_weights)[0]

                for _ in range(n_extra):
                    cat_id     = random.choice([1, 2, 3, 4, 5, 6])
                    units_lost = int(gauss(90, 45, 8, 350))
                    weight     = round(units_lost * avg_weight_kg, 2)
                    cost       = round(weight * price_per_kg * gauss(1.05, 0.12, 0.80, 1.55), 2)
                    cause      = random.choice(ROOT_CAUSES[cat_id])
                    event_id  += 1
                    cur.execute("""
                        INSERT INTO waste_events VALUES (?,?,?,?,?,?,?,?,?)
                    """, (event_id, run_date, run_id, product_id, cat_id,
                          units_lost, weight, cost, cause))


def generate_transport_logs(cur):
    product_dict = {p[0]: p for p in PRODUCTS}
    log_id = 0

    for day_idx in range(NUM_DAYS):
        log_date = (START_DATE + timedelta(days=day_idx)).isoformat()
        n_deliveries = random.randint(2, 4)

        for _ in range(n_deliveries):
            product_id = random.randint(1, 8)
            origin, co2_factor = random.choice(PRODUCT_ORIGINS[product_id])
            supplier = random.choice(SUPPLIERS[origin])

            _, _, _, _, price_per_kg, avg_weight_kg = product_dict[product_id]

            units_received = int(gauss(2200, 520, 400, 5500))
            weight_kg = round(units_received * avg_weight_kg, 1)

            # Lead time shortens slightly post-intervention (better supplier scheduling)
            if day_idx < INTERVENTION_DAY:
                lead_time    = round(gauss(4.8, 1.6, 1, 12))
                on_time_prob = 0.71
            else:
                lead_time    = round(gauss(3.9, 1.3, 1, 9))
                on_time_prob = 0.86

            on_time   = 1 if random.random() < on_time_prob else 0
            total_co2 = round(weight_kg * co2_factor, 2)
            cost_gbp  = round(weight_kg * price_per_kg * gauss(0.94, 0.07, 0.72, 1.18), 2)

            log_id += 1
            cur.execute("""
                INSERT INTO transport_logs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (log_id, log_date, product_id, origin, supplier,
                  units_received, weight_kg, lead_time, on_time,
                  co2_factor, total_co2, cost_gbp))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(SCHEMA)

    cur.executemany("INSERT INTO products VALUES (?,?,?,?,?,?)", PRODUCTS)
    cur.executemany("INSERT INTO waste_categories VALUES (?,?,?)", WASTE_CATEGORIES)

    generate_production_and_waste(cur)
    generate_transport_logs(cur)

    conn.commit()

    # --- Summary ---
    print(f"\nDatabase created: {DB_PATH}")
    print(f"Simulation: {NUM_DAYS} days from {START_DATE}  |  Lean intervention: day {INTERVENTION_DAY}\n")

    tables = [
        "products", "waste_categories",
        "production_runs", "waste_events", "transport_logs",
    ]
    col_w = max(len(t) for t in tables)
    for table in tables:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        n = cur.fetchone()[0]
        print(f"  {table:<{col_w}}  {n:>6} rows")

    cur.execute("""
        SELECT
            CASE WHEN run_date < ? THEN 'Pre-intervention (days 1–45) '
                 ELSE 'Post-intervention (days 46–90)'
            END AS period,
            ROUND(AVG(oee) * 100, 1) AS avg_oee_pct,
            ROUND(MIN(oee) * 100, 1) AS min_oee_pct,
            ROUND(MAX(oee) * 100, 1) AS max_oee_pct
        FROM production_runs
        GROUP BY period
        ORDER BY period
    """, ((START_DATE + timedelta(days=INTERVENTION_DAY)).isoformat(),))

    print("\nOEE summary (all lines, all shifts):")
    print(f"  {'Period':<32}  {'Avg':>6}  {'Min':>6}  {'Max':>6}")
    print(f"  {'-'*32}  {'------':>6}  {'------':>6}  {'------':>6}")
    for period, avg, mn, mx in cur.fetchall():
        print(f"  {period:<32}  {avg:>5.1f}%  {mn:>5.1f}%  {mx:>5.1f}%")

    cur.execute("""
        SELECT
            CASE WHEN log_date < ? THEN 'Pre-intervention '
                 ELSE 'Post-intervention'
            END AS period,
            ROUND(AVG(on_time) * 100, 1) AS on_time_pct,
            ROUND(AVG(lead_time_days), 1) AS avg_lead_days
        FROM transport_logs
        GROUP BY period
        ORDER BY period
    """, ((START_DATE + timedelta(days=INTERVENTION_DAY)).isoformat(),))

    print("\nTransport summary:")
    print(f"  {'Period':<18}  {'On-time':>8}  {'Avg lead':>9}")
    print(f"  {'-'*18}  {'--------':>8}  {'---------':>9}")
    for period, ot, lead in cur.fetchall():
        print(f"  {period:<18}  {ot:>7.1f}%  {lead:>7.1f} days")

    cur.execute("""
        SELECT wc.name, SUM(we.cost_gbp) AS total_cost
        FROM waste_events we
        JOIN waste_categories wc ON we.category_id = wc.category_id
        GROUP BY wc.name
        ORDER BY total_cost DESC
    """)

    print("\nWaste cost by TIMWOOD category (full 90 days):")
    for name, cost in cur.fetchall():
        print(f"  {name:<16}  £{cost:>10,.2f}")

    conn.close()
    print()


if __name__ == "__main__":
    main()
