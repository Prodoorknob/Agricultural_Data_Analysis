import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add project root to path so we can import backend modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env file if present (so DATABASE_URL is available without shell export)
ENV_FILE = PROJECT_ROOT / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

from backend.database import Base
from backend.models.db_tables import (  # noqa: F401 — registers models with Base
    AcreageAccuracy,
    AcreageForecast,
    CrpEnrollment,
    DroughtIndex,
    DxyDaily,
    ErsFertilizerPrice,
    ErsProductionCost,
    ExportCommitment,
    FeatureWeekly,
    FuturesDaily,
    PriceForecast,
    RmaInsuredAcres,
    SoilFeature,
    WasdeRelease,
    YieldAccuracy,
    YieldForecast,
)

config = context.config

# Override sqlalchemy.url from environment if available
db_url = os.environ.get("DATABASE_URL")
if db_url:
    # Alembic needs synchronous URL (psycopg2, not asyncpg)
    db_url = db_url.replace("+asyncpg", "")
    config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
