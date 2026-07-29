import streamlit as st
import boto3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import time
import os
from datetime import datetime, timezone
from decimal import Decimal

st.set_page_config(
    page_title="Weather Anomaly Detection",
    page_icon="🌩️",
    layout="wide"
)

st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    .metric-card {
        background: #1c1f26;
        border: 1px solid #2d3139;
        border-radius: 8px;
        padding: 1.2rem;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

REGION = "us-east-1"

@st.cache_resource
def get_aws():
    return {
        "dynamodb": boto3.resource("dynamodb", region_name=REGION),
        "athena":   boto3.client("athena",    region_name=REGION),
    }

aws = get_aws()


def load_alerts():
    tbl  = aws["dynamodb"].Table("weather_alerts")
    resp = tbl.scan()
    items = resp.get("Items", [])
    if not items:
        return pd.DataFrame()
    rows = []
    for item in items:
        rows.append({
            "city":         item.get("city_name", ""),
            "timestamp":    item.get("timestamp", ""),
            "z_score":      float(item.get("z_score", 0)),
            "current_temp": float(item.get("current_temp", 0)),
            "baseline_temp":float(item.get("baseline_temp", 0)),
            "alert_type":   item.get("alert_type", item.get("metric", "N/A")),
            "detected_at":  item.get("detected_at", ""),
        })
    return pd.DataFrame(rows).sort_values("z_score", key=abs, ascending=False)


def load_baselines_sample():
    tbl  = aws["dynamodb"].Table("weather_baselines")
    resp = tbl.scan(Limit=200)
    items = resp.get("Items", [])
    if not items:
        return pd.DataFrame()
    rows = []
    for item in items:
        rows.append({
            "city":      item.get("city_name", ""),
            "hour":      int(item.get("hour_of_day", 0)),
            "temp_mean": float(item.get("temp_mean", 0)),
            "temp_std":  float(item.get("temp_std",  0)),
            "wind_mean": float(item.get("wind_mean", 0)),
        })
    return pd.DataFrame(rows)


CITY_COORDS = {
    "Dublin": (53.33,-6.25), "London": (51.51,-0.13), "Paris": (48.85,2.35),
    "Berlin": (52.52,13.40), "Madrid": (40.42,-3.70), "Rome": (41.90,12.50),
    "Amsterdam": (52.37,4.90), "Vienna": (48.21,16.37), "Warsaw": (52.23,21.01),
    "Moscow": (55.75,37.62), "Istanbul": (41.01,28.95), "New York": (40.71,-74.01),
    "Los Angeles": (34.05,-118.24), "Chicago": (41.85,-87.65), "Toronto": (43.65,-79.38),
    "Mumbai": (19.07,72.87), "Delhi": (28.61,77.21), "Tokyo": (35.68,139.69),
    "Beijing": (39.90,116.40), "Singapore": (1.35,103.82), "Dubai": (25.20,55.27),
    "Seoul": (37.57,126.98), "Bangkok": (13.75,100.52), "Cairo": (30.06,31.25),
    "Lagos": (6.45,3.40), "Nairobi": (-1.29,36.82), "Sydney": (-33.87,151.21),
    "Melbourne": (-37.81,144.96), "Auckland": (-36.86,174.76),
}

st.title("🌩️ Global Weather Anomaly Detection")
st.caption("Lambda Architecture  |  Kinesis + EMR + Lambda + Athena  |  NCI MSc Cloud Computing")

alerts_df    = load_alerts()
baselines_df = load_baselines_sample()

col1, col2, col3, col4 = st.columns(4)
total_alerts     = len(alerts_df)
hot_alerts       = len(alerts_df[alerts_df["alert_type"].str.contains("HOT|TEMPERATURE|temperature", na=False)]) if not alerts_df.empty else 0
cold_alerts      = total_alerts - hot_alerts
cities_monitored = baselines_df["city"].nunique() if not baselines_df.empty else 0

with col1:
    st.metric("Total Alerts", total_alerts, delta="live")
with col2:
    st.metric("🔴 Heat Anomalies", hot_alerts)
with col3:
    st.metric("🔵 Cold Anomalies", cold_alerts)
with col4:
    st.metric("Cities with Baselines", cities_monitored)

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["🗺️ Anomaly Map", "📋 Live Alerts", "📊 Baselines", "⚡ Benchmarks"])

with tab1:
    st.subheader("City Anomaly Map")
    if not alerts_df.empty:
        map_data = []
        for _, row in alerts_df.iterrows():
            coords = CITY_COORDS.get(row["city"])
            if coords:
                map_data.append({
                    "city":     row["city"],
                    "lat":      coords[0],
                    "lon":      coords[1],
                    "z":        abs(row["z_score"]),
                    "type":     row["alert_type"],
                    "temp":     row["current_temp"],
                    "baseline": row["baseline_temp"],
                })
        if map_data:
            map_df = pd.DataFrame(map_data)
            fig = px.scatter_geo(
                map_df,
                lat="lat", lon="lon",
                color="z",
                size="z",
                hover_name="city",
                hover_data={"temp": ":.1f", "baseline": ":.1f", "type": True, "lat": False, "lon": False},
                color_continuous_scale="RdYlGn_r",
                size_max=30,
                projection="natural earth",
                title="Cities with Weather Anomalies"
            )
            fig.update_layout(
                paper_bgcolor="#0f1117",
                plot_bgcolor="#0f1117",
                font_color="white",
                geo=dict(bgcolor="#0f1117", showland=True, landcolor="#1c1f26",
                         showocean=True, oceancolor="#0d1117",
                         showcoastlines=True, coastlinecolor="#2d3139")
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No coordinate data available for current alerts")
    else:
        st.info("No alerts in DynamoDB yet")

with tab2:
    st.subheader("Live Anomaly Alerts from DynamoDB")
    if not alerts_df.empty:
        display = alerts_df.copy()
        display["z_score"]   = display["z_score"].round(2)
        display["temp_diff"] = (display["current_temp"] - display["baseline_temp"]).round(1)
        st.dataframe(display, use_container_width=True, hide_index=True)

        fig2 = px.bar(
            alerts_df.sort_values("z_score", key=abs, ascending=True),
            x="z_score", y="city", orientation="h",
            color="z_score",
            color_continuous_scale="RdBu_r",
            labels={"z_score": "Z-Score", "city": "City"},
            title="Anomaly Severity per City"
        )
        fig2.add_vline(x=3.0,  line_dash="dash", line_color="red",  annotation_text="+3σ")
        fig2.add_vline(x=-3.0, line_dash="dash", line_color="blue", annotation_text="-3σ")
        fig2.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1c1f26", font_color="white")
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No alerts yet")

with tab3:
    st.subheader("Batch Layer — City Baselines")
    if not baselines_df.empty:
        cities   = sorted(baselines_df["city"].unique())
        selected = st.selectbox("Select city", cities)
        city_df  = baselines_df[baselines_df["city"] == selected].sort_values("hour")

        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(
            x=city_df["hour"], y=city_df["temp_mean"],
            name="Mean temp", mode="lines+markers",
            line=dict(color="#4b9eff", width=2)
        ))
        fig3.add_trace(go.Scatter(
            x=city_df["hour"],
            y=city_df["temp_mean"] + 3 * city_df["temp_std"],
            name="+3σ threshold", mode="lines",
            line=dict(color="#ff4b4b", dash="dash", width=1)
        ))
        fig3.add_trace(go.Scatter(
            x=city_df["hour"],
            y=city_df["temp_mean"] - 3 * city_df["temp_std"],
            name="-3σ threshold", mode="lines",
            line=dict(color="#4b9eff", dash="dash", width=1),
            fill="tonexty", fillcolor="rgba(255,75,75,0.05)"
        ))
        fig3.update_layout(
            title=f"{selected} — Hourly Temperature Baseline",
            xaxis_title="Hour of Day",
            yaxis_title="Temperature (°C)",
            paper_bgcolor="#0f1117",
            plot_bgcolor="#1c1f26",
            font_color="white",
            xaxis=dict(tickmode="linear", tick0=0, dtick=2)
        )
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("No baseline data loaded")

with tab4:
    st.subheader("Performance Benchmarks")
    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("**Batch Layer — EMR Speedup**")
        if os.path.exists("benchmarks/graphs/speedup_graph.png"):
            st.image("benchmarks/graphs/speedup_graph.png", use_column_width=True)
        else:
            st.info("speedup_graph.png not found")

    with col_r:
        st.markdown("**Sequential vs Parallel Producer**")
        if os.path.exists("benchmarks/graphs/sequential_vs_parallel.png"):
            st.image("benchmarks/graphs/sequential_vs_parallel.png", use_column_width=True)
        else:
            st.info("sequential_vs_parallel.png not found")

    if os.path.exists("benchmarks/results/latency_benchmark.csv"):
        st.subheader("Speed Layer — Latency Benchmark")
        df = pd.read_csv("benchmarks/results/latency_benchmark.csv")
        df = df[df["latency_ms"] > 0]
        if not df.empty:
            fig4 = px.bar(
                df, x="rate", y="latency_ms", color="city",
                title="Kinesis to DynamoDB Latency by Load Rate",
                labels={"latency_ms": "Latency (ms)", "rate": "Load Rate"}
            )
            fig4.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1c1f26", font_color="white")
            st.plotly_chart(fig4, use_container_width=True)
            st.dataframe(df, hide_index=True)
    else:
        st.info("Run speed/tests/latency_test.py to generate latency data")

st.divider()
st.caption(f"Last refreshed: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC  |  Rishabh Raghav X25106112  |  Ayush Singh X25129180")
