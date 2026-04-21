"""
fill_county_gaps.py - Iteratively fill county-level NASS coverage gaps.

Flow
----
1. Baseline audit. Loads every pipeline/output/{STATE}.parquet and derives
   the current (state, commodity, year) coverage set.
2. Gap computation. Ideal = for every COUNTY_COMMODITIES entry (including
   generic WHEAT), every MAJOR_PRODUCERS state minus COUNTY_SKIP_STATES,
   every target year (2001-2025). Gap set = ideal - current - allowlist.
3. Targeted ingest. Per round, iterates gap states one at a time, invoking
   quickstats_ingest.py --county-only --resume --states <ST> per state. Each
   state's parquet is merged and committed atomically before the next state
   starts, so a mid-run 403/timeout loses at most one state's in-flight data.
4. Re-audit + classify. After each round, residuals are classified:
     - year >= current_year - 1 -> PENDING_PUBLICATION with recheck date
     - state-level row has real value (audit section 3 test) -> NASS_SUPPRESSION
     - state-level row is empty -> NOT_GROWN
     - state-level data unavailable locally -> UNCLASSIFIED (not allowlisted;
       eligible for next round or manual review after --max-rounds)
5. Loop or stop. Stops when a round adds < --min-delta rows OR all residuals
   are allowlisted OR --max-rounds reached.

Artifacts
---------
- pipeline/county_coverage_allowlist.json - persistent, grows across runs
- pipeline/fill_county_gaps_report.json   - per-run summary
- pipeline/logs/fill_gaps_YYYYMMDD_HHMMSS.log

Usage
-----
    # Plan-only, no API calls, no side effects:
    python pipeline/fill_county_gaps.py --dry-run

    # Fill all gaps (sequential per-state ingest for throttle safety):
    python pipeline/fill_county_gaps.py

    # Restrict to specific states:
    python pipeline/fill_county_gaps.py --states KS TX OK

    # Budget a tighter run:
    python pipeline/fill_county_gaps.py --max-rounds 1 --min-delta 250
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PIPELINE_DIR / "output"
INGEST_SCRIPT = PIPELINE_DIR / "quickstats_ingest.py"
AUDIT_SCRIPT = PIPELINE_DIR / "_county_coverage_audit.py"
ALLOWLIST_PATH = PIPELINE_DIR / "county_coverage_allowlist.json"
REPORT_PATH = PIPELINE_DIR / "fill_county_gaps_report.json"

LOG_DIR = PIPELINE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(PIPELINE_DIR))
# Reuse the audit's loader + constants to keep the ideal-contract definition
# in one place (MAJOR_PRODUCERS and COMMODITY_WEIGHT live there).
from _county_coverage_audit import (  # noqa: E402
    MAJOR_PRODUCERS,
    load_all,
)
# Pull the live ingestion contract from quickstats_ingest (authoritative;
# audit has a copy but the ingest module is what actually drives fetching).
from quickstats_ingest import (  # noqa: E402
    COUNTY_COMMODITIES,
    COUNTY_SKIP_STATES,
    COUNTY_STAT_CATS,
)

TARGET_YEAR_START, TARGET_YEAR_END = 2001, 2025
TARGET_YEARS = list(range(TARGET_YEAR_START, TARGET_YEAR_END + 1))
CURRENT_YEAR = datetime.now().year

log_file = LOG_DIR / f"fill_gaps_{datetime.now():%Y%m%d_%H%M%S}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(log_file)],
)
logger = logging.getLogger("fill_gaps")


# ---------------------------------------------------------------------------
# Allowlist I/O
# ---------------------------------------------------------------------------
def load_allowlist() -> dict:
    if ALLOWLIST_PATH.exists():
        return json.loads(ALLOWLIST_PATH.read_text())
    return {
        "version": 1,
        "created": datetime.now(timezone.utc).isoformat(),
        "entries": [],  # list of {state, commodity, year, reason, detail, ...}
    }


def save_allowlist(al: dict) -> None:
    al["updated"] = datetime.now(timezone.utc).isoformat()
    ALLOWLIST_PATH.write_text(json.dumps(al, indent=2))


def allowlist_triples(al: dict) -> set[tuple[str, str, int | None]]:
    """Return {(state, commodity, year_or_None)} for O(1) lookup."""
    out: set[tuple[str, str, int | None]] = set()
    for e in al["entries"]:
        yr = e.get("year")
        out.add((e["state"], e["commodity"], int(yr) if yr is not None else None))
    return out


def prune_due_recheck_entries(al: dict) -> int:
    """Remove PENDING_PUBLICATION entries whose recheck_after has passed.
    Returns count removed."""
    today = datetime.now(timezone.utc).date().isoformat()
    keep = []
    dropped = 0
    for e in al["entries"]:
        if e.get("reason") == "PENDING_PUBLICATION" and e.get("recheck_after", "9999-12-31") <= today:
            dropped += 1
            continue
        keep.append(e)
    al["entries"] = keep
    return dropped


# ---------------------------------------------------------------------------
# Ideal contract + gap computation
# ---------------------------------------------------------------------------
def expected_triples() -> set[tuple[str, str, int]]:
    """Ideal (state, commodity, year) set per the ingestion contract.

    For each commodity: MAJOR_PRODUCERS - COUNTY_SKIP_STATES × TARGET_YEARS.
    Generic WHEAT uses the union of WINTER + SPRING producers as its producer set.
    """
    ideal: set[tuple[str, str, int]] = set()
    for com in COUNTY_COMMODITIES:
        if com == "WHEAT":
            producers = (
                MAJOR_PRODUCERS.get("WINTER WHEAT", set())
                | MAJOR_PRODUCERS.get("SPRING WHEAT, (EXCL DURUM)", set())
            )
        else:
            producers = MAJOR_PRODUCERS.get(com, set())
        skip = COUNTY_SKIP_STATES.get(com, set())
        for st in (producers - skip):
            for yr in TARGET_YEARS:
                ideal.add((st, com, yr))
    return ideal


def current_triples(df: pd.DataFrame) -> set[tuple[str, str, int]]:
    """Observed (state, commodity, year) set from loaded county parquets."""
    if df.empty:
        return set()
    g = df.groupby(["state_alpha", "commodity_desc", "year"]).size().reset_index()
    return {
        (str(s), str(c), int(y))
        for s, c, y in zip(g["state_alpha"], g["commodity_desc"], g["year"])
        if pd.notna(y)
    }


def compute_gap_set(
    df: pd.DataFrame,
    allowlist: dict,
) -> pd.DataFrame:
    """Gap = ideal - current - allowlist. Returned as a DataFrame for iteration
    convenience."""
    ideal = expected_triples()
    have = current_triples(df)
    al = allowlist_triples(allowlist)
    al_any_year = {(s, c) for (s, c, y) in al if y is None}

    gaps = []
    for (s, c, y) in ideal:
        if (s, c, y) in have:
            continue
        if (s, c) in al_any_year:
            continue
        if (s, c, y) in al:
            continue
        gaps.append({"state": s, "commodity": c, "year": y})
    return pd.DataFrame(gaps).sort_values(
        ["commodity", "state", "year"], ignore_index=True
    ) if gaps else pd.DataFrame(columns=["state", "commodity", "year"])


# ---------------------------------------------------------------------------
# Classification (state-level test)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=64)
def _load_state_full(state: str) -> pd.DataFrame | None:
    """Load STATE-and-higher-agg rows from one state's parquet. Cached."""
    path = OUTPUT_DIR / f"{state}.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(
            path,
            columns=[
                "agg_level_desc", "commodity_desc", "year",
                "statisticcat_desc", "value_num", "source_desc",
            ],
        )
    except Exception as exc:
        logger.warning("Could not read %s: %s", path.name, exc)
        return None
    return df[df["agg_level_desc"].isin(["STATE", "NATIONAL"])].copy()


def _clear_state_cache() -> None:
    _load_state_full.cache_clear()


def classify_gap(state: str, commodity: str, year: int) -> tuple[str, str]:
    """Return (classification, detail) for a (state, commodity, year) that
    ingest could not fill.

    Recent years always classify as PENDING_PUBLICATION regardless of the
    state-level test — NASS publishes county data in waves and some 2025
    state-level rows exist months before county detail lands.

    Otherwise, apply the audit section 3 state-level test IF local state-level
    data is available. The 2026-04 county-only ingest left many state parquets
    with only COUNTY rows (no STATE/NATIONAL), so the test often cannot run —
    in that case return UNCLASSIFIED and leave the entry off the allowlist.
    """
    if year >= CURRENT_YEAR - 1:
        recheck = f"{CURRENT_YEAR}-10-15"  # NASS Crop Production Annual Summary
        return "PENDING_PUBLICATION", f"recheck_after={recheck}"

    df = _load_state_full(state)
    if df is None or df.empty:
        return (
            "UNCLASSIFIED",
            "no STATE-level rows in local parquet; cannot distinguish "
            "NOT_GROWN vs NASS_SUPPRESSION vs pipeline miss",
        )

    if commodity == "WHEAT":
        commodity_match = df["commodity_desc"].isin(
            ["WHEAT", "WINTER WHEAT", "SPRING WHEAT, (EXCL DURUM)"]
        )
    else:
        commodity_match = df["commodity_desc"] == commodity

    state_rows = df[
        commodity_match
        & (df["year"] == year)
        & (df["statisticcat_desc"].isin(COUNTY_STAT_CATS))
    ]
    if state_rows.empty:
        return "NOT_GROWN", "state-level has zero rows for this commodity-year"

    real = state_rows["value_num"].dropna()
    real = real[real != 0]
    if real.empty:
        return "NOT_GROWN", "state-level present but all null/zero"

    return "NASS_SUPPRESSION", (
        f"state-level value present (n={len(real)}, "
        f"max={real.max():.0f}) but county rows suppressed"
    )


# ---------------------------------------------------------------------------
# Targeted ingest (subprocess)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _subprocess_env() -> dict:
    """Build the env dict for the ingest subprocess.

    quickstats_ingest.get_api_key() looks for USDA_QUICKSTATS_API_KEY env var
    first, then falls back to AWS SSM (which requires a live SSO session).
    The project's .env ships the key as QUICKSTATS_API_KEY (different name),
    so read it here and pass it through under the expected name — avoids
    depending on the user having refreshed their AWS SSO token.
    """
    env = os.environ.copy()
    if env.get("USDA_QUICKSTATS_API_KEY"):
        return env

    # Try .env file in project root
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        try:
            for raw in env_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                if k == "QUICKSTATS_API_KEY" and v:
                    env["USDA_QUICKSTATS_API_KEY"] = v
                    logger.info("Loaded QUICKSTATS_API_KEY from .env and re-exported "
                                "as USDA_QUICKSTATS_API_KEY for subprocess.")
                    break
        except Exception as exc:
            logger.warning("Could not parse .env: %s", exc)
    return env


def run_ingest(states: list[str], year_start: int, year_end: int, dry_run: bool = False) -> bool:
    """Invoke quickstats_ingest.py --county-only --resume for a targeted
    state × year window."""
    cmd = [
        sys.executable, str(INGEST_SCRIPT),
        "--county-only", "--resume",
        "--year-start", str(year_start),
        "--year-end", str(year_end),
    ]
    if states:
        cmd.extend(["--states", *sorted(states)])
    if dry_run:
        logger.info("DRY RUN - would execute: %s", " ".join(cmd))
        return True

    logger.info("Ingest subprocess: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, check=False, env=_subprocess_env())
    except Exception as exc:
        logger.error("Ingest subprocess raised: %s", exc)
        return False
    if proc.returncode != 0:
        logger.warning("Ingest subprocess returned %d - continuing", proc.returncode)
        return False
    return True


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------
def summarize(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"rows": 0, "counties": 0, "pairs": 0, "triples": 0}
    return {
        "rows": int(len(df)),
        "counties": int(df["fips"].nunique()),
        "pairs": int(df.groupby(["state_alpha", "commodity_desc"]).ngroups),
        "triples": int(df.groupby(["state_alpha", "commodity_desc", "year"]).ngroups),
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def _print_gap_breakdown(gaps: pd.DataFrame) -> None:
    """Log a by-commodity and by-state summary of a gap DataFrame."""
    if gaps.empty:
        return
    by_com = gaps.groupby("commodity").size().sort_values(ascending=False)
    logger.info("  Gaps by commodity: %s",
                ", ".join(f"{c}={n}" for c, n in by_com.items()))
    by_state = gaps.groupby("state").size().sort_values(ascending=False)
    top_states = ", ".join(f"{s}={n}" for s, n in by_state.head(10).items())
    logger.info("  Top gap states (first 10 of %d): %s", len(by_state), top_states)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fill county-level NASS coverage gaps iteratively.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--states", nargs="+", default=None,
                        help="Restrict to specific 2-letter state codes "
                             "(default: every state that has a gap).")
    parser.add_argument("--max-rounds", type=int, default=2,
                        help="Max ingest iterations.")
    parser.add_argument("--min-delta", type=int, default=100,
                        help="Stop if a round adds fewer than this many new rows.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show the baseline + gap set + per-state plan, then exit. "
                             "No API calls, no classification, no file writes.")
    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("COUNTY COVERAGE GAP FILLER - %s",
                datetime.now().isoformat(timespec="seconds"))
    logger.info("=" * 70)
    logger.info("Contract:     %d commodities | years %d-%d",
                len(COUNTY_COMMODITIES), TARGET_YEAR_START, TARGET_YEAR_END)
    logger.info("WHEAT in contract: %s",
                "yes" if "WHEAT" in COUNTY_COMMODITIES
                else "NO - patch quickstats_ingest.py first")
    logger.info("State filter: %s", args.states if args.states else "ALL")
    logger.info("Max rounds:   %d", args.max_rounds)
    logger.info("Dry run:      %s", args.dry_run)

    allowlist = load_allowlist()
    if not args.dry_run:
        pruned = prune_due_recheck_entries(allowlist)
        if pruned:
            logger.info("Dropped %d PENDING_PUBLICATION entries past recheck.", pruned)
            save_allowlist(allowlist)

    logger.info("\nLoading baseline from %s ...", OUTPUT_DIR)
    df_prev = load_all()
    baseline = summarize(df_prev)
    logger.info("Baseline: %s", baseline)

    ideal_total = len(expected_triples())
    logger.info("Ideal (state, commodity, year) targets: %d", ideal_total)

    # --- Compute initial gap set once for the plan preview ---
    gaps0 = compute_gap_set(df_prev, allowlist)
    if args.states:
        state_filter = {s.upper() for s in args.states}
        gaps0 = gaps0[gaps0["state"].isin(state_filter)].reset_index(drop=True)
        logger.info("Gap set narrowed to --states filter: %d triples", len(gaps0))

    logger.info("Initial gap set: %d triples (coverage %.1f%%)",
                len(gaps0),
                100 * (ideal_total - len(gaps0)) / max(1, ideal_total))
    _print_gap_breakdown(gaps0)

    if args.dry_run:
        # Show per-state plan that a real run would execute, then exit.
        # No side effects: no classification, no allowlist write, no report.
        logger.info("\n=== DRY-RUN PLAN ===")
        if gaps0.empty:
            logger.info("No work to do.")
        else:
            for st in sorted(gaps0["state"].unique()):
                sub = gaps0[gaps0["state"] == st]
                yr_lo, yr_hi = int(sub["year"].min()), int(sub["year"].max())
                coms = sorted(sub["commodity"].unique())
                logger.info("  %s: %d triples, years %d-%d, commodities: %s",
                            st, len(sub), yr_lo, yr_hi, ", ".join(coms))
        logger.info("\n(No API calls made, no files written.)")
        return 0

    rounds_log = []

    for round_n in range(1, args.max_rounds + 1):
        logger.info("\n%s ROUND %d %s", "=" * 25, round_n, "=" * 25)

        gaps = compute_gap_set(df_prev, allowlist)
        if args.states:
            gaps = gaps[gaps["state"].isin({s.upper() for s in args.states})].reset_index(drop=True)

        logger.info("Unfilled triples: %d / %d ideal (%.1f%% coverage)",
                    len(gaps), ideal_total,
                    100 * (ideal_total - len(gaps)) / max(1, ideal_total))
        if gaps.empty:
            logger.info("No gaps - converged.")
            break
        _print_gap_breakdown(gaps)

        # ---- Sequential per-state ingest ----
        # Each state gets its own subprocess call so its parquet is merged +
        # committed before the next state begins. A rate-limit/interrupt
        # mid-run loses at most one state's in-flight work.
        gap_states = sorted(gaps["state"].unique())
        logger.info("Sequential per-state ingest for %d states ...", len(gap_states))

        states_done = 0
        states_failed: list[str] = []
        for i, st in enumerate(gap_states, start=1):
            sub = gaps[gaps["state"] == st]
            yr_lo, yr_hi = int(sub["year"].min()), int(sub["year"].max())
            logger.info("[%d/%d] State %s: %d gap triples, years %d-%d",
                        i, len(gap_states), st, len(sub), yr_lo, yr_hi)
            ok = run_ingest([st], yr_lo, yr_hi, dry_run=False)
            if ok:
                states_done += 1
            else:
                states_failed.append(st)
                logger.warning("  -> %s ingest failed; continuing with next state.", st)

        logger.info("Per-state ingest complete: %d ok, %d failed (%s)",
                    states_done, len(states_failed),
                    ", ".join(states_failed) if states_failed else "none")

        # Re-audit after all states finish (or fail)
        logger.info("Re-auditing post-ingest ...")
        _clear_state_cache()  # parquets rewritten by ingest subprocess
        df_new = load_all()
        delta_rows = len(df_new) - len(df_prev)
        logger.info("delta rows this round: %+d (total %d)", delta_rows, len(df_new))

        # Classify residuals
        residual = compute_gap_set(df_new, allowlist)
        if args.states:
            residual = residual[
                residual["state"].isin({s.upper() for s in args.states})
            ].reset_index(drop=True)
        logger.info("Residual unfilled triples: %d - classifying ...", len(residual))

        counts = {"NOT_GROWN": 0, "NASS_SUPPRESSION": 0,
                  "PENDING_PUBLICATION": 0, "UNCLASSIFIED": 0}
        new_entries = 0
        for row in residual.itertuples(index=False):
            kind, detail = classify_gap(row.state, row.commodity, int(row.year))
            counts[kind] = counts.get(kind, 0) + 1
            if kind == "UNCLASSIFIED":
                # Not allowlisted - stays eligible for later rounds or manual review.
                continue
            entry: dict = {
                "state": row.state,
                "commodity": row.commodity,
                "year": int(row.year),
                "reason": kind,
                "detail": detail,
                "classified_at": datetime.now(timezone.utc).isoformat(),
                "classified_in_round": round_n,
            }
            if kind == "PENDING_PUBLICATION":
                entry["recheck_after"] = detail.split("=", 1)[-1]
            allowlist["entries"].append(entry)
            new_entries += 1
        save_allowlist(allowlist)
        logger.info("Classified: %s (+%d allowlist entries)", counts, new_entries)

        rounds_log.append({
            "round": round_n,
            "gaps_at_start": len(gaps),
            "states_attempted": len(gap_states),
            "states_done": states_done,
            "states_failed": states_failed,
            "residual": len(residual),
            "delta_rows": delta_rows,
            "classification": counts,
            "new_allowlist_entries": new_entries,
        })

        # Stop conditions
        still_unclassified = counts.get("UNCLASSIFIED", 0)
        if len(residual) == 0:
            logger.info("All gaps filled - converged.")
            df_prev = df_new
            break
        if still_unclassified == 0:
            logger.info("No UNCLASSIFIED residuals left; all %d remaining "
                        "are structural (NOT_GROWN/NASS_SUPPRESSION/PENDING).",
                        len(residual))
            df_prev = df_new
            break
        if delta_rows < args.min_delta:
            logger.info("Delta %d below --min-delta %d - plateau detected, stopping.",
                        delta_rows, args.min_delta)
            df_prev = df_new
            break

        df_prev = df_new

    final = summarize(df_prev)
    report = {
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "ideal_triples": ideal_total,
        "baseline": baseline,
        "final": final,
        "delta": {k: final[k] - baseline[k] for k in baseline},
        "coverage_pct": round(100 * final["triples"] / max(1, ideal_total), 2),
        "rounds": rounds_log,
        "allowlist_entries_total": len(allowlist["entries"]),
        "state_filter": args.states,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2))

    logger.info("\n%s SUMMARY %s", "=" * 25, "=" * 25)
    logger.info("Ideal triples:    %d", ideal_total)
    logger.info("Baseline:         %s", baseline)
    logger.info("Final:            %s", final)
    logger.info("delta:            %+d rows, %+d triples",
                report["delta"]["rows"], report["delta"]["triples"])
    logger.info("Coverage:         %.2f%%", report["coverage_pct"])
    logger.info("Allowlist total:  %d", len(allowlist["entries"]))
    logger.info("Report:           %s", REPORT_PATH)
    logger.info("Allowlist:        %s", ALLOWLIST_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
