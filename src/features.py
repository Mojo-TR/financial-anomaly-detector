import os
import pandas as pd
from dotenv import load_dotenv
from pathlib import Path
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
engine = create_engine(os.getenv("DATABASE_URL"))

def build_features(tickers: list, prices: pd.DataFrame) -> None:
    
    for ticker in tickers:
        df = prices[prices['ticker'] == ticker].sort_values('date')
        df["daily_return"] = df["close"].pct_change()
        df["rolling_volatility_20d"] = df["daily_return"].rolling(window=20).std()
        df['volume_zscore'] = (df['volume'] - df['volume'].rolling(20).mean()) / df['volume'].rolling(20).std()
        df['price_zscore'] = (df['close'] - df['close'].rolling(20).mean()) / df['close'].rolling(20).std()
        df = df.dropna(subset=['rolling_volatility_20d'])
        df_out = df[['ticker', 'date', 'daily_return', 'rolling_volatility_20d', 'volume_zscore', 'price_zscore']].copy()
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM features WHERE ticker = :ticker"), {"ticker": ticker}).scalar()
            if count == 0:
                df_out.to_sql('features', engine, if_exists='append', index=False)
                print(f"{ticker}: inserted {len(df_out)} rows")
            else:
                print(f"{ticker}: already exists, skipping")
        print(f"{ticker} features shape: {df.shape}")
        print(df.head())
        
if __name__ == "__main__":
    tickers = ["AAPL", "MSFT", "JPM", "BAC", "XOM", "CVX", "JNJ", "PFE", "AMZN", "TSLA"]
    prices = pd.read_sql("SELECT * FROM price_data", engine)
    build_features(tickers, prices)