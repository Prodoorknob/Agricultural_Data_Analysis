import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.routers import acreage, crops, market, meta, price, yield_forecast

settings = get_settings()
logger = logging.getLogger("uvicorn.error")

ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
COMMODITIES = ("corn", "soybean", "wheat")
HORIZONS = range(1, 7)


def _download_from_s3(s3_key: str, local_path: Path) -> bool:
    """Download a model artifact from S3 to local disk. Returns True on success.

    Also attempts to download the matching .sig sidecar (for HMAC verification
    at load time). A missing sig is not fatal — it only matters if
    MODEL_REQUIRE_SIGNED=1 is set, in which case load() will refuse to unpickle.
    """
    import boto3
    from botocore.exceptions import ClientError

    try:
        s3 = boto3.client("s3", region_name=settings.AWS_REGION)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(settings.S3_BUCKET, s3_key, str(local_path))
        logger.info("Downloaded s3://%s/%s -> %s", settings.S3_BUCKET, s3_key, local_path)

        # Best-effort fetch of the signature sidecar
        sig_key = s3_key + ".sig"
        sig_path = local_path.with_suffix(local_path.suffix + ".sig")
        try:
            s3.download_file(settings.S3_BUCKET, sig_key, str(sig_path))
            logger.debug("Downloaded signature %s", sig_key)
        except ClientError as sig_exc:
            if sig_exc.response["Error"]["Code"] not in ("404", "NoSuchKey"):
                logger.warning("Signature download failed for %s: %s", sig_key, sig_exc)

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


ACREAGE_ARTIFACTS_DIR = ARTIFACTS_DIR / "acreage"
YIELD_ARTIFACTS_DIR = ARTIFACTS_DIR / "yield"
YIELD_WEEKS = range(1, 21)  # 20 weeks of growing season


def _load_acreage_models() -> dict:
    """Load AcreageEnsemble models from local artifacts, falling back to S3."""
    from backend.models.acreage_model import AcreageEnsemble

    models: dict[str, AcreageEnsemble] = {}
    for commodity in COMMODITIES:
        pkl_path = ACREAGE_ARTIFACTS_DIR / commodity / "ensemble.pkl"

        if not pkl_path.exists():
            s3_key = f"models/acreage/{commodity}/ensemble.pkl"
            _download_from_s3(s3_key, pkl_path)

        if pkl_path.exists():
            try:
                ensemble = AcreageEnsemble.load(pkl_path)
                models[commodity] = ensemble
                logger.info("Loaded acreage model: %s (ver=%s)", commodity, ensemble.model_ver)
            except Exception as exc:
                logger.warning("Failed to load acreage model %s: %s", pkl_path, exc)
        else:
            logger.debug("No acreage artifact at %s", pkl_path)
    return models


def _load_yield_models() -> dict:
    """Load YieldModel pickles from local artifacts, falling back to S3."""
    from backend.models.yield_model import YieldModel

    models: dict[tuple[str, int], YieldModel] = {}
    for commodity in COMMODITIES:
        for week in YIELD_WEEKS:
            pkl_path = YIELD_ARTIFACTS_DIR / commodity / f"week_{week}" / "model.pkl"

            if not pkl_path.exists():
                s3_key = f"models/yield/{commodity}/week_{week}/model.pkl"
                _download_from_s3(s3_key, pkl_path)

            if pkl_path.exists():
                try:
                    model = YieldModel.load(pkl_path)
                    models[(commodity, week)] = model
                    logger.info("Loaded yield model: %s week=%d (ver=%s)", commodity, week, model.model_ver)
                except Exception as exc:
                    logger.warning("Failed to load yield model %s: %s", pkl_path, exc)
            else:
                logger.debug("No yield artifact at %s", pkl_path)
    return models


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load models
    app.state.models = _load_models()
    logger.info("Loaded %d/%d price model artifacts", len(app.state.models), len(COMMODITIES) * len(HORIZONS))
    app.state.acreage_models = _load_acreage_models()
    logger.info("Loaded %d/%d acreage model artifacts", len(app.state.acreage_models), len(COMMODITIES))
    app.state.yield_models = _load_yield_models()
    logger.info("Loaded %d/%d yield model artifacts", len(app.state.yield_models), len(COMMODITIES) * len(YIELD_WEEKS))
    yield
    # Shutdown: cleanup
    app.state.models.clear()
    app.state.acreage_models.clear()
    app.state.yield_models.clear()


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
app.include_router(acreage.router, prefix="/api/v1/predict/acreage", tags=["acreage"])
app.include_router(yield_forecast.router, prefix="/api/v1/predict/yield", tags=["yield"])
app.include_router(market.router, prefix="/api/v1/market", tags=["market"])
app.include_router(meta.router, prefix="/api/v1/meta", tags=["meta"])
app.include_router(crops.router, prefix="/api/v1/crops", tags=["crops"])


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "modules": ["price-forecasting", "acreage-prediction", "yield-forecasting", "market-data", "meta"],
        "version": "0.5.0",
    }
