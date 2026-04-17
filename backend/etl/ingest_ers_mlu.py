"""ETL: USDA ERS Major Land Uses (MLU) — state-level, 1945-2017.

The MLU dataset partitions every state's land into six mutually-exclusive
categories (cropland, grassland pasture & range, forest-use land, urban,
special uses, other). Each category ships as its own xlsx file; this ETL
downloads six files, parses each, joins them on (state, year), and writes
to the ``land_use_categories`` RDS table + a parquet aggregate the
frontend Land & Economy tab reads via S3.

Cadence: refresh annually in January once ERS publishes the prior-year
update. The dataset is nominally 5-year (Census years) but ERS
back-extrapolates intercensus years for urban area.

Source landing page:
    https://www.ers.usda.gov/data-products/major-land-uses
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

logger = setup_logging("ingest_ers_mlu")

CACHE_DIR = Path(__file__).resolve().parent / "data" / "mlu"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# (category name, media_id, slug). ERS's URL slug is verbose; must match exactly.
MLU_FILES = [
    ("cropland", 5640, "cropland-1945-2017-by-state-the-sum-of-cropland-used-for-crops-cropland-idled-and-cropland-used-for-pasture"),
    ("pasture",  5642, "grassland-pasture-and-range-1945-2017-by-state-grassland-and-other-nonforested-pasture-and-range-in-farms-plus-estimates-of-open-or-nonforested-grazing-lands-not-in-farms-does-not-include-cropland-used-for-pasture-or-forest-land-grazed"),
    ("forest",   5641, "total-forest-use-land-1945-2017-by-state-the-sum-of-forest-use-land-grazed-and-forest-use-land-not-grazed"),
    ("special",  5644, "total-special-uses-1945-2017-by-state-the-sum-of-land-in-rural-transportation-rural-parks-and-wildlife-defense-and-industrial-plus-miscellaneous-farm-and-other-special-uses"),
    ("urban",    5652, "urban-area-1945-2017-by-state-densely-populated-areas-with-at-least-50000-people-urbanized-areas-and-densely-populated-areas-with-2500-to-50000-people-urban-clusters-intercensus-years-are-extrapolated"),
    ("other",    5643, "all-other-land-uses-1945-2017-by-state"),
]

# Ordered list of region rollups that appear as section breaks in each
# workbook. Rows matching these must be skipped so the melt returns only
# state-level entries. States come between region headers.
REGION_NAMES = {
    "Northeast", "Lake States", "Corn Belt", "Northern Plains",
    "Appalachian", "Southeast", "Delta States", "Southern Plains",
    "Mountain", "Pacific", "Alaska", "Hawaii", "48 States",
    "United States",
}

# Map ERS state names → 2-letter codes. Includes the handful that
# differ from a simple title-case lookup (handled uniformly here).
_STATE_NAME_TO_CODE = {
    "Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA",
    "Colorado":"CO","Connecticut":"CT","Delaware":"DE","Florida":"FL","Georgia":"GA",
    "Hawaii":"HI","Idaho":"ID","Illinois":"IL","Indiana":"IN","Iowa":"IA",
    "Kansas":"KS","Kentucky":"KY","Louisiana":"LA","Maine":"ME","Maryland":"MD",
    "Massachusetts":"MA","Michigan":"MI","Minnesota":"MN","Mississippi":"MS",
    "Missouri":"MO","Montana":"MT","Nebraska":"NE","Nevada":"NV","New Hampshire":"NH",
    "New Jersey":"NJ","New Mexico":"NM","New York":"NY","North Carolina":"NC",
    "North Dakota":"ND","Ohio":"OH","Oklahoma":"OK","Oregon":"OR","Pennsylvania":"PA",
    "Rhode Island":"RI","South Carolina":"SC","South Dakota":"SD","Tennessee":"TN",
    "Texas":"TX","Utah":"UT","Vermont":"VT","Virginia":"VA","Washington":"WA",
    "West Virginia":"WV","Wisconsin":"WI","Wyoming":"WY",
}

_STATE_CODE_TO_FIPS = {
    "AL":"01","AK":"02","AZ":"04","AR":"05","CA":"06","CO":"08","CT":"09","DE":"10",
    "FL":"12","GA":"13","HI":"15","ID":"16","IL":"17","IN":"18","IA":"19","KS":"20",
    "KY":"21","LA":"22","ME":"23","MD":"24","MA":"25","MI":"26","MN":"27","MS":"28",
    "MO":"29","MT":"30","NE":"31","NV":"32","NH":"33","NJ":"34","NM":"35","NY":"36",
    "NC":"37","ND":"38","OH":"39","OK":"40","OR":"41","PA":"42","RI":"44","SC":"45",
    "SD":"46","TN":"47","TX":"48","UT":"49","VT":"50","VA":"51","WA":"53","WV":"54",
    "WI":"55","WY":"56",
}


def _download(category: str, media_id: int, slug: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = CACHE_DIR / f"{category}.xlsx"
    url = f"https://www.ers.usda.gov/media/{media_id}/{slug}.xlsx"
    logger.info(f"Downloading {category} from {url}")
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    # ERS's "not found" HTML response is ~30KB; smaller legitimate xlsx
    # files (like the special-uses summary) are ~20KB. Detect the HTML
    # error response explicitly rather than by size.
    if r.content[:4] != b"PK\x03\x04":
        raise FileNotFoundError(
            f"{category}: download returned {len(r.content)} bytes but not a ZIP/xlsx "
            f"(got: {r.content[:16]!r}). Media ID {media_id} slug may have changed — "
            "re-scrape from https://www.ers.usda.gov/data-products/major-land-uses."
        )
    dest.write_bytes(r.content)
    return dest


def _parse_mlu_sheet(path: Path, category: str) -> pd.DataFrame:
    """Parse one MLU xlsx into long-format rows (state_fips, year, acres)."""
    df = pd.read_excel(path, sheet_name=0, header=None)

    # Row 1 is the header row: [label, 1945, 1949, ...]. Some sheets have
    # footnote suffixes on the year cells like "1969 /2" or "2002 6/, 7/" —
    # extract the leading 4-digit year with a regex rather than float-cast.
    import re
    year_re = re.compile(r"(19\d{2}|20\d{2})")

    header = df.iloc[1]
    year_cols: dict[int, int] = {}
    for col_idx, val in enumerate(header):
        text = str(val)
        m = year_re.search(text)
        if m:
            year_cols[col_idx] = int(m.group(1))

    records: list[dict] = []
    for i in range(2, len(df)):
        label = str(df.iloc[i, 0]).strip()
        if not label or label in REGION_NAMES or label.startswith("Source") or label.startswith("Note"):
            continue
        code = _STATE_NAME_TO_CODE.get(label)
        if code is None:
            continue
        fips = _STATE_CODE_TO_FIPS[code]
        for col_idx, year in year_cols.items():
            raw = df.iloc[i, col_idx]
            try:
                val = float(raw)
            except (TypeError, ValueError):
                continue
            if pd.isna(val):
                continue
            # Values are in 1000 acres — convert to acres for consistency with
            # NASS area rows across the app.
            records.append({
                "state_fips": fips,
                "state_alpha": code,
                "year": year,
                "category": category,
                "acres": val * 1000,
            })

    out = pd.DataFrame.from_records(records)
    logger.info(f"  {category}: parsed {len(out):,} rows "
                f"(years {out['year'].min()}-{out['year'].max()}, "
                f"{out['state_alpha'].nunique()} states)" if not out.empty else f"  {category}: no rows")
    return out


def fetch_all() -> pd.DataFrame:
    frames = []
    for cat, media_id, slug in MLU_FILES:
        try:
            path = _download(cat, media_id, slug)
            frames.append(_parse_mlu_sheet(path, cat))
        except Exception as e:
            logger.error(f"{cat}: {e}")
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def upsert(rows: pd.DataFrame) -> int:
    if rows.empty:
        return 0
    from backend.models.db_tables import LandUseCategory

    session = get_sync_session()
    try:
        payload = rows.to_dict(orient="records")
        stmt = insert(LandUseCategory.__table__).values(payload)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_land_use_categories",
            set_={"acres": stmt.excluded.acres,
                  "state_alpha": stmt.excluded.state_alpha},
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
    frame = fetch_all()
    if frame.empty:
        logger.error("no rows parsed")
        sys.exit(1)

    n = upsert(frame)
    log_ingest_summary(logger, "land_use_categories", n, start)

    # Also write a single compact parquet for the frontend.
    out_parquet = Path(__file__).resolve().parent.parent.parent / "pipeline" / "output_overview" / "land_use.parquet"
    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out_parquet, index=False, compression="snappy")
    logger.info(f"wrote {out_parquet} ({out_parquet.stat().st_size:,} bytes, {len(frame):,} rows)")


if __name__ == "__main__":
    run()
