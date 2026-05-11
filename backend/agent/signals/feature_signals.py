"""Feature/explainer signal source — educational + structural narratives.

Counterweight to the 8 anomaly-driven sources. Emits stable, rotation-driven
candidates that answer "what is?", "how does this work?", "when does X
happen?" — useful when the week's anomalies are light, or as a complementary
brief alongside event-driven leads.

Three subcategories, all with stable signal_ids so the 8-week novelty
machinery rotates them automatically:

  - feature-trend     25-year acreage/yield trajectory for a state's
                      season-relevant crop (rotates through ~6 states/wk).
  - feature-region    Curated multi-state cluster spotlight (Ogallala,
                      Corn Belt, Mississippi Delta, etc).
  - feature-explainer Calendar-anchored seasonal primer (no DB).

Editor + writer prompts know about `feature-*` domains and mix them with
anomaly briefs to keep the newsletter both timely AND teaching.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import text

from backend.agent.signal_board import Signal
from backend.agent.signals._common import (
    ScoreParts,
    calendar_fit_score,
    compute_score,
    novelty_score,
    reach_score,
)
from backend.agent.signals._fips_label import state_label
from backend.etl.common import get_sync_session

logger = logging.getLogger(__name__)


def collect(as_of_date: date) -> list[Signal]:
    out: list[Signal] = []
    out.extend(_state_trend_signals(as_of_date))
    out.extend(_regional_cluster_signals(as_of_date))
    out.extend(_seasonal_explainer_signals(as_of_date))
    return out


# ---------------------------------------------------------------------------
# 1. State trend — 25-year acreage trajectory.
# ---------------------------------------------------------------------------


# Top states with deep history per crop. The seasonal helper picks which
# crop list to draw from based on the calendar.
TREND_STATE_FIPS_BY_CROP = {
    "corn":    ["19", "17", "18", "27", "31", "39", "55", "26"],   # IA IL IN MN NE OH WI MI
    "soybean": ["19", "17", "18", "27", "29", "39", "31", "38"],   # IA IL IN MN MO OH NE ND
    "wheat":   ["20", "38", "30", "40", "46", "53", "27", "31"],   # KS ND MT OK SD WA MN NE
}


def _season_focus_crop(as_of: date) -> str:
    """Calendar-aware crop selection so trend stories track the season."""
    m = as_of.month
    if m in (3, 4, 5):
        return "corn"          # planting
    if m in (6, 7, 8):
        return "soybean"       # bloom + pod-fill
    if m in (9, 10, 11):
        return "wheat"         # winter wheat planting
    return "soybean"           # off-season default


def _state_trend_signals(as_of: date) -> list[Signal]:
    crop = _season_focus_crop(as_of)
    candidates = TREND_STATE_FIPS_BY_CROP.get(crop, [])[:6]
    out: list[Signal] = []
    for state_fips in candidates:
        sig = _build_state_trend(crop, state_fips, as_of)
        if sig:
            out.append(sig)
    return out


def _build_state_trend(crop: str, state_fips: str, as_of: date) -> Signal | None:
    sql = text(
        """
        SELECT forecast_year, AVG(usda_june_actual) AS acres
        FROM acreage_accuracy
        WHERE state_fips = :sf AND commodity = :c
          AND usda_june_actual IS NOT NULL
          AND forecast_year >= :y0 AND forecast_year <= :y1
          AND updated_at <= :as_of
        GROUP BY forecast_year ORDER BY forecast_year
        """
    )
    with get_sync_session() as s:
        rows = s.execute(
            sql,
            {
                "sf": state_fips, "c": crop,
                "y0": as_of.year - 25, "y1": as_of.year - 1, "as_of": as_of,
            },
        ).all()
    if len(rows) < 3:
        return None

    earliest, latest = rows[0], rows[-1]
    if not earliest.acres or not latest.acres or float(earliest.acres) <= 0:
        return None
    pct_change = (float(latest.acres) - float(earliest.acres)) / float(earliest.acres) * 100

    scope = f"state:{state_fips}"
    domain = "feature-trend"
    state = state_label(state_fips)

    parts = ScoreParts(
        magnitude=40 + min(40, abs(pct_change) / 2),  # 40-80 base, scales with magnitude
        reach=reach_score("acreage", scope, commodity=crop),
        novelty=novelty_score(domain, scope, 50, as_of),
        calendar=0.0,
    )
    score = compute_score(parts)

    return Signal(
        id=f"feature-trend:{crop}:{state_fips}",
        domain=domain,
        scope=scope,
        headline=(
            f"{state} {crop} acres: {float(earliest.acres):,.0f} "
            f"({earliest.forecast_year}) → {float(latest.acres):,.0f} "
            f"({latest.forecast_year}), {pct_change:+.0f}% over "
            f"{int(latest.forecast_year) - int(earliest.forecast_year)} years"
        ),
        score=score,
        direction="positive" if pct_change > 0 else "negative",
        evidence={
            "state_fips": state_fips,
            "state_name": state,
            "crop": crop,
            "first_year": int(earliest.forecast_year),
            "last_year": int(latest.forecast_year),
            "first_acres": float(earliest.acres),
            "last_acres": float(latest.acres),
            "pct_change": round(pct_change, 1),
            "n_years": len(rows),
            "feature_type": "state_trend",
            "score_parts": parts.__dict__,
        },
        sources=["acreage_accuracy"],
    )


# ---------------------------------------------------------------------------
# 2. Regional cluster spotlights — curated multi-state narratives.
# ---------------------------------------------------------------------------


REGIONAL_CLUSTERS: dict[str, dict[str, Any]] = {
    "ogallala": {
        "label": "Ogallala Aquifer states",
        "states": ["20", "31", "40", "48", "08", "46", "56"],  # KS NE OK TX CO SD WY
        "narrative": (
            "Irrigated crop production drawing on a depleting aquifer. Roughly "
            "30% of U.S. irrigated cropland; recharge runs centuries behind "
            "withdrawal in the southern half."
        ),
    },
    "cornbelt_istates": {
        "label": "Corn Belt I-states",
        "states": ["17", "18", "19", "27"],  # IL IN IA MN
        "narrative": (
            "Core U.S. corn + soybean production. Roughly 60% of national corn "
            "output; rotation between corn and soy is the dominant land-use "
            "decision each spring."
        ),
    },
    "highplains_wheat": {
        "label": "High Plains wheat belt",
        "states": ["20", "38", "30", "40", "46"],  # KS ND MT OK SD
        "narrative": (
            "U.S. wheat production heartland. Hard red winter wheat in the south "
            "(KS/OK), hard red spring + durum in the north (ND/MT/SD). Different "
            "harvests, different export markets."
        ),
    },
    "delta_soy": {
        "label": "Mississippi Delta soy & cotton",
        "states": ["05", "22", "28"],  # AR LA MS
        "narrative": (
            "Soybean and cotton on Mississippi River alluvial soils. Fastest-"
            "growing soy region of the last decade; barge access drives a freight"
            " advantage to Gulf export terminals."
        ),
    },
    "pnw_wheat": {
        "label": "Pacific Northwest soft white wheat",
        "states": ["53", "16", "41"],  # WA ID OR
        "narrative": (
            "Soft white wheat for Asian export markets, primarily noodle and "
            "pastry flour buyers. Geography insulates the region from much of "
            "the Hard Red price cycle."
        ),
    },
    "dairy_belt": {
        "label": "Dairy Belt",
        "states": ["55", "27", "36", "06", "16"],  # WI MN NY CA ID
        "narrative": (
            "Milk production concentrated across a small set of states with very "
            "different production models — pasture-based in the upper Midwest, "
            "industrial-scale in CA + ID."
        ),
    },
    "southeast_cotton": {
        "label": "Southeast cotton region",
        "states": ["13", "01", "28", "37", "45"],  # GA AL MS NC SC
        "narrative": (
            "Cotton + peanut + poultry. Cotton acres compete directly with "
            "soybeans on price; the region's poultry density also makes it a "
            "major corn + soybean MEAL consumer rather than producer."
        ),
    },
}


def _regional_cluster_signals(as_of: date) -> list[Signal]:
    out: list[Signal] = []
    for cluster_id, cfg in REGIONAL_CLUSTERS.items():
        sig = _build_cluster(cluster_id, cfg, as_of)
        if sig:
            out.append(sig)
    return out


def _build_cluster(
    cluster_id: str, cfg: dict[str, Any], as_of: date
) -> Signal | None:
    states = cfg["states"]
    sql = text(
        """
        SELECT commodity, AVG(usda_june_actual) AS avg_acres
        FROM acreage_accuracy
        WHERE state_fips = ANY(:sf)
          AND usda_june_actual IS NOT NULL
          AND forecast_year = (
              SELECT MAX(forecast_year) FROM acreage_accuracy
              WHERE usda_june_actual IS NOT NULL AND updated_at <= :as_of
          )
          AND updated_at <= :as_of
        GROUP BY commodity ORDER BY avg_acres DESC
        """
    )
    try:
        with get_sync_session() as s:
            rows = s.execute(sql, {"sf": states, "as_of": as_of}).all()
    except Exception as exc:  # noqa: BLE001
        logger.warning("regional cluster %s query failed: %s", cluster_id, exc)
        return None
    if not rows:
        return None

    top = [(r.commodity, float(r.avg_acres)) for r in rows[:3] if r.avg_acres]
    if not top:
        return None
    crops_str = ", ".join(f"{c} {a / 1e6:.1f}M ac" for c, a in top)

    scope = f"region:{cluster_id}"
    domain = "feature-region"

    parts = ScoreParts(
        magnitude=55.0,
        reach=80.0,
        novelty=novelty_score(domain, scope, 50, as_of),
        calendar=0.0,
    )
    score = compute_score(parts)

    return Signal(
        id=f"feature-region:{cluster_id}",
        domain=domain,
        scope=scope,
        headline=(
            f"{cfg['label']} ({len(states)} states): {crops_str}"
        ),
        score=score,
        direction="neutral",
        evidence={
            "cluster_id": cluster_id,
            "label": cfg["label"],
            "state_fips_list": states,
            "state_names": [state_label(sf) for sf in states],
            "narrative": cfg["narrative"],
            "top_commodities": [
                {"commodity": c, "avg_acres": round(a, 0)} for c, a in top
            ],
            "feature_type": "regional_cluster",
            "score_parts": parts.__dict__,
        },
        sources=["acreage_accuracy"],
    )


# ---------------------------------------------------------------------------
# 3. Seasonal explainers — calendar-anchored primers, no DB.
# ---------------------------------------------------------------------------


EXPLAINER_LIBRARY: list[dict[str, Any]] = [
    {
        "id": "prospective-plantings",
        "active_months": (2, 3),
        "title": "What Prospective Plantings actually tells us (and doesn't)",
        "narrative": (
            "USDA's March 31 Prospective Plantings is farmers' STATED INTENTIONS "
            "from a survey conducted in early March. June Acreage measures actual "
            "planted area. The gap, especially in mixed corn-soy decision states, "
            "is where weather + spring price swings show up."
        ),
    },
    {
        "id": "emergence",
        "active_months": (4, 5),
        "title": "Emergence: what GDD and V-stages mean for yield",
        "narrative": (
            "Corn typically emerges 5-7 days after planting given 100-150 growing "
            "degree days. The V3-V6 stages (3-6 leaves) are when nitrogen demand "
            "ramps and weed competition peaks. Late or uneven emergence narrows "
            "the rest of the season's yield ceiling."
        ),
    },
    {
        "id": "pollination",
        "active_months": (6, 7),
        "title": "Pollination: the 14 days that decide 60% of corn yield",
        "narrative": (
            "Corn silking and pollen shed run roughly 2 weeks per plant, longer "
            "across an unevenly emerged field. Heat stress above ~95°F or drought "
            "during this window reduces kernel set; final yield variance is "
            "dominated by what happens here."
        ),
    },
    {
        "id": "wasde-101",
        "active_months": (5, 6, 7, 8),
        "title": "WASDE 101: stocks-to-use is the right lens",
        "narrative": (
            "USDA's monthly World Ag Supply/Demand Estimates. Stocks-to-use = "
            "ending stocks divided by total use; below 10% historically signals "
            "tight, above 18% loose. The SURPRISE vs prior month moves futures "
            "within minutes of the report; the absolute level matters less."
        ),
    },
    {
        "id": "harvest-revisions",
        "active_months": (9, 10, 11),
        "title": "Why September Crop Production estimates keep moving",
        "narrative": (
            "NASS September Crop Production tightens estimates as harvest "
            "progresses. Final January estimate typically lands within 1.5% of "
            "August NASS in normal years — but mid-cycle revisions of 5%+ are "
            "common in drought years. Watch the September → November revision "
            "direction more than the absolute number."
        ),
    },
    {
        "id": "cattle-on-feed",
        "active_months": (1, 2, 11, 12),
        "title": "Cattle on Feed and the placement signal",
        "narrative": (
            "USDA's monthly Cattle on Feed report. Placements (cattle entering "
            "feedlots) vs trade expectations move live cattle futures. Roughly "
            "90% of finish-stage cattle sit in feedlots, so the report covers "
            "essentially all near-term beef supply."
        ),
    },
    {
        "id": "corn-soy-ratio",
        "active_months": (1, 2, 3),
        "title": "How the corn/soy price ratio drives spring acreage",
        "narrative": (
            "November soybean futures divided by December corn futures, computed "
            "in February-March, predicts spring planting decisions. Below 2.2 "
            "historically pulls 2-4M acres into soybeans; above 2.5 favors corn. "
            "Insurance crop revenue guarantees in February cement the call."
        ),
    },
    {
        "id": "drought-monitor",
        "active_months": (4, 5, 6, 7, 8, 9),
        "title": "Reading the U.S. Drought Monitor",
        "narrative": (
            "Released weekly Thursday by NDMC. D0-D4 categories track abnormally "
            "dry → exceptional drought. The Drought Severity and Coverage Index "
            "(DSCI) aggregates a state into one number 0-500; >250 in a major "
            "producer state during pollination is the threshold worth watching."
        ),
    },
    {
        "id": "crp-explained",
        "active_months": (10, 11, 12, 1, 2),
        "title": "CRP: how the conservation program shapes acreage supply",
        "narrative": (
            "USDA's Conservation Reserve Program pays landowners to retire "
            "cropland for 10-15 year contracts. About 24M acres enrolled today; "
            "expirations create a year-by-year supply of returnable cropland that "
            "moves with commodity price cycles."
        ),
    },
    {
        "id": "fas-export-sales",
        "active_months": (10, 11, 12, 1, 2, 3, 4, 5, 6),
        "title": "FAS Export Sales 101",
        "narrative": (
            "USDA Foreign Agricultural Service Export Sales is published every "
            "Thursday, covering the prior week's grain shipments + outstanding "
            "sales. Outstanding sales as of late spring is the cleanest single "
            "indicator of the marketing year's export trajectory."
        ),
    },
]


def _seasonal_explainer_signals(as_of: date) -> list[Signal]:
    out: list[Signal] = []
    for ex in EXPLAINER_LIBRARY:
        if as_of.month not in ex["active_months"]:
            continue
        scope = "national"
        domain = "feature-explainer"
        parts = ScoreParts(
            magnitude=50.0,
            reach=100.0,
            novelty=novelty_score(domain, f"explainer:{ex['id']}", 50, as_of),
            calendar=calendar_fit_score("calendar", as_of),
        )
        score = compute_score(parts)
        out.append(
            Signal(
                id=f"feature-explainer:{ex['id']}",
                domain=domain,
                scope=scope,
                headline=ex["title"],
                score=score,
                direction="neutral",
                evidence={
                    "topic_id": ex["id"],
                    "narrative": ex["narrative"],
                    "active_months": list(ex["active_months"]),
                    "feature_type": "seasonal_explainer",
                    "score_parts": parts.__dict__,
                },
                sources=["calendar"],
            )
        )
    return out
