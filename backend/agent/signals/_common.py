"""Shared helpers for the per-source signal builders.

Spec: §4.2 of analyst-agent-tech-spec.md.

`compute_score` blends magnitude / reach / novelty / calendar fit per the
v0 weight set. The weights are placeholders — `backend/agent/calibrate.py`
fits real values from labelled history.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.etl.common import get_sync_session

logger = logging.getLogger(__name__)


# Default weight set (§4.2 — calibrate.py replaces these).
DEFAULT_WEIGHTS = {
    "magnitude": 0.50,
    "reach": 0.25,
    "novelty": 0.15,
    "calendar": 0.10,
}


@lru_cache(maxsize=1)
def _load_calibrated_weights() -> dict[str, float]:
    """Load weights.json from disk if present, else return DEFAULT_WEIGHTS.

    The fitter writes to backend/agent/data/weights.json. If absent, we run
    with defaults — the agent stays functional, just uncalibrated.
    """
    import json
    from pathlib import Path

    weights_path = Path(__file__).parent.parent / "data" / "weights.json"
    if not weights_path.exists():
        return dict(DEFAULT_WEIGHTS)
    try:
        payload = json.loads(weights_path.read_text())
        weights = payload.get("weights") or {}
        # Validate shape — fall back to defaults on any anomaly.
        if set(weights.keys()) != set(DEFAULT_WEIGHTS.keys()):
            logger.warning("weights.json has unexpected keys, using defaults")
            return dict(DEFAULT_WEIGHTS)
        s = sum(weights.values())
        if abs(s - 1.0) > 0.01:
            logger.warning("weights.json sums to %.3f (not 1.0), using defaults", s)
            return dict(DEFAULT_WEIGHTS)
        return {k: float(v) for k, v in weights.items()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("weights.json load failed (%s), using defaults", exc)
        return dict(DEFAULT_WEIGHTS)


def get_weights() -> dict[str, float]:
    """Public accessor — call this instead of touching DEFAULT_WEIGHTS directly."""
    return _load_calibrated_weights()


@dataclass
class ScoreParts:
    """Decomposed score components — kept on Signal.evidence for audit."""

    magnitude: float  # 0-100 (z-score or %dev capped to a sane band)
    reach: float      # 0-100 (acres / $ value of affected region)
    novelty: float    # 0-100 (lower if same domain+scope fired in last 8 weeks)
    calendar: float   # 0-100 (bonus if signal ties to upcoming USDA report)


def compute_score(parts: ScoreParts, weights: dict[str, float] | None = None) -> float:
    """Blend the four components into a single 0-100 score.

    Defaults to calibrated weights from weights.json if present, else
    falls back to DEFAULT_WEIGHTS.
    """
    w = weights or get_weights()
    return (
        parts.magnitude * w["magnitude"]
        + parts.reach * w["reach"]
        + parts.novelty * w["novelty"]
        + parts.calendar * w["calendar"]
    )


# ---------------------------------------------------------------------------
# Reach: acres-affected estimates per scope. Plain heuristics — refine later.
# ---------------------------------------------------------------------------

# Approximate planted acres per major commodity (millions of acres).
COMMODITY_NATIONAL_REACH = {
    "corn": 92.0,
    "soybean": 84.0,
    "wheat": 45.0,
    "sorghum": 6.0,
    "cotton": 11.0,
}

# Top producer states per commodity, with approximate share of national acres.
COMMODITY_STATE_REACH_FRACTION: dict[str, dict[str, float]] = {
    "corn": {"19": 0.15, "17": 0.12, "31": 0.10, "27": 0.09, "20": 0.06, "39": 0.05, "38": 0.04, "18": 0.06},
    "soybean": {"19": 0.12, "17": 0.12, "31": 0.06, "27": 0.08, "20": 0.05, "39": 0.05, "29": 0.06},
    "wheat": {"20": 0.20, "38": 0.15, "30": 0.10, "46": 0.08, "31": 0.06, "41": 0.05, "53": 0.05},
}


def reach_score(domain: str, scope: str, commodity: str | None = None) -> float:
    """Heuristic 0-100 reach score from scope.

    'national' => 100. 'state:XX' => fraction of national * 100. 'county:NNNNN'
    => crude 1/3000 of national = ~3 (scaled to 30 to reward county-level
    drama). Calibration will tune the constants.
    """
    if scope == "national":
        return 100.0
    if scope.startswith("state:"):
        fips = scope.split(":", 1)[1]
        if commodity:
            frac = COMMODITY_STATE_REACH_FRACTION.get(commodity, {}).get(fips, 0.02)
        else:
            frac = 0.05
        return min(100.0, frac * 200)  # arbitrary scale: 50% of national → 100
    if scope.startswith("county:"):
        return 35.0
    return 50.0


# ---------------------------------------------------------------------------
# Novelty: penalize the same domain+scope firing in last 8 weeks.
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _recent_picks_index(as_of_iso: str) -> dict[tuple[str, str], dict]:
    """Return {(domain, scope): {n_recent, max_score}} for picks in the
    8 weeks preceding `as_of`. Cached per as_of to avoid hammering DB.
    """
    as_of = date.fromisoformat(as_of_iso)
    cutoff = as_of - timedelta(weeks=8)

    index: dict[tuple[str, str], dict] = {}
    with get_sync_session() as session:
        rows = session.execute(
            text(
                """
                SELECT signal_domain, signal_scope, COUNT(*) AS n,
                       COALESCE(MAX(score), 0) AS max_score
                FROM agent_picks
                JOIN agent_runs ON agent_picks.run_id = agent_runs.id
                WHERE agent_runs.run_date BETWEEN :cutoff AND :as_of
                GROUP BY signal_domain, signal_scope
                """
            ),
            {"cutoff": cutoff, "as_of": as_of},
        ).all()
    for r in rows:
        index[(r.signal_domain, r.signal_scope)] = {
            "n": int(r.n),
            "max_score": float(r.max_score),
        }
    return index


# Continuous slow-moving variables (week-to-week trajectories). Their
# anomaly readings drift gradually, so a stricter novelty knock prevents the
# same narrative from filling consecutive weeks unless the magnitude has
# truly accelerated. Step-change variables (price-regime, futures-move,
# accuracy outliers) keep the default 25-point knock.
CONTINUOUS_DOMAINS: frozenset[str] = frozenset({
    "exports", "drought", "weather",
})


def novelty_score(domain: str, scope: str, current_score: float, as_of: date) -> float:
    """100 if (domain, scope) has not been published in last 8 weeks; else
    fall off. Re-publish allowed if magnitude has materially increased
    (>1.5x prior published score), per §4.3.

    Continuous domains (slow-moving trajectories) get a tighter 40-point
    knock per fire instead of 25 — the underlying variable drifts smoothly
    week-to-week, so repeats are usually noise unless the trajectory has
    materially shifted.
    """
    index = _recent_picks_index(as_of.isoformat())
    prior = index.get((domain, scope))
    if prior is None:
        return 100.0
    if current_score > 1.5 * prior["max_score"]:
        return 80.0  # diminished but allowed
    knock_per_fire = 40.0 if domain in CONTINUOUS_DOMAINS else 25.0
    return max(10.0, 100.0 - knock_per_fire * prior["n"])


# ---------------------------------------------------------------------------
# Calendar fit: bonus if a USDA report lands within 7 days.
# ---------------------------------------------------------------------------

# Months when major reports drop. Used as a quick proximity heuristic — a
# detailed calendar lives in calendar_signals.py.
USDA_REPORT_MONTHS = {
    "WASDE": "every-month",         # ~2nd Tuesday
    "Crop Production": "monthly",
    "Prospective Plantings": (3,),  # late March
    "Acreage": (6,),                # late June
    "Grain Stocks": (3, 6, 9, 12),
    "Cattle on Feed": "monthly",
}


def calendar_fit_score(domain: str, as_of: date) -> float:
    """Bonus if signal's domain ties to a USDA report dropping within 7 days."""
    upcoming = upcoming_usda_reports(as_of, days=7)
    if not upcoming:
        return 0.0
    # Match domain → relevant report.
    relevant = {
        "wasde": "WASDE",
        "acreage": "Prospective Plantings" if as_of.month in (2, 3) else "Acreage",
        "yield": "Crop Production",
        "exports": None,
        "price": "WASDE",
    }
    target = relevant.get(domain)
    if target is None:
        return 0.0
    if any(r["report"] == target for r in upcoming):
        return 100.0
    return 30.0  # SOMETHING is coming, partial credit


def upcoming_usda_reports(as_of: date, *, days: int = 14) -> list[dict]:
    """Return list of {report, date, days_until} for reports landing in next N days.

    Approximate dates only — used for "is something coming?" questions, not
    for precise scheduling.
    """
    out: list[dict] = []
    horizon = as_of + timedelta(days=days)

    # WASDE: 2nd Tuesday of each month.
    for month_offset in range(0, 2):
        candidate = (as_of.replace(day=1) + timedelta(days=32 * month_offset)).replace(day=1)
        # Find 2nd Tuesday.
        first_dow = candidate.weekday()
        # Tuesday = 1
        days_to_tuesday = (1 - first_dow) % 7
        wasde_date = candidate + timedelta(days=days_to_tuesday + 7)
        if as_of <= wasde_date <= horizon:
            out.append({
                "report": "WASDE",
                "date": wasde_date,
                "days_until": (wasde_date - as_of).days,
            })

    # Prospective Plantings: March 31 (approximate)
    pp_date = date(as_of.year, 3, 31)
    if as_of <= pp_date <= horizon:
        out.append({"report": "Prospective Plantings", "date": pp_date, "days_until": (pp_date - as_of).days})

    # Acreage: June 30 (approximate)
    acreage_date = date(as_of.year, 6, 30)
    if as_of <= acreage_date <= horizon:
        out.append({"report": "Acreage", "date": acreage_date, "days_until": (acreage_date - as_of).days})

    # Crop Production: monthly Aug-Nov
    if as_of.month in (8, 9, 10, 11):
        cp_date = (as_of.replace(day=1) + timedelta(days=11)).replace(day=12)
        if as_of <= cp_date <= horizon:
            out.append({
                "report": "Crop Production",
                "date": cp_date,
                "days_until": (cp_date - as_of).days,
            })

    return out


# ---------------------------------------------------------------------------
# Convenience: collect signals from all sources, swallow exceptions per source.
# ---------------------------------------------------------------------------


def gather(sources: Iterable[callable], as_of_date: date) -> list:
    """Run each source's collect() with as_of, accumulate Signals, log failures.

    A single source failing must not wedge the whole run — the LLM still has
    candidates from the other 11.
    """
    from backend.agent.signal_board import Signal  # avoid circular import

    out: list[Signal] = []
    for src in sources:
        name = getattr(src, "__module__", str(src))
        try:
            sigs = src(as_of_date)
            out.extend(sigs)
            logger.info("signal source %s: %d signals", name, len(sigs))
        except Exception as exc:  # noqa: BLE001
            logger.warning("signal source %s failed: %s", name, exc, exc_info=False)
    return out
