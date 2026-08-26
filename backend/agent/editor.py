"""Editor step (§6 of analyst-agent-tech-spec.md).

Takes ranked candidates + 8-week pick history + mood JSON, returns the LLM's
1 lead + 2-3 briefs as a strict JSON object. No tools — pure selection.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text

from backend.agent.llm import CallStats, call_json, load_prompt
from backend.agent.mood import Mood
from backend.agent.signal_board import Signal
from backend.etl.common import get_sync_session

logger = logging.getLogger(__name__)


@dataclass
class Pick:
    """One editor pick — lead or brief."""

    role: str  # 'lead' | 'brief'
    signal: Signal
    editorial_angle: str
    rationale: str = ""


@dataclass
class EditorPlan:
    """Editor's full output for a week."""

    lead: Pick
    briefs: list[Pick]
    raw_json: dict[str, Any] = field(default_factory=dict)

    def all_picks(self) -> list[Pick]:
        return [self.lead, *self.briefs]


def pick_stories(
    candidates: list[Signal],
    *,
    mood: Mood,
    as_of_date: date,
    stats: CallStats | None = None,
    extra_note: str | None = None,
) -> EditorPlan:
    """Run the editor step.

    Raises ValueError if the LLM picks an invalid signal_id, the briefs count
    is out of [2, 3], or the response can't be parsed.

    extra_note: optional operator instruction appended to the user message,
    used by special issues (e.g. the all-educational run) to relax standing
    rules like the 2-feature cap for one issue.
    """
    if not candidates:
        raise ValueError("editor: no candidates to pick from")

    by_id = {s.id: s for s in candidates}
    prior_picks = _recent_picks_for_prompt(as_of_date)
    user_msg = _format_user(candidates, prior_picks, mood)
    if extra_note:
        user_msg += f"\n\nOPERATOR_NOTE (overrides standing rules for THIS issue only):\n{extra_note}"

    raw = call_json(
        system=load_prompt("editor_system"),
        user=user_msg,
        max_tokens=2048,
        stats=stats,
    )

    plan = _validate(raw, by_id)
    return _enforce_diet(plan, candidates)


def _validate(raw: dict[str, Any], by_id: dict[str, Signal]) -> EditorPlan:
    lead_data = raw.get("lead") or {}
    briefs_data = raw.get("briefs") or []
    if not isinstance(lead_data, dict):
        raise ValueError("editor.lead must be a dict")
    if not isinstance(briefs_data, list):
        raise ValueError("editor.briefs must be a list")

    lead_id = lead_data.get("signal_id")
    if lead_id not in by_id:
        raise ValueError(f"editor: lead signal_id {lead_id!r} not in candidates")

    if not (2 <= len(briefs_data) <= 3):
        raise ValueError(f"editor: briefs must be 2 or 3, got {len(briefs_data)}")

    seen_ids: set[str] = {lead_id}
    briefs: list[Pick] = []
    for b in briefs_data:
        bid = b.get("signal_id")
        if bid not in by_id:
            raise ValueError(f"editor: brief signal_id {bid!r} not in candidates")
        if bid in seen_ids:
            raise ValueError(f"editor: duplicate signal_id across picks: {bid}")
        seen_ids.add(bid)
        briefs.append(
            Pick(
                role="brief",
                signal=by_id[bid],
                editorial_angle=str(b.get("editorial_angle", "")).strip(),
                rationale=str(b.get("rationale", "")).strip(),
            )
        )

    lead = Pick(
        role="lead",
        signal=by_id[lead_id],
        editorial_angle=str(lead_data.get("editorial_angle", "")).strip(),
        rationale=str(lead_data.get("rationale", "")).strip(),
    )
    return EditorPlan(lead=lead, briefs=briefs, raw_json=raw)


# ---------------------------------------------------------------------------
# Deterministic editorial-diet enforcement (2026-08-03 review).
# ---------------------------------------------------------------------------


def _enforce_diet(plan: EditorPlan, candidates: list[Signal]) -> EditorPlan:
    """Post-LLM guardrails the prompt asks for but cannot guarantee:

      1. An accuracy-domain signal never leads. If the LLM leads with one,
         swap it with the highest-scored non-accuracy brief.
      2. Exactly-one-feature slot: if any feature-* candidate exists but no
         feature was picked, replace the lowest-scored non-feature brief
         with the best feature candidate. The newsletter's educational
         mission gets a reserved seat, not a lottery ticket.
    """
    # --- rule 1: accuracy never leads ---
    if plan.lead.signal.domain == "accuracy":
        swap_idx = None
        best = -1.0
        for i, b in enumerate(plan.briefs):
            if b.signal.domain != "accuracy" and b.signal.final_score > best:
                best = b.signal.final_score
                swap_idx = i
        if swap_idx is not None:
            old_lead, promoted = plan.lead, plan.briefs[swap_idx]
            logger.info(
                "diet: demoting accuracy lead %s; promoting %s",
                old_lead.signal.id, promoted.signal.id,
            )
            plan.lead = Pick(
                role="lead",
                signal=promoted.signal,
                editorial_angle=promoted.editorial_angle,
                rationale="promoted: accuracy stories do not lead",
            )
            plan.briefs[swap_idx] = Pick(
                role="brief",
                signal=old_lead.signal,
                editorial_angle=old_lead.editorial_angle,
                rationale="demoted from lead: accuracy stories do not lead",
            )

    # --- rule 2: guaranteed feature slot ---
    has_feature = any(
        p.signal.domain.startswith("feature-") for p in plan.all_picks()
    )
    if not has_feature:
        features = [s for s in candidates if s.domain.startswith("feature-")]
        picked_ids = {p.signal.id for p in plan.all_picks()}
        features = [s for s in features if s.id not in picked_ids]
        if features:
            best_feature = max(features, key=lambda s: s.final_score)
            idx = min(
                range(len(plan.briefs)),
                key=lambda i: plan.briefs[i].signal.final_score,
            )
            logger.info(
                "diet: swapping brief %s for feature %s (reserved slot)",
                plan.briefs[idx].signal.id, best_feature.id,
            )
            plan.briefs[idx] = Pick(
                role="brief",
                signal=best_feature,
                editorial_angle=(
                    "Reserved educational slot: teach the mechanism behind "
                    "this structural feature and anchor it to the current season."
                ),
                rationale="deterministic feature slot (editor picked none)",
            )
    return plan


# ---------------------------------------------------------------------------
# Prior-picks lookup for dedup memory.
# ---------------------------------------------------------------------------


def _recent_picks_for_prompt(as_of: date) -> list[dict[str, Any]]:
    """Last 8 weeks of (domain, scope, headline, role) for the editor's prompt."""
    cutoff = as_of - timedelta(weeks=8)
    sql = text(
        """
        SELECT p.signal_domain, p.signal_scope, p.headline, p.role, p.score, r.run_date
        FROM agent_picks p
        JOIN agent_runs r ON r.id = p.run_id
        WHERE r.run_date BETWEEN :cutoff AND :as_of
        ORDER BY r.run_date DESC, p.role
        """
    )
    out: list[dict[str, Any]] = []
    with get_sync_session() as s:
        for row in s.execute(sql, {"cutoff": cutoff, "as_of": as_of}).all():
            out.append(
                {
                    "run_date": str(row.run_date),
                    "role": row.role,
                    "domain": row.signal_domain,
                    "scope": row.signal_scope,
                    "score": float(row.score) if row.score is not None else None,
                    "headline": row.headline,
                }
            )
    return out


def _format_user(
    candidates: list[Signal],
    prior_picks: list[dict[str, Any]],
    mood: Mood,
) -> str:
    """Render input as a single user message."""
    cand_lines = ["RANKED_CANDIDATES (sorted by final_score, top is best):"]
    for s in candidates:
        cand_lines.append(
            f"  - id={s.id} domain={s.domain} scope={s.scope} score={s.final_score:.1f} "
            f"direction={s.direction}"
        )
        cand_lines.append(f"    headline: {s.headline}")
        # Compact evidence (drop score_parts to save tokens).
        ev = {k: v for k, v in s.evidence.items() if k != "score_parts"}
        cand_lines.append(f"    evidence: {json.dumps(ev, default=str)[:600]}")
    cand_block = "\n".join(cand_lines)

    if prior_picks:
        pp_lines = ["PRIOR_PICKS (last 8 weeks):"]
        for p in prior_picks:
            pp_lines.append(
                f"  - {p['run_date']} {p['role']:5s} domain={p['domain']} "
                f"scope={p['scope']} score={p['score']}"
            )
        pp_block = "\n".join(pp_lines)
    else:
        pp_block = "PRIOR_PICKS: (none — first issue)"

    mood_block = (
        "MOOD:\n"
        f"  primary_narrative: {mood.primary_narrative}\n"
        f"  tags: {mood.mood_tags}\n"
        f"  biases: {mood.biases}\n"
        f"  avoid_unless_dramatic: {mood.avoid_unless_dramatic}"
    )

    return "\n\n".join([cand_block, pp_block, mood_block])
