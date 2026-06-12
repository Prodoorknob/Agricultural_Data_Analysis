"""Slack + email notifications for FieldPulse Weekly.

Implements the Knowledge Curator Slack pattern: server-side `slack_sdk`
WebClient with a bot token, no MCP dependency. Used by the publisher (§9.1)
for both success/draft-ready pings and failure alerts.

Config (read from `.env` via `backend.config.Settings`):
  SLACK_BOT_TOKEN             - xoxb-... bot token
  SLACK_CHANNEL_FIELDPULSE    - channel ID (Cxxxxxxxx) for #fieldpulse-weekly
  FIELDPULSE_ALERT_EMAIL      - optional email for failure alerts
  PUBLIC_BASE_URL             - frontend host, used to build draft links

Both `notify_draft_ready` and `notify_failure` are best-effort: they log
exceptions and return a status dict instead of raising, because a Slack
outage should never wedge the agent run.
"""

from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

from backend.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class NotifyResult:
    slack_ok: bool
    slack_error: str | None
    email_ok: bool
    email_error: str | None


def _slack_client():
    """Construct a slack_sdk WebClient or return None if unconfigured."""
    settings = get_settings()
    if not settings.SLACK_BOT_TOKEN or not settings.SLACK_CHANNEL_FIELDPULSE:
        return None
    try:
        from slack_sdk import WebClient
    except ImportError:
        logger.warning("slack_sdk not installed; skipping Slack notification")
        return None
    return WebClient(token=settings.SLACK_BOT_TOKEN)


def _post_slack(blocks: list[dict[str, Any]], fallback_text: str) -> tuple[bool, str | None]:
    """Post a Block Kit message. Returns (ok, error)."""
    settings = get_settings()
    client = _slack_client()
    if client is None:
        return False, "slack not configured"
    try:
        client.chat_postMessage(
            channel=settings.SLACK_CHANNEL_FIELDPULSE,
            text=fallback_text,
            blocks=blocks,
        )
        return True, None
    except Exception as exc:
        logger.exception("Slack post failed: %s", exc)
        return False, str(exc)


def _send_email(subject: str, body: str) -> tuple[bool, str | None]:
    """Best-effort SMTP send for failure alerts.

    Uses local SMTP relay on the EC2 host (postfix or AWS SES via SMTP
    interface). Configured outside this module — if no SMTP server is
    reachable, the call silently fails and we rely on Slack.
    """
    settings = get_settings()
    to_addr = settings.FIELDPULSE_ALERT_EMAIL
    if not to_addr:
        return False, "no alert email configured"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"fieldpulse-agent@{_smtp_domain()}"
    msg["To"] = to_addr
    msg.set_content(body)
    try:
        with smtplib.SMTP("localhost", timeout=5) as smtp:
            smtp.send_message(msg)
        return True, None
    except Exception as exc:
        logger.exception("Email send failed: %s", exc)
        return False, str(exc)


def _smtp_domain() -> str:
    settings = get_settings()
    base = settings.PUBLIC_BASE_URL or "rvedire.com"
    return base.replace("https://", "").replace("http://", "").rstrip("/").split("/")[0]


def notify_draft_ready(
    *,
    run_id: int,
    slug: str,
    headline: str,
    cost_usd: float,
    n_tool_calls: int,
    one_shot_token: str,
    fact_issues: list[str] | None = None,
) -> NotifyResult:
    """Slack ping when a draft is ready for human review.

    Includes a magic-link URL with the one-shot token (§9.3) — clicking
    sets the signed cookie that auths /insights/draft/<slug>.

    `fact_issues`, when non-empty, are residual fact-check flags the reviser
    could not auto-clear; they are listed in the ping so the approver knows
    exactly what to verify before clicking Approve.
    """
    settings = get_settings()
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    draft_url = f"{base}/insights/draft/{slug}/auth?t={one_shot_token}"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "FieldPulse Weekly — draft ready"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Lead:* {headline}"},
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"run_id: `{run_id}`"},
                {"type": "mrkdwn", "text": f"cost: ${cost_usd:.2f}"},
                {"type": "mrkdwn", "text": f"tool calls: {n_tool_calls}"},
            ],
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Review draft"},
                    "url": draft_url,
                    "style": "primary",
                },
            ],
        },
    ]
    if fact_issues:
        flagged = "\n".join(f"• {line}" for line in fact_issues[:8])
        # Insert before the actions block so the buttons stay at the bottom.
        blocks.insert(-1, {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Please verify before approving* — fact-check flags the "
                    f"reviser could not auto-clear:\n{flagged}"
                ),
            },
        })
    slack_ok, slack_err = _post_slack(blocks, f"FieldPulse draft ready: {headline}")
    return NotifyResult(slack_ok=slack_ok, slack_error=slack_err, email_ok=True, email_error=None)


def notify_published(*, run_id: int, slug: str, headline: str) -> NotifyResult:
    """Lightweight FYI ping after auto-publish promotes the draft."""
    settings = get_settings()
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    public_url = f"{base}/insights/{slug}"
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":newspaper: *Published:* <{public_url}|{headline}>",
            },
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"run_id: `{run_id}`"}],
        },
    ]
    slack_ok, slack_err = _post_slack(blocks, f"FieldPulse published: {headline}")
    return NotifyResult(slack_ok=slack_ok, slack_error=slack_err, email_ok=True, email_error=None)


def notify_failure(
    *,
    run_id: int | None,
    failed_at_step: str,
    issues: list[str],
    draft_url: str | None = None,
) -> NotifyResult:
    """Slack + email alert on any step failure. Draft (if any) is left in
    `newsletters/draft/` for manual triage — this function only delivers the
    payload, not the cleanup."""
    issue_list = "\n".join(f"- {x}" for x in issues[:10]) or "_(no detail)_"
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":warning: FieldPulse run failed"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Step:* `{failed_at_step}`"},
                {"type": "mrkdwn", "text": f"*Run id:* `{run_id}`"},
            ],
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Issues:*\n{issue_list}"},
        },
    ]
    if draft_url:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Open draft"},
                        "url": draft_url,
                    }
                ],
            }
        )

    slack_ok, slack_err = _post_slack(
        blocks, f"FieldPulse run failed at {failed_at_step}: {len(issues)} issue(s)"
    )

    email_body = (
        f"FieldPulse Weekly run failed.\n\n"
        f"Step: {failed_at_step}\n"
        f"Run id: {run_id}\n\n"
        f"Issues:\n{issue_list}\n\n"
        f"Draft URL: {draft_url or '(no draft staged)'}\n"
    )
    email_ok, email_err = _send_email(
        subject=f"[FieldPulse] run failed at {failed_at_step}",
        body=email_body,
    )

    return NotifyResult(
        slack_ok=slack_ok,
        slack_error=slack_err,
        email_ok=email_ok,
        email_error=email_err,
    )
