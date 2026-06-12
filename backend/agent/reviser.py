"""Reviser (corrections editor).

Takes a draft, the fact-checker's flagged issues, and the dossier, and returns
a corrected draft. The reviser sees ONLY the dossier numbers and the flagged
claims, and is instructed to correct each figure from the dossier or drop it,
never to invent one. This closes the loop on the fact-checker: instead of a
single bad number aborting the whole run, the writer's draft gets a bounded
number of targeted corrective passes before the gate is re-evaluated.

No tools. Pure dossier-grounded text-in, text-out, mirroring writer.py.
"""

from __future__ import annotations

import logging

from backend.agent.factcheck import CheckResult, _dossier_summary
from backend.agent.llm import CallStats, call_text, load_prompt
from backend.agent.researcher import FullDossier
from backend.agent.writer import WrittenDraft, _scrub_em_dashes

logger = logging.getLogger(__name__)


def revise_draft(
    draft: WrittenDraft,
    fact_result: CheckResult,
    *,
    dossier: FullDossier,
    stats: CallStats | None = None,
) -> WrittenDraft:
    """Return a corrected draft addressing the fact-checker's major issues.

    chart_specs are carried over unchanged; only the prose is revised.
    """
    user_msg = _format_user(draft.markdown, fact_result, dossier)
    md = call_text(
        system=load_prompt("reviser_system"),
        user=user_msg,
        max_tokens=4096,
        stats=stats,
        temperature=0.2,  # conservative: faithful corrections, not rewrites
    )
    md = _scrub_em_dashes(md)
    return WrittenDraft(markdown=md, chart_specs=draft.chart_specs)


def _format_user(
    markdown: str, fact_result: CheckResult, dossier: FullDossier
) -> str:
    parts: list[str] = []
    parts.append(
        "FLAGGED_ISSUES (each is a number or claim the fact-checker could not "
        "verify against the dossier). Fix every one:"
    )
    majors = fact_result.major_issues
    for i, iss in enumerate(majors, 1):
        parts.append(f"  {i}. [{iss.source}] {iss.detail}")
        if iss.quote:
            parts.append(f'     context: "{iss.quote}"')
    parts.append("")
    parts.append("DOSSIER (the ONLY permitted source of numbers):")
    parts.append(_dossier_summary(dossier))
    parts.append("")
    parts.append("CURRENT_DRAFT:")
    parts.append(markdown)
    return "\n".join(parts)
