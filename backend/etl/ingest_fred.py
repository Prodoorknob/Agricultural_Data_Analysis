"""ETL: Ingest US Dollar Index (DXY) from FRED API.

Schedule: Daily, 7:00 AM ET (alongside futures ingest).
API: https://api.stlouisfed.org/fred/series/observations
Series: DTWEXBGS (Trade Weighted USD Index — Broad Goods)
Rate limit: 120 calls/day (free tier) — we use 1 call/day.
Target table: dxy_daily
"""

import sys
from datetime import date, timedelta, datetime

import pandas as pd
import requests
from sqlalchemy.dialects.postgresql import insert

from backend.etl.common import get_env, get_sync_session, setup_logging, log_ingest_summary

logger = setup_logging("ingest_fred")

FRED_API_KEY = get_env("FRED_API_KEY")
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
SERIES_ID = "DTWEXBGS"


def fetch_dxy(start_date: str) -> pd.DataFrame:
    """Fetch DXY observations from FRED since start_date."""
    params = {
        "series_id": SERIES_ID,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start_date,
    }
    logger.info(f"Fetching DXY ({SERIES_ID}) from FRED since {start_date}")
    resp = requests.get(FRED_BASE, params=params, timeout=20)
    resp.raise_for_status()

    observations = resp.json().get("observations", [])
    if not observations:
        logger.warning("No DXY observations returned")
        return pd.DataFrame()

    df = pd.DataFrame(observations)[["date", "value"]]
    df.columns = ["trade_date", "dxy"]
    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    df["dxy"] = pd.to_numeric(df["dxy"], errors="coerce")
    df = df.dropna(subset=["dxy"])
    df["source"] = "fred"

    logger.info(f"  Fetched {len(df)} DXY observations")
    return df


def upsert_dxy(df: pd.DataFrame) -> int:
    """Upsert DXY data into the dxy_daily table. Returns rows affected."""
    if df.empty:
        return 0

    session = get_sync_session()
    try:
        from backend.models.db_tables import DxyDaily

        rows = df.to_dict(orient="records")
        stmt = insert(DxyDaily.__table__).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["trade_date"],
            set_={
                "dxy": stmt.excluded.dxy,
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


def run(lookback_days: int = 14):
    """Main entry point — fetch recent DXY observations."""
    start = datetime.utcnow()
    start_date = (date.today() - timedelta(days=lookback_days)).isoformat()

    df = fetch_dxy(start_date)
    n = upsert_dxy(df)

    log_ingest_summary(logger, "dxy_daily", n, start)


if __name__ == "__main__":
    lookback = int(sys.argv[1]) if len(sys.argv) > 1 else 14
    run(lookback_days=lookback)
