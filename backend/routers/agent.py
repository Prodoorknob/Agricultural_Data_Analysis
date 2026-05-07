"""Agent control plane router.

Endpoints (all under /api/v1/agent):
    POST /promote/{run_id}      - Idempotently publish an approved draft.
                                  Called by the Next.js Approve button.
    POST /reject/{run_id}        - Mark a draft as rejected.
    GET  /runs                   - Recent runs (status + cost summary).
    GET  /draft/{slug}/auth      - Validate a one-shot magic-link token,
                                   return a short-lived signed token suitable
                                   for the frontend cookie.
    GET  /chart/{slug}/{name}    - Proxy chart PNG from S3 (draft or published).

The promote/reject endpoints expect a server-side shared secret in the
`X-Agent-Token` header (FIELDPULSE_DRAFT_SECRET). The Next.js API route
holds that secret and forwards calls.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import boto3
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.agent.publisher import promote
from backend.config import get_settings
from backend.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_agent_token(
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
) -> None:
    """Reject unless the caller passes the right shared secret."""
    settings = get_settings()
    expected = settings.FIELDPULSE_DRAFT_SECRET
    if not expected:
        raise HTTPException(503, "agent secret not configured")
    if not x_agent_token or not _constant_time_eq(x_agent_token, expected):
        raise HTTPException(401, "invalid agent token")


def _constant_time_eq(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ---------------------------------------------------------------------------
# Promote / reject.
# ---------------------------------------------------------------------------


@router.post("/promote/{run_id}", dependencies=[Depends(_require_agent_token)])
async def promote_run(
    run_id: int,
    approved_by: str | None = Query(None, max_length=50),
    db: AsyncSession = Depends(get_db),
):
    """Idempotently promote a draft to published. Calls publisher.promote().

    Optional ?approved_by= records who clicked Approve.
    """
    # Hand off to the sync publisher fn; FastAPI runs sync deps in a threadpool.
    import asyncio

    try:
        prefix = await asyncio.to_thread(promote, run_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    if approved_by:
        await db.execute(
            text("UPDATE agent_runs SET approved_by = :u WHERE id = :id"),
            {"u": approved_by, "id": run_id},
        )
        await db.commit()
    return {"ok": True, "run_id": run_id, "s3_prefix": prefix}


@router.post("/reject/{run_id}", dependencies=[Depends(_require_agent_token)])
async def reject_run(
    run_id: int,
    rejected_by: str | None = Query(None, max_length=50),
    reason: str | None = Query(None, max_length=500),
    db: AsyncSession = Depends(get_db),
):
    """Mark a run as rejected; preserves S3 draft for later inspection."""
    result = await db.execute(
        text(
            """
            UPDATE agent_runs
            SET status = 'rejected',
                approved_by = COALESCE(:u, approved_by),
                approved_at = NOW()
            WHERE id = :id AND status IN ('draft','approved')
            RETURNING id
            """
        ),
        {"u": rejected_by, "id": run_id},
    )
    row = result.first()
    if row is None:
        raise HTTPException(404, "run not found or not in draft/approved state")
    await db.commit()
    logger.info("run %d rejected by %s; reason=%s", run_id, rejected_by, reason)
    return {"ok": True, "run_id": run_id, "status": "rejected"}


# ---------------------------------------------------------------------------
# Recent runs (read-only, no auth — surface in /insights index).
# ---------------------------------------------------------------------------


@router.get("/runs")
async def list_runs(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    sql = text(
        """
        SELECT id, run_date, status, slug, newsletter_path,
               cost_usd, n_tool_calls, duration_sec, approved_by, approved_at
        FROM agent_runs
        ORDER BY run_date DESC LIMIT :limit
        """
    )
    rows = (await db.execute(sql, {"limit": limit})).mappings().all()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Magic-link token validation (§9.3).
# ---------------------------------------------------------------------------


@router.get("/draft/{slug}/auth")
async def validate_draft_token(
    slug: str,
    t: str = Query(..., min_length=8),
    db: AsyncSession = Depends(get_db),
):
    """Validate a one-shot magic-link token and consume it.

    On success returns the run metadata; the Next.js route then sets a
    signed `fp_draft_auth` HTTP-only cookie via its server-side handler.
    Token can be redeemed once.
    """
    row = (
        await db.execute(
            text(
                """
                SELECT t.token, t.run_id, t.slug, t.expires_at, t.consumed_at,
                       r.id AS run_pk, r.status, r.newsletter_path
                FROM agent_draft_tokens t
                JOIN agent_runs r ON r.id = t.run_id
                WHERE t.token = :t AND t.slug = :slug
                """
            ),
            {"t": t, "slug": slug},
        )
    ).first()
    if row is None:
        raise HTTPException(404, "token not found")
    if row.consumed_at is not None:
        raise HTTPException(410, "token already used")
    if row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(410, "token expired")

    await db.execute(
        text("UPDATE agent_draft_tokens SET consumed_at = NOW() WHERE token = :t"),
        {"t": t},
    )
    await db.commit()
    return {
        "ok": True,
        "run_id": int(row.run_pk),
        "slug": row.slug,
        "status": row.status,
        "newsletter_path": row.newsletter_path,
    }


# ---------------------------------------------------------------------------
# Chart PNG proxy (§9.3).
# ---------------------------------------------------------------------------


@router.get("/markdown/{slug}")
async def markdown_proxy(
    slug: str,
    draft: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Stream the issue markdown for the given slug from S3.

    /api/v1/agent/markdown/<slug>            → published path
    /api/v1/agent/markdown/<slug>?draft=1    → draft path

    Draft fetches require the caller (Next.js route handler) to have
    already validated the user's session — this endpoint does NOT enforce
    auth. The Next.js side is the trust boundary.
    """
    settings = get_settings()
    if "/" in slug or "\\" in slug or ".." in slug:
        raise HTTPException(400, "invalid slug")
    if draft:
        key = f"{settings.NEWSLETTER_S3_PREFIX}draft/{slug}/{slug}.md"
    else:
        row = (
            await db.execute(
                text("SELECT newsletter_path FROM agent_runs WHERE slug = :s"),
                {"s": slug},
            )
        ).first()
        if row is None or not row.newsletter_path:
            raise HTTPException(404, "no published path for slug")
        key = f"{row.newsletter_path}{slug}.md"

    s3 = boto3.client("s3", region_name=settings.AWS_REGION)
    try:
        obj = s3.get_object(Bucket=settings.S3_BUCKET, Key=key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("markdown fetch %s failed: %s", key, exc)
        raise HTTPException(404, "markdown not found")
    return Response(
        content=obj["Body"].read(),
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/chart/{slug}/{name}")
async def chart_proxy(
    slug: str,
    name: str,
    draft: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Stream a chart PNG from S3 for the given slug.

    /api/v1/agent/chart/<slug>/chart_1.png      → published path
    /api/v1/agent/chart/<slug>/chart_1.png?draft=1 → draft path
    """
    settings = get_settings()
    if not name.endswith(".png") or "/" in name or "\\" in name:
        raise HTTPException(400, "name must be a flat .png filename")

    if draft:
        key = f"{settings.NEWSLETTER_S3_PREFIX}draft/{slug}/{name}"
    else:
        # Look up newsletter_path from agent_runs.
        row = (
            await db.execute(
                text("SELECT newsletter_path FROM agent_runs WHERE slug = :s"),
                {"s": slug},
            )
        ).first()
        if row is None or not row.newsletter_path:
            raise HTTPException(404, "no published path for slug")
        key = f"{row.newsletter_path}{name}"

    s3 = boto3.client("s3", region_name=settings.AWS_REGION)
    try:
        obj = s3.get_object(Bucket=settings.S3_BUCKET, Key=key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("chart fetch %s failed: %s", key, exc)
        raise HTTPException(404, "chart not found")
    return Response(content=obj["Body"].read(), media_type="image/png")
