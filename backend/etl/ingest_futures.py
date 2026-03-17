"""ETL: Ingest CME futures daily settlement prices from Nasdaq Data Link.

Schedule: Daily, 7:00 AM ET (after CME close).
API: https://data.nasdaq.com/api/v3/datasets/CHRIS/CME_{code}.json
Rate limit: 50 calls/day (free tier) — we use 3 calls/day.
Target table: futures_daily
"""

import sys
from datetime import date, timedelta, datetime

import pandas as pd
import requests
from sqlalchemy.dialects.postgresql import insert

from backend.etl.common import get_env, get_sync_session, setup_logging, log_ingest_summary

logger = setup_logging("ingest_futures")

NASDAQ_DL_API_KEY = get_env("NASDAQ_DL_API_KEY")

# Nearest continuous contract tickers
TICKER_MAP = {
    "corn": "CHRIS/CME_C1",
    "soybean": "CHRIS/CME_S1",
    "wheat": "CHRIS/CME_W1",
}

API_BASE = "https://data.nasdaq.com/api/v3/datasets"


def infer_contract_month(commodity: str, trade_date: date) -> str:
    """Infer the nearest active contract month for a commodity.

    CME contract months:
      Corn:    Mar(H), May(K), Jul(N), Sep(U), Dec(Z)
      Soybean: Jan(F), Mar(H), May(K), Jul(N), Aug(Q), Sep(U), Nov(X)
      Wheat:   Mar(H), May(K), Jul(N), Sep(U), Dec(Z)

    Returns the next contract month as 'YYYY-MM' from trade_date.
    """
    contract_months = {
        "corn": [3, 5, 7, 9, 12],
        "soybean": [1, 3, 5, 7, 8, 9, 11],
        "wheat": [3, 5, 7, 9, 12],
    }
    months = contract_months[commodity]
    year = trade_date.year
    for m in months:
        if m >= trade_date.month:
            return f"{year}-{m:02d}"
    # Wrap to next year
    return f"{year + 1}-{months[0]:02d}"


def fetch_futures(commodity: str, start_date: str) -> pd.DataFrame:
    """Fetch daily settlement prices for a commodity from Nasdaq Data Link."""
    ticker = TICKER_MAP[commodity]
    url = f"{API_BASE}/{ticker}.json"
    params = {
        "api_key": NASDAQ_DL_API_KEY,
        "start_date": start_date,
    }
    logger.info(f"Fetching {commodity} futures from {ticker} since {start_date}")
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()

    dataset = resp.json()["dataset"]
    columns = [c.lower().replace(" ", "_") for c in dataset["column_names"]]
    df = pd.DataFrame(dataset["data"], columns=columns)

    if df.empty:
        logger.warning(f"No data returned for {commodity} since {start_date}")
        return pd.DataFrame()

    # Standardize column names — Nasdaq Data Link CHRIS datasets use:
    # Date, Open, High, Low, Last, Change, Settle, Volume, Previous Day Open Interest
    col_map = {}
    for c in columns:
        if c == "date":
            col_map[c] = "trade_date"
        elif "settle" in c:
            col_map[c] = "settlement"
        elif "volume" in c:
            col_map[c] = "volume"
        elif "open_interest" in c or "previous_day_open_interest" in c:
            col_map[c] = "open_interest"

    df = df.rename(columns=col_map)

    # Keep only the columns we need
    keep = ["trade_date", "settlement", "volume", "open_interest"]
    available = [c for c in keep if c in df.columns]
    df = df[available].copy()

    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["settlement"] = pd.to_numeric(df["settlement"], errors="coerce")
    df = df.dropna(subset=["settlement"])

    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype("Int64")
    if "open_interest" in df.columns:
        df["open_interest"] = pd.to_numeric(df["open_interest"], errors="coerce").astype("Int64")

    df["commodity"] = commodity
    df["contract_month"] = df["trade_date"].apply(lambda d: infer_contract_month(commodity, d))
    df["source"] = "nasdaq_dl"

    return df


def upsert_futures(df: pd.DataFrame) -> int:
    """Upsert futures data into the futures_daily table. Returns rows affected."""
    if df.empty:
        return 0

    session = get_sync_session()
    try:
        from backend.models.db_tables import FuturesDaily

        rows = df.to_dict(orient="records")
        stmt = insert(FuturesDaily.__table__).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_futures_daily",
            set_={
                "settlement": stmt.excluded.settlement,
                "volume": stmt.excluded.volume,
                "open_interest": stmt.excluded.open_interest,
                "ingest_ts": datetime.utcnow(),
            },
        )
        result = session.execute(stmt)
        session.commit()
        return result.rowcount
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run(lookback_days: int = 7):
    """Main entry point — fetch last N days of futures for all commodities."""
    start = datetime.utcnow()
    start_date = (date.today() - timedelta(days=lookback_days)).isoformat()
    total_rows = 0

    for commodity in TICKER_MAP:
        try:
            df = fetch_futures(commodity, start_date)
            n = upsert_futures(df)
            total_rows += n
            logger.info(f"  {commodity}: {n} rows upserted ({len(df)} fetched)")
        except requests.HTTPError as e:
            logger.error(f"  {commodity}: HTTP error — {e}")
            raise
        except Exception as e:
            logger.error(f"  {commodity}: unexpected error — {e}")
            raise

    log_ingest_summary(logger, "futures_daily", total_rows, start)


if __name__ == "__main__":
    lookback = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    run(lookback_days=lookback)
