"""Signal Board — deterministic Python that ranks weekly newsworthiness.

Spec: §4 of analyst-agent-tech-spec.md.

This is the load-bearing piece of the agent: an LLM should never decide what
counts as anomalous. The board normalizes 12 signal sources to a common
shape, scores each on (magnitude, reach, novelty, calendar fit), then hands
the LLM a ranked candidate list to pick from.

Step 2 of §13 (next implementation pass): per-source signal builders in
`backend/agent/signals/*.py` that yield Signal records, plus the weight
calibration over 6 months of historical labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal


SignalDomain = Literal[
    "yield", "price", "acreage", "weather", "drought", "wasde",
    "exports", "futures", "trend_break", "accuracy", "calendar",
]
Direction = Literal["positive", "negative", "neutral"]


@dataclass
class Signal:
    """Common shape for every signal source. See §4 of the spec."""

    id: str                          # stable identifier for dedup
    domain: SignalDomain
    scope: str                       # 'national' | 'state:IA' | 'county:19153'
    headline: str                    # 1-line factual summary
    score: float                     # 0-100 newsworthiness (pre-mood)
    direction: Direction
    evidence: dict                   # raw numbers — handed to LLM as ground truth
    sources: list[str] = field(default_factory=list)  # table names / S3 paths
    valid_until: date | None = None  # when this signal becomes stale

    # Filled in by `apply_mood()` — never set by signal sources directly.
    mood_boost: float = 0.0

    @property
    def final_score(self) -> float:
        return self.score + self.mood_boost


# --- Mood-boost arithmetic (§5, fixed in spec v0.3) ---


def apply_mood_boost(signals: list[Signal], biases: dict[str, float]) -> None:
    """Mutate `signals` in place: set `mood_boost` from the mood JSON's biases.

    Formula (from §5, v0.3 spec): `clamp(score * (bias - 1.0), -30, 30)`.
    A bias of 1.0 means neutral (0 boost). Domains absent from the bias dict
    default to 1.0.
    """
    for sig in signals:
        bias = float(biases.get(sig.domain, 1.0))
        raw = sig.score * (bias - 1.0)
        sig.mood_boost = max(-30.0, min(30.0, raw))


def rank(signals: list[Signal], top_n: int = 20) -> list[Signal]:
    """Sort by final_score descending and take the top N candidates."""
    return sorted(signals, key=lambda s: s.final_score, reverse=True)[:top_n]


# ---------------------------------------------------------------------------
# build_candidates — runs all 12 signal sources and returns ranked output.
# ---------------------------------------------------------------------------


def build_candidates(
    as_of_date: date,
    *,
    top_n: int = 20,
    biases: dict[str, float] | None = None,
) -> list[Signal]:
    """Run all signal sources, apply mood biases, return top-N candidates.

    Sources are imported lazily so a missing dependency in one source
    doesn't break startup for the others.
    """
    import logging

    from backend.agent.signals import (
        acreage_signals,
        calendar_signals,
        exports_signals,
        price_signals,
        trend_signals,
        wasde_signals,
        weather_signals,
        yield_signals,
    )
    from backend.agent.signals._common import gather

    log = logging.getLogger(__name__)

    sources = [
        yield_signals.collect,
        acreage_signals.collect,
        price_signals.collect,
        wasde_signals.collect,
        weather_signals.collect,
        exports_signals.collect,
        trend_signals.collect,
        calendar_signals.collect,
    ]

    signals = gather(sources, as_of_date)
    log.info("signal_board: gathered %d candidates from %d sources", len(signals), len(sources))

    if biases:
        apply_mood_boost(signals, biases)

    ranked = rank(signals, top_n=top_n)
    log.info(
        "signal_board: top-%d candidates (max final_score=%.1f)",
        len(ranked),
        ranked[0].final_score if ranked else 0.0,
    )
    return ranked
