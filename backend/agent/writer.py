"""Writer (§8.1 of analyst-agent-tech-spec.md).

Turns a FullDossier into a publishable markdown draft. No tools — the writer
only sees the dossier and is forbidden from inventing numbers.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from backend.agent.llm import CallStats, call_text, load_prompt
from backend.agent.mood import Mood
from backend.agent.researcher import FullDossier, StoryDossier

logger = logging.getLogger(__name__)


@dataclass
class WrittenDraft:
    """Writer output."""

    markdown: str
    chart_specs: list[dict[str, Any]] = field(default_factory=list)


def write_issue(
    dossier: FullDossier,
    *,
    mood: Mood,
    as_of_date: date,
    stats: CallStats | None = None,
) -> WrittenDraft:
    user_msg = _format_user(dossier, mood, as_of_date)
    md = call_text(
        system=load_prompt("writer_system"),
        user=user_msg,
        max_tokens=4096,
        stats=stats,
        temperature=0.4,
    )

    md = _scrub_em_dashes(md)
    chart_specs = _gather_chart_specs(dossier)
    return WrittenDraft(markdown=md, chart_specs=chart_specs)


def _scrub_em_dashes(md: str) -> str:
    """Replace any em dashes the model snuck in. Project convention (§8.1)."""
    if "—" not in md:
        return md
    logger.warning("writer: model emitted em dashes; scrubbing")
    return md.replace("—", ", ")


def _gather_chart_specs(dossier: FullDossier) -> list[dict[str, Any]]:
    """Flatten chart_specs across stories for the publisher to render."""
    out: list[dict[str, Any]] = []
    for story in dossier.all():
        for spec in story.chart_specs:
            spec = dict(spec)
            spec["_source_story"] = story.signal_id
            out.append(spec)
    return out


def _format_user(dossier: FullDossier, mood: Mood, as_of_date: date) -> str:
    parts: list[str] = []
    parts.append(f"as_of_date: {as_of_date.isoformat()}")
    parts.append(f"title_seed: fieldpulse-{as_of_date.isoformat()}")
    parts.append("")
    parts.append("MOOD:")
    parts.append(f"  primary_narrative: {mood.primary_narrative}")
    parts.append(f"  tags: {mood.mood_tags}")
    parts.append("")
    parts.append("LEAD:")
    parts.append(_render_story(dossier.lead))
    parts.append("")
    parts.append("BRIEFS:")
    for i, b in enumerate(dossier.briefs, 1):
        parts.append(f"--- brief {i} ---")
        parts.append(_render_story(b))
        parts.append("")
    return "\n".join(parts)


def _render_story(story: StoryDossier) -> str:
    return (
        f"  signal_id: {story.signal_id}\n"
        f"  headline: {story.headline}\n"
        f"  editorial_angle: {story.editorial_angle}\n"
        f"  claims:\n" + "".join(f"    - {c}\n" for c in story.claims) +
        f"  peer_context:\n" + "".join(f"    - {p}\n" for p in story.peer_context) +
        f"  what_to_watch: {story.what_to_watch}\n"
        f"  chart_specs: {json.dumps(story.chart_specs, default=str)[:600]}"
    )
