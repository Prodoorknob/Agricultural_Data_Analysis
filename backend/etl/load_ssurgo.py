"""Load SSURGO soil features (AWC, drainage class) via NRCS Soil Data Access API.

Uses the SDA REST API to query county-aggregated soil properties, avoiding the
need to download and parse the full SSURGO national dump.

The SDA API returns results as a list of lists (not dicts), so we must map
column indices manually based on the SELECT clause order.

Usage: python -m backend.etl.load_ssurgo [--dry-run]
"""

import argparse
import csv
import time
from pathlib import Path

import requests
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.etl.common import get_sync_session, setup_logging, log_ingest_summary
from backend.models.db_tables import SoilFeature

logger = setup_logging("load_ssurgo")

SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/SDMTabularService/post.rest"

# USDA drainage class name -> numeric code mapping
DRAIN_CLASS_MAP = {
    "Excessively drained": 1,
    "Somewhat excessively drained": 2,
    "Well drained": 3,
    "Moderately well drained": 4,
    "Somewhat poorly drained": 5,
    "Poorly drained": 6,
    "Very poorly drained": 7,
    "Subaqueous": 8,
}

CENTROIDS_PATH = Path(__file__).parent / "data" / "county_centroids.csv"

# State FIPS -> state abbreviation mapping
STATE_FIPS_TO_ABBR = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY",
}


def _query_sda(sql: str) -> list[list]:
    """Execute a query against the NRCS Soil Data Access API.

    Returns a list of lists (each inner list is a row of column values).
    The SDA API does NOT return column names in its JSON response — only
    the raw Table array of row-arrays.
    """
    payload = {"query": sql, "format": "JSON"}
    resp = requests.post(SDA_URL, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    if "Table" not in data:
        return []
    rows = data["Table"]
    if not rows:
        return []
    return rows


def load_soil_features():
    """Query county-level AWC and drainage class from SDA, one state at a time.

    The SDA SQL query returns 3 columns per row:
      [0] areasymbol  (e.g., "IA001")
      [1] awc_cm      (e.g., "0.1860")
      [2] drain_class_name (e.g., "Well drained")
    """
    # Load county FIPS list for validation
    if not CENTROIDS_PATH.exists():
        logger.error("County centroids not found at %s. Run load_county_centroids.py first.", CENTROIDS_PATH)
        return []

    fips_set = set()
    fips_to_state = {}
    with open(CENTROIDS_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fips_set.add(row["fips"])
            fips_to_state[row["fips"]] = row["state_fips"]

    unique_state_fips = sorted(set(fips_to_state.values()))
    results = []

    for sf in unique_state_fips:
        abbr = STATE_FIPS_TO_ABBR.get(sf)
        if not abbr:
            continue

        sql = f"""
        SELECT
            l.areasymbol,
            CAST(
                SUM(CAST(c.comppct_r AS FLOAT) * ISNULL(CAST(ch.awc_r AS FLOAT), 0))
                / NULLIF(SUM(CAST(c.comppct_r AS FLOAT)), 0)
                AS DECIMAL(6,4)
            ) AS awc_cm,
            (SELECT TOP 1 c2.drainagecl
             FROM component c2
             INNER JOIN mapunit mu2 ON mu2.mukey = c2.mukey
             INNER JOIN legend l2 ON l2.lkey = mu2.lkey
             WHERE l2.areasymbol = l.areasymbol AND c2.drainagecl IS NOT NULL
             ORDER BY c2.comppct_r DESC) AS drain_class_name
        FROM legend l
        INNER JOIN mapunit mu ON mu.lkey = l.lkey
        INNER JOIN component c ON c.mukey = mu.mukey
        LEFT JOIN chorizon ch ON ch.cokey = c.cokey AND ch.hzdept_r = 0
        WHERE l.areasymbol LIKE '{abbr}%'
          AND c.comppct_r IS NOT NULL
        GROUP BY l.areasymbol
        """

        try:
            rows = _query_sda(sql)
            state_count = 0

            for row in rows:
                # SDA returns list of lists: [areasymbol, awc_cm, drain_class_name]
                if not isinstance(row, list) or len(row) < 2:
                    continue

                areasym = str(row[0]).strip()
                awc_str = row[1]
                drain_name = str(row[2]).strip() if len(row) > 2 and row[2] else ""

                # Convert areasymbol (e.g., "IA001") to 5-digit FIPS
                # areasymbol = 2-letter state abbr + 3-digit survey area code
                county_code = areasym[2:] if len(areasym) >= 5 else ""
                fips = sf + county_code.zfill(3) if county_code else None

                if not fips or fips not in fips_set:
                    continue

                # Parse AWC
                try:
                    awc_val = float(awc_str) if awc_str is not None else None
                except (ValueError, TypeError):
                    awc_val = None

                # Map drainage class name to code
                drain_code = DRAIN_CLASS_MAP.get(drain_name)

                results.append({
                    "fips": fips,
                    "awc_cm": awc_val,
                    "drain_class": drain_code,
                })
                state_count += 1

            logger.info("State %s (%s): %d counties from SDA (%d raw rows)", sf, abbr, state_count, len(rows))
        except Exception as exc:
            logger.warning("SDA query failed for state %s (%s): %s", sf, abbr, exc)

        time.sleep(1.5)  # Rate limit between state queries

    return results


def upsert_soil_features(rows: list[dict], dry_run: bool = False) -> int:
    """Upsert soil features to the soil_features table."""
    if dry_run:
        logger.info("DRY RUN: would upsert %d rows", len(rows))
        return 0

    session = get_sync_session()
    count = 0
    try:
        for row in rows:
            stmt = pg_insert(SoilFeature).values(
                fips=row["fips"],
                awc_cm=row["awc_cm"],
                drain_class=row["drain_class"],
            ).on_conflict_do_update(
                index_elements=["fips"],
                set_={
                    "awc_cm": row["awc_cm"],
                    "drain_class": row["drain_class"],
                },
            )
            session.execute(stmt)
            count += 1

        session.commit()
        logger.info("Upserted %d soil feature rows", count)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return count


if __name__ == "__main__":
    import time as _time

    parser = argparse.ArgumentParser(description="Load SSURGO soil features via SDA API")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't write to DB")
    args = parser.parse_args()

    t0 = _time.time()
    rows = load_soil_features()
    logger.info("Retrieved %d county soil records from SDA", len(rows))

    if rows:
        n = upsert_soil_features(rows, dry_run=args.dry_run)
        log_ingest_summary(logger, "soil_features", n, _time.time() - t0)
    else:
        logger.warning("No soil data retrieved. Check SDA API availability.")
