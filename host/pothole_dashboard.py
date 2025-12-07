"""
pothole_dashboard.py
--------------------
Dash app to visualize live-logged pothole / speed breaker events.

Now reads from TWO JSON files written by the logger:
- potholes.json       (POTHOLE events; has severity 1..3)
- speedbreakers.json  (SPEEDBRK events; no severity)

Highlights:
- Auto reload every 1 second
- Session selector (latest by default)
- RSI per selected session (uses mock GPS x,y path distance)
- XY "map": path + colored pothole markers by severity (green/yellow/red)
- Table: Timestamp, Event Type, Severity label (light/moderate/severe), severity level, peak_mV, width, x, y
"""

import json
import math
import os
import time
import pandas as pd
from dash import Dash, dcc, html, Input, Output, dash_table
import plotly.graph_objects as go

POTHOLES_FILE = "potholes.json"
SPEEDBRK_FILE = "speedbreakers.json"

SEV_LABEL = {1: "light", 2: "moderate", 3: "severe"}
TYPE_LABEL = {"POTHOLE": "Pothole", "SPEEDBRK": "Speed Breaker"}

# -------- Data loading --------
def _load_json(path: str):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []

def load_data():
    """Load and merge pothole + speed breaker events into one DataFrame."""
    pots = _load_json(POTHOLES_FILE)
    spds = _load_json(SPEEDBRK_FILE)

    # Normalize keys; severity absent for speed breakers
    df_p = pd.DataFrame(pots)
    df_s = pd.DataFrame(spds)

    # Ensure columns exist in both
    base_cols = ["timestamp","type","severity","peak_mV","width","x","y","session"]
    for df in (df_p, df_s):
        for c in base_cols:
            if c not in df.columns:
                df[c] = None

    # Cast types
    for df in (df_p, df_s):
        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
        df["severity"]  = pd.to_numeric(df["severity"], errors="coerce")  # speedbrk stays NaN
        df["peak_mV"]   = pd.to_numeric(df["peak_mV"], errors="coerce")
        df["width"]     = pd.to_numeric(df["width"], errors="coerce")
        df["x"]         = pd.to_numeric(df["x"], errors="coerce")
        df["y"]         = pd.to_numeric(df["y"], errors="coerce")
        df["type"]      = df["type"].astype(str).str.upper()
        df["session"]   = df["session"].astype(str).fillna("default")

    # Merge & derive
    df = pd.concat([df_p, df_s], ignore_index=True)
    if df.empty:
        return pd.DataFrame(columns=base_cols + ["t_readable","event_type","severity_label","sev_plot"])

    df["t_readable"] = pd.to_datetime(df["timestamp"], unit="ms", origin="unix", errors="coerce")
    df["event_type"] = df["type"].map(lambda t: TYPE_LABEL.get(str(t).upper(), "Unknown"))
    df["severity_label"] = df["severity"].map(SEV_LABEL).fillna("—")
    df["sev_plot"] = df["severity"].fillna(0)

    df = df.sort_values(["session","timestamp"]).dropna(subset=["t_readable"])
    return df

# -------- Metrics --------
def compute_distance(df: pd.DataFrame) -> float:
    """Compute total path distance from successive (x,y) in selected session."""
    path = df.dropna(subset=["x","y"])
    if path.shape[0] < 2:
        return 0.0
    x = path["x"].to_numpy()
    y = path["y"].to_numpy()
    dist = 0.0
    for i in range(1, len(x)):
        dx = x[i] - x[i-1]
        dy = y[i] - y[i-1]
        dist += math.hypot(dx, dy)
    return dist  # "grid units" from mock GPS

def compute_rsi(df: pd.DataFrame) -> float:
    """
    RSI (0..100): 100=very smooth, 0=very rough.
    Weighted events per distance: pothole severity (1/2/3), speed breaker weight=0.5
    RSI = clip(100 - K * (weighted / max(distance,1)))
    """
    if df.empty:
        return 100.0
    dist = compute_distance(df)
    potholes = df[df["type"] == "POTHOLE"]
    speedbrk = df[df["type"] == "SPEEDBRK"]

    weighted = 0.0
    if not potholes.empty:
        weighted += potholes["severity"].fillna(0).sum()
    if not speedbrk.empty:
        weighted += 0.5 * len(speedbrk)

    density = weighted / max(dist, 1.0)
    K = 15.0  # tuning constant
    rsi = max(0.0, min(100.0, 100.0 - K * density))
    return round(rsi, 1)

# -------- App --------
app = Dash(__name__)
app.title = "Pothole Dashboard (Live/1s)"
server = app.server

def card_style(color):
    return {
        "backgroundColor": color,
        "color": "white",
        "padding": "10px",
        "borderRadius": "10px",
        "textAlign": "center",
        "width": "230px",
        "margin": "5px"
    }

app.layout = html.Div([
    html.H2("Pothole Detection Dashboard (Live, JSON via UART, 1s refresh)", style={"textAlign": "center"}),

    # Controls row
    html.Div([
        html.Button("Reload Now", id="reload-btn", n_clicks=0, style={"marginRight": "10px"}),
        html.Span(id="reload-status", children="Loaded."),
        html.Span("  |  "),
        html.Label("Session:"),
        dcc.Dropdown(id="session-dd", options=[], value=None, clearable=False,
                     style={"width":"320px", "display":"inline-block", "marginLeft":"10px"}),
    ], style={"textAlign": "center"}),

    html.Hr(),

    # Summary
    html.Div(id="summary-div", style={
        "display": "flex", "justifyContent": "space-around", "padding": "10px", "flexWrap": "wrap"
    }),

    # Graphs
    html.Div([
        dcc.Graph(id="z-graph"),
        dcc.Graph(id="sev-graph"),
        dcc.Graph(id="xy-graph"),
    ]),

    # Table
    html.H4("Event Log"),
    dash_table.DataTable(
        id="data-table",
        columns=[
            {"name": "Timestamp",         "id": "t_readable"},
            {"name": "Event Type",        "id": "event_type"},
            {"name": "Severity (label)",  "id": "severity_label"},
            {"name": "Severity (1-3)",    "id": "severity"},
            {"name": "peak_mV",           "id": "peak_mV"},
            {"name": "width (samples)",   "id": "width"},
            {"name": "x",                 "id": "x"},
            {"name": "y",                 "id": "y"},
        ],
        page_size=12,
        style_table={"overflowX": "auto"},
        sort_action="native",
    ),

    # Auto refresh every 1 second
    dcc.Interval(id="auto-refresh", interval=1 * 1000, n_intervals=0)
])

# Populate session dropdown (reads from merged data)
@app.callback(
    Output("session-dd", "options"),
    Output("session-dd", "value"),
    Input("reload-btn", "n_clicks"),
    Input("auto-refresh", "n_intervals"),
    prevent_initial_call=False
)
def update_sessions(n_clicks, n_intervals):
    df = load_data()
    if df.empty:
        return [], None
    sessions = df["session"].dropna().unique().tolist()
    latest = df.groupby("session")["timestamp"].max().idxmax()
    opts = [{"label": s, "value": s} for s in sessions]
    return opts, latest

@app.callback(
    Output("reload-status", "children"),
    Output("summary-div", "children"),
    Output("z-graph", "figure"),
    Output("sev-graph", "figure"),
    Output("xy-graph", "figure"),
    Output("data-table", "data"),
    Input("reload-btn", "n_clicks"),
    Input("auto-refresh", "n_intervals"),
    Input("session-dd", "value"),
)
def update_dashboard(n_clicks, n_intervals, session_value):
    df_all = load_data()
    if df_all.empty or session_value is None:
        return "No data found.", [], go.Figure(), go.Figure(), go.Figure(), []

    df = df_all[df_all["session"] == session_value]
    if df.empty:
        return f"No data for session {session_value}.", [], go.Figure(), go.Figure(), go.Figure(), []

    # Summary
    n_total     = len(df)
    n_potholes  = int((df["type"] == "POTHOLE").sum())
    n_speedbrk  = int((df["type"] == "SPEEDBRK").sum())
    avg_sev     = round(df.loc[df["type"]=="POTHOLE","severity"].fillna(0).mean(), 2)
    max_sev     = df.loc[df["type"]=="POTHOLE","severity"].fillna(0).max()
    rsi         = compute_rsi(df)
    last_update = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    # Session duration
    t0 = pd.to_datetime(df["timestamp"].min(), unit="ms", origin="unix", errors="coerce")
    t1 = pd.to_datetime(df["timestamp"].max(), unit="ms", origin="unix", errors="coerce")
    duration = "-"
    if pd.notna(t0) and pd.notna(t1):
        duration = str(t1 - t0).split(".")[0]

    summary_cards = [
        html.Div([html.H4("Session"), html.H3(session_value)],               style=card_style("#263238")),
        html.Div([html.H4("Duration"), html.H3(duration)],                   style=card_style("#455A64")),
        html.Div([html.H4("Total Events"), html.H3(str(n_total))],           style=card_style("#6C63FF")),
        html.Div([html.H4("Potholes"), html.H3(str(n_potholes))],            style=card_style("#00BFA6")),
        html.Div([html.H4("Speed Breakers"), html.H3(str(n_speedbrk))],      style=card_style("#7C4DFF")),
        html.Div([html.H4("Avg Severity (Pothole)"), html.H3(str(avg_sev))], style=card_style("#FF6B6B")),
        html.Div([html.H4("Max Severity (Pothole)"), html.H3(str(max_sev))], style=card_style("#FFAB00")),
        html.Div([html.H4("RSI (0–100)"), html.H3(str(rsi))],                style=card_style("#009688")),
        html.Div([html.H4("Last Update"), html.H3(last_update)],             style=card_style("#8D6E63")),
    ]

    # Z proxy (use peak_mV)
    fig_z = go.Figure()
    fig_z.add_trace(go.Scatter(x=df["t_readable"], y=df["peak_mV"], mode="lines+markers", name="peak_mV"))
    fig_z.update_layout(title="Z-axis Proxy (peak_mV) Over Time", xaxis_title="Time", yaxis_title="peak_mV")

    # Severity (potholes only)
    fig_sev = go.Figure()
    df_p = df[df["type"]=="POTHOLE"]
    fig_sev.add_trace(go.Scatter(
        x=df_p["t_readable"], y=df_p["sev_plot"],
        mode="lines+markers", name="Severity (1–3, potholes)"
    ))
    fig_sev.update_layout(title="Severity Over Time (Potholes)", xaxis_title="Time", yaxis_title="Severity (1–3)")

    # XY “map”
    fig_xy = go.Figure()
    path = df.dropna(subset=["x","y"])
    if not path.empty:
        fig_xy.add_trace(go.Scatter(
            x=path["x"], y=path["y"], mode="lines+markers",
            name="Path (mock GPS)", line=dict(width=2), marker=dict(size=4)
        ))
    pots = df[df["type"]=="POTHOLE"].dropna(subset=["x","y"])
    if not pots.empty:
        color_map = {1: "green", 2: "yellow", 3: "red"}
        fig_xy.add_trace(go.Scatter(
            x=pots["x"], y=pots["y"], mode="markers",
            marker=dict(size=10, color=[color_map.get(s, "gray") for s in pots["severity"]]),
            name="Pothole (color by severity)",
            text=[f"sev={SEV_LABEL.get(int(s), '?')}, peak={int(pk)} mV"
                  for s, pk in zip(pots["severity"], pots["peak_mV"])]
        ))
    spd = df[df["type"]=="SPEEDBRK"].dropna(subset=["x","y"])
    if not spd.empty:
        fig_xy.add_trace(go.Scatter(
            x=spd["x"], y=spd["y"], mode="markers",
            marker=dict(size=8, color="blue", symbol="triangle-up"),
            name="Speed Breaker"
        ))
    fig_xy.update_layout(title="XY Plot (mock GPS path & potholes)",
                         xaxis_title="X (grid units)", yaxis_title="Y (grid units)")

    # Table
    table_df = df[["t_readable","event_type","severity_label","severity","peak_mV","width","x","y"]]
    table_data = table_df.to_dict("records")

    status = f"Reloaded {n_total} events @ {last_update}"
    return status, summary_cards, fig_z, fig_sev, fig_xy, table_data

if __name__ == "__main__":
    print(f"✅ Serving dashboard (auto-refresh every 1s). Reading from {POTHOLES_FILE} & {SPEEDBRK_FILE}")
    app.run(debug=True)

# python pothole_dashboard.py