import os
import sys
import pandas as pd

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
ANALYST_PROCESSED = os.path.join(DATA_DIR, "analyst_ratings_processed.csv")
RAW_ANALYST = os.path.join(DATA_DIR, "raw_analyst_ratings.csv")
RAW_PARTNER = os.path.join(DATA_DIR, "raw_partner_headlines.csv")
NEWS_CSV = os.path.join(DATA_DIR, "news.csv")
COMPANIES_CSV = os.path.join(DATA_DIR, "companies.csv")

REQUIRED_NEWS_COLUMNS = {"title", "date", "stock"}


def find_columns(columns):
    """Return a dict mapping required lower-case names to actual column names if present."""
    lower_map = {c.lower(): c for c in columns}
    mapping = {}
    for req in REQUIRED_NEWS_COLUMNS:
        if req in lower_map:
            mapping[req] = lower_map[req]
    return mapping


def build_from_analyst_processed():
    if not os.path.exists(ANALYST_PROCESSED):
        return False

    # inspect header only to find columns
    try:
        header = pd.read_csv(ANALYST_PROCESSED, nrows=0)
    except Exception as e:
        print(f"Failed reading header of {ANALYST_PROCESSED}: {e}")
        return False

    mapping = find_columns(header.columns)
    if set(mapping.keys()) != REQUIRED_NEWS_COLUMNS:
        print(f"analyst_ratings_processed.csv missing required columns. Found: {list(header.columns)}")
        return False

    # read only needed columns (use the actual names)
    usecols = [mapping[c] for c in ["title", "date", "stock"]]
    try:
        df = pd.read_csv(ANALYST_PROCESSED, usecols=usecols)
    except Exception as e:
        print(f"Failed to read required columns from {ANALYST_PROCESSED}: {e}")
        return False

    # normalize column names to exactly what notebook expects
    df = df.rename(columns={mapping["title"]: "title", mapping["date"]: "date", mapping["stock"]: "stock"})

    # Ensure no index column sneaks in
    if "Unnamed: 0" in df.columns:
        df = df.drop(columns=[c for c in df.columns if c.startswith("Unnamed")])

    # Drop rows with missing date or title or stock
    df = df.dropna(subset=["date", "title", "stock"]).copy()

    # Curated universe
    curated = [
        "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","NFLX","AMD","INTC",
        "JPM","GS","V","MA","AXP","WMT","COST","UNH","KO","PEP",
    ]

    # normalize stock column to uppercase strings for matching
    df["stock"] = df["stock"].astype(str).str.upper()
    available = sorted(set(df["stock"].unique()) & set(curated))

    # filter df to only curated symbols present in the dataset
    df_filtered = df[df["stock"].isin(available)].copy()

    # Reorder columns to date, stock, title
    df_filtered = df_filtered[["date", "stock", "title"]]

    # write out
    df_filtered.to_csv(NEWS_CSV, index=False)

    # companies.csv: curated symbols present
    companies = pd.DataFrame({"Symbol": available})
    companies.to_csv(COMPANIES_CSV, index=False)

    # compute date range for printing
    try:
        dates = pd.to_datetime(df_filtered["date"], errors="coerce", utc=True)
        dates = dates.dropna()
        if not dates.empty:
            min_date = dates.min().strftime('%Y-%m-%d')
            max_date = dates.max().strftime('%Y-%m-%d')
        else:
            min_date = max_date = "N/A"
    except Exception:
        min_date = max_date = "N/A"

    print(f"Selected companies: {len(available)}")
    print(f"News rows retained: {len(df_filtered)}")
    print(f"Date range: {min_date} to {max_date}")

    print(f"Wrote {NEWS_CSV} ({len(df_filtered)} rows) and {COMPANIES_CSV} ({len(companies)} symbols) from {ANALYST_PROCESSED}")

    return True


def fallback_from_raw_partner():
    # try to use raw_partner_headlines.csv if present; attempt to find columns
    if not os.path.exists(RAW_PARTNER):
        return False
    try:
        header = pd.read_csv(RAW_PARTNER, nrows=0)
    except Exception as e:
        print(f"Failed reading header of {RAW_PARTNER}: {e}")
        return False

    mapping = find_columns(header.columns)
    if set(mapping.keys()) != REQUIRED_NEWS_COLUMNS:
        print(f"raw_partner_headlines.csv missing required columns. Found: {list(header.columns)}")
        return False

    usecols = [mapping[c] for c in ["title", "date", "stock"]]
    try:
        df = pd.read_csv(RAW_PARTNER, usecols=usecols)
    except Exception as e:
        print(f"Failed to read required columns from {RAW_PARTNER}: {e}")
        return False

    df = df.rename(columns={mapping["title"]: "title", mapping["date"]: "date", mapping["stock"]: "stock"})
    df = df.dropna(subset=["date", "title", "stock"]).copy()
    df = df[["date", "stock", "title"]]
    df.to_csv(NEWS_CSV, index=False)
    symbols = pd.Series(df["stock"].unique()).astype(str)
    companies = pd.DataFrame({"Symbol": symbols})
    companies.to_csv(COMPANIES_CSV, index=False)
    print(f"Wrote {NEWS_CSV} and {COMPANIES_CSV} from {RAW_PARTNER}")
    return True


def fallback_from_raw_analyst():
    if not os.path.exists(RAW_ANALYST):
        return False
    try:
        header = pd.read_csv(RAW_ANALYST, nrows=0)
    except Exception as e:
        print(f"Failed reading header of {RAW_ANALYST}: {e}")
        return False

    mapping = find_columns(header.columns)
    if set(mapping.keys()) != REQUIRED_NEWS_COLUMNS:
        print(f"raw_analyst_ratings.csv missing required columns. Found: {list(header.columns)}")
        return False

    usecols = [mapping[c] for c in ["title", "date", "stock"]]
    try:
        df = pd.read_csv(RAW_ANALYST, usecols=usecols)
    except Exception as e:
        print(f"Failed to read required columns from {RAW_ANALYST}: {e}")
        return False

    df = df.rename(columns={mapping["title"]: "title", mapping["date"]: "date", mapping["stock"]: "stock"})
    df = df.dropna(subset=["date", "title", "stock"]).copy()
    df = df[["date", "stock", "title"]]
    df.to_csv(NEWS_CSV, index=False)
    symbols = pd.Series(df["stock"].unique()).astype(str)
    companies = pd.DataFrame({"Symbol": symbols})
    companies.to_csv(COMPANIES_CSV, index=False)
    print(f"Wrote {NEWS_CSV} and {COMPANIES_CSV} from {RAW_ANALYST}")
    return True


def validate_outputs():
    # attempt to load the files the notebook will read
    try:
        news = pd.read_csv(NEWS_CSV)
        companies = pd.read_csv(COMPANIES_CSV)
    except Exception as e:
        print(f"Validation failed reading output CSVs: {e}")
        return False

    # check columns
    if not set([c.lower() for c in news.columns]).issuperset({"date", "stock", "title"}):
        print(f"news.csv has incorrect columns: {list(news.columns)}")
        return False
    if "Symbol" not in companies.columns:
        print(f"companies.csv missing 'Symbol' column: {list(companies.columns)}")
        return False

    print(f"Validation succeeded: news rows={len(news)}, companies symbols={len(companies)}")
    return True


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)

    # Primary: use analyst_ratings_processed.csv
    ok = build_ok = build_from_analyst_processed()
    if not ok:
        print("Primary source failed or lacks required columns; attempting fallbacks...")
        ok = fallback_from_raw_partner() or fallback_from_raw_analyst()

    if not ok:
        print("Failed to build news.csv and companies.csv from provided datasets. Exiting.")
        sys.exit(2)

    valid = validate_outputs()
    if not valid:
        print("Created files but validation failed. Exiting.")
        sys.exit(3)

    print("prepare_dataset.py completed successfully.")
