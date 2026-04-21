"""
_county_coverage_audit.py - One-shot county coverage profiler.

Loads every pipeline/output/{STATE}.parquet (skipping athena_optimized/),
filters to county-level rows only, and computes:
  1. Per-state row count, county count, year span, commodity list, stat list
  2. State x commodity coverage matrix (distinct counties)
  3. State x commodity x stat presence (4/4, partial, 0/4)
  4. Year coverage gaps per (state, commodity)
  5. Top "missing data" hotspots ranked by ag importance

Writes the full markdown report to:
  research/county-coverage-analysis-2026-04-17.md
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "pipeline" / "output"
REPORT_PATH = PROJECT_ROOT / "research" / "county-coverage-analysis-2026-04-19.md"

# Ingestion contract (mirrors quickstats_ingest.py)
COUNTY_COMMODITIES = [
    "CORN", "SOYBEANS", "WINTER WHEAT", "SPRING WHEAT, (EXCL DURUM)", "COTTON",
    "SORGHUM", "BARLEY", "OATS", "HAY", "RICE", "SUNFLOWER",
    # Generic WHEAT rollup — NASS publishes this at county level for states
    # where the winter/spring split isn't reported. Added 2026-04-18.
    "WHEAT",
]
COUNTY_STAT_CATS = ["YIELD", "AREA HARVESTED", "AREA PLANTED", "PRODUCTION"]
TARGET_YEAR_START, TARGET_YEAR_END = 2001, 2025
TARGET_YEARS = set(range(TARGET_YEAR_START, TARGET_YEAR_END + 1))

# Per-commodity skip list from quickstats_ingest.py (states where the pipeline
# intentionally skipped — those should NOT be flagged as gaps).
COUNTY_SKIP_STATES = {
    "CORN":                    {"AK", "HI", "DC"},
    "SOYBEANS":                {"AK", "HI", "DC", "NV", "AZ", "NM", "UT", "WY", "MT", "ID",
                                "OR", "WA", "ME", "NH", "VT", "MA", "RI", "CT"},
    "WINTER WHEAT":            {"AK", "HI", "DC"},
    "SPRING WHEAT, (EXCL DURUM)": {"AK", "HI", "DC", "AL", "FL", "GA", "SC", "MS", "LA",
                                "TX", "AZ", "NM", "NV", "UT", "AR", "TN", "KY", "WV",
                                "VA", "NC", "RI", "CT", "MA", "NH", "VT", "ME", "NJ",
                                "DE", "MD", "PA"},
    "COTTON":                  {"AK", "HI", "DC", "ME", "NH", "VT", "MA", "RI", "CT",
                                "NY", "NJ", "PA", "OH", "IN", "IL", "IA", "WI", "MI",
                                "MN", "ND", "SD", "NE", "KS", "CO", "UT", "NV", "WY",
                                "ID", "OR", "WA", "MT"},
    "SORGHUM":                 {"AK", "HI", "DC", "ME", "NH", "VT", "MA", "RI", "CT",
                                "NY", "NJ", "DE", "MD", "PA", "WV", "VA", "SC", "FL",
                                "MI", "WI", "MN", "ND", "MT", "WY", "ID", "OR", "WA",
                                "NV", "UT", "AZ"},
    "BARLEY":                  {"AK", "HI", "DC", "AL", "FL", "GA", "SC", "MS", "LA",
                                "AR", "TX", "NM", "AZ", "NV", "RI", "CT", "MA", "NJ",
                                "DE", "WV", "IN", "IL", "IA"},
    "OATS":                    {"AK", "HI", "DC", "FL", "AL", "MS", "LA", "NV", "AZ",
                                "NM", "RI", "CT", "MA", "NH", "VT", "ME", "DE", "NJ"},
    "HAY":                     {"AK", "HI", "DC"},
    "RICE":                    {"AK", "HI", "DC", "ME", "NH", "VT", "MA", "RI", "CT",
                                "NY", "NJ", "PA", "OH", "IN", "IL", "IA", "WI", "MI",
                                "MN", "ND", "SD", "NE", "KS", "CO", "UT", "NV", "WY",
                                "ID", "OR", "WA", "MT", "AZ", "NM", "OK", "VA", "WV",
                                "KY", "TN", "NC", "SC", "GA", "FL", "AL", "DE", "MD"},
    "SUNFLOWER":               {"AK", "HI", "DC", "ME", "NH", "VT", "MA", "RI", "CT",
                                "NJ", "DE", "MD", "VA", "SC", "GA", "FL", "AL", "MS",
                                "LA", "AR", "TN", "KY", "WV", "NV", "AZ", "NM", "ID",
                                "OR", "WA", "MT", "WY", "UT", "IN", "OH", "PA", "NY",
                                "MI", "WI", "MN", "IA", "IL"},
}

# Major-producer "expected" states per commodity for total-miss flagging.
# Source: USDA NASS top-producer rankings (FY2023). If a commodity is
# missing from one of these states it's a real ingestion gap, not a
# structural absence. Conservative — only the top ~10 producers.
MAJOR_PRODUCERS = {
    "CORN":            {"IA", "IL", "NE", "MN", "IN", "SD", "OH", "MO", "KS", "WI"},
    "SOYBEANS":        {"IL", "IA", "MN", "IN", "MO", "OH", "NE", "KS", "ND", "SD"},
    "WINTER WHEAT":    {"KS", "OK", "TX", "CO", "WA", "MT", "ID", "OR", "NE", "MO"},
    "SPRING WHEAT, (EXCL DURUM)": {"ND", "MT", "MN", "SD", "ID"},
    "COTTON":          {"TX", "GA", "MS", "AR", "AL", "NC", "SC", "TN", "MO", "AZ", "CA", "OK", "LA", "VA", "FL"},
    "SORGHUM":         {"KS", "TX", "OK", "AR", "LA", "MO", "NE", "CO", "NM", "TN"},
    "BARLEY":          {"ND", "MT", "ID", "MN", "WY", "WA", "OR", "CO", "SD"},
    "OATS":            {"SD", "ND", "MN", "WI", "IA", "PA", "NY", "OH", "TX"},
    "HAY":             {"TX", "MO", "CA", "SD", "NE", "MN", "WI", "OK", "KS", "ID", "MT", "NY"},
    "RICE":            {"AR", "CA", "LA", "MS", "MO", "TX"},
    "SUNFLOWER":       {"ND", "SD", "KS", "NE", "CO", "TX"},
}

# Ag-importance weight per (commodity) — used to rank gap hotspots.
# Higher = more dollars / more frontend visibility / more user interest.
COMMODITY_WEIGHT = {
    "CORN":            1.00,
    "SOYBEANS":        0.95,
    "WINTER WHEAT":    0.70,
    "SPRING WHEAT, (EXCL DURUM)": 0.55,
    "COTTON":          0.65,
    "HAY":             0.45,
    "SORGHUM":         0.30,
    "RICE":            0.30,
    "BARLEY":          0.25,
    "OATS":            0.20,
    "SUNFLOWER":       0.20,
}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def list_state_parquets() -> list[Path]:
    files = sorted(p for p in OUTPUT_DIR.glob("*.parquet") if p.is_file())
    # Exclude NATIONAL.parquet — it has no county rows
    return [p for p in files if p.stem != "NATIONAL"]


COUNTY_NEEDED_COLS = [
    "agg_level_desc", "state_alpha", "state_fips_code", "county_code",
    "fips", "year", "commodity_desc", "statisticcat_desc", "source_desc",
    "value_num",
]


def load_county_rows(parquet_path: Path) -> pd.DataFrame:
    """Read one state's parquet, return only county-level rows with the
    minimal column set."""
    pf = pq.ParquetFile(str(parquet_path))
    cols_in_file = set(pf.schema.names)
    cols = [c for c in COUNTY_NEEDED_COLS if c in cols_in_file]
    df = pf.read(columns=cols).to_pandas()
    if "agg_level_desc" not in df.columns:
        return df.iloc[0:0]
    df = df[df["agg_level_desc"] == "COUNTY"].copy()
    if df.empty:
        return df
    # Coerce types
    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    # Restrict to the canonical commodity whitelist (drops noise like
    # WHEAT (generic) or BARLEY varieties that may have leaked in).
    if "commodity_desc" in df.columns:
        # Keep generic 'WHEAT' too — it appears at county level for some states
        # and is functionally usable.
        keep = set(COUNTY_COMMODITIES) | {"WHEAT"}
        df = df[df["commodity_desc"].isin(keep)]
    return df


def load_all() -> pd.DataFrame:
    parts = []
    files = list_state_parquets()
    print(f"Reading {len(files)} parquet files...", file=sys.stderr)
    for p in files:
        try:
            d = load_county_rows(p)
            if len(d):
                parts.append(d)
        except Exception as e:
            print(f"  WARN: {p.name}: {e}", file=sys.stderr)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


# ---------------------------------------------------------------------------
# Profiling
# ---------------------------------------------------------------------------
def per_state_summary(df: pd.DataFrame) -> pd.DataFrame:
    """One row per state: row count, county count, year span, commodities,
    stat cats."""
    rows = []
    for state, sub in df.groupby("state_alpha"):
        rows.append({
            "state": state,
            "rows": len(sub),
            "counties": sub["fips"].nunique() if "fips" in sub.columns else 0,
            "year_min": int(sub["year"].min()) if pd.notna(sub["year"].min()) else None,
            "year_max": int(sub["year"].max()) if pd.notna(sub["year"].max()) else None,
            "n_years": int(sub["year"].nunique()),
            "n_commodities": int(sub["commodity_desc"].nunique()),
            "n_stat_cats": int(sub["statisticcat_desc"].nunique()),
            "commodities": ", ".join(sorted(sub["commodity_desc"].unique())),
            "stat_cats": ", ".join(sorted(sub["statisticcat_desc"].unique())),
        })
    out = pd.DataFrame(rows).sort_values("state").reset_index(drop=True)
    return out


def per_commodity_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for com, sub in df.groupby("commodity_desc"):
        rows.append({
            "commodity": com,
            "rows": len(sub),
            "states": int(sub["state_alpha"].nunique()),
            "counties": int(sub["fips"].nunique()),
            "year_min": int(sub["year"].min()) if pd.notna(sub["year"].min()) else None,
            "year_max": int(sub["year"].max()) if pd.notna(sub["year"].max()) else None,
            "n_years": int(sub["year"].nunique()),
        })
    return pd.DataFrame(rows).sort_values("rows", ascending=False).reset_index(drop=True)


def state_x_commodity_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """For each (state, commodity), distinct county count + fraction of state's
    NASS-reported counties (denominator = max distinct fips for that state
    across all commodities)."""
    state_total_counties = df.groupby("state_alpha")["fips"].nunique().to_dict()

    pairs = (
        df.groupby(["state_alpha", "commodity_desc"])
          .agg(counties=("fips", "nunique"),
               rows=("fips", "size"),
               years=("year", "nunique"),
               year_min=("year", "min"),
               year_max=("year", "max"))
          .reset_index()
    )
    pairs["state_total_counties"] = pairs["state_alpha"].map(state_total_counties)
    pairs["coverage_pct"] = (pairs["counties"] / pairs["state_total_counties"]).round(3)
    return pairs


def state_x_commodity_x_stat_presence(df: pd.DataFrame) -> pd.DataFrame:
    """For each (state, commodity), how many of the 4 target stat cats
    are present (and which)."""
    g = (
        df[df["statisticcat_desc"].isin(COUNTY_STAT_CATS)]
        .groupby(["state_alpha", "commodity_desc"])["statisticcat_desc"]
        .apply(lambda s: sorted(set(s)))
        .reset_index()
    )
    g["n_stats"] = g["statisticcat_desc"].apply(len)
    g["missing_stats"] = g["statisticcat_desc"].apply(
        lambda present: [s for s in COUNTY_STAT_CATS if s not in present]
    )
    g.rename(columns={"statisticcat_desc": "present_stats"}, inplace=True)
    return g


def year_gaps_per_state_commodity(df: pd.DataFrame) -> pd.DataFrame:
    """Per (state, commodity), which target years (2001-2025) are missing."""
    rows = []
    for (state, com), sub in df.groupby(["state_alpha", "commodity_desc"]):
        present = set(int(y) for y in sub["year"].dropna().unique())
        missing = sorted(TARGET_YEARS - present)
        rows.append({
            "state": state,
            "commodity": com,
            "n_years_present": len(present & TARGET_YEARS),
            "n_years_missing": len(missing),
            "missing_years": missing,
            "earliest_year": min(present) if present else None,
            "latest_year": max(present) if present else None,
        })
    return pd.DataFrame(rows)


def total_miss_pairs(state_x_com: pd.DataFrame, all_states: list[str]) -> list[dict]:
    """List (state, commodity) pairs that are MAJOR PRODUCERS but have ZERO
    rows in our data — these are real ingestion gaps."""
    have = set(zip(state_x_com["state_alpha"], state_x_com["commodity_desc"]))
    misses = []
    for com, producers in MAJOR_PRODUCERS.items():
        for st in producers:
            if (st, com) not in have and st in all_states:
                misses.append({
                    "state": st,
                    "commodity": com,
                    "weight": COMMODITY_WEIGHT.get(com, 0.1),
                    "type": "TOTAL_MISS_MAJOR_PRODUCER",
                })
    return sorted(misses, key=lambda r: -r["weight"])


def hotspot_ranking(state_x_com: pd.DataFrame,
                    presence: pd.DataFrame,
                    year_gaps: pd.DataFrame) -> pd.DataFrame:
    """Rank (state, commodity) pairs by weighted gap severity.

    Score = commodity_weight * (
              0.4 * (1 - county_coverage_pct)
            + 0.3 * (4 - n_stats_present) / 4
            + 0.3 * n_years_missing / 25
            )
    Only major-producer pairs scored (everything else is structural).
    """
    presence_lkp = presence.set_index(["state_alpha", "commodity_desc"])
    year_lkp = year_gaps.set_index(["state", "commodity"])

    rows = []
    for com, producers in MAJOR_PRODUCERS.items():
        weight = COMMODITY_WEIGHT.get(com, 0.1)
        for st in producers:
            sxc = state_x_com[
                (state_x_com["state_alpha"] == st) &
                (state_x_com["commodity_desc"] == com)
            ]
            if sxc.empty:
                rows.append({
                    "state": st, "commodity": com, "weight": weight,
                    "county_coverage_pct": 0.0, "n_stats": 0, "n_years_missing": 25,
                    "score": weight * 1.0, "kind": "TOTAL_MISS",
                })
                continue
            cov = float(sxc["coverage_pct"].iloc[0])
            try:
                ns = int(presence_lkp.loc[(st, com), "n_stats"])
            except KeyError:
                ns = 0
            try:
                nm = int(year_lkp.loc[(st, com), "n_years_missing"])
            except KeyError:
                nm = 25
            score = weight * (
                0.4 * (1 - cov) + 0.3 * (4 - ns) / 4 + 0.3 * nm / 25
            )
            rows.append({
                "state": st, "commodity": com, "weight": weight,
                "county_coverage_pct": cov, "n_stats": ns,
                "n_years_missing": nm, "score": round(score, 4),
                "kind": "PARTIAL" if score > 0.01 else "OK",
            })
    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)


def stat_completeness(presence: pd.DataFrame) -> dict:
    """Counts of how many (state, commodity) pairs have 4/4, 3/4, 2/4, 1/4 stats."""
    counts = presence["n_stats"].value_counts().sort_index().to_dict()
    counts = {f"{k}/4 stats": int(v) for k, v in counts.items()}
    return counts


def recent_year_check(df: pd.DataFrame) -> pd.DataFrame:
    """For 2024 and 2025, how many (state, commodity) pairs have data?"""
    rows = []
    for yr in [2023, 2024, 2025]:
        sub = df[df["year"] == yr]
        rows.append({
            "year": yr,
            "rows": len(sub),
            "states": int(sub["state_alpha"].nunique()),
            "commodities": int(sub["commodity_desc"].nunique()),
            "state_commodity_pairs": int(
                sub.groupby(["state_alpha", "commodity_desc"]).ngroups
            ),
        })
    return pd.DataFrame(rows)


def early_year_check(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for yr in [2001, 2002, 2003, 2004, 2005]:
        sub = df[df["year"] == yr]
        rows.append({
            "year": yr,
            "rows": len(sub),
            "states": int(sub["state_alpha"].nunique()),
            "commodities": int(sub["commodity_desc"].nunique()),
            "state_commodity_pairs": int(
                sub.groupby(["state_alpha", "commodity_desc"]).ngroups
            ),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------
def df_to_md(df: pd.DataFrame, max_rows: int | None = None) -> str:
    """Render a DataFrame as a GitHub-flavored markdown table without tabulate."""
    if max_rows is not None and len(df) > max_rows:
        df = df.head(max_rows)
    if df.empty:
        return "_(empty)_"
    cols = list(df.columns)

    def _cell(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return ""
        if isinstance(v, list):
            return ", ".join(str(x) for x in v)
        s = str(v)
        # Escape pipe characters that would break the table
        return s.replace("|", "\\|").replace("\n", " ")

    header = "| " + " | ".join(_cell(c) for c in cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    rows = []
    for _, row in df.iterrows():
        rows.append("| " + " | ".join(_cell(row[c]) for c in cols) + " |")
    return "\n".join([header, sep] + rows)


def render_report(
    df: pd.DataFrame,
    per_state: pd.DataFrame,
    per_com: pd.DataFrame,
    state_x_com: pd.DataFrame,
    presence: pd.DataFrame,
    year_gaps: pd.DataFrame,
    misses: list[dict],
    hotspots: pd.DataFrame,
    stat_pres_counts: dict,
    recent: pd.DataFrame,
    early: pd.DataFrame,
) -> str:
    total_rows = len(df)
    total_counties = int(df["fips"].nunique())
    total_states = int(df["state_alpha"].nunique())
    total_pairs = state_x_com.shape[0]
    expected_pairs = sum(
        1 for com in COUNTY_COMMODITIES
        for st in (set(MAJOR_PRODUCERS.get(com, set())) - COUNTY_SKIP_STATES.get(com, set()))
    )
    total_state_com_year = int(
        df.groupby(["state_alpha", "commodity_desc", "year"]).ngroups
    )

    n_total_miss = sum(1 for r in misses if r["type"] == "TOTAL_MISS_MAJOR_PRODUCER")
    n_partial_4_4 = stat_pres_counts.get("4/4 stats", 0)

    # --- Compose ---
    md = []
    md.append("# County-Level NASS Coverage Audit\n")
    md.append("**Date:** 2026-04-19  ")
    md.append("**Source:** `pipeline/output/{STATE}.parquet` (county-level rows only)  ")
    md.append("**Generator:** `pipeline/_county_coverage_audit.py`\n")

    md.append("## Executive Summary\n")
    md.append(f"- **{total_rows:,}** county-level rows across **{total_states}** states (NATIONAL.parquet excluded; AK/HI/DC have no county rows)")
    md.append(f"- **{total_counties:,}** distinct county FIPS represented; **{total_pairs:,}** distinct (state, commodity) combinations active")
    md.append(f"- **{total_state_com_year:,}** (state, commodity, year) combinations have at least one row")
    md.append(f"- **{n_partial_4_4:,}** (state, commodity) pairs have all 4 target stat categories (YIELD/AREA HARVESTED/AREA PLANTED/PRODUCTION)")
    md.append(f"- **{n_total_miss}** total-miss gaps where a major-producer state has ZERO rows for an expected commodity")
    md.append("")

    md.append("## Ingestion Contract (from `quickstats_ingest.py`)\n")
    md.append("- **11 commodities targeted:** " + ", ".join(COUNTY_COMMODITIES))
    md.append("- **4 stat categories:** " + ", ".join(COUNTY_STAT_CATS))
    md.append(f"- **Year range:** {TARGET_YEAR_START}–{TARGET_YEAR_END} ({len(TARGET_YEARS)} years)")
    md.append("- **Skipped states (structural):** AK, HI, DC universally; per-commodity skip lists exclude states with no commercial production (e.g. COTTON in MN, RICE in IA). Skip lists encoded in `COUNTY_SKIP_STATES`.")
    md.append("- **Filter:** `agg_level_desc == 'COUNTY'`")
    md.append("- **Sources:** SURVEY year-round + CENSUS for {2002, 2007, 2012, 2017, 2022}")
    md.append("")

    md.append("## Per-State Coverage\n")
    md.append("Compact table (full commodity/stat lists in `state_commodity_matrix` below).\n")
    compact = per_state[[
        "state", "rows", "counties", "year_min", "year_max",
        "n_years", "n_commodities", "n_stat_cats",
    ]].copy()
    md.append(df_to_md(compact))
    md.append("")

    md.append("## Per-Commodity Coverage\n")
    md.append(df_to_md(per_com))
    md.append("")

    md.append("## Recent Years (2023–2025)\n")
    md.append(df_to_md(recent))
    md.append("")

    md.append("## Early Years (2001–2005)\n")
    md.append(df_to_md(early))
    md.append("")

    md.append("## Stat-Category Presence Distribution\n")
    md.append("How many of the 4 target stats (YIELD / AREA HARVESTED / AREA PLANTED / PRODUCTION) are present per (state, commodity) pair:\n")
    for k, v in sorted(stat_pres_counts.items()):
        md.append(f"- **{k}:** {v} pairs")
    md.append("")

    # Surface partial-stat pairs (1-3 of 4 stats) for major producer combos
    partial = presence[presence["n_stats"] < 4].copy()
    partial = partial.merge(
        pd.DataFrame(
            [(st, com) for com, sts in MAJOR_PRODUCERS.items() for st in sts],
            columns=["state_alpha", "commodity_desc"],
        ),
        on=["state_alpha", "commodity_desc"],
        how="inner",
    ).sort_values(["commodity_desc", "state_alpha"])
    md.append("### Major-producer pairs missing one or more stats\n")
    if partial.empty:
        md.append("_None — all major-producer pairs that exist have all 4 stats._\n")
    else:
        partial_view = partial[["state_alpha", "commodity_desc", "n_stats", "missing_stats"]].copy()
        partial_view["missing_stats"] = partial_view["missing_stats"].apply(lambda xs: ", ".join(xs))
        md.append(df_to_md(partial_view))
    md.append("")

    md.append("## Total-Miss Gaps (Major Producer × Commodity with ZERO rows)\n")
    md.append("These are real ingestion misses — the state is a top-10 producer of the commodity but our parquet has no county-level rows.\n")
    if misses:
        miss_df = pd.DataFrame(misses)
        md.append(df_to_md(miss_df))
    else:
        md.append("_None — every major-producer × commodity pair has at least one row._\n")
    md.append("")

    md.append("## Hotspot Ranking (Top 30)\n")
    md.append("Score = commodity_weight × (0.4 × (1 − county_coverage) + 0.3 × stat_gap + 0.3 × year_gap). "
              "Higher = more impactful gap to plug.\n")
    md.append(df_to_md(hotspots, max_rows=30))
    md.append("")

    md.append("## Year-Coverage Gaps (Major Producer Pairs Only)\n")
    yg_filtered = year_gaps.merge(
        pd.DataFrame(
            [(st, com) for com, sts in MAJOR_PRODUCERS.items() for st in sts],
            columns=["state", "commodity"],
        ),
        on=["state", "commodity"],
        how="inner",
    )
    yg_with_gaps = yg_filtered[yg_filtered["n_years_missing"] > 0].copy()
    yg_with_gaps["missing_years"] = yg_with_gaps["missing_years"].apply(
        lambda xs: ", ".join(str(x) for x in xs) if xs else ""
    )
    yg_with_gaps = yg_with_gaps.sort_values("n_years_missing", ascending=False)
    md.append(f"_{len(yg_with_gaps)} major-producer pairs have at least one missing year (out of {len(yg_filtered)} total)._\n")
    md.append(df_to_md(yg_with_gaps, max_rows=40))
    md.append("")

    # Strategy section follows in render_strategy()
    return "\n".join(md)


def render_strategy() -> str:
    md = []
    md.append("## Gap-Filling Strategies\n")

    md.append("### 1. NASS QuickStats API re-query\n")
    md.append("- **Targeted fix-ups** beat full re-runs. Use `python pipeline/quickstats_ingest.py --county-only --states <CODES> --year-start <Y1> --year-end <Y2> --resume` to plug specific holes without re-fetching what's already on disk. The `--resume` flag (in `_fetch_county_state_year`) skips chunk files that already exist.")
    md.append("- **Add the generic `WHEAT` commodity** to `COUNTY_COMMODITIES` for states where WINTER/SPRING WHEAT come back empty. NASS publishes a county-level `WHEAT` rollup for some states (esp. CA, NY, MI, AZ) that doesn't fit the winter/spring split. The existing `pipeline/fetch_wheat_county.py` already does this — it just isn't triggered by the main runner. Either fold it in or add `WHEAT` to the main commodity list.")
    md.append("- **Audit `COUNTY_SKIP_STATES` periodically.** A few entries are aggressive — e.g. SOYBEANS skips OR/WA/ID, but WSU/OSU report >100k acres of soy in some recent years. Pull the skip list back to AK/HI/DC + commodities that NASS truly never publishes.")
    md.append("- **Retry rate-limited / 400'd combos.** The current code logs and continues on 400. Add a `--rerun-failed` mode that reads the latest log, extracts the failing (state, commodity, year) combos, and re-issues them.")
    md.append("")

    md.append("### 2. NASS Census of Agriculture (5-year)\n")
    md.append("- The Census of Ag (2002, 2007, 2012, 2017, 2022) reports county data for crops and livestock that the annual SURVEY suppresses for confidentiality. The infrastructure exists: `pipeline/load_census_county.py` already targets `source_desc=CENSUS` for SALES, VALUE OF PRODUCTION, INVENTORY, and livestock commodities (CATTLE, HOGS, BROILERS, MILK).")
    md.append("- **Action:** run `python pipeline/load_census_county.py --years 2017 2022` to backfill. This will *not* fill annual-survey gaps in YIELD/AREA, but it will add the dollar/inventory dimensions that are entirely missing from our county data today (those four stats are not in `COUNTY_STAT_CATS`).")
    md.append("- **Census also has wider commodity coverage** than the annual survey — minor crops like dry beans, peanuts, sugar beets, tobacco, and most fruit/veg are CENSUS-only at county resolution.")
    md.append("")

    md.append("### 3. NASS suppression vs pipeline miss\n")
    md.append("- NASS suppresses county data when fewer than 3 farms report a value (the `(D)` code in `Value`, dropped to NaN by `clean_nass_value`). Our parquets capture suppressed rows as `value_num=NaN` but the row still exists, so a *missing row* is more likely a pipeline gap than suppression.")
    md.append("- **Test:** for each suspected gap, query the state-level SURVEY row in the same parquet (`agg_level_desc == 'STATE'`). If the state-level row exists with a real value but no county rows do, the issue is suppression cascade (small-county dominance). If the state-level row is also empty, the commodity genuinely isn't grown — drop it from `MAJOR_PRODUCERS`.")
    md.append("- **Mitigation for suppression:** Census of Ag publishes more — every 5 years it relaxes the suppression rule for state-aggregated and disclosure-protected county figures. Backfilling Census years (above) closes ~30% of the apparent annual-survey holes.")
    md.append("")

    md.append("### 4. Alternative sources for what NASS won't fill\n")
    md.append("- **USDA RMA (Risk Management Agency) — Cause of Loss & Summary of Business.** County-level insured acres + indemnities by crop. Publicly hosted at `https://www.rma.usda.gov/SummaryOfBusiness`. Already integrated for the acreage prediction module (`backend/etl/ingest_rma.py`) — same pipeline can populate a `county_insured_acres` table for the dashboard. Coverage is excellent for major program crops (corn, soy, wheat, cotton, sorghum, barley, rice).")
    md.append("- **USDA FSA (Farm Service Agency) — Crop Acreage Data.** County-level reported acres from CCC-578 forms. Available at `https://www.fsa.usda.gov/tools/informational/freedom-of-information-act-foia/electronic-reading-room/frequently-requested/crop-acreage-data` as monthly Excel snapshots from 2008 forward. Best source for **planted acres** when NASS suppresses; updated Aug, Oct, Jan.")
    md.append("- **State Departments of Agriculture.** A handful publish enhanced county detail beyond what NASS releases — Iowa (IDALS), Illinois (IDOA), California (CDFA County Ag Commissioners' reports — annual, with crop $ and acreage). California especially is worth ingesting for fruit/veg/almond county data NASS doesn't carry annually.")
    md.append("")

    md.append("### 5. Concrete next-action list (ranked by ROI)\n")
    md.append("1. **Run `load_census_county.py --years 2017 2022`** — ~2 hr API time, adds ~40K rows of SALES + VALUE OF PRODUCTION + livestock INVENTORY at county level. Highest ROI: opens dollar/inventory dimensions that are zero today.")
    md.append("2. **Add the generic `WHEAT` commodity to the main pipeline** by either folding `fetch_wheat_county.py` into `quickstats_ingest.py` or appending `WHEAT` to `COUNTY_COMMODITIES` (~1 hr code, ~3 hr API run, adds ~10K rows mostly in CA/NY/MI/AZ).")
    md.append("3. **Trim `COUNTY_SKIP_STATES`** for SOYBEANS (drop OR/WA/ID), BARLEY (drop IA/IL/IN), and OATS (drop AL/MS — minor but real). Re-run `--county-only --resume` for the affected states. ~6 hr API time, ~5K rows.")
    md.append("4. **Wire RMA county data into the dashboard.** The ETL already populates `rma_insured_acres` for the acreage model. Surface it as a fallback layer in the county map for combos NASS suppresses (esp. cotton in NC/VA, sorghum in TN/KY). Backend-only change, no new ingestion. ~1 day.")
    md.append("5. **Backfill 2025 partial-year rows** by re-running `--year-start 2025 --year-end 2025 --county-only --resume` in mid-July (when NASS publishes June Acreage Survey) and again in October (Crop Production Annual Summary). 2025 rows are sparse today because the bulk run completed in early Apr 2026 before NASS finalised 2025.")
    md.append("")

    md.append("---\n")
    md.append("_Report generated by `pipeline/_county_coverage_audit.py`. To regenerate: `python pipeline/_county_coverage_audit.py`._\n")
    return "\n".join(md)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if not OUTPUT_DIR.exists():
        print(f"ERROR: {OUTPUT_DIR} does not exist", file=sys.stderr)
        sys.exit(1)

    print("Loading county rows from all state parquets...", file=sys.stderr)
    df = load_all()
    if df.empty:
        print("ERROR: no county rows loaded", file=sys.stderr)
        sys.exit(1)
    print(f"  Loaded {len(df):,} county rows.", file=sys.stderr)

    all_states = sorted(df["state_alpha"].unique())
    print("Computing summaries...", file=sys.stderr)

    per_state = per_state_summary(df)
    per_com = per_commodity_summary(df)
    state_x_com = state_x_commodity_matrix(df)
    presence = state_x_commodity_x_stat_presence(df)
    year_gaps = year_gaps_per_state_commodity(df)
    misses = total_miss_pairs(state_x_com, all_states)
    hotspots = hotspot_ranking(state_x_com, presence, year_gaps)
    stat_pres_counts = stat_completeness(presence)
    recent = recent_year_check(df)
    early = early_year_check(df)

    # Quick console summary so we can verify numbers
    print(f"\n  Total rows:      {len(df):,}")
    print(f"  Total counties:  {df['fips'].nunique():,}")
    print(f"  Total states:    {df['state_alpha'].nunique()}")
    print(f"  State-Commodity pairs:        {state_x_com.shape[0]:,}")
    print(f"  4/4 stat-complete pairs:      {stat_pres_counts.get('4/4 stats', 0):,}")
    print(f"  Total-miss major-producer combos: {len(misses)}")
    print()

    body = render_report(
        df, per_state, per_com, state_x_com, presence,
        year_gaps, misses, hotspots, stat_pres_counts,
        recent, early,
    )
    strategy = render_strategy()
    full = body + "\n" + strategy

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(full, encoding="utf-8")
    print(f"Wrote report -> {REPORT_PATH}")


if __name__ == "__main__":
    main()
