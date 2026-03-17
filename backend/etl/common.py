"""Shared utilities for ETL scripts — sync DB engine, logging, settings."""

import logging
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


def _load_env() -> dict[str, str]:
    """Parse .env file into a dict (avoids python-dotenv dependency for cron scripts)."""
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    return env


_env = _load_env()


def get_env(key: str, default: str = "") -> str:
    """Get env var from .env file or os.environ."""
    import os
    return os.environ.get(key, _env.get(key, default))


@lru_cache
def get_sync_engine():
    """Create a synchronous SQLAlchemy engine for ETL scripts."""
    db_url = get_env("DATABASE_URL")
    # Convert async driver to sync: asyncpg -> psycopg2
    sync_url = db_url.replace("+asyncpg", "+psycopg2").replace("postgresql+psycopg2", "postgresql+psycopg2")
    return create_engine(sync_url, echo=False, pool_size=3, pool_pre_ping=True)


@lru_cache
def get_session_factory():
    return sessionmaker(bind=get_sync_engine())


def get_sync_session() -> Session:
    return get_session_factory()()


def setup_logging(name: str) -> logging.Logger:
    """Configure logging for an ETL script."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
    return logger


def log_ingest_summary(logger: logging.Logger, table: str, rows_upserted: int, start: datetime):
    elapsed = (datetime.utcnow() - start).total_seconds()
    logger.info(f"Completed: {rows_upserted} rows upserted into {table} in {elapsed:.1f}s")
