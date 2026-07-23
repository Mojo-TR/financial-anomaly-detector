import os
import mlflow
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
mlflow.set_tracking_uri(f"sqlite:///{Path(__file__).resolve().parent.parent / 'mlflow.db'}")

st.set_page_config(
    page_title="Financial Anomaly Detector",
    page_icon="📈",
    layout="wide"
)

@st.cache_resource
def get_engine():
    return create_engine(os.getenv("DATABASE_URL"))

@st.cache_data
def get_tickers():
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT DISTINCT ticker FROM price_data"))
            tickers = [row[0] for row in result]
            return tickers
    except Exception as e:
        st.error(f"Could not load tickers: {e}")
        return []
    
@st.cache_data
def get_dates():
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT MIN(date), MAX(date) FROM price_data"))
            min_date, max_date = result.fetchone()
            return min_date, max_date
    except Exception as e:
        st.error(f"Could not load date range: {e}")
        return None, None
    
@st.cache_data
def get_price_data(selected_tickers, start_date, end_date):
    if not selected_tickers:
        return pd.DataFrame()
    try:
        engine = get_engine()
        tickers_str = ", ".join(f"'{ticker}'" for ticker in selected_tickers)
        
        query = text(f"""
            SELECT
                alerts.ticker,
                alerts.date,
                alerts.anomaly_score,
                alerts.is_anomaly,
                alerts.r_pvalue,
                features.volume_zscore,
                price_data.close
            FROM alerts
            INNER JOIN price_data
                ON alerts.ticker = price_data.ticker
                AND alerts.date = price_data.date
            LEFT JOIN features
                ON alerts.ticker = features.ticker
                AND alerts.date = features.date
            WHERE alerts.ticker IN ({tickers_str})
            AND alerts.date BETWEEN :start_date AND :end_date
        """)
        
        return pd.read_sql(query, engine, params={"start_date": start_date, "end_date": end_date})
    except Exception as e:
        st.error(f"Could not load price data: {e}")
        return pd.DataFrame()
    
@st.cache_data
def get_model_metadata():
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT ticker, last_trained, contamination, anomaly_count, 
                       drift_ks_statistic, drift_p_value
                FROM model_metadata
                ORDER BY last_trained DESC
            """))
            rows = result.fetchall()
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame(rows, columns=[
                'ticker', 'last_trained', 'contamination', 
                'anomaly_count', 'drift_ks_statistic', 'drift_p_value'
            ])
    except Exception as e:
        st.error(f"Could not load model metadata: {e}")
        return pd.DataFrame()

def color_rows(row):
    if row["dual_confirmed"]:
        return ["background-color: #3d0000"] * len(row)
    else:
        return ["background-color: #3d3000"] * len(row)
    
st.title("Financial Anomaly Detector")

st.sidebar.header("Database Connection")

engine = get_engine()
available_tickers = get_tickers()
default_tickers = [t for t in ["AAPL", "MSFT"] if t in available_tickers]
selected_tickers = st.sidebar.multiselect("Select Tickers", available_tickers, default=default_tickers)
min_date, max_date = get_dates()

if min_date is None or max_date is None:
    st.warning("No data available in the database.")
    st.stop()

date_range = st.sidebar.date_input("Select Date Range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
show_dual_only = st.sidebar.checkbox("Show only dual-confirmed anomalies")

if len(date_range) != 2:
    st.warning("Please select both a start and end date.")
    st.stop()
    
price_data = get_price_data(selected_tickers, date_range[0], date_range[1])

if not price_data.empty and len(date_range) == 2:
    # Price and Anomaly Plot
    anomaly_fig = go.Figure()

    for ticker in selected_tickers:
        
        ticker_df = price_data[price_data["ticker"] == ticker]
        ticker_df = ticker_df.sort_values("date")
        
        anomaly_fig.add_trace(
            go.Scatter(
                x=ticker_df["date"],
                y=ticker_df["close"],
                mode="lines",
                name=f"{ticker} price",
                customdata=ticker_df[["anomaly_score"]].values,
                hovertemplate="<b>%{x}</b><br>Price: %{y:.2f}<br>Anomaly Score: %{customdata[0]:.3f}<extra></extra>"
            )
        )
        
        if show_dual_only:
            anomaly_df = ticker_df[(ticker_df["is_anomaly"] == True) & (ticker_df["r_pvalue"].notna())]
        else:
            anomaly_df = ticker_df[ticker_df["is_anomaly"] == True]

        anomaly_fig.add_trace(
            go.Scatter(
                x=anomaly_df["date"],
                y=anomaly_df["close"],
                mode="markers",
                name=f"{ticker} anomalies",
                customdata=anomaly_df[["anomaly_score", "r_pvalue", "volume_zscore"]].values,
                hovertemplate="<b>%{x}</b><br>Price: $%{y:.2f}<br>Anomaly Score: %{customdata[0]:.3f}<br>R p-value: %{customdata[1]:.3f}<br>Volume Z-Score: %{customdata[2]:.3f}<extra></extra>" if show_dual_only else "<b>%{x}</b><br>Price: %{y:.2f}<br>Anomaly Score: %{customdata[0]:.3f}<extra></extra>"
            )
        )
        
    anomaly_fig.update_layout(
        title="Stock Prices with Anomalies",
        xaxis_title="Date",
        yaxis_title="Price",
        legend_title="Legend",
        
    )

    st.plotly_chart(anomaly_fig, width='stretch')
    
    heatmap_data = price_data[price_data["is_anomaly"] == True]

    heatmap_df = heatmap_data.pivot_table(
        index="ticker",
        columns="date",
        values="anomaly_score"
    )

    heatmap_fig = go.Figure(data=go.Heatmap(
        z=heatmap_df.values,
        x=heatmap_df.columns,
        y=heatmap_df.index,
        colorscale='Bluered',
        zmin=-1,
        zmax=1,
        colorbar=dict(title="Anomaly Score")
        )
    )

    st.subheader("Anomaly Score Heatmap")
    heatmap_fig.update_layout(
        xaxis_title="Date",
        yaxis_title="Ticker",
        autosize=True,
        height=600,
    )

    st.plotly_chart(heatmap_fig, width='stretch')
    
    alert_df = price_data[price_data["is_anomaly"] == True].copy()
    alert_df["dual_confirmed"] = alert_df["is_anomaly"] & alert_df["r_pvalue"].notna()

    if show_dual_only:
        alert_df = alert_df[alert_df["dual_confirmed"]]
        
    styled_df = alert_df[["ticker", "date", "anomaly_score", "r_pvalue", "dual_confirmed"]].sort_values(by=["date", "ticker"], ascending=[False, True]).style.apply(color_rows, axis=1)

    st.subheader("Alert Log")
    st.dataframe(
        styled_df,
        hide_index=True,
        column_config={
            "ticker": "Ticker",
            "date": "Date",
            "anomaly_score": st.column_config.NumberColumn("Anomaly Score", format="%.3f"),
            "r_pvalue": st.column_config.NumberColumn("R p-value", format="%.3f"),
            "dual_confirmed": st.column_config.CheckboxColumn("Dual Confirmed"),
        }
    )
    
    metadata = get_model_metadata()
    if not metadata.empty:
        latest_run_time = metadata['last_trained'].max()
        avg_drift_ks = metadata['drift_ks_statistic'].mean()
        avg_anomaly_count = metadata['anomaly_count'].mean()
        latest_metadata = metadata.sort_values(
            "last_trained",
            ascending=False
        )
        
        latest_run_time = (
            latest_run_time
            .tz_localize("UTC")
            .tz_convert("America/Chicago")
        )


        contamination = latest_metadata.iloc[0]["contamination"]
        
        st.subheader("Model Metadata")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Last Trained", latest_run_time.strftime("%Y-%m-%d"))
        col2.metric("Contamination", contamination)
        col3.metric("Avg Anomaly Count", f"{avg_anomaly_count:.1f}")
        col4.metric("Avg Drift KS", f"{avg_drift_ks:.3f}")
    else:
        st.subheader("Model Metadata")
        st.info("No model metadata available yet.")
        
    latest_date = price_data['date'].max()
    st.subheader(f"Last Data Refresh: {latest_date}")

elif not selected_tickers:
    st.warning("Please select at least one ticker to display data.")
    
elif price_data.empty:
    st.warning("No data available for the selected tickers and date range.")