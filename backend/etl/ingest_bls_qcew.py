"""ETL: Bureau of Labor Statistics Quarterly Census of Employment and Wages.

Pulls state-level establishment counts, employment, and average annual wages
for NAICS 111 (Crop Production) and 112 (Animal Production). This fills two
holes in the frontend:

1. Crops-tab OPERATIONS card: NASS only publishes farm-operations data in
   Census years (2017, 2022). QCEW gives us annual cadence between Census
   years — not commodity-specific, but at least accurate state totals.

2. Land-&-Economy labor: NASS WAGE RATE is sparse (Indiana has 30 rows in
   8 years). QCEW publishes avg annual pay for every state-year where any
   payroll was reported, giving dense coverage 1990-present.

Source API: https://data.bls.gov/cew/data/api/{year}/a/industry/{naics}.csv
Public, no auth. One CSV per (year, industry). ~500KB each.

Cadence: refresh annually in March once prior-year data is final (BLS
releases QCEW annual files ~6 months after year-end).
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy.dialects.postgresql import insert

from backend.etl.common import get_sync_session, setup_logging, log_ingest_summary

logger = setup_logging("ingest_bls_qcew")

CACHE_DIR = Path(__file__).resolve().parent / "data" / "qcew"
NAICS_CODES = [111, 112]  # Crop production, Animal production
YEARS = range(2001, 2025)  # matches NASS coverage window
OWNERSHIP = 5               # Private sector only


def _download(year: int, naics: int) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = CACHE_DIR / f"{year}_{naics}.csv"
    if dest.exists() and dest.stat().st_size > 10_000:
        return dest
    url = f"https://data.bls.gov/cew/data/api/{year}/a/industry/{naics}.csv"
    logger.info(f"Downloading QCEW {year}/{naics} from {url}")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest


def _parse(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"area_fips": str})

    # State-level rows: area_fips = SS000 (2-digit state + '000'). County
    # rows are SSCCC. Drop the national row (US000).
    state_mask = df["area_fips"].str.endswith("000") & (df["area_fips"].str.len() == 5)
    state_mask &= df["area_fips"] != "US000"
    rows = df[state_mask & (df["own_code"] == OWNERSHIP)].copy()
    if rows.empty:
        return rows

    rows["state_fips"] = rows["area_fips"].str[:2]
    rows = rows.rename(columns={
        "industry_code": "naics",
        "annual_avg_estabs": "establishments",
        "annual_avg_emplvl": "employment",
        "avg_annual_pay": "avg_annual_pay",
    })
    rows["naics"] = rows["naics"].astype(str)
    # BLS may report 0 (suppressed small establishments). Keep them as 0 —
    # frontend distinguishes between "no data" (null) and "reported zero".
    rows["year"] = rows["year"].astype(int)
    return rows[["state_fips", "year", "naics", "establishments",
                 "employment", "avg_annual_pay"]]


def upsert(rows: pd.DataFrame) -> int:
    if rows.empty:
        return 0
    from backend.models.db_tables import BlsEstablishment

    session = get_sync_session()
    try:
        payload = rows.to_dict(orient="records")
        stmt = insert(BlsEstablishment.__table__).values(payload)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_bls_establishments",
            set_={
                "establishments": stmt.excluded.establishments,
                "employment":     stmt.excluded.employment,
                "avg_annual_pay": stmt.excluded.avg_annual_pay,
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


def run():
    start = datetime.utcnow()
    all_rows: list[pd.DataFrame] = []
    failed: list[tuple[int, int]] = []
    for year in YEARS:
        for naics in NAICS_CODES:
            try:
                path = _download(year, naics)
                rows = _parse(path)
                all_rows.append(rows)
                logger.info(f"  {year}/{naics}: {len(rows)} state rows")
            except requests.HTTPError as e:
                logger.warning(f"  {year}/{naics}: HTTP error ({e}) — skip")
                failed.append((year, naics))
            except Exception as e:
                logger.error(f"  {year}/{naics}: {e}")
                failed.append((year, naics))
    if not all_rows:
        logger.error("no rows fetched")
        sys.exit(1)

    frame = pd.concat(all_rows, ignore_index=True)
    n = upsert(frame)
    log_ingest_summary(logger, "bls_establishments", n, start)

    # Also emit compact parquet for frontend.
    out = Path(__file__).resolve().parent.parent.parent / "pipeline" / "output_overview" / "bls_establishments.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out, index=False, compression="snappy")
    logger.info(f"wrote {out} ({out.stat().st_size:,} bytes, {len(frame):,} rows)")

    if failed:
        logger.warning(f"Skipped {len(failed)} (year, naics) pairs: {failed}")


if __name__ == "__main__":
    run()
