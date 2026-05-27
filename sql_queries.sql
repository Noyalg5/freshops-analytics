-- =============================================================================
-- sql_queries.sql — FreshOps Analytics
-- 8 analytical queries for freshops.db
-- Requires SQLite 3.25+ for window function support (SUM/RANK OVER).
-- Intervention split date: 2024-02-15 (day 45 of the 90-day simulation).
-- =============================================================================


-- =============================================================================
-- 1. OEE SUMMARY BY LINE AND WEEK
--    Breaks OEE into its three components (Availability × Performance × Quality)
--    per production line per week. Useful for spotting which line is dragging
--    the overall OEE figure and tracking the post-intervention ramp.
-- =============================================================================

SELECT
    line,
    CAST((julianday(run_date) - julianday('2024-01-01')) / 7 AS INTEGER) + 1
                                                    AS week,
    date(MIN(run_date))                             AS week_start,
    CASE
        WHEN MIN(run_date) < '2024-02-15' THEN 'Pre-Intervention'
        ELSE 'Post-Intervention'
    END                                             AS phase,
    COUNT(DISTINCT run_date)                        AS days_active,
    -- OEE components
    ROUND(AVG(availability) * 100, 1)              AS availability_pct,
    ROUND(AVG(performance)  * 100, 1)              AS performance_pct,
    ROUND(AVG(quality)      * 100, 1)              AS quality_pct,
    ROUND(AVG(oee)          * 100, 1)              AS oee_pct,
    -- Volume
    SUM(planned_units)                              AS planned_units,
    SUM(actual_units)                               AS actual_units,
    SUM(good_units)                                 AS good_units,
    ROUND(SUM(good_units) * 100.0
          / NULLIF(SUM(planned_units), 0), 1)       AS yield_pct
FROM production_runs
GROUP BY
    line,
    CAST((julianday(run_date) - julianday('2024-01-01')) / 7 AS INTEGER)
ORDER BY
    week,
    line;


-- =============================================================================
-- 2. TIMWOOD WASTE PARETO (by cost)
--    Ranks all seven TIMWOOD categories by total waste cost and computes a
--    running cumulative percentage — ready for an 80/20 Pareto chart.
-- =============================================================================

WITH category_totals AS (
    SELECT
        wc.name                         AS category,
        wc.description,
        COUNT(*)                        AS events,
        SUM(we.units_lost)              AS total_units_lost,
        ROUND(SUM(we.cost_gbp), 2)      AS cost_gbp,
        ROUND(AVG(we.cost_gbp), 2)      AS avg_event_cost_gbp
    FROM waste_events    we
    JOIN waste_categories wc ON we.category_id = wc.category_id
    GROUP BY wc.name, wc.description
)
SELECT
    category,
    description,
    events,
    total_units_lost,
    cost_gbp,
    avg_event_cost_gbp,
    ROUND(cost_gbp * 100.0
          / SUM(cost_gbp) OVER (),                                   1) AS cost_pct,
    ROUND(SUM(cost_gbp) OVER (
              ORDER BY cost_gbp DESC
              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
          ) * 100.0 / SUM(cost_gbp) OVER (),                         1) AS cumulative_pct
FROM category_totals
ORDER BY cost_gbp DESC;


-- =============================================================================
-- 3. ROOT CAUSE ANALYSIS
--    Ranks every root-cause string by total cost and frequency, with its
--    TIMWOOD classification. Cumulative cost % supports Pareto drill-down.
-- =============================================================================

WITH root_totals AS (
    SELECT
        we.root_cause,
        wc.name                         AS timwood_category,
        COUNT(*)                        AS frequency,
        SUM(we.units_lost)              AS total_units_lost,
        ROUND(SUM(we.cost_gbp),  2)     AS total_cost_gbp,
        ROUND(AVG(we.cost_gbp),  2)     AS avg_cost_gbp,
        ROUND(MIN(we.cost_gbp),  2)     AS min_cost_gbp,
        ROUND(MAX(we.cost_gbp),  2)     AS max_cost_gbp
    FROM waste_events    we
    JOIN waste_categories wc ON we.category_id = wc.category_id
    GROUP BY we.root_cause, wc.name
)
SELECT
    root_cause,
    timwood_category,
    frequency,
    total_units_lost,
    total_cost_gbp,
    avg_cost_gbp,
    min_cost_gbp,
    max_cost_gbp,
    ROUND(total_cost_gbp * 100.0
          / SUM(total_cost_gbp) OVER (),                             1) AS pct_of_total_cost,
    ROUND(SUM(total_cost_gbp) OVER (
              ORDER BY total_cost_gbp DESC
              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
          ) * 100.0 / SUM(total_cost_gbp) OVER (),                  1) AS cumulative_cost_pct,
    RANK() OVER (ORDER BY total_cost_gbp DESC)                          AS cost_rank,
    RANK() OVER (ORDER BY frequency        DESC)                        AS frequency_rank
FROM root_totals
ORDER BY total_cost_gbp DESC;


-- =============================================================================
-- 4. BEFORE / AFTER LEAN INTERVENTION COMPARISON
--    Splits the dataset at day 45 (2024-02-15) and compares production,
--    waste, and transport KPIs across both periods in a single result set.
-- =============================================================================

WITH prod AS (
    SELECT
        CASE WHEN run_date < '2024-02-15'
             THEN 'Before (Days 1–45)'
             ELSE 'After  (Days 46–90)'
        END                                             AS period,
        CASE WHEN run_date < '2024-02-15' THEN 1 ELSE 2 END AS sort_order,
        availability, performance, quality, oee,
        planned_units, actual_units, good_units,
        (actual_units - good_units)                     AS defect_units
    FROM production_runs
),
prod_agg AS (
    SELECT
        period, sort_order,
        ROUND(AVG(availability) * 100, 1)              AS avg_availability_pct,
        ROUND(AVG(performance)  * 100, 1)              AS avg_performance_pct,
        ROUND(AVG(quality)      * 100, 1)              AS avg_quality_pct,
        ROUND(AVG(oee)          * 100, 1)              AS avg_oee_pct,
        SUM(planned_units)                              AS total_planned,
        SUM(good_units)                                 AS total_good,
        ROUND(SUM(good_units) * 100.0
              / NULLIF(SUM(planned_units), 0), 1)       AS yield_pct,
        ROUND(SUM(defect_units) * 100.0
              / NULLIF(SUM(actual_units),  0), 1)       AS defect_rate_pct
    FROM prod
    GROUP BY period, sort_order
),
waste_agg AS (
    SELECT
        CASE WHEN event_date < '2024-02-15'
             THEN 'Before (Days 1–45)'
             ELSE 'After  (Days 46–90)'
        END                                             AS period,
        COUNT(*)                                        AS waste_events,
        ROUND(SUM(cost_gbp), 2)                         AS waste_cost_gbp,
        ROUND(AVG(cost_gbp), 2)                         AS avg_event_cost_gbp
    FROM waste_events
    GROUP BY period
),
transport_agg AS (
    SELECT
        CASE WHEN log_date < '2024-02-15'
             THEN 'Before (Days 1–45)'
             ELSE 'After  (Days 46–90)'
        END                                             AS period,
        ROUND(AVG(on_time)        * 100, 1)             AS on_time_pct,
        ROUND(AVG(lead_time_days),      1)              AS avg_lead_days,
        ROUND(SUM(total_co2_kg)
              / NULLIF(SUM(weight_kg), 0), 3)           AS co2_intensity_kg_per_kg
    FROM transport_logs
    GROUP BY period
)
SELECT
    p.period,
    p.avg_availability_pct,
    p.avg_performance_pct,
    p.avg_quality_pct,
    p.avg_oee_pct,
    p.yield_pct,
    p.defect_rate_pct,
    p.total_planned,
    p.total_good,
    w.waste_events,
    w.waste_cost_gbp,
    w.avg_event_cost_gbp,
    t.on_time_pct,
    t.avg_lead_days,
    t.co2_intensity_kg_per_kg
FROM      prod_agg      p
JOIN      waste_agg     w ON p.period = w.period
JOIN      transport_agg t ON p.period = t.period
ORDER BY  p.sort_order;


-- =============================================================================
-- 5. THROUGHPUT AND YIELD BY PRODUCT
--    Aggregates 90-day volume, yield, defect rate, and estimated defect cost
--    per product. Price-weighted defect cost surfaces the highest-value losses.
-- =============================================================================

SELECT
    p.name                                                              AS product,
    p.category,
    p.price_per_kg,
    p.avg_weight_kg,
    -- Volume
    SUM(pr.planned_units)                                               AS planned_units,
    SUM(pr.actual_units)                                                AS actual_units,
    SUM(pr.good_units)                                                  AS good_units,
    SUM(pr.actual_units - pr.good_units)                                AS defect_units,
    -- Rates
    ROUND(SUM(pr.good_units)     * 100.0
          / NULLIF(SUM(pr.planned_units), 0), 1)                        AS yield_pct,
    ROUND(SUM(pr.actual_units - pr.good_units) * 100.0
          / NULLIF(SUM(pr.actual_units),   0), 1)                       AS defect_rate_pct,
    -- OEE
    ROUND(AVG(pr.availability) * 100, 1)                                AS avg_availability_pct,
    ROUND(AVG(pr.performance)  * 100, 1)                                AS avg_performance_pct,
    ROUND(AVG(pr.quality)      * 100, 1)                                AS avg_quality_pct,
    ROUND(AVG(pr.oee)          * 100, 1)                                AS avg_oee_pct,
    -- Estimated defect cost: defect units × avg weight × price per kg
    ROUND(SUM(pr.actual_units - pr.good_units)
          * p.avg_weight_kg * p.price_per_kg,   2)                      AS est_defect_cost_gbp
FROM production_runs pr
JOIN products         p  ON pr.product_id = p.product_id
GROUP BY p.name, p.category, p.price_per_kg, p.avg_weight_kg
ORDER BY est_defect_cost_gbp DESC;


-- =============================================================================
-- 6. TRANSPORT KPIs BY ORIGIN
--    Supplier-origin scorecard: delivery reliability, lead time spread,
--    CO2 intensity, and cost-per-kg. High CO2 origins flag air-freight risk.
-- =============================================================================

SELECT
    tl.origin,
    COUNT(DISTINCT tl.supplier)                         AS suppliers,
    COUNT(*)                                            AS deliveries,
    -- Volume
    SUM(tl.units_received)                              AS total_units_received,
    ROUND(SUM(tl.weight_kg),              0)            AS total_weight_kg,
    -- Reliability
    ROUND(AVG(tl.on_time) * 100,          1)            AS on_time_pct,
    -- Lead time
    ROUND(AVG(tl.lead_time_days),         1)            AS avg_lead_days,
    MIN(tl.lead_time_days)                              AS min_lead_days,
    MAX(tl.lead_time_days)                              AS max_lead_days,
    ROUND(AVG(tl.lead_time_days)
          - MIN(tl.lead_time_days),       1)            AS lead_time_variability_days,
    -- CO2
    ROUND(AVG(tl.co2_kg_per_kg_product),  3)            AS co2_intensity_kg_per_kg,
    ROUND(SUM(tl.total_co2_kg),           1)            AS total_co2_kg,
    -- Cost
    ROUND(SUM(tl.cost_gbp),               2)            AS total_cost_gbp,
    ROUND(SUM(tl.cost_gbp)
          / NULLIF(SUM(tl.weight_kg), 0), 3)            AS cost_per_kg_gbp,
    -- Share of total CO2
    ROUND(SUM(tl.total_co2_kg) * 100.0
          / SUM(SUM(tl.total_co2_kg)) OVER (),          1) AS pct_of_total_co2
FROM transport_logs tl
GROUP BY tl.origin
ORDER BY total_co2_kg DESC;


-- =============================================================================
-- 7. INVENTORY TURNOVER PROXY
--    Compares weekly inbound weight (transport_logs) against weight consumed
--    in production (actual_units × avg_weight_kg). Derives a running stock
--    balance, weekly turnover ratio, and days-of-supply estimate.
--    Note: this is a flow-based proxy — the DB has no explicit stock table.
-- =============================================================================

WITH weekly_received AS (
    SELECT
        CAST((julianday(log_date) - julianday('2024-01-01')) / 7 AS INTEGER) + 1
                                            AS week,
        date(MIN(log_date))                 AS week_start,
        ROUND(SUM(weight_kg),        1)     AS weight_received_kg,
        SUM(units_received)                 AS units_received,
        ROUND(SUM(cost_gbp),         2)     AS inbound_cost_gbp
    FROM transport_logs
    GROUP BY week
),
weekly_consumed AS (
    SELECT
        CAST((julianday(run_date) - julianday('2024-01-01')) / 7 AS INTEGER) + 1
                                            AS week,
        ROUND(SUM(pr.actual_units * p.avg_weight_kg), 1) AS weight_consumed_kg,
        SUM(pr.actual_units)                AS units_consumed,
        SUM(pr.good_units)                  AS good_units_produced
    FROM production_runs pr
    JOIN products         p ON pr.product_id = p.product_id
    GROUP BY week
)
SELECT
    r.week,
    r.week_start,
    CASE WHEN r.week_start < '2024-02-15' THEN 'Pre-Intervention'
         ELSE 'Post-Intervention'
    END                                                         AS phase,
    r.weight_received_kg,
    c.weight_consumed_kg,
    ROUND(r.weight_received_kg - c.weight_consumed_kg,     1)  AS net_flow_kg,
    -- Running cumulative balance (positive = stock building, negative = drawdown)
    ROUND(SUM(r.weight_received_kg - c.weight_consumed_kg)
              OVER (ORDER BY r.week
                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 1)
                                                                AS running_balance_kg,
    -- Turnover ratio: how much of what arrived was consumed that week
    ROUND(c.weight_consumed_kg
          / NULLIF(r.weight_received_kg, 0),                   2) AS weekly_turnover_ratio,
    -- Days of supply at current consumption rate (7 days per week)
    ROUND(7.0 * r.weight_received_kg
          / NULLIF(c.weight_consumed_kg, 0),                   1) AS days_of_supply,
    r.inbound_cost_gbp,
    r.units_received,
    c.units_consumed,
    c.good_units_produced
FROM weekly_received  r
JOIN weekly_consumed  c ON r.week = c.week
ORDER BY r.week;


-- =============================================================================
-- 8. WEEKLY KPI SCORECARD — POWER BI FEED
--    One row per week combining production, waste, transport, and CO2 KPIs
--    into a single flat table. Designed for direct import as a Power BI
--    dataset: each column maps to a card, line chart, or slicer visual.
--    The `phase` column drives the Before/After slicer.
-- =============================================================================

WITH week_spine AS (
    -- Anchor the week grid on production_runs (all 90 days present)
    SELECT
        CAST((julianday(run_date) - julianday('2024-01-01')) / 7 AS INTEGER) + 1
                                                AS week,
        date(MIN(run_date))                     AS week_start,
        date(MAX(run_date))                     AS week_end,
        CASE WHEN MIN(run_date) < '2024-02-15'
             THEN 'Pre-Intervention'
             ELSE 'Post-Intervention'
        END                                     AS phase
    FROM production_runs
    GROUP BY week
),
prod_kpis AS (
    SELECT
        CAST((julianday(run_date) - julianday('2024-01-01')) / 7 AS INTEGER) + 1
                                                        AS week,
        ROUND(AVG(availability) * 100, 1)               AS oee_availability_pct,
        ROUND(AVG(performance)  * 100, 1)               AS oee_performance_pct,
        ROUND(AVG(quality)      * 100, 1)               AS oee_quality_pct,
        ROUND(AVG(oee)          * 100, 1)               AS oee_pct,
        SUM(planned_units)                              AS planned_units,
        SUM(actual_units)                               AS actual_units,
        SUM(good_units)                                 AS good_units,
        SUM(actual_units - good_units)                  AS defect_units,
        ROUND(SUM(good_units) * 100.0
              / NULLIF(SUM(planned_units), 0), 1)        AS yield_pct,
        ROUND(AVG(cycle_time_seconds),         2)        AS avg_takt_time_secs,
        ROUND(AVG(run_time_mins * 60.0
              / NULLIF(actual_units, 0)),      2)        AS avg_cycle_time_secs
    FROM production_runs
    GROUP BY week
),
waste_kpis AS (
    SELECT
        CAST((julianday(event_date) - julianday('2024-01-01')) / 7 AS INTEGER) + 1
                                                        AS week,
        COUNT(*)                                        AS waste_events,
        ROUND(SUM(cost_gbp),  2)                        AS waste_cost_gbp,
        ROUND(AVG(cost_gbp),  2)                        AS avg_event_cost_gbp,
        SUM(units_lost)                                 AS units_lost_to_waste,
        ROUND(SUM(weight_lost_kg), 1)                   AS weight_lost_kg
    FROM waste_events
    GROUP BY week
),
transport_kpis AS (
    SELECT
        CAST((julianday(log_date) - julianday('2024-01-01')) / 7 AS INTEGER) + 1
                                                        AS week,
        COUNT(*)                                        AS deliveries,
        ROUND(AVG(on_time) * 100,         1)            AS on_time_delivery_pct,
        ROUND(AVG(lead_time_days),        1)            AS avg_lead_time_days,
        ROUND(SUM(weight_kg),             1)            AS weight_received_kg,
        ROUND(SUM(cost_gbp),              2)            AS transport_cost_gbp,
        ROUND(SUM(total_co2_kg),          1)            AS total_co2_kg,
        ROUND(SUM(total_co2_kg)
              / NULLIF(SUM(weight_kg), 0), 3)           AS co2_intensity_kg_per_kg
    FROM transport_logs
    GROUP BY week
)
SELECT
    -- Dimensions / slicers
    ws.week,
    ws.week_start,
    ws.week_end,
    ws.phase,
    -- Production KPIs
    pk.oee_pct,
    pk.oee_availability_pct,
    pk.oee_performance_pct,
    pk.oee_quality_pct,
    pk.planned_units,
    pk.actual_units,
    pk.good_units,
    pk.defect_units,
    pk.yield_pct,
    pk.avg_takt_time_secs,
    pk.avg_cycle_time_secs,
    -- Waste KPIs
    wk.waste_events,
    wk.waste_cost_gbp,
    wk.avg_event_cost_gbp,
    wk.units_lost_to_waste,
    wk.weight_lost_kg,
    -- Transport KPIs
    tk.deliveries,
    tk.on_time_delivery_pct,
    tk.avg_lead_time_days,
    tk.weight_received_kg,
    tk.transport_cost_gbp,
    -- CO2 KPIs
    tk.total_co2_kg,
    tk.co2_intensity_kg_per_kg,
    -- Derived / calculated columns useful in Power BI DAX
    ROUND(wk.waste_cost_gbp
          / NULLIF(pk.good_units, 0),     4)            AS waste_cost_per_good_unit_gbp,
    ROUND(tk.total_co2_kg
          / NULLIF(tk.weight_received_kg, 0), 3)        AS co2_per_kg_received,
    ROUND((pk.good_units * 1.0
           / NULLIF(pk.planned_units, 0))
          * 100,                           1)           AS overall_equipment_effectiveness_pct
FROM       week_spine      ws
LEFT JOIN  prod_kpis       pk ON ws.week = pk.week
LEFT JOIN  waste_kpis      wk ON ws.week = wk.week
LEFT JOIN  transport_kpis  tk ON ws.week = tk.week
ORDER BY   ws.week;
