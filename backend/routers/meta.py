"""FastAPI router for forecast-model metadata.

Base path: /api/v1/meta

Single read-only endpoint feeding the About page's "live model metadata"
strip. Reads backend/artifacts/**/metrics.json on disk and returns a
normalized view so the About page stays honest across retrains without
any manual edit.

Design notes:
- No DB access. Pure file read + JSON shaping.
- Failures on any single artifact (missing file, malformed JSON) are
  degraded gracefully — the entry is omitted, not the whole response.
- Yield models ship as 20 per-week artifacts. We summarize at the crop
  level (avg test-RRMSE, best/worst week, gate pass-rate) rather than
  returning 60 rows.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

ARTIFACTS_ROOT = Path(__file__).resolve().parent.parent / "artifacts"

PRICE_HORIZONS = [1, 3, 6, 9, 12, 18]
PRICE_COMMODITIES = ["corn", "soybean", "wheat"]
ACREAGE_COMMODITIES = ["corn", "soybean", "wheat_winter", "wheat_spring"]
YIELD_CROPS = ["corn", "soybean", "wheat"]


class ModelMetaItem(BaseModel):
    """One forecast model's current state. Fields are nullable to tolerate
    partially-trained or in-progress artifacts."""
    task: str                       # "price" | "acreage" | "yield"
    commodity: str                  # corn / soybean / wheat_winter / ...
    horizon: str | None = None      # "3m" for price, "week_12" for yield, None for acreage
    model_ver: str | None = None    # ISO date string from metrics.json
    test_metric_name: str | None = None   # "MAPE" | "RRMSE"
    test_metric_value: float | None = None
    baseline_metric_value: float | None = None
    beats_baseline: bool | None = None
    gate_status: str | None = None  # "pass" | "fail" | "partial" | "unknown"
    coverage: float | None = None   # conformal interval coverage
    n_train: int | None = None
    n_val: int | None = None
    n_test: int | None = None
    n_features: int | None = None
    top_features: list[str] = []
    artifact_exists: bool = True


class MetaResponse(BaseModel):
    as_of: date
    models: list[ModelMetaItem]
    summary: dict


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"failed to load {path}: {e}")
        return None


def _feature_names(raw) -> list[str]:
    """Normalize top_features into a flat list of strings.

    Yield trainers emit `[{"name": ..., "importance": ...}, ...]`; acreage
    and price trainers emit `[name, ...]`. The About page only needs names.
    """
    if not raw:
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            name = item.get("name") or item.get("feature")
            if name:
                out.append(str(name))
    return out


def _classify_gate(test_val: float | None, baseline: float | None,
                   tolerance_pp: float = 0.5) -> str:
    """Classify test-metric vs baseline.

    Uses the test-set metric (the user-facing deployment-relevant number),
    not val. "borderline" = within ±tolerance_pp percentage points of the
    baseline either way — where the user-facing UI surfaces EXPERIMENTAL.
    """
    if test_val is None or baseline is None:
        return "unknown"
    if test_val < baseline - tolerance_pp:
        return "pass"
    if test_val > baseline + tolerance_pp:
        return "fail"
    return "borderline"


def _price_item(commodity: str, horizon: int) -> ModelMetaItem | None:
    metrics = _load_json(ARTIFACTS_ROOT / commodity / f"horizon_{horizon}" / "metrics.json")
    if metrics is None:
        return None
    test_val = metrics.get("mape_test")
    baseline = metrics.get("futures_baseline_mape")
    gate = _classify_gate(test_val, baseline, tolerance_pp=1.5)  # price gate spec
    return ModelMetaItem(
        task="price",
        commodity=commodity,
        horizon=f"{horizon}m",
        model_ver=metrics.get("model_ver"),
        test_metric_name="MAPE",
        test_metric_value=test_val,
        baseline_metric_value=baseline,
        beats_baseline=(gate == "pass"),
        gate_status=gate,
        coverage=metrics.get("coverage_90_test") or metrics.get("coverage_90"),
        n_train=metrics.get("n_train"),
        n_val=metrics.get("n_val"),
        n_test=metrics.get("n_test"),
    )


def _acreage_item(commodity: str) -> ModelMetaItem | None:
    metrics = _load_json(ARTIFACTS_ROOT / "acreage" / commodity / "metrics.json")
    if metrics is None:
        return None
    test_val = metrics.get("test_mape")
    baseline = metrics.get("best_baseline_mape")
    gate = _classify_gate(test_val, baseline)
    return ModelMetaItem(
        task="acreage",
        commodity=commodity,
        model_ver=metrics.get("model_ver"),
        test_metric_name="MAPE",
        test_metric_value=test_val,
        baseline_metric_value=baseline,
        beats_baseline=(gate == "pass"),
        gate_status=gate,
        coverage=metrics.get("coverage_80_test") or metrics.get("coverage_80_val"),
        n_train=metrics.get("n_train"),
        n_val=metrics.get("n_val"),
        n_test=metrics.get("n_test"),
        top_features=_feature_names(metrics.get("top_features")),
    )


def _yield_item(crop: str) -> ModelMetaItem | None:
    """Summarize 20 weekly artifacts into one per-crop row. Prefers an
    already-computed summary.json when the trainer has written one."""
    crop_dir = ARTIFACTS_ROOT / "yield" / crop
    summary = _load_json(crop_dir / "summary.json")
    if summary is not None:
        # Trainer-written summary has the canonical gate-status classification
        return ModelMetaItem(
            task="yield",
            commodity=crop,
            model_ver=summary.get("model_ver"),
            test_metric_name="RRMSE",
            test_metric_value=summary.get("avg_test_rrmse"),
            baseline_metric_value=summary.get("avg_baseline_rrmse"),
            beats_baseline=summary.get("gate_status") == "pass",
            gate_status=summary.get("gate_status"),
            n_features=summary.get("n_features"),
            top_features=_feature_names(summary.get("top_features")),
        )

    # Fall back to computing the summary from per-week files.
    week_files = sorted(crop_dir.glob("week_*/metrics.json"))
    if not week_files:
        return None
    weekly = [_load_json(f) for f in week_files]
    weekly = [w for w in weekly if w is not None]
    if not weekly:
        return None
    test_vals = [w["test_rrmse"] for w in weekly if "test_rrmse" in w]
    baseline_vals = [w.get("baselines", {}).get("county_mean_rrmse") for w in weekly]
    baseline_vals = [b for b in baseline_vals if b is not None]
    n_pass = sum(1 for w in weekly if w.get("beats_baseline"))
    n_total = len(weekly)
    # Yield gate is surface-with-annotation (class-project policy): pass=all,
    # partial=majority, fail=none.
    if n_pass == n_total:
        gate = "pass"
    elif n_pass >= n_total / 2:
        gate = "partial"
    else:
        gate = "fail"
    return ModelMetaItem(
        task="yield",
        commodity=crop,
        model_ver=weekly[-1].get("model_ver"),
        test_metric_name="RRMSE",
        test_metric_value=round(sum(test_vals) / len(test_vals), 2) if test_vals else None,
        baseline_metric_value=round(sum(baseline_vals) / len(baseline_vals), 2) if baseline_vals else None,
        beats_baseline=(gate == "pass"),
        gate_status=gate,
        n_features=weekly[-1].get("n_features"),
        top_features=_feature_names(weekly[-1].get("top_features")),
    )


@router.get("/models", response_model=MetaResponse)
async def get_model_metadata():
    items: list[ModelMetaItem] = []

    for c in PRICE_COMMODITIES:
        for h in PRICE_HORIZONS:
            item = _price_item(c, h)
            if item is not None:
                items.append(item)

    for c in ACREAGE_COMMODITIES:
        item = _acreage_item(c)
        if item is not None:
            items.append(item)

    for c in YIELD_CROPS:
        item = _yield_item(c)
        if item is not None:
            items.append(item)

    # Rollup counts for the About-page header strip.
    summary = {
        "total_models": len(items),
        "price_models": sum(1 for i in items if i.task == "price"),
        "acreage_models": sum(1 for i in items if i.task == "acreage"),
        "yield_crops": sum(1 for i in items if i.task == "yield"),
        "passing_gate": sum(1 for i in items if i.gate_status == "pass"),
        "failing_gate": sum(1 for i in items if i.gate_status == "fail"),
        "borderline_gate": sum(1 for i in items if i.gate_status == "borderline"),
        "partial_gate": sum(1 for i in items if i.gate_status == "partial"),
    }

    return MetaResponse(as_of=date.today(), models=items, summary=summary)
