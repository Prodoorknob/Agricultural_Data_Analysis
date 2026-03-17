from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.routers import price

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load models, verify DB connection
    yield
    # Shutdown: cleanup


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
