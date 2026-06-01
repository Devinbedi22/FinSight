import os
from datetime import datetime

import pandas as pd
import yfinance as yf

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
COMPANIES_CSV = os.path.join(DATA_DIR, "companies.csv")
NEWS_CSV = os.path.join(DATA_DIR, "news.csv")

HARDCODED_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "NFLX", "AMD", "INTC",
    "JPM", "GS", "V", "MA", "AXP", "WMT", "COST", "UNH", "KO", "PEP",
]


def build_companies_csv():
    """Create data/companies.csv from a hardcoded list of large-cap tickers."""
    companies = pd.DataFrame({"Symbol": HARDCODED_TICKERS})
    companies.to_csv(COMPANIES_CSV, index=False)
    return companies


def fetch_yfinance_news(ticker, max_news=20):
    """Fetch recent headlines from yfinance for a ticker."""
    result = []
    try:
        info = yf.Ticker(ticker)
        news_items = info.news
    except Exception:
        return result

    for item in news_items[:max_news]:
        title = item.get("title")
        ts = item.get("providerPublishTime")
        if not title or not ts:
            continue
        date = datetime.utcfromtimestamp(int(ts)).date().isoformat()
        result.append({"date": date, "stock": ticker, "title": title})
    return result


def build_news_csv(companies, max_news_per_ticker=15):
    """Create data/news.csv with yfinance headlines for each company."""
    rows = []
    for ticker in companies["Symbol"].tolist():
        rows.extend(fetch_yfinance_news(ticker, max_news=max_news_per_ticker))

    if not rows:
        raise RuntimeError(
            "No news rows were fetched. Verify internet access or use a public news dataset instead."
        )

    news_df = pd.DataFrame(rows)
    news_df = news_df.drop_duplicates(subset=["date", "stock", "title"])
    news_df.to_csv(NEWS_CSV, index=False)
    return news_df


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    companies = build_companies_csv()
    print(f"Created {COMPANIES_CSV} with {len(companies)} tickers")
    news = build_news_csv(companies, max_news_per_ticker=10)
    print(f"Created {NEWS_CSV} with {len(news)} rows")


if __name__ == "__main__":
    main()
