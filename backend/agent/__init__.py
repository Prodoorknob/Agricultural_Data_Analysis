"""FieldPulse Weekly — Module 05 analyst agent.

Spec: research/analyst-agent-tech-spec.md (v0.3).

Build order (§13 of the spec):
  1. Schema + as-of-date plumbing                  - DONE
  2. Signal board + weight calibration             - TODO (signal_board.py + signals/)
  3. Mood synthesizer + editor                     - TODO (mood.py, editor.py)
  4. Researcher loop                               - TODO (researcher.py, tools.py)
  5. Writer + fact-checker                         - TODO (writer.py, factcheck.py)
  6. Publisher + chart renderer + Slack/email      - PARTIAL (notify.py shipped)
  7. Frontend /insights + /insights/draft          - TODO (web_app side)
  8. Cron + monitoring + 12-week backfill          - TODO (runner.py)
"""

__all__ = [
    "notify",
]
