"""Composite signal source — bundles cross-commodity narratives.

Spec context: when soybean export pace runs -49% AND corn runs +20% in the
same week, the natural editorial framing is "export pace diverges" (one
composite story), not two competing briefs. Without composites the editor
can only pick one; with composites the editor sees a higher-scored
"diverging-export" candidate it will naturally prefer.

Runs AFTER the per-source `gather()` in signal_board.build_candidates.
Returns (new_composites, suppress_ids) so the caller can drop the
constituent singletons before ranking.

Scope today: same-domain, same-week, multi-commodity national signals.
Future v2: cross-domain ("drought + export pace + WASDE all bearish corn")
and multi-state regional clusters.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from typing import Any

from backend.agent.signal_board import Signal
from backend.agent.signals._common import (
    ScoreParts,
    calendar_fit_score,
    compute_score,
    novelty_score,
    reach_score,
)

logger = logging.getLogger(__name__)


# Domains where multi-commodity bundling produces a stronger story than
# the components. Excluded: 'accuracy' (per-county misses don't compose),
# 'trend_break' (already cross-history), 'calendar' (singleton by nature),
# 'price'/'acreage' (low-frequency, the editor handles them naturally).
COMPOSITE_DOMAINS = {
    "exports": "Export commitments",
    "wasde": "WASDE supply outlook",
    "futures": "Front-month futures",
    "drought": "Drought stress",
    "weather": "Crop weather",
}

# Bundling bonus added to max-component-score, then capped at 100.
BUNDLING_BONUS = 8.0

# Minimum number of distinct commodities required to bundle.
MIN_COMPONENTS = 2


def build_composites(
    signals: list[Signal], as_of_date: date
) -> tuple[list[Signal], set[str]]:
    """Group same-domain signals by commodity and emit composites.

    Returns:
        (new_composite_signals, ids_of_constituent_singletons_to_suppress)
    """
    suppress: set[str] = set()
    composites: list[Signal] = []

    # Bucket by domain.
    by_domain: dict[str, list[tuple[str, Signal]]] = defaultdict(list)
    for sig in signals:
        if sig.domain not in COMPOSITE_DOMAINS:
            continue
        commodity = _extract_commodity(sig)
        if not commodity:
            continue
        by_domain[sig.domain].append((commodity, sig))

    for domain, components in by_domain.items():
        # Need ≥ MIN_COMPONENTS distinct commodities.
        commodities = {c for c, _ in components}
        if len(commodities) < MIN_COMPONENTS:
            continue

        # Pick the strongest signal per commodity (a domain may emit multiple
        # rows for the same commodity, e.g. price-regime + futures-move).
        strongest_per_commodity: dict[str, Signal] = {}
        for commodity, sig in components:
            cur = strongest_per_commodity.get(commodity)
            if cur is None or sig.score > cur.score:
                strongest_per_commodity[commodity] = sig

        ordered = sorted(
            strongest_per_commodity.items(),
            key=lambda cs: cs[1].score,
            reverse=True,
        )[:5]

        comp_signals = [s for _, s in ordered]
        max_score = max(s.score for s in comp_signals)
        composite_score_pre = min(100.0, max_score + BUNDLING_BONUS)

        scope = "national"
        composite_domain = f"composite-{domain}"

        parts = ScoreParts(
            magnitude=composite_score_pre,
            reach=100.0,
            novelty=novelty_score(composite_domain, scope, composite_score_pre, as_of_date),
            calendar=calendar_fit_score(domain, as_of_date),
        )
        score = compute_score(parts)

        directions = {s.direction for s in comp_signals}
        spread = "diverges" if len(directions) > 1 else (
            "uniformly negative" if "negative" in directions else "uniformly positive"
        )

        headline = _format_headline(domain, ordered, spread)
        composite_id = (
            f"composite-{domain}:{scope}:{as_of_date.isoformat()}"
        )

        evidence: dict[str, Any] = {
            "constituent_domain": domain,
            "spread": spread,
            "as_of_date": as_of_date.isoformat(),
            "components": [
                {
                    "commodity": commodity,
                    "signal_id": s.id,
                    "score": round(s.score, 1),
                    "direction": s.direction,
                    "headline": s.headline,
                    "metric": _extract_metric(s),
                }
                for commodity, s in ordered
            ],
            "score_parts": parts.__dict__,
        }

        composites.append(
            Signal(
                id=composite_id,
                domain=composite_domain,
                scope=scope,
                headline=headline,
                score=score,
                direction="neutral" if len(directions) > 1 else next(iter(directions)),
                evidence=evidence,
                sources=sorted({src for s in comp_signals for src in s.sources}),
            )
        )
        suppress.update(s.id for s in comp_signals)

    return composites, suppress


# ---------------------------------------------------------------------------
# Per-domain headline + metric formatting.
# ---------------------------------------------------------------------------


def _extract_commodity(sig: Signal) -> str | None:
    """Pull a normalized commodity slug from a signal's evidence/id."""
    ev = sig.evidence
    if isinstance(ev, dict):
        c = ev.get("commodity") or ev.get("crop")
        if c:
            return str(c).split("_")[0].lower()  # wheat_winter -> wheat
    # Fallback: parse from id like "export-pace:soybean:2026-04-02"
    parts = sig.id.split(":")
    if len(parts) >= 2:
        candidate = parts[1].lower()
        if candidate in {"corn", "soybean", "wheat", "sorghum", "cotton", "rice", "oats", "barley"}:
            return candidate
    return None


def _extract_metric(sig: Signal) -> str:
    """Render the headline-relevant magnitude as a short string per domain."""
    ev = sig.evidence if isinstance(sig.evidence, dict) else {}
    if sig.domain == "exports":
        v = ev.get("pace_pct_vs_5yr")
        return f"{v:+.0f}%" if isinstance(v, (int, float)) else "—"
    if sig.domain == "wasde":
        v = ev.get("delta_pp")
        return f"{v:+.1f} pp" if isinstance(v, (int, float)) else "—"
    if sig.domain == "futures":
        v = ev.get("pct_move_5d")
        return f"{v:+.1f}%" if isinstance(v, (int, float)) else "—"
    if sig.domain == "drought":
        v = ev.get("delta_points")
        return f"{v:+.0f} DSCI" if isinstance(v, (int, float)) else "—"
    if sig.domain == "weather":
        v = ev.get("anomaly_pct_vs_baseline") or ev.get("drop_points")
        if isinstance(v, (int, float)):
            return (
                f"{v:+.0f}%"
                if "anomaly_pct_vs_baseline" in ev
                else f"{v:.0f}-pt CCI drop"
            )
        return "—"
    return "—"


def _format_headline(
    domain: str, ordered: list[tuple[str, Signal]], spread: str
) -> str:
    label = COMPOSITE_DOMAINS.get(domain, domain)
    parts = [
        f"{commodity} {_extract_metric(s)}" for commodity, s in ordered
    ]
    return f"{label} {spread} across crops: " + " / ".join(parts)
