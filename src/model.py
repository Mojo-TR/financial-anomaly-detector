import os
import pandas as pd
import mlflow
import mlflow.sklearn
from dotenv import load_dotenv
from pathlib import Path
from sqlalchemy import create_engine, text
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from scipy.stats import ks_2samp

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

mlflow.set_tracking_uri(
    f"sqlite:///{Path(__file__).resolve().parent.parent / 'mlflow.db'}"
)

engine = create_engine(os.getenv("DATABASE_URL"))

def get_previous_scores(ticker):
    """Pull anomaly scores from the last run stored in alerts table."""
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT anomaly_score FROM alerts WHERE ticker = :ticker AND alert_type = 'isolation_forest'"
        ), {"ticker": ticker})
        rows = result.fetchall()
    return [r[0] for r in rows] if rows else []

def train_and_log(tickers):
    mlflow.set_experiment("financial_anomaly_detection")

    for ticker in tickers:
        df = pd.read_sql(
            f"SELECT ticker, date, daily_return, rolling_volatility_20d, volume_zscore, price_zscore FROM features WHERE ticker = '{ticker}'",
            engine
        )

        X = df[['daily_return', 'rolling_volatility_20d', 'volume_zscore', 'price_zscore']]

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        with mlflow.start_run(run_name=f"{ticker}_isolation_forest"):
            contamination = 0.05
            n_estimators = 100
            mlflow.log_param("ticker", ticker)
            mlflow.log_param("contamination", contamination)
            mlflow.log_param("n_estimators", n_estimators)

            model = IsolationForest(contamination=contamination, n_estimators=n_estimators, random_state=42)
            model.fit(X_scaled)

            df['anomaly_score'] = model.decision_function(X_scaled)
            df['is_anomaly'] = model.predict(X_scaled) == -1

            anomaly_count = int(df['is_anomaly'].sum())
            mlflow.log_metric("anomaly_count", anomaly_count)
            mlflow.log_metric("anomaly_pct", anomaly_count / len(df))

            # Drift monitoring — compare new scores against previous run in alerts
            stat = 0.0
            p_value = 1.0

            previous_scores = get_previous_scores(ticker)
            if previous_scores:
                stat, p_value = ks_2samp(previous_scores, df['anomaly_score'].tolist())
                mlflow.log_metric("drift_ks_statistic", stat)
                mlflow.log_metric("drift_p_value", p_value)
                if p_value < 0.05:
                    print(f"⚠️  {ticker}: drift detected (KS={stat:.3f}, p={p_value:.4f})")
                else:
                    print(f"✅ {ticker}: no drift detected (KS={stat:.3f}, p={p_value:.4f})")
            else:
                mlflow.log_metric("drift_ks_statistic", 0.0)
                mlflow.log_metric("drift_p_value", 1.0)
                print(f"📊 {ticker}: no previous scores — drift check skipped (baseline run)")

            mlflow.sklearn.log_model(model, "isolation_forest_model")

            # Write to alerts (duplicate-safe)
            df_out = df[['ticker', 'date', 'anomaly_score', 'is_anomaly']].copy()
            df_out['alert_type'] = 'isolation_forest'
            with engine.connect() as conn:
                for _, row in df_out.iterrows():
                    conn.execute(text("""
                        INSERT INTO alerts (ticker, date, anomaly_score, is_anomaly, alert_type)
                        VALUES (:ticker, :date, :anomaly_score, :is_anomaly, :alert_type)
                        ON CONFLICT (ticker, date, alert_type) DO NOTHING
                    """), row.to_dict())
                conn.commit()

            print(f"{ticker}: {anomaly_count} anomalies logged")
            
        # Write metadata to Supabase-accessible table
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO model_metadata 
                    (
                        ticker,
                        last_trained,
                        contamination,
                        anomaly_count,
                        drift_ks_statistic,
                        drift_p_value
                    )
                VALUES 
                    (
                        :ticker,
                        NOW(),
                        :contamination,
                        :anomaly_count,
                        :drift_ks_statistic,
                        :drift_p_value
                    )
            """), {
                "ticker": ticker,
                "contamination": float(contamination),
                "anomaly_count": int(anomaly_count),
                "drift_ks_statistic": float(stat),
                "drift_p_value": float(p_value)
            })
        conn.commit()

if __name__ == "__main__":
    tickers = ["AAPL", "MSFT", "JPM", "BAC", "XOM", "CVX", "JNJ", "PFE", "AMZN", "TSLA"]
    train_and_log(tickers)