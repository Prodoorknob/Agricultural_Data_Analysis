"""CLI: Run acreage prediction inference and persist results.

Predicts for each top state, rolls up to national, upserts to DB.

Usage:
    python -m backend.models.acreage_inference
    python -m backend.models.acreage_inference --year 2026 --commodity corn
"""

import argparse
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy.dialects.postgresql import insert

from backend.etl.common import get_sync_session, setup_logging
from backend.features.acreage_features import (
    FIPS_TO_STATE,
    TOP_STATES,
    build_acreage_features,
)
from backend.models.acreage_model import AcreageEnsemble, compute_national_forecast

logger = setup_logging("acreage_inference")

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "acreage"
NASS_CACHE = Path(__file__).resolve().parent.parent / "etl" / "data" / "nass_cache" / "nass_acreage_yield.csv"
COMMODITIES = ["corn", "soybean", "wheat"]


def _load_nass_data() -> pd.DataFrame:
    if not NASS_CACHE.exists():
        raise FileNotFoundError(
            f"NASS cache not found at {NASS_CACHE}. "
            "Run 'python -m backend.models.train_acreage' first."
        )
    return pd.read_csv(NASS_CACHE, dtype={"state_fips": str})


def run_inference(
    forecast_year: int | None = None,
    commodities: list[str] | None = None,
    publish_date: date | None = None,
):
    """Load ensembles, predict per-state, roll up national, upsert to DB."""
    from backend.models.db_tables import AcreageForecast

    if forecast_year is None:
        forecast_year = date.today().year
    if commodities is None:
        commodities = COMMODITIES
    if publish_date is None:
        publish_date = date.today()

    nass_data = _load_nass_data()
    session = get_sync_session()

    for commodity in commodities:
        pkl_path = ARTIFACTS_DIR / commodity / "ensemble.pkl"
        if not pkl_path.exists():
            logger.warning(f"No ensemble artifact for {commodity} at {pkl_path}")
            continue

        ensemble = AcreageEnsemble.load(pkl_path)
        logger.info(f"Loaded {commodity} ensemble (ver={ensemble.model_ver})")

        # Predict for top states
        states = TOP_STATES.get(commodity, [])
        state_results = []
        drivers = []

        for state_fips in states:
            features = build_acreage_features(state_fips, commodity, forecast_year, nass_data)
            avail_cols = [c for c in ensemble.feature_cols if c in features.index]
            X = pd.DataFrame([features[avail_cols]])

            pred = ensemble.predict(X)
            key_driver = ensemble.get_key_driver(features[avail_cols])
            drivers.append(key_driver)

            state_results.append({
                "state_fips": state_fips,
                "p50": pred["p50"],
                "p10": pred["p10"],
                "p90": pred["p90"],
                "key_driver": key_driver,
            })

            state_name = FIPS_TO_STATE.get(state_fips, state_fips)
            logger.info(
                f"  {state_name}: {pred['p50']/1e6:.2f}M acres "
                f"[{pred['p10']/1e6:.2f} - {pred['p90']/1e6:.2f}]"
            )

        # National rollup
        if state_results:
            state_df = pd.DataFrame(state_results)
            national = compute_national_forecast(state_df, commodity=commodity)
        else:
            features = build_acreage_features("00", commodity, forecast_year, nass_data)
            avail_cols = [c for c in ensemble.feature_cols if c in features.index]
            X = pd.DataFrame([features[avail_cols]])
            national = ensemble.predict(X)

        # Most common key driver across states
        national_driver = Counter(drivers).most_common(1)[0][0] if drivers else "N/A"

        # Corn/soy ratio for context
        nat_features = build_acreage_features("00", commodity, forecast_year, nass_data)
        csr = nat_features.get("corn_soy_ratio")

        logger.info(
            f"  NATIONAL: {national['p50']/1e6:.2f}M acres "
            f"[{national['p10']/1e6:.2f} - {national['p90']/1e6:.2f}]"
        )

        # Build upsert rows
        rows = []

        def _py(v):
            """Convert numpy types to Python native for DB."""
            if v is None:
                return None
            return round(float(v), 1)

        # National
        rows.append({
            "forecast_year": forecast_year,
            "state_fips": "00",
            "commodity": commodity,
            "forecast_acres": _py(national["p50"]),
            "p10_acres": _py(national["p10"]),
            "p90_acres": _py(national["p90"]),
            "corn_soy_ratio": float(csr) if csr is not None else None,
            "key_driver": national_driver,
            "model_ver": ensemble.model_ver,
            "published_at": publish_date,
        })

        # States
        for sr in state_results:
            rows.append({
                "forecast_year": forecast_year,
                "state_fips": sr["state_fips"],
                "commodity": commodity,
                "forecast_acres": _py(sr["p50"]),
                "p10_acres": _py(sr["p10"]),
                "p90_acres": _py(sr["p90"]),
                "corn_soy_ratio": None,
                "key_driver": sr["key_driver"],
                "model_ver": ensemble.model_ver,
                "published_at": publish_date,
            })

        # Upsert
        try:
            stmt = insert(AcreageForecast.__table__).values(rows)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_acreage_forecasts",
                set_={
                    "forecast_acres": stmt.excluded.forecast_acres,
                    "p10_acres": stmt.excluded.p10_acres,
                    "p90_acres": stmt.excluded.p90_acres,
                    "corn_soy_ratio": stmt.excluded.corn_soy_ratio,
                    "key_driver": stmt.excluded.key_driver,
                    "published_at": stmt.excluded.published_at,
                },
            )
            session.execute(stmt)
            session.commit()
            logger.info(f"  Upserted {len(rows)} rows ({len(state_results)} states + national)")
        except Exception as e:
            session.rollback()
            logger.error(f"  DB upsert failed for {commodity}: {e}")
            raise

    session.close()
    logger.info("Acreage inference complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run acreage prediction inference")
    parser.add_argument("--year", type=int, default=None, help="Forecast year")
    parser.add_argument("--commodity", type=str, default=None, help="Single commodity")
    parser.add_argument("--publish-date", type=str, default=None, help="Publish date (YYYY-MM-DD)")
    args = parser.parse_args()

    commodities = [args.commodity] if args.commodity else None
    pub_date = date.fromisoformat(args.publish_date) if args.publish_date else None

    run_inference(
        forecast_year=args.year,
        commodities=commodities,
        publish_date=pub_date,
    )
