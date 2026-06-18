from prefect import flow, task
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv
from pathlib import Path
import os
import datetime as dt
from prefect.client.schemas.schedules import CronSchedule


load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@task(retries=2, retry_delay_seconds=30, log_prints=True)
def ingest_task(tickers, start, end):
    from src.ingest import ingest_prices
    ingest_prices(tickers, start, end)

@task(log_prints=True)
def feature_task(tickers, prices):
    from src.features import build_features
    build_features(tickers, prices)

@task(log_prints=True)
def model_task(tickers):
    from src.model import train_and_log
    train_and_log(tickers)

@task(log_prints=True)
def validate_r_task(tickers):
    from src.validate_r import validate_with_r
    for t in tickers: 
        validate_with_r(t)

# @task(log_prints=True)
# def alert_task():
#     from src.alerts import generate_alerts
#     generate_alerts()

@flow(name="financial-anomaly-pipeline")
def run_pipeline():
    tickers = ["AAPL", "MSFT", "JPM", "BAC", "XOM", "CVX", "JNJ", "PFE", "AMZN", "TSLA"]
    local_engine = create_engine(os.getenv("DATABASE_URL"))
    ingest_task(tickers, start="2023-01-01", end=dt.date.today().isoformat())
    prices = pd.read_sql("SELECT * FROM price_data", local_engine)
    feature_task(tickers, prices)
    model_task(tickers)
    validate_r_task(tickers)
    
if __name__ == "__main__":
    run_pipeline.serve(
        name="daily-market-close",
        schedule=CronSchedule(cron="30 16 * * 1-5", timezone="America/New_York")
    )