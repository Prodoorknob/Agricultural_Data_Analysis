"""Backfill USDM county-level drought history into a single parquet cache.

For every (state, year) in the requested range, fetches all weekly USDM
observations from the public CountyStatistics API in one request. Output
goes to ``backend/etl/data/drought_history.parquet`` with columns
``[fips, date, none_pct, d0_pct, d1_pct, d2_pct, d3_pct, d4_pct, d3d4_pct]``.

This is the cache that ``train_yield.load_drought_history()`` reads. Without
it, the new yield models train (and serve) without the
``drought_d3d4_pct`` feature — see
research/yield-model-nc-2024-investigation.md for why it matters (NC corn
2024 outlier signal washed out by state-level fall-aggregated drought).

Usage:
    python -m backend.etl.backfill_drought_history
    python -m backend.etl.backfill_drought_history --year-start 2018 --year-end 2025
    python -m backend.etl.backfill_drought_history --growing-season-only

Notes:
- The CountyStatistics endpoint takes a state ABBREVIATION ("NC", "IA", ...)
  in the ``aoi`` param, not a numeric FIPS, and returns lower-case JSON
  fields. State FIPS-numeric requests return empty. We loop the abbreviation
  list and ask each one for an entire year's growing season at once, so
  total calls ≈ 50 × n_years (~10 min at 0.5s throttle, vs ~5 hours if we
  iterated per-Thursday).
- Re-running is idempotent: existing parquet rows for a given (fips, date)
  are overwritten on output.
"""

import argparse
import time as _time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from backend.etl.common import setup_logging

logger = setup_logging("backfill_drought")

USDM_API_BASE = (
    "https://usdmdataservices.unl.edu/api/CountyStatistics/"
    "GetDroughtSeverityStatisticsByAreaPercent"
)
DEFAULT_OUTPUT = Path(__file__).parent / "data" / "drought_history.parquet"

STATE_ABBREVS = [
    "AL", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI",
    "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY",
    "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
]


def _format_usdm_date(d: date) -> str:
    """USDM API expects m/d/yyyy with no zero-padding."""
    return f"{d.month}/{d.day}/{d.year}"


def fetch_state_year(state_abbrev: str, year: int, growing_season_only: bool) -> list[dict]:
    """Fetch every weekly USDM snapshot for one (state, year)."""
    if growing_season_only:
        start = date(year, 4, 1)
        end = date(year, 10, 31)
    else:
        start = date(year, 1, 1)
        end = date(year, 12, 31)

    params = {
        "aoi": state_abbrev,
        "startdate": _format_usdm_date(start),
        "enddate": _format_usdm_date(end),
        "statisticsType": "1",
    }
    try:
        resp = requests.get(
            USDM_API_BASE,
            params=params,
            timeout=120,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json() or []
    except requests.RequestException as exc:
        logger.warning("USDM fetch failed for %s %d: %s", state_abbrev, year, exc)
        return []

    rows = []
    for entry in data:
        # API returns lowercase JSON: fips, mapDate, none, d0..d4
        fips = str(entry.get("fips") or entry.get("FIPS") or "").zfill(5)
        if len(fips) != 5:
            continue
        map_date = entry.get("mapDate") or entry.get("MapDate") or entry.get("validStart")
        if not map_date:
            continue
        try:
            dt = pd.Timestamp(str(map_date).split("T")[0])
        except (ValueError, TypeError):
            continue

        d3 = float(entry.get("d3", entry.get("D3", 0)) or 0)
        d4 = float(entry.get("d4", entry.get("D4", 0)) or 0)
        rows.append({
            "fips": fips,
            "date": dt,
            "none_pct": float(entry.get("none", entry.get("None", 0)) or 0),
            "d0_pct": float(entry.get("d0", entry.get("D0", 0)) or 0),
            "d1_pct": float(entry.get("d1", entry.get("D1", 0)) or 0),
            "d2_pct": float(entry.get("d2", entry.get("D2", 0)) or 0),
            "d3_pct": d3,
            "d4_pct": d4,
            "d3d4_pct": d3 + d4,
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill USDM drought history parquet cache")
    parser.add_argument("--year-start", type=int, default=2000)
    parser.add_argument("--year-end", type=int, default=date.today().year)
    parser.add_argument("--growing-season-only", action="store_true",
                        help="Only fetch Apr-Oct observations")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--throttle", type=float, default=0.5,
                        help="Seconds between API requests")
    parser.add_argument("--states", default="all",
                        help="Comma-separated state abbreviations, or 'all'")
    args = parser.parse_args()

    states = STATE_ABBREVS if args.states == "all" else [s.strip().upper() for s in args.states.split(",")]
    years = list(range(args.year_start, args.year_end + 1))
    n_calls = len(states) * len(years)
    logger.info(
        "Backfilling %d state-years (%d states × %d years, growing_season_only=%s, throttle=%.1fs) -> %s",
        n_calls, len(states), len(years), args.growing_season_only, args.throttle, args.output,
    )

    all_rows: list[dict] = []
    t0 = _time.time()
    n_done = 0
    for state in states:
        for year in years:
            rows = fetch_state_year(state, year, args.growing_season_only)
            all_rows.extend(rows)
            n_done += 1
            if n_done % 50 == 0 or n_done == n_calls:
                logger.info(
                    "  %d/%d state-years fetched (%.1fs elapsed, %d rows so far)",
                    n_done, n_calls, _time.time() - t0, len(all_rows),
                )
            if args.throttle > 0:
                _time.sleep(args.throttle)

    if not all_rows:
        logger.error("No rows fetched. Aborting (parquet not written).")
        return

    df = pd.DataFrame(all_rows).drop_duplicates(subset=["fips", "date"], keep="last")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    if args.output.exists():
        try:
            old = pd.read_parquet(args.output)
            combined = pd.concat([old, df], ignore_index=True)
            df = combined.drop_duplicates(subset=["fips", "date"], keep="last")
        except Exception as exc:
            logger.warning("Could not merge with existing parquet (%s); overwriting", exc)

    df.to_parquet(args.output, index=False)
    logger.info(
        "Wrote %d rows (%d counties, %d dates) to %s in %.1fs",
        len(df),
        df["fips"].nunique(),
        df["date"].nunique(),
        args.output,
        _time.time() - t0,
    )


if __name__ == "__main__":
    main()
