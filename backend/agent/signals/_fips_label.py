"""FIPS code → human-readable label helpers.

Used in signal headlines so a labelling reviewer doesn't have to look up
"FIPS 40047" to know it's Cherokee County, OK.

Source: backend/etl/data/county_centroids.csv (Census Gazetteer dump).
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

_CENTROIDS_CSV = Path(__file__).resolve().parents[2] / "etl" / "data" / "county_centroids.csv"


# Two-letter USPS abbreviations keyed by 2-digit state FIPS.
STATE_FIPS_TO_ABBREV: dict[str, str] = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA",
    "08": "CO", "09": "CT", "10": "DE", "11": "DC", "12": "FL",
    "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN",
    "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME",
    "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS",
    "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI",
    "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
    "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI",
    "56": "WY", "60": "AS", "66": "GU", "69": "MP", "72": "PR",
    "78": "VI",
    "00": "US",
}


@lru_cache(maxsize=1)
def _county_index() -> dict[str, tuple[str, str]]:
    """Return {fips5: (county_name, state_fips2)} loaded from the centroids CSV."""
    if not _CENTROIDS_CSV.exists():
        return {}
    out: dict[str, tuple[str, str]] = {}
    with _CENTROIDS_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fips = row.get("fips", "").zfill(5)
            if len(fips) == 5:
                out[fips] = (
                    row.get("county_name", "") or f"County FIPS {fips}",
                    row.get("state_fips", "") or fips[:2],
                )
    return out


def county_label(fips5: str) -> str:
    """5-digit county FIPS → 'Cherokee County, OK'. Falls back gracefully."""
    if not fips5:
        return ""
    fips5 = fips5.zfill(5)
    idx = _county_index()
    info = idx.get(fips5)
    if info is None:
        return f"FIPS {fips5}"
    county_name, state_fips = info
    state = STATE_FIPS_TO_ABBREV.get(state_fips, "")
    return f"{county_name}, {state}" if state else county_name


def state_label(fips2: str) -> str:
    """2-digit state FIPS → 'Iowa' (full name) or 'IA' falls back to 'FIPS NN'."""
    abbrev = STATE_FIPS_TO_ABBREV.get(fips2)
    if abbrev is None:
        return f"FIPS {fips2}"
    # Reverse to full name via the existing dict in acreage_features.
    try:
        from backend.features.acreage_features import FIPS_TO_STATE
    except Exception:
        return abbrev
    return FIPS_TO_STATE.get(fips2, abbrev)


def state_abbrev(fips2: str) -> str:
    """2-digit state FIPS → 'IA'."""
    return STATE_FIPS_TO_ABBREV.get(fips2, fips2)
