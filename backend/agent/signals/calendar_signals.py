"""Calendar-proximity signal source.

Spec §4.1 source 12: a USDA report drops within 7 days, national.

Pure Python — no DB. The output is a single low-magnitude signal that exists
mostly to bias the editor toward narratives the upcoming report will move.
"""

from __future__ import annotations

from datetime import date

from backend.agent.signal_board import Signal
from backend.agent.signals._common import (
    ScoreParts,
    compute_score,
    novelty_score,
    upcoming_usda_reports,
)


def collect(as_of_date: date) -> list[Signal]:
    upcoming = upcoming_usda_reports(as_of_date, days=7)
    out: list[Signal] = []
    for rpt in upcoming:
        days_until = int(rpt["days_until"])
        # Closer = higher magnitude; floor at 30, ceiling at 80.
        magnitude = max(30.0, 80.0 - days_until * 5)
        scope = "national"
        domain = "calendar"

        parts = ScoreParts(
            magnitude=magnitude,
            reach=100.0,
            novelty=novelty_score(domain, scope, magnitude * 0.5, as_of_date),
            calendar=100.0,  # tautologically calendar-fit
        )
        score = compute_score(parts)

        out.append(
            Signal(
                id=f"calendar:{rpt['report'].lower().replace(' ', '-')}:{rpt['date']}",
                domain=domain,
                scope=scope,
                headline=(
                    f"USDA {rpt['report']} drops in {days_until} days "
                    f"({rpt['date']})"
                ),
                score=score,
                direction="neutral",
                evidence={
                    "report": rpt["report"],
                    "report_date": str(rpt["date"]),
                    "days_until": days_until,
                    "score_parts": parts.__dict__,
                },
                sources=["calendar"],
            )
        )
    return out
