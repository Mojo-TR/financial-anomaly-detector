import os
import json
import tempfile
import subprocess
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

engine = create_engine(os.getenv("DATABASE_URL"))

def validate_with_r(ticker: str) -> None:
    # Pull daily returns from features table
    df = pd.read_sql(
        f"SELECT date, daily_return FROM features WHERE ticker = '{ticker}' ORDER BY date",
        engine
    )

    if df.empty:
        print(f"{ticker}: no data in features table, skipping")
        return

    # Write to temp CSV
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        temp_path = f.name
        df.to_csv(f, index=False)

    try:
        # Call R script
        result = subprocess.run(
            ['Rscript', 'r_scripts/statistical_check.R', temp_path],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"{ticker}: R script failed — {result.stderr[-500:]}")
            return

        # Parse JSON output
        r_results = json.loads(result.stdout)
        r_df = pd.DataFrame(r_results)
        r_df['date'] = pd.to_datetime(r_df['date']).dt.date

        # Update alerts table with r_confidence score for matching dates
        anomaly_dates = r_df[r_df['is_anomaly'] == True]

        with engine.connect() as conn:
            updated = 0
            for _, row in anomaly_dates.iterrows():
                res = conn.execute(text("""
                    UPDATE alerts
                    SET r_pvalue = :confidence
                    WHERE ticker = :ticker
                    AND date = :date
                    AND alert_type = 'isolation_forest'
                """), {
                    "confidence": float(row['confidence']),
                    "ticker": ticker,
                    "date": row['date']
                })
                updated += res.rowcount
            conn.commit()

        r_anomaly_count = len(anomaly_dates)
        print(f"{ticker}: R flagged {r_anomaly_count} anomalies, {updated} matched alerts table")

    finally:
        os.unlink(temp_path)

if __name__ == "__main__":
    tickers = ["AAPL", "MSFT", "JPM", "BAC", "XOM", "CVX", "JNJ", "PFE", "AMZN", "TSLA"]
    for ticker in tickers:
        validate_with_r(ticker)