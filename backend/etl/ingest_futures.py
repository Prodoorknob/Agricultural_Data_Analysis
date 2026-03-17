"""ETL: Ingest CME futures daily settlement prices via Yahoo Finance.

Schedule: Daily, 7:00 AM ET (after CME close).
Source: Yahoo Finance (free, no API key required).
Target table: futures_daily
"""

import sys
from datetime import date, timedelta, datetime, timezone

import pandas as pd
import yfinance as yf
from sqlalchemy.dialects.postgresql import insert

from backend.etl.common import get_sync_session, setup_logging, log_ingest_summary

logger = setup_logging("ingest_futures")

# Yahoo Finance continuous front-month futures tickers
TICKER_MAP = {
    "corn": "ZC=F",
    "soybean": "ZS=F",
    "wheat": "ZW=F",
}


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
    """Fetch daily futures prices for a commodity from Yahoo Finance."""
    ticker = TICKER_MAP[commodity]
    logger.info("Fetching %s futures from %s since %s", commodity, ticker, start_date)

    df = yf.download(ticker, start=start_date, auto_adjust=True, progress=False)

    if df.empty:
        logger.warning("No data returned for %s since %s", commodity, start_date)
        return pd.DataFrame()

    # yfinance returns: Open, High, Low, Close, Volume
    # Close is the settlement price for continuous contracts
    df = df.reset_index()

    # Handle multi-level columns from yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] if col[1] == "" or col[1] == ticker else col[0] for col in df.columns]

    df = df.rename(columns={
        "Date": "trade_date",
        "Close": "settlement",
        "Volume": "volume",
    })

    keep = ["trade_date", "settlement", "volume"]
    available = [c for c in keep if c in df.columns]
    df = df[available].copy()

    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["settlement"] = pd.to_numeric(df["settlement"], errors="coerce")
    df = df.dropna(subset=["settlement"])

    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype("Int64")

    # Yahoo Finance doesn't provide open interest in daily bars
    df["open_interest"] = pd.NA

    df["commodity"] = commodity
    df["contract_month"] = df["trade_date"].apply(lambda d: infer_contract_month(commodity, d))
    df["source"] = "yahoo_finance"

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
                "ingest_ts": datetime.now(timezone.utc),
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
    start = datetime.now(timezone.utc)
    start_date = (date.today() - timedelta(days=lookback_days)).isoformat()
    total_rows = 0

    for commodity in TICKER_MAP:
        try:
            df = fetch_futures(commodity, start_date)
            n = upsert_futures(df)
            total_rows += n
            logger.info(f"  {commodity}: {n} rows upserted ({len(df)} fetched)")
        except Exception as e:
            logger.error("  %s: error — %s", commodity, e)
            raise

    log_ingest_summary(logger, "futures_daily", total_rows, start)


if __name__ == "__main__":
    lookback = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    run(lookback_days=lookback)
