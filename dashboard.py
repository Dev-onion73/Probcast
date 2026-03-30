import streamlit as st
import json
import pandas as pd
import numpy as np
import os
from datetime import datetime
import yaml
import time
import requests

PRED_PATH = "outputs/latest_preds.json"
LABEL_PATH = "outputs/latest_labels.json"
HIER_PATH = "outputs/latest_hierarchy.json"
CONFIG_PATH = "config/connectors.yaml"

@st.cache_data(ttl=30)
def load_preds():
    if not os.path.exists(PRED_PATH):
        return []
    with open(PRED_PATH) as f:
        return json.load(f)

@st.cache_data(ttl=30)
def load_labels():
    if not os.path.exists(LABEL_PATH):
        return []
    with open(LABEL_PATH) as f:
        return json.load(f)

@st.cache_data(ttl=30)
def load_hierarchy():
    if not os.path.exists(HIER_PATH):
        return {}
    with open(HIER_PATH) as f:
        return json.load(f)

@st.cache_data(ttl=45)
def load_connectors_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)

def entity_index_from_config(cfg):
    # entity_id → (connector_url, metadata)
    index = {}
    for connector in cfg.get('connectors', []):
        url = connector['url']
        for e in connector.get('entities', []):
            eid = e["id"]
            meta = e["metadata"]
            index[eid] = (url, meta)
    return index

def make_label_matrix(labels, preds):
    entity_ids = [row["entity_id"] for row in labels]
    if preds:
        classes = list(next(iter(preds))["probs_per_class"].keys())
    else:
        all_labels = set(lab for row in labels for lab in row.get("detected_labels", []))
        classes = sorted(list(all_labels))
    data = []
    for row in labels:
        active = set(row.get("detected_labels", []))
        vals = [1 if c in active else 0 for c in classes]
        data.append(vals)
    df = pd.DataFrame(data, index=entity_ids, columns=classes)
    return df

def style_compact(df):
    def highlight(val):
        if val == 1:
            return (
                "background-color:#ff4d4d;"
                "color:white;"
                "font-weight:bold;"
                "text-align:center;"
                "border:1px solid #bbb;"
                "padding:0px;"
                "font-size:0.85em;"
                "width:22px;"
                "min-width:22px;max-width:22px;"
                "height:22px;min-height:22px;max-height:22px;"
            )
        else:
            return (
                "background-color:white;"
                "color:#222;"
                "text-align:center;"
                "border:1px solid #eee;"
                "padding:0px;"
                "font-size:0.85em;"
                "width:22px;"
                "min-width:22px;max-width:22px;"
                "height:22px;min-height:22px;max-height:22px;"
            )
    styled = (
        df.style
        .applymap(highlight)
        .set_properties(**{
            "font-size": "0.85em",
            "padding": "0px",
            "height": "22px",
            "width": "22px",
            "min-width": "22px",
            "max-width": "22px",
            "min-height": "22px",
            "max-height": "22px",
            "text-align": "center",
        })
    )
    return styled

def style_risk_table(df):
    return (
        df.style
        .set_properties(**{
            "font-size": "0.95em",
            "padding": "2px",
            "text-align": "center",
            "min-width": "30px",
            "max-width": "90px",
        })
    )

def log_color(severity, unit=None):
    colors = {
        "CRITICAL": "#ff3333",
        "ERROR": "#ff7f2a",
        "WARNING": "#fcf37c",
        "INFO": "#a5f46c",
        "DEBUG": "#bbbbbb",
    }
    col = colors.get(severity.upper(), "#eeeeee")
    style = f"color:#222;background-color:{col};"
    if unit and ('kernel' in unit.lower() or 'systemd' in unit.lower()):
        style += "font-weight:bold;"
    return style

def log_html(records):
    def fmt_log(rec):
        sev = rec.get('level', '').upper()
        style = log_color(sev, rec.get("unit", ""))
        ts = rec.get("timestamp", None)
        try:
            if isinstance(ts, str): ts = float(ts)
            ts_str = datetime.utcfromtimestamp(ts).strftime("%H:%M:%S") if ts else ""
        except Exception:
            ts_str = ""
        msg = rec.get("message", "")
        unit = rec.get("unit", "")
        return f'<div style="{style};font-family:monospace;font-size:0.96em;padding:0 2px 0 0;margin:0;">' \
               f'[{ts_str}] <b>{sev}</b> {unit} {msg}</div>'
    out = [fmt_log(r) for r in records]
    return "<br>".join(out)

def fetch_metrics_rest(connector_url, entity_id, start_ts, end_ts):
    # Use the correct endpoint for your combined mock server
    try:
        resp = requests.get(
            f"{connector_url}/metrics/data",
            params={"entity_id": entity_id, "start_ts": start_ts, "end_ts": end_ts},
            timeout=4
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return []

def fetch_logs_rest(connector_url, entity_id, start_ts, end_ts):
    try:
        resp = requests.get(
            f"{connector_url}/journal/data",
            params={"entity_id": entity_id, "start_ts": start_ts, "end_ts": end_ts},
            timeout=4
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return []

def minimal_resource_normalize(record):
    return {
        "metric_type": record.get("metric_type", "unknown"),
        "value": float(record.get("value", 0)),
        "timestamp": float(record.get("timestamp", 0))
    }

def minimal_log_normalize(record):
    return {
        "level": record.get("level", ""),
        "unit": record.get("unit", ""),
        "message": record.get("message", ""),
        "timestamp": float(record.get("timestamp", 0))
    }

def fetch_live_telemetry(entity_id, connector_url, window=3600):
    now = int(time.time())
    start_ts = now - window
    try:
        metrics = fetch_metrics_rest(connector_url, entity_id, start_ts, now)
        metrics = [minimal_resource_normalize(r) for r in metrics]
    except Exception:
        metrics = []
    try:
        logs = fetch_logs_rest(connector_url, entity_id, start_ts, now)
        logs = [minimal_log_normalize(r) for r in logs]
    except Exception:
        logs = []
    return metrics, logs

import matplotlib.pyplot as plt
import itertools

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import math

def render_entity_metrics_live(metrics):
    if not metrics:
        st.info("No resource records available for selected entity.")
        return
    df_metrics = pd.DataFrame(metrics)
    if "metric_type" not in df_metrics.columns or "value" not in df_metrics.columns:
        st.info("No resource metric values found.")
        return

    st.subheader("Resource Metrics (interactive 2×2 grid, live)")
    metric_types = df_metrics['metric_type'].unique()
    n_metrics = len(metric_types)
    nrows_per_grid = 2
    ncols_per_grid = 2
    n_plots_per_grid = nrows_per_grid * ncols_per_grid

    palette = [
        "#278fea", "#a5f46c", "#f76c5e", "#a16ae8", "#fad02c",
        "#86d1d6", "#fcaf58", "#ed4c4c", "#3cba54", "#e27396"
    ]

    # Break into 2x2 grids (group by 4)
    for group_start in range(0, n_metrics, n_plots_per_grid):
        metric_group = metric_types[group_start:group_start+n_plots_per_grid]
        subplot_titles = [m.replace("_", " ").title() for m in metric_group]
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=subplot_titles
        )
        for sub_idx, metric in enumerate(metric_group):
            row = (sub_idx // ncols_per_grid) + 1
            col = (sub_idx % ncols_per_grid) + 1
            mdf = df_metrics[df_metrics['metric_type'] == metric].sort_values('timestamp')
            if len(mdf) == 0:
                continue
            x = pd.to_datetime(mdf['timestamp'], unit='s')
            color = palette[sub_idx % len(palette)]
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=mdf['value'],
                    mode="lines+markers",
                    name=metric.replace("_", " ").title(),
                    line=dict(color=color, width=2),
                    marker=dict(size=5),
                    hovertemplate="%{x}<br>Value: %{y:.2f}<extra></extra>",
                ),
                row=row, col=col
            )
            fig.update_xaxes(title_text="Time", row=row, col=col)
            fig.update_yaxes(title_text="Value", row=row, col=col)
            # Do NOT update fig.layout.annotations here—titles are already set by make_subplots
        fig.update_layout(height=390, template="plotly_dark", showlegend=False, margin=dict(t=40, b=30, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("---")

def make_plotly_metric_grid(df_metrics, metric_group, palette, nrows, ncols):
    fig = make_empty_grid(nrows, ncols)
    for sub_idx, metric in enumerate(metric_group):
        row = (sub_idx // ncols) + 1
        col = (sub_idx % ncols) + 1
        mdf = df_metrics[df_metrics['metric_type'] == metric].sort_values('timestamp')
        if len(mdf) == 0:
            continue
        x = pd.to_datetime(mdf['timestamp'], unit='s')
        color = palette[sub_idx % len(palette)]
        fig.add_trace(
            go.Scatter(
                x=x,
                y=mdf['value'],
                mode="lines+markers",
                name=metric.replace("_", " ").title(),
                line=dict(color=color, width=2),
                marker=dict(size=5),
                hovertemplate="%{x}<br>Value: %{y:.2f}<extra></extra>",
            ),
            row=row, col=col
        )
        # Update subplot title
        fig.update_xaxes(title_text="Time", row=row, col=col)
        fig.update_yaxes(title_text="Value", row=row, col=col)
        fig.layout.annotations[(row-1)*ncols+col-1]['text'] = metric.replace("_", " ").title()  # update
    fig.update_layout(height=390, template="plotly_dark", showlegend=False, margin=dict(t=30, b=30, l=10, r=10))
    return fig

def make_empty_grid(nrows, ncols):
    from plotly.subplots import make_subplots
    subplot_titles = [""] * (nrows * ncols)
    fig = make_subplots(rows=nrows, cols=ncols, subplot_titles=subplot_titles)
    return fig
def render_entity_logs_live(logs):
    if not logs:
        st.info("No journal records available for selected entity.")
        return
    st.subheader("Entity Journal Log Stream (LIVE)")
    logs_sorted = sorted(logs, key=lambda x: x.get("timestamp", 0), reverse=False)
    html = log_html(logs_sorted[-60:])
    st.markdown(f"<div style='max-height:330px;overflow-y:auto;background:#23272d;border-radius:6px;padding:6px 8px;'>{html}</div>", 
                unsafe_allow_html=True)

def main():
    st.set_page_config(page_title="ProbCast Dashboard", layout="wide")

    preds = load_preds()
    labels = load_labels()
    hierarchy = load_hierarchy()
    connectors_cfg = load_connectors_config()
    entity_index = entity_index_from_config(connectors_cfg)

    df = pd.DataFrame(preds)
    entity_ids = df['entity_id'].unique() if len(df) else []
    horizons = df['forecast_horizon'].unique() if len(df) else []

    st.sidebar.title("🔎 ProbCast UI")
    selected_page = st.sidebar.radio(
        "Dashboard Page",
        options=["Risk Overview", "Entity Telemetry"],
        index=0
    )

    if selected_page == "Risk Overview":
        st.title("ProbCast: Infrastructure Risk Forecasting Dashboard")
        if not preds:
            st.warning("No prediction data found. Is the backend running?")
            st.stop()
        st.sidebar.subheader("Show risk for entity")
        sel_entity = st.sidebar.selectbox("Select entity", entity_ids)
        sel_horizon = st.sidebar.selectbox("Forecast horizon", horizons)
        st.subheader("Risk Overview (all entities)")
        risk_matrix = []
        for eid in entity_ids:
            row = {'Entity': eid}
            for horizon in horizons:
                preds_row = next((p for p in preds if p['entity_id'] == eid and p['forecast_horizon'] == horizon), None)
                if preds_row:
                    for cls, val in preds_row['probs_per_class'].items():
                        row[f'{cls} @ {horizon}'] = round(val, 3)
            risk_matrix.append(row)
        df_risk = pd.DataFrame(risk_matrix)
        st.dataframe(style_risk_table(df_risk), width="stretch", height=min(600, 35 * len(df_risk) + 40))
        st.subheader("Detected Failure Labels — Matrix View (auto-updates every 30s)")
        if labels:
            df_labels = make_label_matrix(labels, preds)
            st.dataframe(style_compact(df_labels), width="content", height=min(600, 28 * len(df_labels) + 38))
            st.caption("Red = failure detected for entity in latest window. Table auto-updates.")
        else:
            st.info("No label data found for current polling window.")
        st.subheader(f"Forecast for: {sel_entity}")
        entity_preds = [p for p in preds if p['entity_id'] == sel_entity and p['forecast_horizon'] == sel_horizon]
        if entity_preds:
            pc = entity_preds[0]['probs_per_class']
            st.bar_chart(pd.Series(pc), width='stretch')
        else:
            st.info("No prediction found for this entity/horizon.")
        st.subheader("Detected Failure Labels (L2 Labelling)")
        entity_labels = next((l for l in labels if l['entity_id'] == sel_entity), None)
        if entity_labels and entity_labels['detected_labels']:
            st.write(f"Detected failure classes: {', '.join(entity_labels['detected_labels'])}")
        else:
            st.write("No failure labels detected for this entity in the last window.")
        st.subheader("Entity in Hierarchy")
        if hierarchy and "tree" in hierarchy:
            st.json(hierarchy["tree"])
        st.caption("ProbCast Demo Dashboard – Streamlit · PathB only · Data auto-refreshes every 30s")
    else:   # "Entity Telemetry" page
        st.title("ProbCast: Entity Metrics & Log Stream")
        st.subheader("Select an Entity to Inspect")
        sel_entity2 = st.selectbox("Select entity", entity_ids, key="entity_telemetry")
        entity_info = entity_index.get(sel_entity2, None)
        if entity_info is None:
            st.error("Could not find selected entity in connectors config.")
        else:
            connector_url, entity_meta = entity_info
            with st.spinner("Fetching latest metrics and logs…"):
                metrics, logs = fetch_live_telemetry(sel_entity2, connector_url)
            render_entity_metrics_live(metrics)
            st.markdown("---")
            render_entity_logs_live(logs)
            st.caption("All available metrics (per entity) are shown above. Logs are colored by severity. Click entity to refresh.")

if __name__ == "__main__":
    main()