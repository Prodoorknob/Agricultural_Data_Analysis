import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.routers import price

settings = get_settings()
logger = logging.getLogger("uvicorn.error")

ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
COMMODITIES = ("corn", "soybean", "wheat")
HORIZONS = range(1, 7)


def _download_from_s3(s3_key: str, local_path: Path) -> bool:
    """Download a model artifact from S3 to local disk. Returns True on success."""
    import boto3
    from botocore.exceptions import ClientError

    try:
        s3 = boto3.client("s3", region_name=settings.AWS_REGION)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(settings.S3_BUCKET, s3_key, str(local_path))
        logger.info("Downloaded s3://%s/%s -> %s", settings.S3_BUCKET, s3_key, local_path)
        return True
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        if error_code in ("404", "NoSuchKey"):
            logger.debug("No S3 artifact at s3://%s/%s", settings.S3_BUCKET, s3_key)
        else:
            logger.warning("S3 download failed for %s: %s", s3_key, exc)
        return False
    except Exception as exc:
        logger.warning("S3 download failed for %s: %s", s3_key, exc)
        return False


def _load_models() -> dict:
    """Load all PriceEnsemble models from local artifacts, falling back to S3."""
    from backend.models.price_model import PriceEnsemble

    models: dict[tuple[str, int], "PriceEnsemble"] = {}
    for commodity in COMMODITIES:
        for horizon in HORIZONS:
            pkl_path = ARTIFACTS_DIR / commodity / f"horizon_{horizon}" / "ensemble.pkl"

            # If not on local disk, try downloading from S3
            if not pkl_path.exists():
                s3_key = f"{settings.MODEL_ARTIFACTS_S3_PREFIX}{commodity}/horizon_{horizon}/ensemble.pkl"
                _download_from_s3(s3_key, pkl_path)

            if pkl_path.exists():
                try:
                    ensemble = PriceEnsemble.load(pkl_path)
                    models[(commodity, horizon)] = ensemble
                    logger.info("Loaded model: %s h=%d (ver=%s)", commodity, horizon, ensemble.model_ver)
                except Exception as exc:
                    logger.warning("Failed to load %s: %s", pkl_path, exc)
            else:
                logger.debug("No artifact at %s (local or S3)", pkl_path)
    return models


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load models
    app.state.models = _load_models()
    logger.info("Loaded %d/%d model artifacts", len(app.state.models), len(COMMODITIES) * len(HORIZONS))
    yield
    # Shutdown: cleanup
    app.state.models.clear()


app = FastAPI(
    title="Agricultural Dashboard — Prediction API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(price.router, prefix="/api/v1/predict/price", tags=["price"])


@app.get("/health")
async def health():
    return {"status": "ok", "module": "price-forecasting", "version": "0.1.0"}
