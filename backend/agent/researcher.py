"""Researcher (§7 of analyst-agent-tech-spec.md).

Runs one tool-use loop per story (lead + briefs), capped at 8 tool calls per
story and 30 across the run (§7.2). Returns a Dossier the writer can use.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from backend.agent.editor import EditorPlan, Pick
from backend.agent.llm import CallStats, call_with_tools, load_prompt
from backend.agent.mood import Mood
from backend.agent.tools import build_tool_handlers, build_tool_specs
from backend.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class StoryDossier:
    """Researcher output for a single story."""

    role: str          # 'lead' | 'brief'
    signal_id: str
    headline: str
    editorial_angle: str
    claims: list[str] = field(default_factory=list)
    peer_context: list[str] = field(default_factory=list)
    what_to_watch: str = ""
    chart_specs: list[dict[str, Any]] = field(default_factory=list)
    tool_log: list[dict[str, Any]] = field(default_factory=list)
    raw_text: str = ""


@dataclass
class FullDossier:
    """All stories' dossiers + global tool budget tracking."""

    lead: StoryDossier
    briefs: list[StoryDossier]
    total_tool_calls: int = 0

    def all(self) -> list[StoryDossier]:
        return [self.lead, *self.briefs]


def research(
    plan: EditorPlan,
    *,
    mood: Mood,
    as_of_date: date,
    stats: CallStats | None = None,
) -> FullDossier:
    settings = get_settings()
    per_story_cap = settings.AGENT_TOOL_CALL_PER_STORY_CAP
    global_cap = settings.AGENT_TOOL_CALL_GLOBAL_CAP

    tool_specs = build_tool_specs()
    tool_handlers = build_tool_handlers(as_of_date)
    system_prompt = load_prompt("researcher_system")

    used = 0
    dossiers: list[StoryDossier] = []
    for pick in plan.all_picks():
        remaining_global = max(0, global_cap - used)
        story_cap = max(0, min(per_story_cap, remaining_global))
        if story_cap == 0:
            logger.warning(
                "researcher: hit global tool-call cap (%d), skipping story %s",
                global_cap, pick.signal.id,
            )
            dossiers.append(_empty_dossier(pick))
            continue
        ds = _research_one(
            pick, mood,
            tool_specs=tool_specs,
            tool_handlers=tool_handlers,
            system_prompt=system_prompt,
            story_cap=story_cap,
            stats=stats,
        )
        dossiers.append(ds)
        used += len([t for t in ds.tool_log if not t.get("is_error")])

    return FullDossier(
        lead=dossiers[0],
        briefs=dossiers[1:],
        total_tool_calls=used,
    )


def _empty_dossier(pick: Pick) -> StoryDossier:
    return StoryDossier(
        role=pick.role,
        signal_id=pick.signal.id,
        headline=pick.signal.headline,
        editorial_angle=pick.editorial_angle,
        what_to_watch="(researcher skipped — global tool-call budget exhausted)",
    )


def _research_one(
    pick: Pick,
    mood: Mood,
    *,
    tool_specs: list[dict[str, Any]],
    tool_handlers: dict[str, Any],
    system_prompt: str,
    story_cap: int,
    stats: CallStats | None,
) -> StoryDossier:
    user_msg = _format_story(pick, mood)
    result = call_with_tools(
        system=system_prompt,
        user=user_msg,
        tools=tool_specs,
        tool_handlers=tool_handlers,
        max_tokens=2048,
        max_tool_calls=story_cap,
        stats=stats,
    )
    parsed = _parse_dossier_text(result["final_text"])
    return StoryDossier(
        role=pick.role,
        signal_id=pick.signal.id,
        headline=pick.signal.headline,
        editorial_angle=pick.editorial_angle,
        claims=parsed["claims"],
        peer_context=parsed["peer_context"],
        what_to_watch=parsed["what_to_watch"],
        chart_specs=parsed["chart_specs"],
        tool_log=result["tool_log"],
        raw_text=result["final_text"],
    )


def _format_story(pick: Pick, mood: Mood) -> str:
    sig = pick.signal
    ev = {k: v for k, v in sig.evidence.items() if k != "score_parts"}
    return (
        f"ROLE: {pick.role}\n"
        f"STORY:\n"
        f"  signal_id: {sig.id}\n"
        f"  domain: {sig.domain}\n"
        f"  scope: {sig.scope}\n"
        f"  headline: {sig.headline}\n"
        f"  evidence: {json.dumps(ev, default=str)}\n\n"
        f"EDITORIAL_ANGLE:\n  {pick.editorial_angle}\n\n"
        f"WEEK_MOOD:\n"
        f"  primary_narrative: {mood.primary_narrative}\n"
        f"  tags: {mood.mood_tags}\n"
    )


_SECTION_RE = re.compile(
    r"^\s*(CLAIMS|PEER_CONTEXT|WHAT_TO_WATCH|CHART_SPECS)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def _parse_dossier_text(text: str) -> dict[str, Any]:
    """Parse the researcher's plain-text output into a dossier dict.

    Sections are recognized as bare lines containing one of the four section
    headers. Bullets ("- ...") under each section become list items.
    """
    if not text:
        return {"claims": [], "peer_context": [], "what_to_watch": "", "chart_specs": []}

    sections: dict[str, list[str]] = {
        "claims": [], "peer_context": [], "what_to_watch": [], "chart_specs": [],
    }
    current: str | None = None
    for line in text.splitlines():
        m = _SECTION_RE.match(line)
        if m:
            key = m.group(1).strip().lower()
            current = {
                "claims": "claims",
                "peer_context": "peer_context",
                "what_to_watch": "what_to_watch",
                "chart_specs": "chart_specs",
            }.get(key, current)
            continue
        if current is None:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        # Strip leading bullet markers.
        cleaned = re.sub(r"^[-*•]\s+", "", stripped)
        sections[current].append(cleaned)

    chart_specs: list[dict[str, Any]] = []
    for line in sections["chart_specs"]:
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and obj.get("id") and obj.get("kind"):
                chart_specs.append(obj)
        except json.JSONDecodeError:
            continue

    return {
        "claims": sections["claims"],
        "peer_context": sections["peer_context"],
        "what_to_watch": " ".join(sections["what_to_watch"]).strip(),
        "chart_specs": chart_specs,
    }
