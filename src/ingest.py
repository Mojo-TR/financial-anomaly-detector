import os
import pandas as pd
import plotly.express as px
import yfinance as yf
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from pathlib import Path

load_dotenv()
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
engine = create_engine(os.getenv("DATABASE_URL"))

def ingest_prices(tickers, start, end):  
    
    prices = yf.download(tickers, start=start, end=end, group_by='ticker')

    frames = []
    for tick in tickers:
        temp = prices[tick].copy()
        temp = temp.reset_index()
        temp.columns = [col.lower() for col in temp.columns]
        temp['ticker'] = tick
        temp = temp[['ticker', 'date', 'open', 'high', 'low', 'close', 'volume']]
        frames.append(temp)
    
    df_out = pd.concat(frames, ignore_index=True)
    df_out['date'] = pd.to_datetime(df_out['date']).dt.date
    
    df_out.to_sql('price_data', engine, if_exists='append', index=False)
    print(f"Inserted {len(df_out)} rows into price_data")
    
    with engine.connect() as conn:
        result = conn.execute(text("SELECT ticker, COUNT(*) FROM price_data GROUP BY ticker ORDER BY ticker"))
        for row in result:
            print(row)

if __name__ == "__main__":
    tickers = ["AAPL", "MSFT", "JPM", "BAC", "XOM", "CVX", "JNJ", "PFE", "AMZN", "TSLA"]
    ingest_prices(tickers, start="2023-01-01", end="2025-01-01")