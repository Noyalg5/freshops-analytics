# FreshOps Analytics

A lean waste and efficiency analytics dashboard for a fresh produce packing operation.

Built as a Knowledge Transfer Partnership (KTP) prototype in collaboration between **Anglia Ruskin University (ARU)** and **Wealmoor Ltd**.

## Purpose

FreshOps Analytics provides real-time and historical visibility into packing line performance, waste volumes, and throughput efficiency. The goal is to surface actionable insights that help operations teams reduce waste, improve yield, and maintain quality standards across fresh produce packing workflows.

## Features

- Waste tracking by product line, shift, and cause category
- Throughput and efficiency KPIs across packing stations
- Trend analysis with interactive time-series charts
- Exportable summaries for shift reports and management review

## Tech Stack

| Tool    | Role                              |
|---------|-----------------------------------|
| Dash    | Interactive web dashboard framework |
| Plotly  | Data visualisation                |
| Pandas  | Data wrangling and aggregation    |
| NumPy   | Numerical computation             |

## Getting Started

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:8050` in your browser.

## Project Context

This dashboard is part of a KTP project between ARU and Wealmoor Ltd, aimed at applying data-driven methods to fresh produce logistics and packing operations. It is a prototype intended for iterative development and stakeholder feedback.
