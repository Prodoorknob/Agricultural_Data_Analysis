"""One-time backfill: fill agent_picks.story_title for pre-014 issues.

For every run with a slug and an S3 newsletter path, download the published
markdown, extract the writer's story titles (lead H2 + brief H3s via the
composer parser), and assign them positionally to that run's picks (which
were inserted lead-first, so ORDER BY id ASC matches document order).

Idempotent: rows that already have a story_title are only overwritten when
--force is passed.

Usage:
    python -m backend.agent.backfill_story_titles [--dry-run] [--force]
"""

from __future__ import annotations

import argparse
import logging

import boto3
from sqlalchemy import text

from backend.agent.publisher import _extract_story_titles
from backend.config import get_settings
from backend.etl.common import get_sync_session

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _fetch_markdown(s3, bucket: str, prefix: str, slug: str) -> str | None:
    key = f"{prefix.rstrip('/')}/{slug}.md"
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        return obj["Body"].read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        logger.warning("  could not fetch s3://%s/%s: %s", bucket, key, exc)
        return None


def run(dry_run: bool = False, force: bool = False) -> None:
    settings = get_settings()
    s3 = boto3.client("s3", region_name=settings.AWS_REGION)

    with get_sync_session() as session:
        runs = session.execute(
            text(
                """
                SELECT id, slug, newsletter_path, status
                FROM agent_runs
                WHERE slug IS NOT NULL AND newsletter_path IS NOT NULL
                ORDER BY run_date
                """
            )
        ).all()

        n_updated = 0
        for r in runs:
            picks = session.execute(
                text(
                    """
                    SELECT id, role, story_title FROM agent_picks
                    WHERE run_id = :rid ORDER BY id ASC
                    """
                ),
                {"rid": r.id},
            ).all()
            if not picks:
                logger.info("run %s (%s): no picks, skipping", r.id, r.slug)
                continue
            if not force and all(p.story_title for p in picks):
                logger.info("run %s (%s): titles already set, skipping", r.id, r.slug)
                continue

            md = _fetch_markdown(s3, settings.S3_BUCKET, r.newsletter_path, r.slug)
            if md is None:
                continue
            titles = _extract_story_titles(md)
            if not titles:
                logger.warning("run %s (%s): no titles parsed", r.id, r.slug)
                continue
            if picks[0].role != "lead":
                logger.warning(
                    "run %s (%s): first pick is %s, not lead — skipping to be safe",
                    r.id, r.slug, picks[0].role,
                )
                continue
            if len(titles) != len(picks):
                logger.warning(
                    "run %s (%s): %d titles vs %d picks — assigning the overlap",
                    r.id, r.slug, len(titles), len(picks),
                )

            for pick, title in zip(picks, titles):
                if pick.story_title and not force:
                    continue
                logger.info(
                    "run %s (%s): pick %s [%s] <- %r",
                    r.id, r.slug, pick.id, pick.role, title[:70],
                )
                if not dry_run:
                    session.execute(
                        text(
                            "UPDATE agent_picks SET story_title = :t WHERE id = :id"
                        ),
                        {"t": title[:300], "id": pick.id},
                    )
                    n_updated += 1
        if not dry_run:
            session.commit()
        logger.info("done: %d pick rows updated%s", n_updated, " (dry run)" if dry_run else "")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill agent_picks.story_title.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Overwrite existing titles.")
    args = parser.parse_args()
    run(dry_run=args.dry_run, force=args.force)
