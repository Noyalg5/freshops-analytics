"""
lean_analysis.py — FreshOps Analytics
Query functions for lean / OEE analysis of freshops.db.
Run directly to print a full summary report.
"""

import sqlite3
import pandas as pd
from contextlib import contextmanager
from pathlib import Path

DB_PATH = "freshops.db"
START_DATE = "2024-01-01"
INTERVENTION_DATE = "2024-02-15"   # day 45 boundary (2024-01-01 + 45 days)


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

def weekly_oee(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Weekly average OEE broken down into Availability, Performance, and Quality.
    Week numbers are 1-indexed from the simulation start date.
    """
    sql = """
        SELECT
            CAST((julianday(run_date) - julianday(?)) / 7 AS INTEGER) + 1  AS week,
            date(MIN(run_date))                                             AS week_start,
            ROUND(AVG(availability) * 100, 1)                              AS availability_pct,
            ROUND(AVG(performance)  * 100, 1)                              AS performance_pct,
            ROUND(AVG(quality)      * 100, 1)                              AS quality_pct,
            ROUND(AVG(oee)          * 100, 1)                              AS oee_pct,
            COUNT(DISTINCT run_date)                                        AS days
        FROM production_runs
        GROUP BY week
        ORDER BY week
    """
    return pd.read_sql_query(sql, conn, params=(START_DATE,))


def throughput_by_product(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Total planned, actual, and good units per product across all 90 days.
    Sorted by good units descending.
    """
    sql = """
        SELECT
            p.name                                                                    AS product,
            p.category,
            SUM(pr.planned_units)                                                     AS planned_units,
            SUM(pr.actual_units)                                                      AS actual_units,
            SUM(pr.good_units)                                                        AS good_units,
            ROUND(SUM(pr.good_units) * 100.0 / NULLIF(SUM(pr.planned_units), 0), 1) AS yield_pct,
            ROUND(SUM(pr.actual_units - pr.good_units) * 100.0
                  / NULLIF(SUM(pr.actual_units), 0), 1)                              AS defect_rate_pct
        FROM production_runs pr
        JOIN products p ON pr.product_id = p.product_id
        GROUP BY p.name, p.category
        ORDER BY good_units DESC
    """
    return pd.read_sql_query(sql, conn)


def waste_pareto(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    TIMWOOD waste Pareto sorted by total cost (GBP) with cumulative percentage.
    An 80/20 threshold is flagged in the cumulative_pct column.
    """
    sql = """
        SELECT
            wc.name                      AS category,
            COUNT(*)                     AS events,
            ROUND(SUM(we.cost_gbp), 2)   AS cost_gbp,
            ROUND(AVG(we.units_lost), 0) AS avg_units_lost
        FROM waste_events we
        JOIN waste_categories wc ON we.category_id = wc.category_id
        GROUP BY wc.name
        ORDER BY cost_gbp DESC
    """
    df = pd.read_sql_query(sql, conn)
    total = df["cost_gbp"].sum()
    df["cost_pct"]       = (df["cost_gbp"] / total * 100).round(1)
    df["cumulative_pct"] = df["cost_pct"].cumsum().round(1)
    return df


def weekly_waste_cost(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Total waste cost and event count per week.
    Useful for spotting the intervention effect on waste spend over time.
    """
    sql = """
        SELECT
            CAST((julianday(event_date) - julianday(?)) / 7 AS INTEGER) + 1 AS week,
            date(MIN(event_date))                                            AS week_start,
            COUNT(*)                                                         AS events,
            ROUND(SUM(cost_gbp), 2)                                         AS waste_cost_gbp,
            ROUND(AVG(cost_gbp), 2)                                         AS avg_event_cost_gbp
        FROM waste_events
        GROUP BY week
        ORDER BY week
    """
    return pd.read_sql_query(sql, conn, params=(START_DATE,))


def root_cause_frequency(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Root cause frequency count and associated cost, sorted by occurrence.
    Joins to waste_categories for TIMWOOD classification.
    """
    sql = """
        SELECT
            we.root_cause                 AS root_cause,
            wc.name                       AS timwood_category,
            COUNT(*)                      AS frequency,
            ROUND(SUM(we.cost_gbp), 2)    AS total_cost_gbp,
            ROUND(AVG(we.cost_gbp), 2)    AS avg_cost_gbp,
            ROUND(SUM(we.units_lost), 0)  AS total_units_lost
        FROM waste_events we
        JOIN waste_categories wc ON we.category_id = wc.category_id
        GROUP BY we.root_cause, wc.name
        ORDER BY frequency DESC
    """
    return pd.read_sql_query(sql, conn)


def vsm_metrics(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Simplified Value Stream Map metrics aggregated across all lines and shifts.

    takt_time_secs          — planned seconds per unit (demand-driven rate)
    actual_cycle_time_secs  — real seconds per unit produced
    transport_lead_time_days— average inbound supplier lead time
    value_add_ratio_pct     — OEE used as proxy for value-add ratio
    process_quality_pct     — good units as % of units actually produced
    co2_intensity_kg_per_kg — average CO2 per kg of produce received
    """
    cur = conn.cursor()

    cur.execute("""
        SELECT
            AVG(cycle_time_seconds)                                        AS takt_time_secs,
            AVG(run_time_mins * 60.0 / NULLIF(actual_units, 0))           AS actual_cycle_time_secs,
            ROUND(AVG(oee) * 100, 1)                                       AS value_add_ratio_pct,
            ROUND(AVG(good_units * 100.0 / NULLIF(actual_units, 0)), 1)   AS process_quality_pct
        FROM production_runs
        WHERE actual_units > 0
    """)
    prod = cur.fetchone()

    cur.execute("""
        SELECT
            AVG(lead_time_days),
            SUM(total_co2_kg) / NULLIF(SUM(weight_kg), 0)
        FROM transport_logs
    """)
    transport = cur.fetchone()

    rows = [
        ("takt_time_secs",           round(prod[0], 2),
         "Target seconds per unit (planned rate)"),
        ("actual_cycle_time_secs",   round(prod[1], 2),
         "Actual seconds per unit produced"),
        ("transport_lead_time_days", round(transport[0], 1),
         "Average inbound lead time from supplier"),
        ("value_add_ratio_pct",      prod[2],
         "OEE as proxy for value-add ratio (%)"),
        ("process_quality_pct",      prod[3],
         "Good units as % of actual units produced"),
        ("co2_intensity_kg_per_kg",  round(transport[1], 3),
         "Average CO2 (kg) per kg of produce received"),
    ]
    return pd.DataFrame(rows, columns=["metric", "value", "description"])


def before_after_comparison(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Side-by-side comparison of key operational metrics split at day 45.
    Returns a transposed DataFrame: metrics as rows, Before/After as columns.
    """
    prod_sql = """
        SELECT
            CASE WHEN run_date < ? THEN 'Before' ELSE 'After' END          AS period,
            ROUND(AVG(availability) * 100, 1)                              AS availability_pct,
            ROUND(AVG(performance)  * 100, 1)                              AS performance_pct,
            ROUND(AVG(quality)      * 100, 1)                              AS quality_pct,
            ROUND(AVG(oee)          * 100, 1)                              AS oee_pct,
            ROUND(SUM(good_units) * 100.0 / NULLIF(SUM(planned_units),0), 1) AS yield_pct,
            SUM(planned_units)                                             AS planned_units,
            SUM(good_units)                                                AS good_units
        FROM production_runs
        GROUP BY period
        ORDER BY period DESC
    """
    waste_sql = """
        SELECT
            CASE WHEN event_date < ? THEN 'Before' ELSE 'After' END AS period,
            ROUND(SUM(cost_gbp), 2)                                  AS total_waste_cost_gbp,
            COUNT(*)                                                  AS waste_events,
            ROUND(AVG(cost_gbp), 2)                                  AS avg_event_cost_gbp
        FROM waste_events
        GROUP BY period
        ORDER BY period DESC
    """
    transport_sql = """
        SELECT
            CASE WHEN log_date < ? THEN 'Before' ELSE 'After' END AS period,
            ROUND(AVG(on_time) * 100, 1)                           AS on_time_pct,
            ROUND(AVG(lead_time_days), 1)                          AS avg_lead_days,
            ROUND(SUM(total_co2_kg) / NULLIF(SUM(weight_kg), 0), 3) AS co2_intensity_kg_per_kg
        FROM transport_logs
        GROUP BY period
        ORDER BY period DESC
    """
    prod_df      = pd.read_sql_query(prod_sql,      conn, params=(INTERVENTION_DATE,))
    waste_df     = pd.read_sql_query(waste_sql,     conn, params=(INTERVENTION_DATE,))
    transport_df = pd.read_sql_query(transport_sql, conn, params=(INTERVENTION_DATE,))

    merged = prod_df.merge(waste_df, on="period").merge(transport_df, on="period")
    pivoted = merged.set_index("period").T

    # Ensure column order is Before → After
    cols = [c for c in ("Before", "After") if c in pivoted.columns]
    pivoted = pivoted[cols]

    if "Before" in pivoted.columns and "After" in pivoted.columns:
        pivoted["Δ (After − Before)"] = (
            pd.to_numeric(pivoted["After"],  errors="coerce")
            - pd.to_numeric(pivoted["Before"], errors="coerce")
        ).round(2)

    return pivoted


# ---------------------------------------------------------------------------
# Print summary
# ---------------------------------------------------------------------------

def _header(title: str, width: int = 72):
    print(f"\n{'─' * width}")
    print(f"  {title}")
    print(f"{'─' * width}")


def print_summary():
    if not Path(DB_PATH).exists():
        print(f"\n[ERROR] Database not found: {DB_PATH}")
        print("        Run generate_data.py first.\n")
        return

    pd.set_option("display.max_rows",     200)
    pd.set_option("display.width",        120)
    pd.set_option("display.max_colwidth", 55)
    pd.set_option("display.float_format", "{:.2f}".format)

    print("\n" + "═" * 72)
    print("  FreshOps Analytics — Lean Analysis Summary")
    print("  90-day simulation  |  Lean intervention: day 45 (2024-02-15)")
    print("═" * 72)

    with _connect() as conn:

        _header("1  Weekly OEE — Availability · Performance · Quality")
        df = weekly_oee(conn)
        print(df.to_string(index=False))

        _header("2  Throughput by Product (90-day totals)")
        df = throughput_by_product(conn)
        print(df.to_string(index=False))

        _header("3  TIMWOOD Waste Pareto — by Cost (GBP)")
        df = waste_pareto(conn)
        print(df.to_string(index=False))

        _header("4  Weekly Waste Cost Trend")
        df = weekly_waste_cost(conn)
        print(df.to_string(index=False))

        _header("5  Root Cause Frequency Analysis (top 20 by occurrence)")
        df = root_cause_frequency(conn)
        print(df.head(20).to_string(index=False))

        _header("6  Simplified VSM Metrics (all lines, all shifts)")
        df = vsm_metrics(conn)
        print(df.to_string(index=False))

        _header("7  Before / After Intervention Comparison (split at day 45)")
        df = before_after_comparison(conn)
        print(df.to_string())

    print("\n" + "═" * 72 + "\n")


if __name__ == "__main__":
    print_summary()
