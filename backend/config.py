from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://ag_app:password@localhost:5432/ag_dashboard"

    # API keys
    NASDAQ_DL_API_KEY: str = ""
    FRED_API_KEY: str = ""

    # AWS
    S3_BUCKET: str = "usda-analysis-datasets"
    AWS_REGION: str = "us-east-2"
    MODEL_ARTIFACTS_S3_PREFIX: str = "models/price/"

    # App
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
