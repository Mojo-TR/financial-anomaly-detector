import os
import pandas as pd
import yfinance as yf
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from pathlib import Path

load_dotenv()
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
engine = create_engine(os.getenv("DATABASE_URL"))

def ingest_prices(tickers, start, end):  
    
    prices = yf.download(tickers, start=start, end=end, group_by='ticker')

    df = pd.DataFrame()
    for tick in tickers:
        temp = prices[tick].copy()
        temp = temp.reset_index()
        temp['Ticker'] = tick
        temp = temp.rename(columns={
            'Date': 'date',
            'Open': 'open',
            'High': 'high',
            'Low': 'low',
            'Close': 'close',
            'Volume': 'volume',
            'Ticker': 'ticker'
        })
        df = pd.concat([df, temp], ignore_index=True)
        
    with engine.connect() as conn:
        for _, row in df.iterrows():
            conn.execute(text("""
                INSERT INTO price_data (ticker, date, open, high, low, close, volume)
                VALUES (:ticker, :date, :open, :high, :low, :close, :volume)
                ON CONFLICT DO NOTHING
            """), row.to_dict())
        conn.commit()
        
    print(f"Inserted {len(df)} rows into price_data")
    
    with engine.connect() as conn:
        result = conn.execute(text("SELECT ticker, COUNT(*) FROM price_data GROUP BY ticker ORDER BY ticker"))
        for row in result:
            print(row)
    
    print(df.head())
    
if __name__ == "__main__":
    tickers = ["AAPL", "MSFT", "JPM", "BAC", "XOM", "CVX", "JNJ", "PFE", "AMZN", "TSLA"]
    ingest_prices(tickers, start="2023-01-01", end="2025-01-01")