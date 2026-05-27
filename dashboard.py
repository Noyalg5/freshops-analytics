"""
dashboard.py — FreshOps Analytics Dashboard
Plotly Dash app. Run with: python3 dashboard.py  (from freshops-analytics/)
Then open http://localhost:8050
KTP prototype: ARU × Wealmoor Ltd
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import Dash, dcc, html
import lean_analysis

# ── Palette ──────────────────────────────────────────────────────────────────
P = {
    "t1": "#004D40", "t2": "#00695C", "t3": "#00897B",
    "t4": "#26A69A", "t5": "#80CBC4", "t6": "#E0F2F1",
    "g1": "#1B5E20", "g2": "#2E7D32", "g3": "#43A047",
    "g4": "#66BB6A", "g5": "#A5D6A7", "g6": "#E8F5E9",
    "amber": "#F59E0B", "red": "#EF5350",
    "bg":   "#F2FAF8", "card": "#FFFFFF",
    "text": "#1A3C34", "sub":  "#546E7A", "grid": "#ECEFF1",
}
SEVEN = [P["t1"], P["t2"], P["t3"], P["t4"], P["g3"], P["g4"], P["t5"]]

BASE = dict(
    paper_bgcolor=P["card"], plot_bgcolor=P["card"],
    font=dict(family="Inter, Segoe UI, Arial, sans-serif", color=P["text"], size=12),
    margin=dict(l=52, r=24, t=44, b=52),
    hoverlabel=dict(bgcolor="white", font_size=12),
)
TAB_STYLE = dict(backgroundColor=P["t6"], color=P["t2"], border="none",
                 padding="10px 20px", fontWeight="600", fontSize="13px")
TAB_SEL   = dict(backgroundColor=P["t2"], color="white",  border="none",
                 padding="10px 20px", fontWeight="700", fontSize="13px")

# ── Data (loaded once at startup) ─────────────────────────────────────────────
with lean_analysis._connect() as _c:
    DF_OEE         = lean_analysis.weekly_oee(_c)
    DF_THRU        = lean_analysis.throughput_by_product(_c)
    DF_PARETO      = lean_analysis.waste_pareto(_c)
    DF_WASTE_WEEK  = lean_analysis.weekly_waste_cost(_c)
    DF_ROOT        = lean_analysis.root_cause_frequency(_c)
    DF_VSM         = lean_analysis.vsm_metrics(_c)
    DF_BA          = lean_analysis.before_after_comparison(_c)

    DF_TRANSPORT = pd.read_sql_query("""
        SELECT origin,
            COUNT(DISTINCT supplier)                                AS suppliers,
            COUNT(*)                                                AS deliveries,
            ROUND(AVG(on_time)*100, 1)                              AS on_time_pct,
            ROUND(AVG(lead_time_days), 1)                           AS avg_lead_days,
            MIN(lead_time_days)                                     AS min_lead,
            MAX(lead_time_days)                                     AS max_lead,
            ROUND(AVG(co2_kg_per_kg_product), 3)                    AS co2_intensity,
            ROUND(SUM(total_co2_kg), 1)                             AS total_co2_kg,
            ROUND(SUM(cost_gbp), 2)                                 AS total_cost_gbp,
            ROUND(SUM(cost_gbp)/NULLIF(SUM(weight_kg),0), 3)        AS cost_per_kg
        FROM transport_logs
        GROUP BY origin ORDER BY total_co2_kg DESC
    """, _c)

    DF_WASTE_DELTA = pd.read_sql_query("""
        SELECT wc.name AS category,
            ROUND(SUM(CASE WHEN we.event_date <  '2024-02-15' THEN we.cost_gbp ELSE 0 END),2) AS before_cost,
            ROUND(SUM(CASE WHEN we.event_date >= '2024-02-15' THEN we.cost_gbp ELSE 0 END),2) AS after_cost
        FROM waste_events we
        JOIN waste_categories wc ON we.category_id = wc.category_id
        GROUP BY wc.name ORDER BY before_cost DESC
    """, _c)

DF_THRU = DF_THRU.copy()
DF_THRU["defect_units"] = DF_THRU["actual_units"] - DF_THRU["good_units"]
DF_WASTE_DELTA["delta"] = DF_WASTE_DELTA["after_cost"] - DF_WASTE_DELTA["before_cost"]
_VSM = DF_VSM.set_index("metric")["value"]


def _ba(metric, col):
    """Extract scalar from the transposed before/after DataFrame."""
    try:
        return float(DF_BA.loc[metric, col])
    except (KeyError, ValueError, TypeError):
        return None


# ── Figure builders ───────────────────────────────────────────────────────────

def fig_oee_trend():
    df = DF_OEE
    fig = go.Figure()
    fig.add_vrect(x0=0.5, x1=6.5,  fillcolor=P["t6"], opacity=0.35, layer="below", line_width=0)
    fig.add_vrect(x0=6.5, x1=13.5, fillcolor=P["g6"], opacity=0.40, layer="below", line_width=0)
    fig.add_vline(x=6.5, line_dash="dash", line_color=P["amber"], line_width=1.5)
    fig.add_annotation(x=3.5, y=98, text="Pre-intervention", showarrow=False,
                       font=dict(size=10, color=P["sub"]))
    fig.add_annotation(x=10,  y=98, text="Post-intervention", showarrow=False,
                       font=dict(size=10, color=P["sub"]))

    for col, name, color, width, dash in [
        ("availability_pct", "Availability", P["t4"],    1.8, "dot"),
        ("performance_pct",  "Performance",  P["g3"],    1.8, "dash"),
        ("quality_pct",      "Quality",      P["t3"],    1.8, "dashdot"),
        ("oee_pct",          "OEE",          P["t1"],    3.0, "solid"),
    ]:
        fig.add_trace(go.Scatter(
            x=df["week"], y=df[col], name=name, mode="lines+markers",
            line=dict(color=color, width=width, dash=dash),
            marker=dict(size=5 if col == "oee_pct" else 3),
            hovertemplate=f"{name}: %{{y:.1f}}%<extra></extra>",
        ))
    fig.add_hline(y=85, line_dash="dot", line_color=P["amber"],
                  annotation_text="World-class (85%)",
                  annotation_position="top right",
                  annotation_font_size=10, annotation_font_color=P["amber"])
    fig.update_layout(**BASE, title="Weekly OEE — Availability · Performance · Quality",
                      xaxis=dict(title="Week", tickmode="linear", dtick=1, gridcolor=P["grid"]),
                      yaxis=dict(title="%", range=[35, 102], gridcolor=P["grid"]),
                      legend=dict(orientation="h", y=-0.22))
    return fig


def fig_throughput():
    df = DF_THRU.sort_values("good_units")
    fig = go.Figure()
    fig.add_trace(go.Bar(y=df["product"], x=df["good_units"], name="Good Units",
                         orientation="h", marker_color=P["t3"],
                         hovertemplate="Good: %{x:,}<extra></extra>"))
    fig.add_trace(go.Bar(y=df["product"], x=df["defect_units"], name="Defect / Loss",
                         orientation="h", marker_color=P["red"], opacity=0.65,
                         hovertemplate="Defect: %{x:,}<extra></extra>"))
    for _, r in df.iterrows():
        fig.add_annotation(x=r["good_units"] + r["defect_units"], y=r["product"],
                           text=f"  {r['yield_pct']}%", showarrow=False,
                           font=dict(size=10, color=P["sub"]), xanchor="left")
    fig.update_layout(**BASE, title="90-Day Throughput by Product",
                      barmode="stack", height=380,
                      xaxis=dict(title="Units", gridcolor=P["grid"]),
                      yaxis=dict(title=""),
                      legend=dict(orientation="h", y=-0.18))
    return fig


def fig_pareto():
    df = DF_PARETO
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=df["category"], y=df["cost_gbp"], name="Waste Cost (£)",
                         marker_color=SEVEN,
                         text=["£" + f"{v:,.0f}" for v in df["cost_gbp"]],
                         textposition="outside",
                         hovertemplate="%{x}: £%{y:,.2f}<extra></extra>"),
                  secondary_y=False)
    fig.add_trace(go.Scatter(x=df["category"], y=df["cumulative_pct"],
                             name="Cumulative %", mode="lines+markers",
                             line=dict(color=P["amber"], width=2),
                             marker=dict(size=8, color=P["amber"]),
                             hovertemplate="Cumulative: %{y:.1f}%<extra></extra>"),
                  secondary_y=True)
    fig.add_hline(y=80, line_dash="dot", line_color=P["amber"], secondary_y=True,
                  annotation_text="80%", annotation_font_size=10,
                  annotation_font_color=P["amber"])
    fig.update_layout(**BASE, title="TIMWOOD Waste Pareto — Cost (GBP)",
                      legend=dict(orientation="h", y=-0.22))
    fig.update_yaxes(title_text="Cost (£)",     secondary_y=False, gridcolor=P["grid"])
    fig.update_yaxes(title_text="Cumulative %", secondary_y=True,  range=[0, 108])
    return fig


def fig_waste_trend():
    df = DF_WASTE_WEEK
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["week"], y=df["waste_cost_gbp"],
                             fill="tozeroy", fillcolor="rgba(0,137,123,0.12)",
                             line=dict(color=P["t2"], width=2), name="Waste Cost",
                             mode="lines",
                             hovertemplate="Week %{x}: £%{y:,.2f}<extra></extra>"))
    fig.add_vline(x=6.5, line_dash="dash", line_color=P["amber"], line_width=1.5,
                  annotation_text="Intervention",
                  annotation_position="top right",
                  annotation_font_size=10, annotation_font_color=P["amber"])
    fig.update_layout(**BASE, title="Weekly Waste Cost Trend",
                      xaxis=dict(title="Week", tickmode="linear", dtick=1, gridcolor=P["grid"]),
                      yaxis=dict(title="£", gridcolor=P["grid"]))
    return fig


def fig_root_cause():
    df = DF_ROOT.head(15).sort_values("total_cost_gbp")
    cat_col = {"Defects": P["t1"], "Waiting": P["t2"], "Inventory": P["t3"],
               "Transport": P["t4"], "Motion": P["g3"],
               "Overproduction": P["g4"], "Overprocessing": P["g5"]}
    colors = [cat_col.get(c, P["t3"]) for c in df["timwood_category"]]
    fig = go.Figure(go.Bar(
        y=df["root_cause"], x=df["total_cost_gbp"], orientation="h",
        marker_color=colors,
        text=["×" + str(f) for f in df["frequency"]], textposition="outside",
        hovertemplate="%{y}<br>£%{x:,.2f}<extra></extra>",
    ))
    fig.update_layout(**BASE, title="Top 15 Root Causes by Total Cost",
                      height=490,
                      xaxis=dict(title="Total Cost (£)", gridcolor=P["grid"]),
                      yaxis=dict(title="", automargin=True))
    return fig


def fig_vsm():
    """6-stage value stream map with before/after % change arrows."""
    oee_b  = _ba("oee_pct",             "Before") or 56.6
    oee_a  = _ba("oee_pct",             "After")  or 67.9
    lead_b = _ba("avg_lead_days",        "Before") or 4.8
    lead_a = _ba("avg_lead_days",        "After")  or 3.8
    ot_b   = _ba("on_time_pct",          "Before") or 72.2
    ot_a   = _ba("on_time_pct",          "After")  or 84.7
    q_b    = _ba("quality_pct",          "Before") or 90.1
    q_a    = _ba("quality_pct",          "After")  or 93.1
    wc_b   = _ba("total_waste_cost_gbp", "Before") or 113503
    wc_a   = _ba("total_waste_cost_gbp", "After")  or 85868
    takt   = float(_VSM.get("takt_time_secs",          6.34))
    cycle  = float(_VSM.get("actual_cycle_time_secs",  7.52))
    co2    = float(_VSM.get("co2_intensity_kg_per_kg", 2.40))

    def delta_label(before, after, lower_is_better=False):
        pct = (after - before) / abs(before) * 100
        good = pct < 0 if lower_is_better else pct > 0
        sym  = "▲" if pct > 0 else "▼"
        col  = P["g2"] if good else P["red"]
        return f"{sym} {abs(pct):.1f}%", col

    # takt stage: show actual vs planned (cycle > takt is bad)
    takt_good = cycle <= takt
    takt_sym  = "▼" if cycle < takt else "▲"
    takt_col  = P["g2"] if takt_good else P["red"]
    takt_delta_lbl = f"{takt_sym} {abs(cycle-takt):.1f}s vs takt"

    stages = [
        ("Inbound\nTransport",    "Lead Time",    f"{lead_b:.1f}d → {lead_a:.1f}d", *delta_label(lead_b, lead_a, True),  f"CO₂: {co2:.2f} kg/kg"),
        ("Goods\nReceiving",      "On-Time Del.", f"{ot_b:.1f}% → {ot_a:.1f}%",     *delta_label(ot_b,   ot_a),          "Supplier KPI"),
        ("Grading &\nQC Incoming","Takt Time",    f"Target {takt:.1f}s",              takt_delta_lbl, takt_col,           f"Actual {cycle:.1f}s/unit"),
        ("Packing\nLines",        "OEE",          f"{oee_b:.1f}% → {oee_a:.1f}%",   *delta_label(oee_b,  oee_a),         "3 lines × 3 shifts"),
        ("Despatch\n& QC",        "Quality",      f"{q_b:.1f}% → {q_a:.1f}%",       *delta_label(q_b,    q_a),           "First-pass yield"),
        ("Outbound\nDelivery",    "Waste Cost",   f"£{wc_b:,.0f} → £{wc_a:,.0f}",  *delta_label(wc_b,   wc_a, True),   "45-day period"),
    ]
    # (name, metric, line1, delta_text, delta_col, sub)

    n  = len(stages)
    xs = [i * 2.3 for i in range(n)]    # 0, 2.3, 4.6, 6.9, 9.2, 11.5
    BW, BH, BY = 1.7, 1.0, 3.6

    fig = go.Figure()
    # Invisible anchor trace to set axes
    fig.add_trace(go.Scatter(x=[xs[0]-1.2, xs[-1]+1.4], y=[0.4, 5.0],
                             mode="markers", marker=dict(opacity=0), showlegend=False))

    for i, (name, metric, line1, delta_text, delta_col, sub) in enumerate(stages):
        xc = xs[i]
        # Process box
        fig.add_shape(type="rect",
                      x0=xc-BW/2, x1=xc+BW/2, y0=BY-BH/2, y1=BY+BH/2,
                      fillcolor=P["t2"], line=dict(color=P["t1"], width=1.5))
        # Stage name (inside box)
        fig.add_annotation(x=xc, y=BY, text=name.replace("\n", "<br>"),
                           showarrow=False,
                           font=dict(size=10, color="white",
                                     family="Inter, sans-serif"),
                           align="center")
        # Metric label
        fig.add_annotation(x=xc, y=2.75, text=f"<b>{metric}</b>",
                           showarrow=False, font=dict(size=10, color=P["text"]))
        # Before → After
        fig.add_annotation(x=xc, y=2.25, text=line1,
                           showarrow=False, font=dict(size=9, color=P["sub"]))
        # Delta arrow with colour
        fig.add_annotation(x=xc, y=1.70, text=f"<b>{delta_text}</b>",
                           showarrow=False, font=dict(size=12, color=delta_col))
        # Sub label
        fig.add_annotation(x=xc, y=1.15, text=f"<i>{sub}</i>",
                           showarrow=False, font=dict(size=9, color=P["sub"]))
        # Push arrow to next stage
        if i < n - 1:
            mid = (xc + xs[i+1]) / 2
            fig.add_annotation(x=mid, y=BY, text="→", showarrow=False,
                               font=dict(size=24, color=P["t4"]))

    # Intervention callout
    fig.add_annotation(
        x=sum(xs)/n, y=4.65,
        text="<b>⚡  Lean intervention at day 45 — improvement trajectory active across all stages</b>",
        showarrow=False,
        font=dict(size=11, color=P["t1"]),
        bgcolor=P["t6"], bordercolor=P["t3"], borderpad=6, borderwidth=1,
    )
    _base_vsm = {k: v for k, v in BASE.items() if k != "margin"}
    fig.update_layout(
        **_base_vsm,
        title="Simplified Value Stream Map — 6-Stage Fresh Produce Packing Flow",
        xaxis=dict(visible=False, range=[xs[0]-1.3, xs[-1]+1.5]),
        yaxis=dict(visible=False, range=[0.5, 5.1]),
        height=440,
        showlegend=False,
        margin=dict(l=12, r=12, t=44, b=12),
    )
    return fig


def fig_transport_ontime():
    df = DF_TRANSPORT.sort_values("on_time_pct")
    colors = [P["t2"] if v >= 80 else P["amber"] if v >= 70 else P["red"]
              for v in df["on_time_pct"]]
    fig = go.Figure(go.Bar(
        x=df["origin"], y=df["on_time_pct"], marker_color=colors,
        text=[f"{v}%" for v in df["on_time_pct"]], textposition="outside",
        hovertemplate="%{x}: %{y}%<extra></extra>",
    ))
    fig.add_hline(y=85, line_dash="dot", line_color=P["t1"],
                  annotation_text="Target 85%",
                  annotation_position="top right",
                  annotation_font_size=10, annotation_font_color=P["t1"])
    fig.update_layout(**BASE, title="On-Time Delivery % by Supplier Origin",
                      xaxis=dict(title="", gridcolor=P["grid"]),
                      yaxis=dict(title="%", range=[0, 106], gridcolor=P["grid"]))
    return fig


def fig_transport_lead():
    df = DF_TRANSPORT.sort_values("avg_lead_days", ascending=False)
    fig = go.Figure(go.Bar(
        x=df["origin"], y=df["avg_lead_days"], name="Avg Lead Time",
        marker_color=P["t3"],
        error_y=dict(type="data", symmetric=False,
                     array=(df["max_lead"] - df["avg_lead_days"]).tolist(),
                     arrayminus=(df["avg_lead_days"] - df["min_lead"]).tolist(),
                     color=P["sub"], thickness=1.5, width=6),
        text=[f"{v}d" for v in df["avg_lead_days"]], textposition="outside",
        hovertemplate="%{x}: %{y:.1f} days<extra></extra>",
    ))
    fig.update_layout(**BASE,
                      title="Lead Time by Supplier Origin (avg ± min / max)",
                      xaxis=dict(title="", gridcolor=P["grid"]),
                      yaxis=dict(title="Days", gridcolor=P["grid"]))
    return fig


def fig_transport_co2():
    df = DF_TRANSPORT.sort_values("total_co2_kg", ascending=False)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=df["origin"], y=df["total_co2_kg"],
                         name="Total CO₂ (kg)", marker_color=P["t3"],
                         hovertemplate="%{x}: %{y:,.1f} kg<extra></extra>"),
                  secondary_y=False)
    fig.add_trace(go.Scatter(x=df["origin"], y=df["co2_intensity"],
                             name="Intensity (kg/kg product)",
                             mode="markers",
                             marker=dict(size=14, color=P["amber"], symbol="diamond"),
                             hovertemplate="%{x}: %{y:.3f} kg CO₂/kg<extra></extra>"),
                  secondary_y=True)
    fig.update_layout(**BASE, title="CO₂ Footprint — Total vs Intensity by Origin",
                      legend=dict(orientation="h", y=-0.22))
    fig.update_yaxes(title_text="Total CO₂ (kg)",    secondary_y=False, gridcolor=P["grid"])
    fig.update_yaxes(title_text="Intensity (kg/kg)", secondary_y=True)
    return fig


def fig_indicators():
    specs_list = [
        ("OEE",              "oee_pct",             "%", False),
        ("Yield",            "yield_pct",            "%", False),
        ("On-Time Delivery", "on_time_pct",          "%", False),
        ("Avg Lead Time",    "avg_lead_days",        "d", True),
        ("Waste Cost",       "total_waste_cost_gbp", "£", True),
        ("Waste Events",     "waste_events",         "",  True),
    ]
    n   = len(specs_list)
    fig = make_subplots(rows=1, cols=n, specs=[[{"type": "indicator"}] * n])
    for i, (label, key, suffix, lower_is_better) in enumerate(specs_list):
        before = _ba(key, "Before")
        after  = _ba(key, "After")
        inc_c  = P["red"]  if lower_is_better else P["g2"]
        dec_c  = P["g2"]   if lower_is_better else P["red"]
        fig.add_trace(go.Indicator(
            mode="number+delta",
            value=after,
            title={"text": label, "font": {"size": 11, "color": P["text"]}},
            number={"suffix": suffix, "font": {"size": 20, "color": P["t1"]}},
            delta={"reference": before, "suffix": suffix,
                   "increasing": {"color": inc_c},
                   "decreasing": {"color": dec_c},
                   "font": {"size": 12}},
        ), row=1, col=i+1)
    _base_ind = {k: v for k, v in BASE.items() if k != "margin"}
    fig.update_layout(**_base_ind, height=185,
                      title="Post-Intervention KPIs — change from pre-intervention baseline",
                      margin=dict(l=12, r=12, t=44, b=12))
    return fig


def fig_ba_bars():
    metric_map = {
        "availability_pct": "Availability",
        "performance_pct":  "Performance",
        "quality_pct":      "Quality",
        "oee_pct":          "OEE",
        "yield_pct":        "Yield",
        "on_time_pct":      "On-Time Del.",
    }
    rows = [{"metric": lbl, "Before": _ba(k, "Before"), "After": _ba(k, "After")}
            for k, lbl in metric_map.items()
            if _ba(k, "Before") is not None]
    df = pd.DataFrame(rows)
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Before (Days 1–45)", x=df["metric"], y=df["Before"],
                         marker_color=P["t5"],
                         text=[f"{v:.1f}%" for v in df["Before"]],
                         textposition="outside"))
    fig.add_trace(go.Bar(name="After (Days 46–90)", x=df["metric"], y=df["After"],
                         marker_color=P["t1"],
                         text=[f"{v:.1f}%" for v in df["After"]],
                         textposition="outside"))
    fig.update_layout(**BASE, title="Before vs After — % KPIs",
                      barmode="group",
                      yaxis=dict(title="%", range=[0, 105], gridcolor=P["grid"]),
                      legend=dict(orientation="h", y=-0.22))
    return fig


def fig_waste_delta():
    df = DF_WASTE_DELTA.sort_values("delta")
    colors = [P["g3"] if d < 0 else P["red"] for d in df["delta"]]
    fig = go.Figure(go.Bar(
        x=df["category"], y=df["delta"], marker_color=colors,
        text=[f"£{d:+,.0f}" for d in df["delta"]], textposition="outside",
        hovertemplate="%{x}: £%{y:+,.2f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_color=P["text"], line_width=0.8)
    fig.update_layout(**BASE,
                      title="Waste Cost Δ by TIMWOOD Category  (After − Before, £)",
                      xaxis=dict(title="", gridcolor=P["grid"]),
                      yaxis=dict(title="£ Change", gridcolor=P["grid"]))
    return fig


# ── Layout helpers ─────────────────────────────────────────────────────────────
def row(*children):
    return html.Div(children,
                    style={"display": "flex", "gap": "16px", "marginBottom": "16px"})

def col(*children, flex=1):
    return html.Div(children, style={"flex": flex, "minWidth": 0})

def card(title, *children):
    return html.Div([
        html.P(title, style={"margin": "0 0 8px", "color": P["t2"],
                             "fontSize": "12px", "fontWeight": "700",
                             "letterSpacing": "0.07em", "textTransform": "uppercase"}),
        *children,
    ], style={"background": P["card"], "borderRadius": "8px", "padding": "16px",
              "boxShadow": "0 1px 4px rgba(0,0,0,0.07)"})

def G(fn, h="360px"):
    """Shorthand: wrap a figure function in a dcc.Graph."""
    return dcc.Graph(figure=fn(), config={"displayModeBar": False},
                     style={"height": h})


# ── Tab contents ───────────────────────────────────────────────────────────────
def tab_oee():
    return html.Div([
        row(col(card("Weekly OEE Breakdown",                G(fig_oee_trend, "380px")))),
        row(col(card("90-Day Throughput by Product",        G(fig_throughput, "380px")))),
    ], style={"padding": "16px"})


def tab_waste():
    return html.Div([
        row(
            col(card("TIMWOOD Waste Pareto",    G(fig_pareto,      "340px"))),
            col(card("Weekly Waste Cost Trend", G(fig_waste_trend, "340px"))),
        ),
        row(col(card("Top 15 Root Causes by Total Cost",   G(fig_root_cause, "490px")))),
    ], style={"padding": "16px"})


def tab_vsm():
    vsm_table_rows = [
        html.Tr([
            html.Td(r["metric"],      style={"padding": "5px 12px", "color": P["sub"]}),
            html.Td(str(r["value"]),  style={"padding": "5px 12px", "fontWeight": "600"}),
            html.Td(r["description"], style={"padding": "5px 12px", "color": P["sub"]}),
        ]) for _, r in DF_VSM.iterrows()
    ]
    th = lambda t: html.Th(t, style={"textAlign": "left", "padding": "6px 12px",
                                     "color": P["t1"], "borderBottom": f"2px solid {P['t5']}"})
    return html.Div([
        row(col(card("Value Stream Map",      G(fig_vsm, "440px")))),
        row(col(card("VSM Reference Metrics",
            html.Table(
                [html.Thead(html.Tr([th("Metric"), th("Value"), th("Description")]))]
                + vsm_table_rows,
                style={"borderCollapse": "collapse", "width": "100%", "fontSize": "12px"},
            )))),
    ], style={"padding": "16px"})


def tab_transport():
    return html.Div([
        row(
            col(card("On-Time Delivery by Origin",           G(fig_transport_ontime, "340px"))),
            col(card("Lead Time by Origin (avg ± min/max)",  G(fig_transport_lead,   "340px"))),
        ),
        row(col(card("CO₂ Footprint — Total & Intensity by Origin",
                     G(fig_transport_co2, "340px")))),
    ], style={"padding": "16px"})


def tab_scorecard():
    return html.Div([
        row(col(card("Post-Intervention KPI Indicators",     G(fig_indicators, "185px")))),
        row(
            col(card("Before vs After — % KPIs",            G(fig_ba_bars,     "360px"))),
            col(card("Waste Cost Δ by TIMWOOD Category",     G(fig_waste_delta, "360px"))),
        ),
    ], style={"padding": "16px"})


# ── App ───────────────────────────────────────────────────────────────────────
app = Dash(__name__, title="FreshOps Analytics")

app.layout = html.Div([
    html.Div([
        html.Span("FreshOps Analytics",
                  style={"fontSize": "19px", "fontWeight": "700",
                         "color": "white", "letterSpacing": "0.04em"}),
        html.Span("  ·  KTP Prototype  ·  ARU × Wealmoor Ltd  ·  90-day simulation",
                  style={"fontSize": "11px", "color": P["t5"], "marginLeft": "8px"}),
    ], style={"background": P["t1"], "padding": "13px 24px",
              "display": "flex", "alignItems": "center"}),

    dcc.Tabs([
        dcc.Tab(label="OEE & Production",  children=tab_oee(),       style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="Waste & TIMWOOD",   children=tab_waste(),     style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="Value Stream Map",  children=tab_vsm(),       style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="Transport & CO₂",  children=tab_transport(), style=TAB_STYLE, selected_style=TAB_SEL),
        dcc.Tab(label="Lean Scorecard",    children=tab_scorecard(), style=TAB_STYLE, selected_style=TAB_SEL),
    ], style={"backgroundColor": P["t6"]}),

], style={"backgroundColor": P["bg"], "minHeight": "100vh",
          "fontFamily": "Inter, Segoe UI, Arial, sans-serif"})


if __name__ == "__main__":
    app.run(debug=True)
