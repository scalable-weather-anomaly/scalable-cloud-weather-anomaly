import os
import time
from datetime import datetime, timezone

import boto3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


# -----------------------------
# Streamlit page configuration
# -----------------------------
st.set_page_config(
    page_title="Weather Anomaly Detection",
    page_icon="🌩️",
    layout="wide"
)

st.markdown(
    """
    <style>
        .block-container { padding-top: 1.5rem; }
    </style>
    """,
    unsafe_allow_html=True
)

REGION          = "us-east-1"
ATHENA_DATABASE = "weatheranalytics"
ATHENA_OUTPUT   = "s3://weather-anomaly-ca-2026/serving/"   # Athena query results bucket/prefix


# -----------------------------
# AWS clients (Dynamic session to avoid ExpiredTokenException in Labs)
# -----------------------------
def get_aws():
    """
    Dynamically instantiate Boto3 session to prevent caching expired tokens.
    """
    session = boto3.Session(region_name=REGION)
    return {
        "athena":   session.client("athena"),
        "dynamodb": session.resource("dynamodb"),
    }


# -----------------------------
# Athena helpers
# -----------------------------
def _run_athena_query(query: str) -> pd.DataFrame:
    """Run an Athena query and return a DataFrame."""
    aws = get_aws()
    athena = aws["athena"]

    resp = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": ATHENA_DATABASE},
        ResultConfiguration={"OutputLocation": ATHENA_OUTPUT},
    )
    qid = resp["QueryExecutionId"]

    # Wait for completion
    for _ in range(60):
        status = athena.get_query_execution(QueryExecutionId=qid)
        state = status["QueryExecution"]["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            reason = status["QueryExecution"]["Status"].get("StateChangeReason", "")
            st.error(f"Athena query failed: {reason}")
            return pd.DataFrame()
        time.sleep(1)

    # Fetch all rows
    rows = []
    paginator = athena.get_paginator("get_query_results")
    for page in paginator.paginate(QueryExecutionId=qid):
        rows.extend(page["ResultSet"]["Rows"])

    if len(rows) < 2:
        return pd.DataFrame()

    headers = [c["VarCharValue"] for c in rows[0]["Data"]]
    data = [[c.get("VarCharValue", "") for c in r["Data"]] for r in rows[1:]]

    return pd.DataFrame(data, columns=headers)


@st.cache_data(ttl=30)
def load_serving_view() -> pd.DataFrame:
    """
    Load the full serving-layer view from Athena:
    weatheranalytics.current_weather_anomalies
    """
    query = """
        SELECT
            city_name,
            latitude,
            longitude,
            timestamp,
            current_temperature,
            current_wind_speed,
            temp_mean,
            temp_std,
            wind_mean,
            wind_std,
            temperature_z_score,
            wind_z_score,
            anomaly_status
        FROM weatheranalytics.current_weather_anomalies
    """

    df = _run_athena_query(query)
    if df.empty:
        return df

    # Convert numeric columns
    numeric_cols = [
        "latitude", "longitude",
        "current_temperature", "current_wind_speed",
        "temp_mean", "temp_std",
        "wind_mean", "wind_std",
        "temperature_z_score", "wind_z_score",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    # Filter out records where z-score or map coordinates could not be parsed
    df = df.dropna(subset=["temperature_z_score", "latitude", "longitude"]).copy()
    
    # Compute absolute z-score and guarantee non-NaN values
    df["abs_z"] = df["temperature_z_score"].abs().fillna(0.0)

    return df


@st.cache_data(ttl=60)
def load_baselines_via_athena() -> pd.DataFrame:
    """
    Load city/hour baselines from Athena weather_baselines table.
    """
    query = """
        SELECT
            city_name,
            hour_of_day,
            temp_mean,
            temp_std,
            wind_mean,
            wind_std
        FROM weatheranalytics.weather_baselines
    """

    df = _run_athena_query(query)
    if df.empty:
        return df

    df["hour_of_day"] = pd.to_numeric(df["hour_of_day"], errors="coerce").astype("Int64")
    for col in ["temp_mean", "temp_std", "wind_mean", "wind_std"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.rename(columns={"city_name": "city", "hour_of_day": "hour"})
    return df


# -----------------------------
# DynamoDB helper (speed layer)
# -----------------------------
@st.cache_data(ttl=15)
def load_alerts_from_dynamodb() -> pd.DataFrame:
    """
    Load live speed-layer alerts from DynamoDB weather_alerts.
    """
    aws = get_aws()
    tbl = aws["dynamodb"].Table("weather_alerts")
    resp = tbl.scan()
    items = resp.get("Items", [])
    if not items:
        return pd.DataFrame()

    rows = []
    for item in items:
        z = float(item.get("z_score", 0.0))

        # Classify into HOT/COLD based on z and alert_type/metric
        raw_type = str(item.get("alert_type", item.get("metric", ""))).lower()
        if "temperature" in raw_type or "hot" in raw_type:
            category = "HOT" if z > 0 else "COLD"
        elif "cold" in raw_type:
            category = "COLD"
        else:
            category = "HOT" if z > 0 else "COLD"

        rows.append({
            "city":          item.get("city_name", ""),
            "timestamp":     item.get("timestamp", ""),
            "z_score":       z,
            "current_temp":  float(item.get("current_temp", 0.0)),
            "baseline_temp": float(item.get("baseline_temp", 0.0)),
            "alert_type":    category,
            "detected_at":   item.get("detected_at", ""),
        })

    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df.sort_values("z_score", key=abs, ascending=False)


# -----------------------------
# Top-level layout
# -----------------------------
st.title("🌩️ Global Weather Anomaly Detection")
st.caption("Lambda Architecture  |  Batch + Speed + Serving  |  Athena + DynamoDB")

with st.spinner("Loading Athena serving-layer view..."):
    serving_df = load_serving_view()

baseline_df = load_baselines_via_athena()
alerts_df   = load_alerts_from_dynamodb()


# -----------------------------
# KPI metrics (from Athena view)
# -----------------------------
if not serving_df.empty:
    anomalies = serving_df[serving_df["anomaly_status"] != "NORMAL"]
    total_serving_alerts = len(anomalies)
    hot_anomalies        = len(anomalies[anomalies["temperature_z_score"] > 0])
    cold_anomalies       = len(anomalies[anomalies["temperature_z_score"] < 0])
    cities_monitored     = serving_df["city_name"].nunique()
else:
    total_serving_alerts = hot_anomalies = cold_anomalies = cities_monitored = 0

total_speed_alerts = len(alerts_df) if not alerts_df.empty else 0

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Serving-layer anomalies (Athena)", total_serving_alerts)
with col2:
    st.metric("🔴 Hot anomalies (Athena)", hot_anomalies)
with col3:
    st.metric("🔵 Cold anomalies (Athena)", cold_anomalies)
with col4:
    st.metric("Cities monitored (Athena)", cities_monitored)
with col5:
    st.metric("Speed-layer alerts (DynamoDB)", total_speed_alerts)

st.divider()


# -----------------------------
# Tabs: Map / Athena anomalies / Live DynamoDB alerts / Baselines / Benchmarks
# -----------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🗺️ Serving map (Athena)",
    "📋 Anomalies (Athena)",
    "⚡ Live alerts (DynamoDB)",
    "📊 Batch baselines (Athena)",
    "📈 Benchmarks & drill-down"
])


# --- Tab 1: Anomaly map from Athena ---
with tab1:
    st.subheader("Serving Layer — Global Anomaly Map (Athena current_weather_anomalies)")

    if not serving_df.empty:
        # Get latest record per city
        latest = (
            serving_df.sort_values("timestamp")
                      .groupby("city_name", as_index=False)
                      .tail(1)
                      .copy()
        )

        # Drop any remaining NaNs across map coordinates and metrics, fill abs_z, and add floor offset
        latest = latest.dropna(subset=["latitude", "longitude", "temperature_z_score", "abs_z"])
        latest["abs_z"] = pd.to_numeric(latest["abs_z"], errors="coerce").fillna(0.0)
        
        # Floor value offset (+0.5) to ensure Plotly gets positive non-zero sizes without NaN
        latest["marker_size"] = latest["abs_z"] + 0.5

        if not latest.empty:
            fig = px.scatter_geo(
                latest,
                lat="latitude",
                lon="longitude",
                color="temperature_z_score",
                size="marker_size",
                hover_name="city_name",
                hover_data={
                    "timestamp": True,
                    "current_temperature": ":.1f",
                    "temp_mean": ":.1f",
                    "temperature_z_score": ":.2f",
                    "anomaly_status": True,
                    "latitude": False,
                    "longitude": False,
                    "abs_z": False,
                    "marker_size": False,
                },
                color_continuous_scale="RdBu_r",
                range_color=[-5, 5],
                size_max=24,
                projection="natural earth",
                title="Cities with temperature anomalies (Athena view: raw + baselines)",
            )
            fig.update_layout(
                paper_bgcolor="#0f1117",
                plot_bgcolor="#0f1117",
                font_color="white",
                geo=dict(
                    bgcolor="#0f1117",
                    showland=True, landcolor="#1c1f26",
                    showocean=True, oceancolor="#0d1117",
                    showcoastlines=True, coastlinecolor="#2d3139",
                ),
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f"Showing {len(latest)} cities from current_weather_anomalies Athena view")
        else:
            st.info("No valid geometric data points available to map.")
    else:
        st.info("No data returned from Athena — check weatheranalytics.current_weather_anomalies view.")


# --- Tab 2: Anomaly list (Athena) ---
with tab2:
    st.subheader("Serving Layer — Anomalies from Athena")

    if not serving_df.empty:
        anomalies = serving_df[serving_df["anomaly_status"] != "NORMAL"].copy()
        anomalies["temperature_z_score"] = anomalies["temperature_z_score"].round(2)
        anomalies["current_temperature"]  = anomalies["current_temperature"].round(1)
        anomalies["temp_mean"]            = anomalies["temp_mean"].round(1)

        st.dataframe(
            anomalies[
                ["city_name", "timestamp", "current_temperature",
                 "temp_mean", "temperature_z_score", "anomaly_status"]
            ].sort_values("temperature_z_score", key=abs, ascending=False),
            use_container_width=True,
            hide_index=True,
        )

        # Latest anomaly per city
        latest_anomalies = (
            anomalies.sort_values("timestamp")
                     .groupby("city_name", as_index=False)
                     .tail(1)
        )

        fig2 = px.bar(
            latest_anomalies.sort_values("temperature_z_score", key=abs, ascending=True),
            x="temperature_z_score",
            y="city_name",
            orientation="h",
            color="anomaly_status",
            color_discrete_map={
                "TEMPERATURE_ANOMALY": "#ff4b4b",
                "WIND_ANOMALY": "#ffa500",
                "NORMAL": "#4b9eff",
            },
            labels={"temperature_z_score": "Z-Score", "city_name": "City"},
            title="Anomaly severity per city (latest serving-layer record from Athena)",
        )
        fig2.add_vline(x=3.0,  line_dash="dash", line_color="red",  annotation_text="+3σ")
        fig2.add_vline(x=-3.0, line_dash="dash", line_color="blue", annotation_text="-3σ")
        fig2.update_layout(
            paper_bgcolor="#0f1117",
            plot_bgcolor="#1c1f26",
            font_color="white",
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No anomalies in Athena view yet — check current_weather_anomalies.")


# --- Tab 3: Live speed-layer alerts from DynamoDB ---
with tab3:
    st.subheader("Speed Layer — Live Alerts from DynamoDB (weather_alerts)")

    if not alerts_df.empty:
        display = alerts_df.copy()
        display["z_score"]   = display["z_score"].round(2)
        display["temp_diff"] = (display["current_temp"] - display["baseline_temp"]).round(1)

        st.dataframe(display, use_container_width=True, hide_index=True)

        latest_speed = (
            alerts_df.sort_values("timestamp")
                     .groupby("city", as_index=False)
                     .tail(1)
        )

        fig3 = px.bar(
            latest_speed.sort_values("z_score", key=abs, ascending=True),
            x="z_score",
            y="city",
            orientation="h",
            color="alert_type",
            color_discrete_map={"HOT": "#ff4b4b", "COLD": "#4b9eff"},
            labels={"z_score": "Z-Score", "city": "City"},
            title="Speed-layer anomaly severity per city (latest DynamoDB alert)",
        )
        fig3.add_vline(x=3.0,  line_dash="dash", line_color="red",  annotation_text="+3σ")
        fig3.add_vline(x=-3.0, line_dash="dash", line_color="blue", annotation_text="-3σ")
        fig3.update_layout(
            paper_bgcolor="#0f1117",
            plot_bgcolor="#1c1f26",
            font_color="white",
        )
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("No alerts yet in weather_alerts — wait for Lambda to emit anomalies.")


# --- Tab 4: Baselines (Athena weather_baselines) ---
with tab4:
    st.subheader("Batch Layer — City Baselines from Athena (weather_baselines)")

    if not baseline_df.empty:
        cities = sorted(baseline_df["city"].dropna().unique())
        selected = st.selectbox("Select city", cities)
        city_df = baseline_df[baseline_df["city"] == selected].sort_values("hour")

        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(
            x=city_df["hour"],
            y=city_df["temp_mean"],
            name="Mean temp",
            mode="lines+markers",
            line=dict(color="#4b9eff", width=2),
        ))
        fig4.add_trace(go.Scatter(
            x=city_df["hour"],
            y=city_df["temp_mean"] + 3 * city_df["temp_std"],
            name="+3σ",
            mode="lines",
            line=dict(color="#ff4b4b", dash="dash", width=1),
        ))
        fig4.add_trace(go.Scatter(
            x=city_df["hour"],
            y=city_df["temp_mean"] - 3 * city_df["temp_std"],
            name="-3σ",
            mode="lines",
            line=dict(color="#4b9eff", dash="dash", width=1),
            fill="tonexty",
            fillcolor="rgba(255,75,75,0.05)",
        ))
        fig4.update_layout(
            title=f"{selected} — Hourly Temperature Baseline (batch layer via Athena)",
            xaxis_title="Hour of Day",
            yaxis_title="Temperature (°C)",
            paper_bgcolor="#0f1117",
            plot_bgcolor="#1c1f26",
            font_color="white",
            xaxis=dict(tickmode="linear", tick0=0, dtick=2),
        )
        st.plotly_chart(fig4, use_container_width=True)

        c1, c2, c3 = st.columns(3)
        with c1:
            coldest = city_df.loc[city_df["temp_mean"].idxmin(), "hour"]
            st.metric("Coldest hour", f"{int(coldest):02d}:00")
        with c2:
            warmest = city_df.loc[city_df["temp_mean"].idxmax(), "hour"]
            st.metric("Warmest hour", f"{int(warmest):02d}:00")
        with c3:
            st.metric("Avg wind mean", f"{city_df['wind_mean'].mean():.1f} km/h")
    else:
        st.info("No baselines found via Athena — check weatheranalytics.weather_baselines.")


# --- Tab 5: Benchmarks & Athena drill-down ---
with tab5:
    st.subheader("Performance Benchmarks")

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("**Batch Layer — EMR Speedup**")
        if os.path.exists("benchmarks/graphs/speedup_graph.png"):
            st.image("benchmarks/graphs/speedup_graph.png", use_container_width=True)
        else:
            st.info("speedup_graph.png not found (generate from batch benchmarks).")

    with col_r:
        st.markdown("**Sequential vs Parallel Producer**")
        if os.path.exists("benchmarks/graphs/sequential_vs_parallel.png"):
            st.image("benchmarks/graphs/sequential_vs_parallel.png", use_container_width=True)
        else:
            st.info("sequential_vs_parallel.png not found (generate from producer benchmark).")

    latency_csv = "benchmarks/results/latency_benchmark.csv"
    if os.path.exists(latency_csv):
        st.subheader("Speed Layer — Latency Benchmark")
        df_lat = pd.read_csv(latency_csv)
        valid = df_lat[df_lat["latency_ms"] > 0].copy()
        if not valid.empty:
            valid["latency_s"] = (valid["latency_ms"] / 1000).round(1)
            fig5 = px.bar(
                valid,
                x="rate",
                y="latency_s",
                color="city",
                barmode="group",
                title="Kinesis → Lambda → DynamoDB Latency (seconds)",
                labels={"latency_s": "Latency (seconds)", "rate": "Load rate (records/sec)"},
            )
            fig5.add_hline(
                y=300,
                line_dash="dash",
                line_color="orange",
                annotation_text="Lambda batch window (300s)",
            )
            fig5.update_layout(
                paper_bgcolor="#0f1117",
                plot_bgcolor="#1c1f26",
                font_color="white",
            )
            st.plotly_chart(fig5, use_container_width=True)

            summary = valid.groupby("rate")["latency_s"].agg(["mean", "min", "max"]).round(1)
            summary.columns = ["Avg (s)", "Min (s)", "Max (s)"]
            st.dataframe(summary, use_container_width=True)
    else:
        st.info("Run speed/tests/latency_test.py to generate latency_benchmark.csv.")

    st.subheader("Serving Layer — Athena Drill-down Query")
    st.caption("Joins S3 raw weather records with batch baselines to show current vs normal.")

    if st.button("Run Athena high-z-score query"):
        with st.spinner("Running Athena drill-down query..."):
            query = """
                SELECT city_name, timestamp, current_temperature,
                       temp_mean, temp_std, temperature_z_score, anomaly_status
                FROM weatheranalytics.current_weather_anomalies
                ORDER BY abs(temperature_z_score) DESC
                LIMIT 20
            """
            df_top = _run_athena_query(query)
            if not df_top.empty:
                for col in ["temperature_z_score", "current_temperature", "temp_mean", "temp_std"]:
                    df_top[col] = pd.to_numeric(df_top[col], errors="coerce")

                df_top["temperature_z_score"] = df_top["temperature_z_score"].round(2)
                df_top["current_temperature"]  = df_top["current_temperature"].round(1)
                df_top["temp_mean"]            = df_top["temp_mean"].round(1)
                df_top["temp_std"]             = df_top["temp_std"].round(1)

                st.dataframe(df_top, use_container_width=True, hide_index=True)

                anomalies = df_top[df_top["anomaly_status"] != "NORMAL"]
                if not anomalies.empty:
                    fig6 = px.bar(
                        anomalies,
                        x="city_name",
                        y="temperature_z_score",
                        color="anomaly_status",
                        color_discrete_map={
                            "TEMPERATURE_ANOMALY": "#ff4b4b",
                            "WIND_ANOMALY": "#ffa500",
                        },
                        title="Athena serving view — temperature anomalies by city",
                        labels={"temperature_z_score": "Z-Score", "city_name": "City"},
                    )
                    fig6.add_hline(y=3.0,  line_dash="dash", line_color="red")
                    fig6.add_hline(y=-3.0, line_dash="dash", line_color="blue")
                    fig6.update_layout(
                        paper_bgcolor="#0f1117",
                        plot_bgcolor="#1c1f26",
                        font_color="white",
                    )
                    st.plotly_chart(fig6, use_container_width=True)
                    st.success(f"{len(anomalies)} anomalies detected by Athena serving layer")
            else:
                st.warning("No results — check Athena tables and view definitions.")


# -----------------------------
# Footer
# -----------------------------
st.divider()
st.caption(
    f"Refreshed: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC  "
    "|  Rishabh X25106112  |  Ayush X25129180")