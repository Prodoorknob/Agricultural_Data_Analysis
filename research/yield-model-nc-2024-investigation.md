# NC Corn 2024: Yield Model Outliers — Findings Note

**Date:** 2026-05-07
**Trigger:** FieldPulse analyst-agent calibration surfaced extreme `pct_error` values for North Carolina corn (Lee, Durham, Johnston, Granville Co.) and Garfield Co., Oklahoma for forecast_year 2024. NC contributed 93 of 150 county-level outlier rows.
**Question:** Is this a model failure, or a NASS yield-on-planted vs yield-on-harvested unit mismatch?

## Verdict

**Hypothesis 1 (real model failure).** No unit mismatch — NASS published these yields correctly on harvested acres. The model under-anchored to county-specific climatology and over-extrapolated a corn-belt time trend onto a region (SE Atlantic) with structurally different weather exposure.

## Evidence

### Unit mismatch ruled out
Pulled `NC.parquet` (S3, `survey_datasets/partitioned_states_counties/`) and replicated [train_yield.py:100-108](backend/models/train_yield.py:100) filter exactly:
- `statisticcat_desc=YIELD` × `unit_desc=BU/ACRE` × `class_desc=ALL CLASSES` × `domain_desc=TOTAL` × `freq_desc=ANNUAL`

All 58 NC corn 2024 rows resolve uniformly:
- `short_desc = "CORN, GRAIN - YIELD, MEASURED IN BU / ACRE"`
- `prodn_practice_desc = ALL PRODUCTION PRACTICES`
- `util_practice_desc = GRAIN`
- `reference_period_desc = YEAR`

NASS computes "YIELD, BU/ACRE" as production ÷ **harvested** acres (not planted). The 26.2 bu/ac for Lee Co is the official harvested-acre yield. Confirmed.

### 2024 was genuinely catastrophic for NC corn
| Year | NC county-mean | NC min | NC max |
|------|---|---|---|
| 2021 | 147.5 | 120.5 | 182.3 |
| 2022 | 123.1 | 84.3 | 169.8 |
| 2023 | 139.4 | 87.9 | 180.9 |
| **2024** | **79.6** | **26.2** | **177.8** |

Statewide YoY drop of 43%. Bottom-10 counties are all in eastern/central NC (Lee 26.2, Durham 30.8, Johnston 32.0, Alamance 42.8, Harnett 43.2, Onslow 45.3). Top counties (e.g. Pasquotank 176.7) held normal — the loss is geographically clustered. Cause stack: mid-summer flash drought + Tropical Storm Debby flooding (early Aug) + Hurricane Helene (late Sep).

Lee Co 37105 historical context (training-set years): 70.0 (2011), 95.5 (2012), 76.4 (2015), 95.0 (2019), 106.1 (2020), 111.4 (2022), 87.9 (2023). The 2024 value of 26.2 is **below every prior year** for that county.

### Why the model overshot
[backend/artifacts/yield/corn/week_17/metrics.json](backend/artifacts/yield/corn/week_17/metrics.json) feature importances:

1. `year` — 1445 (top driver)
2. `county_mean_yield` — 1240
3. `county_yield_std` — 1117
4. `county_yield_trend` — 1114
5. `prior_year_yield` — 988
6. `tmax_avg`, `gdd_ytd` — 908, 835

Three concrete weaknesses:

1. **`year` is the top feature**, encoding a national upward trend. LightGBM trees split first on year, then on county features. For 2024 the leaves average across the corn belt (where yields trend up) and apply that to NC counties whose local trend is flat-to-negative. Lee Co got ~128 predicted because the year=2024 leaf pulled it toward the corn-belt mean.

2. **Weather features are absolute levels, not anomalies.** `gdd_ytd`, `tmax_avg`, `hot_days` are raw counts. NC always has higher heat than Iowa, so the model can't tell "this NC county is unusually hot for *its* climatology" without per-county normalization. Eastern NC's 2024 stress signal is invisible at this representation.

3. **State-level drought, no flood signal.** [drought_index](backend/models/db_tables.py) is *state-level and fall-aggregated* (NC 2024 `dsci_fall_avg=70.6`, lower than 2023's 99.4 — the late-fall view washes out the mid-summer flash drought). [train_yield.py:182-277](backend/models/train_yield.py) doesn't even consume `drought_index`; it relies only on GHCN-derived precip + temp. No feature captures hurricane-driven flood loss.

The 5-yr county mean baseline (88.9 for Lee Co) actually does better than the model on these counties — the model adds noise relative to "predict the recent mean."

### Scope
- **NC corn 2024**: 58 counties, all 20 weeks affected. Avg actual 79.6 vs avg model 138.8.
- **Comparable exposure**: any SE Atlantic county (SC, GA, eastern VA, FL panhandle, AL) in any hurricane-impact year. Garfield Co OK 2024 (corn 28.2, model 149.7; soy 8.7, model 31.6) is the same failure mode in a different stress regime (panhandle drought).
- **Affected county count, generalized**: ~200-300 counties out of ~3,100 in the panel are in hurricane-corridor or flash-drought-prone regions. These produce the long tail of outliers in `yield_accuracy`.

## Recommended fix

**Target reformulation + anomaly-style features.** Stays within the existing 60-model walk-forward training framework. No schema migration needed.

1. **Predict yield anomaly, not absolute yield.**
   `y_target = yield_bu - county_mean(yield_bu, prior 5 years)`
   Re-add `county_mean_yield` at predict time. This eliminates the cross-county leakage that "year" exploits.

2. **Anomaly weather features.** Replace `gdd_ytd`, `tmax_avg`, `hot_days`, `precip_season_in` with deltas vs. county 30-yr GHCN climatology:
   - `gdd_anom = gdd_ytd - county_gdd_climo(week)`
   - `tmax_anom = tmax_avg - county_tmax_climo(week)`
   - `precip_anom_in = precip_season_in - county_precip_climo(week)` (PRISM normals already wired up [train_yield.py:166](backend/models/train_yield.py:166))

3. **Add county drought from `feature_weekly.drought_d3d4_pct`** if the table is populated for the target year. Currently `feature_weekly` is empty for NC corn 2024 (the inference path at [yield_inference.py](backend/models/yield_inference.py) doesn't backfill historical training years), so wire this through `train_yield.py::compute_weather_features` from the USDM source directly, county-resolved, weekly. This is the highest-value addition.

4. **(Optional) Hurricane / flood feature.** Binary indicator per (fips, week) for tropical storm or hurricane landfall within 100 km. Skip for v1 if it adds too much surface area; the drought + anomaly-weather reframing should already meaningfully reduce SE error.

### Retraining scope
- 60 models (3 crops × 20 weeks). Same training matrix shape; only feature engineering changes.
- Single training run cost: ~57 min wall (per [train_yield.py persist run](research/yield-model-nc-2024-investigation.md), historically observed).
- Walk-forward windows unchanged: train ≤2019, val 2020-2022, test 2023-2024.
- Persist via `--persist-accuracy`; that bumps `model_ver` and rewrites `yield_accuracy`. Existing rows stay (constraint includes `model_ver`); a follow-up `DELETE WHERE model_ver < <new>` is needed if we want the agent to stop pulling stale predictions.

### Expected RRMSE delta
- Current corn test RRMSE: **17.97%** (vs baseline 23.78%, gate passes).
- Expected after reformulation:
  - Corn-belt counties: marginal improvement (the existing model is already well-fit there). Estimate −0.5 to −1 pp.
  - SE Atlantic + plains counties: substantial improvement. Estimate −5 to −8 pp on the affected subset.
  - Net all-county test RRMSE: estimate **−1 to −2 pp** (16-17%).
- Frontend impact: gate continues to pass; "Experimental" annotation can stay on wheat (still failing); the agent stops surfacing the long tail of NC/SE outliers as the dominant calibration signal.

### Alternative (not recommended): exclude SE counties from panel
Drops ~10% of training rows; weakens the model elsewhere; doesn't address the underlying problem (year-feature leakage). Reject in favor of (1)+(2).

## Side findings
- `yield_accuracy` accumulates duplicate rows across training runs because the unique constraint includes `model_ver` (Lee Co 37105 corn 2024 week 17 has 3 identical rows: 2026-04-14, 2026-04-15, 2026-04-21). Same shape as the acreage dedup work in 2026-04-16 that was fixed at the API layer for `acreage_forecasts`. Same fix applies here: dedupe on `(fips, crop, forecast_year, week, MAX(model_ver))` in the [yield accuracy] reader, or `DELETE WHERE model_ver < (SELECT MAX(model_ver))`. Not blocking the retrain — just inflates row counts and confuses the analyst agent's outlier ranking.
- `train_yield.py:121` — yield filter rejects `val <= 0`, which correctly drops NASS suppression markers stored as `0.0`. No bug here, just confirming the audit trail.
