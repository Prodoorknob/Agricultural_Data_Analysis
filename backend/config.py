from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path

# Absolute path so the env file resolves regardless of which CWD uvicorn
# runs from (project root vs backend/). Previously env_file="../.env" only
# worked when CWD was backend/.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://ag_app:password@localhost:5432/ag_dashboard"

    # API keys
    NASDAQ_DL_API_KEY: str = ""
    FRED_API_KEY: str = ""
    NOAA_API_KEY: str = ""

    # AWS
    S3_BUCKET: str = "usda-analysis-datasets"
    AWS_REGION: str = "us-east-2"
    MODEL_ARTIFACTS_S3_PREFIX: str = "models/price/"
    NEWSLETTER_S3_PREFIX: str = "newsletters/"

    # App
    CORS_ORIGINS: list[str] = ["*"]
    BACKEND_BASE_URL: str = "http://localhost:8000"
    PUBLIC_BASE_URL: str = "http://localhost:3000"

    # Module 05: FieldPulse Weekly analyst agent
    ANTHROPIC_API_KEY: str = ""
    AGENT_MODEL_PRIMARY: str = "claude-sonnet-4-6"
    AGENT_MODEL_CRITIC: str = "claude-haiku-4-5-20251001"
    AGENT_TOOL_CALL_PER_STORY_CAP: int = 8
    AGENT_TOOL_CALL_GLOBAL_CAP: int = 30
    AGENT_TRUST_STREAK_REQUIRED: int = 6  # consecutive approved runs to flip auto-publish
    SLACK_BOT_TOKEN: str = ""
    SLACK_CHANNEL_FIELDPULSE: str = ""  # channel ID like C0123ABC
    FIELDPULSE_DRAFT_SECRET: str = ""  # HMAC secret for signed draft cookie
    FIELDPULSE_ALERT_EMAIL: str = "rajashekarreddy091@gmail.com"

    model_config = {
        "env_file": str(_ENV_FILE),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        # Treat empty-string env vars as "unset" so .env values aren't shadowed
        # by stray placeholders set in Claude Code / Vercel / systemd / etc.
        "env_ignore_empty": True,
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
