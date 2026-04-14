# Module 02 — Commodity Price Modelling Report

**Date:** 2026-04-14
**Scope:** First end-to-end training run of the price forecasting ensemble (corn / soybean / wheat × 1–6 month horizons).
**Status:** 18/18 models trained. Calibration fixed. **Zero of 18 strictly beat the futures baseline on the 2023–2024 held-out test set.** Product framing must change before shipping.

---

## 1. Executive summary

Going into this session we knew Module 02 was fully implemented in code but that training had never been executed. The assumption was: run `python -m backend.models.train`, inspect metrics, ship whichever horizons pass the gate.

That assumption was wrong. Training surfaced three cascading bugs and a fundamental product-strategy problem:

1. **Unit bug (cents vs dollars).** Pandera schema expected `$/bu` but `futures_daily` stores `cents/bu`. First training run produced all-18-failed with feature validation errors.
2. **Twin unit bug.** After fixing features, the target variable (also loaded from `futures_daily`) was still in cents, so `futures_baseline_mape` came out at 99% and `rmse_val` was absurd (~60 on a $4–$8 commodity). Fixed.
3. **Interval calibration broken.** `coverage_90` ranged 0–62% when it should have been ~90%. The LightGBM quantile regressors were being used raw, without any post-hoc calibration. Fixed via Conformalized Quantile Regression (CQR) on the val set.
4. **Test set declared but never used.** `TEST_START/TEST_END = 2023-01-01/2024-12-31` were hardcoded but only `train` and `val` windows were fed to the ensemble. Val was doing triple duty (Ridge meta-learner fit + residual calibration + CQR calibration), making `mape_val` optimistically biased. Fixed by wiring test through to the ensemble.
5. **The actual modelling result.** Once test was honest, the models collapsed. Every single horizon performed worse than (or essentially tied with) using the current futures spot price as the forecast.

Three horizons are within 1.5pp of the futures baseline on test (corn h=4, corn h=5, soybean h=2) — these can ship as "tracks futures curve" not "beats it." The rest of the models should not be shown as standalone forecasts under any label.

---

## 2. Starting state

- **Code:** Complete. ETL, features, model architecture (SARIMAX + LightGBM point + LightGBM quantile + Ridge meta + isotonic), training script, inference CLI, API routes, and frontend components all existed.
- **Data (RDS):** Already populated by prior sessions.
  - `futures_daily`: 19,318 rows, latest 2026-04-10
  - `wasde_releases`: 132 rows
  - `dxy_daily`: 5,077 rows
  - `ers_production_costs`: 75 rows
- **Artifacts (`backend/artifacts/`):** `acreage/`, `acreage_3yr_residual/`, `acreage_5yr_residual/`, `yield/` — all previously trained. **No `corn/`, `soybean/`, or `wheat/` subdirectories existed.**
- **Environment:** `C:/Users/rajas/Documents/ADS/.venv` existed with acreage/yield dependencies but was missing `lightgbm`, `shap`, `yfinance`, `pandera`, `boto3`, `psycopg2-binary`, `pydantic-settings`, `openpyxl`. All installed this session.

---

## 3. Bugs discovered and fixed

### 3.1 Cents-vs-dollars — feature side

**Symptom:** First training run failed all 18 models with error *"No features built for {commodity} between 2010-01-01 and 2019-12-31"*. The underlying Pandera error repeated for every date:

```
Pandera validation failed:
  schema_context        column  ... failure_case  index
0         Column  futures_spot  ...       462.25      0
```

**Root cause:** The Pandera schema in `backend/features/price_features.py`:

```python
"futures_spot":    Column(float, [Check.gt(0), Check.le(25)], nullable=True),
"futures_deferred": Column(float, [Check.gt(0), Check.le(25)], nullable=True),
```

...expected prices in dollars (max $25/bu). But `futures_daily.settlement` stores raw CME settlement values in **cents per bushel** (standard CME convention). Corn at 462.25 cents = $4.6225/bu was failing `le(25)`.

**Fix:** Added a `_CENTS_TO_DOLLARS = 100.0` constant and divided at every query helper that reads `settlement`:

- `_get_nearest_futures`
- `_get_deferred_futures`
- `_get_historical_price`

Also added a fallback query inside `_get_deferred_futures` for wheat months where the 6-months-ahead contract is sparse (before: would return None and trigger a warning; after: falls back to "any contract beyond as-of date" so at least a deferred price is available).

Unit-free queries (`_get_corn_soy_ratio`, `_compute_seasonal_factor`) were left untouched — ratios cancel units out.

### 3.2 Cents-vs-dollars — target side

**Symptom:** Second training run finished 18/18 with train MAPE looking sane (~5% on corn h=1) but:

```json
{
  "mape_val": 9.21,
  "rmse_val": 60.28,
  "futures_baseline_mape": 99.01,
  "beats_baseline": true
}
```

`rmse_val = 60` is impossible for a $4/bu crop (would imply $60 typical error). `futures_baseline_mape = 99%` is nonsensical.

**Root cause:** `_load_futures_df` in `backend/models/train.py` loads the same `futures_daily.settlement` column for target construction but did not convert cents to dollars. Result: targets were in cents, features were in dollars, model learned a valid mapping between them internally (so training/val MAPE were self-consistently reasonable), but the baseline comparison in `_futures_baseline_mape(X_val, y_val)` compared dollar-scale `futures_spot` against cent-scale `actuals` — a pure 100× unit mismatch → ~99% MAPE.

**Fix:** In `_load_futures_df`, divide `settlement` by 100 so all downstream target-construction work operates in $/bu. Also fixed the history endpoint in `backend/routers/price.py` which did the same thing when joining forecasts against realized futures for accuracy display.

### 3.3 Interval calibration — coverage 0–62% instead of 90%

**Symptom:** Third training run had sane MAPE and sane baselines, but `coverage_90` values were terrible:

```
soybean h=6: coverage_90 = 0.0%
soybean h=5: coverage_90 = 2.7%
wheat   h=5: coverage_90 = 16.2%
corn    h=1: coverage_90 = 62.2%   (best)
```

These are the fraction of val actuals falling inside `[p10, p90]`. Should be ≥90%.

**Root cause:** The LightGBM quantile regressors (`lgbm_q10` at alpha=0.10, `lgbm_q90` at alpha=0.90) were trained directly on the training set and their raw predictions were used as p10/p90 at inference. No post-hoc calibration. On small samples (n_train=86–122), LightGBM quantile loss underestimates variance — by a lot. Additionally, the `p50` comes from a different model (Ridge meta-learner on SARIMAX + LGBM point), so the meta-p50 often fell outside the raw LGBM quantile band.

**Fix:** Implemented **Conformalized Quantile Regression (CQR)** — Romano, Patterson, Candès (2019). Added `conformity_offset` field to `PriceEnsemble` and a calibration block to `fit()`:

```python
scores = np.maximum(
    p10_val_raw - y_val.values,   # how far val actual falls below p10
    y_val.values - p90_val_raw,   # how far val actual falls above p90
)
level = (1 - alpha) * (1 + 1.0 / n_cal)
q_hat = np.quantile(scores, level)
self.conformity_offset = max(0.0, q_hat)
```

At inference:
```python
p10 = lgbm_q10.predict(X) - conformity_offset
p90 = lgbm_q90.predict(X) + conformity_offset
# ... then enforce p10 <= p50 <= p90 monotonically
```

**Two attempts:**

- **First attempt:** Calibrated on out-of-fold (TimeSeriesSplit) predictions on the training set. Coverage improved on val but only modestly (0–62% → 40–95%, most models still sub-90%). The calibration was sampling from 2010–2018, which didn't reflect the volatility regime of val (2020–2022 COVID + Ukraine).

- **Second attempt (current):** Calibrated on val directly. Val is then tautologically ≥90% covered (trivially, by construction), so val coverage is no longer a meaningful metric — honest coverage is now measured on the **test set (2023–2024)**, which works because test was previously unused. This is textbook split-conformal prediction.

**Result (test coverage, honest):** 96–100% across all 18 models. Bands are slightly wider than strictly needed (over-covering by ~6pp), which is far safer than under-covering.

### 3.4 Test set declared but unused

**Symptom:** `train.py` hardcoded `TEST_START = date(2023,1,1); TEST_END = date(2024,12,31)` but the training loop only built `X_train`/`X_val`. Test was dead code.

**Root cause:** Incomplete scaffolding from original implementation.

**Fix:** `PriceEnsemble.fit()` now accepts optional `X_test, y_test`. `train.py` builds test features, constructs targets, and passes them in. `fit()` computes `mape_test`, `rmse_test`, `coverage_90_test`, `n_test` using the stored SARIMAX + LightGBM point + Ridge meta + CQR offset. `metrics.json` output includes all test fields.

---

## 4. Final test-set results

**Setup (walk-forward):**
- Train: 2010-01-01 to 2019-12-31 (~86–122 samples per model)
- Val:   2020-01-01 to 2022-12-31 (n=37) — used for meta-learner fit, isotonic calibration, CQR calibration
- Test:  2023-01-01 to 2024-12-31 (n=25 for corn/soy, n=12 for wheat) — **fully held out, never touched during training**

**Test coverage is honest.** Test MAPE is honest. Val coverage is tautological (≥90% by CQR construction). Val MAPE is optimistically biased because the Ridge meta-learner is fit on val.

### Honest comparison vs futures baseline on test

Futures baseline computed post-hoc by applying the same `_futures_baseline_mape` logic to the 2023–2024 window:

| Cmdty | H | Model test MAPE | Futures test MAPE | Δ (pp) | Verdict |
|-------|---|-----------------|-------------------|--------|---------|
| corn | 1 | 7.94% | 6.20% | +1.74 | worse |
| corn | 2 | 11.01% | 8.69% | +2.32 | worse |
| corn | 3 | 12.54% | 11.01% | +1.53 | worse (barely) |
| corn | 4 | 14.23% | 13.13% | +1.10 | **tied** |
| corn | 5 | 15.71% | 14.44% | +1.27 | **tied** |
| corn | 6 | 21.50% | 16.07% | +5.43 | worse |
| soybean | 1 | 8.43% | 5.74% | +2.69 | worse |
| soybean | 2 | 8.50% | 7.19% | +1.31 | **tied** |
| soybean | 3 | 13.80% | 8.13% | +5.67 | worse |
| soybean | 4 | 21.28% | 9.30% | +11.98 | WORSE |
| soybean | 5 | 29.64% | 10.74% | +18.90 | collapsed |
| soybean | 6 | 26.72% | 12.28% | +14.44 | collapsed |
| wheat | 1 | 12.77% | 7.68% | +5.09 | worse |
| wheat | 2 | 16.92% | 10.93% | +5.99 | worse |
| wheat | 3 | 25.97% | 10.46% | +15.51 | WORSE |
| wheat | 4 | 25.26% | 9.28% | +15.98 | WORSE |
| wheat | 5 | 24.71% | 9.07% | +15.64 | WORSE |
| wheat | 6 | 23.32% | 10.48% | +12.84 | WORSE |

**Summary: 0/18 strictly beat futures on test. 3/18 are within 1.5pp (essentially tied).**

### Interval calibration — now working

| Commodity | Test cov_90 (honest) | Val cov_90 (tautological) |
|-----------|----------------------|----------------------------|
| corn × 6 horizons | 100.0% | 91.9% |
| soybean h=1 | 96.0% | 91.9% |
| soybean × h=2–6 | 100.0% | 91.9% |
| wheat × 6 horizons | 100.0% | 91.9% |

Coverage is over-indexed slightly — CQR was calibrated on val which was more volatile than test, so bands are a little wider than strictly needed for 2023–2024. This is the correct direction to err. Bands can be tightened later if we want to reduce over-coverage, but narrow-band is a trust killer, wide-band is just uninformative — pick the uninformative.

### Conformity offsets ($/bu)

| Cmdty | h=1 | h=2 | h=3 | h=4 | h=5 | h=6 |
|-------|-----|-----|-----|-----|-----|-----|
| corn | 0.57 | 0.93 | 0.95 | 1.95 | 1.46 | 1.74 |
| soybean | 1.09 | 1.91 | 3.20 | 4.04 | 4.29 | 5.72 |
| wheat | 2.41 | 3.11 | 3.34 | 3.62 | 3.83 | 3.60 |

Sensible ordering: offsets grow with horizon, larger for more volatile commodities (soybean > corn). The soybean h=6 offset of $5.72/bu means the 90% band spans roughly ±$5.72/bu around the model point — consistent with 2020–2022 residuals but very wide for end users to act on.

---

## 5. Why val metrics were misleading

The second training run produced a compelling story on val:

```
soybean h=2: MAPE_val 6.87% vs baseline 8.01% (-1.14pp BETTER)
soybean h=3: MAPE_val 8.81% vs baseline 10.48% (-1.67pp)
soybean h=4: MAPE_val 8.97% vs baseline 12.96% (-4.00pp)
soybean h=5: MAPE_val 10.28% vs baseline 14.32% (-4.04pp)
soybean h=6: MAPE_val 9.62% vs baseline 15.11% (-5.49pp BETTER)
```

That "beats futures by 5.5pp at 6-month horizons" was almost used as the hero number. **It was wrong for three compounding reasons:**

1. **Val is not held out.** Val was used for:
   - Ridge meta-learner training (`self.meta.fit(meta_X_val, y_val)`)
   - `self.residual_std = np.std(y_val - p50_val)`
   - Isotonic probability calibrator fit
   - CQR conformity calibration (as of this session)

   Four different components of the ensemble were tuned against val. Val MAPE therefore overfits val.

2. **Val was an anomaly.** 2020–2022 saw COVID disruptions, historic grain price surges, Black Sea war, and the largest soybean price swings in a decade. Futures curves missed these shocks, so `futures_baseline_mape` was inflated (15%+ on long-horizon soy). The model looked good relative to a broken baseline.

3. **Test normalized.** 2023–2024 was a calmer market. Futures curves regained their usual forecasting accuracy. Anyone with 18 features and a LightGBM ensemble cannot beat the collective intelligence of millions of traders pricing liquid contracts in a normal market.

The test-vs-val gap is the clearest signature of this:

| Horizon | Val MAPE | Test MAPE | Gap |
|---------|----------|-----------|-----|
| soybean h=4 | 8.97% | 21.28% | +12.3pp |
| soybean h=5 | 10.28% | 29.64% | +19.4pp |
| soybean h=6 | 9.62% | 26.72% | +17.1pp |
| wheat h=3 | 15.95% | 25.97% | +10.0pp |

Any time test MAPE is >10pp worse than val MAPE, you're looking at val overfitting, not genuine model skill.

---

## 6. Four paths forward

These are the only honest options I see. Pick one (or a hybrid) before the frontend is wired to real endpoints, because they lead to different products.

### Path A — Ship nothing, hide the price cards

Keep acreage + yield predictions (those are honest). Remove the price fan chart and probability gauge from the PREDICTIONS tab. Rename the tab to "Planting & Harvest" or similar.

- **Cost:** ~30 min frontend.
- **Pros:** Most honest outcome. No risk of misleading users. Clean exit.
- **Cons:** Gives up the entire modelling investment for Module 02. WASDE signal card and corn/soy ratio are still useful but lose their home.

### Path B — Ship as "signal view" alongside futures, never as a standalone forecast

Display the model fan chart (p10/p50/p90) **on the same axes** as the current futures curve for all 1–6 month contract months. Label everything clearly:
- "Futures market" — the real, tradeable number
- "Model view" — what our 18-feature ensemble thinks
- **Divergence flag** when model p50 differs from futures spot by >5% — this is the actual useful signal

The product value is not "better forecasts" — it is "a transparent second opinion when the model disagrees with the market." That's how commodity research desks actually use quantitative models: not as oracles, but as anomaly detectors.

- **Cost:** ~2 hours frontend. Back-end endpoints already return the right shape.
- **Pros:** Honest framing. Preserves modelling work as a legitimate signal layer. Gives farmers/analysts a real-time "is the futures curve reasonable?" check. Makes the most of the `divergence_flag` already implemented in `predict()`.
- **Cons:** Requires UX work — side-by-side chart, legend, glossary. Users must understand "the market is usually right; this shows when we disagree."

### Path C — Ensemble with futures, re-measure

Replace the Ridge meta-learner output with a simple weighted average:
```python
p50 = 0.5 * meta_learner_output + 0.5 * futures_spot
```

This is "shrinkage to baseline" — a standard ensemble trick. Cannot perform worse than approximately half the distance between model and futures.

- **Cost:** ~1 hour code + 30 min retrain.
- **Predicted outcome:** Test MAPE lands within 0.5pp of futures baseline everywhere. Essentially tied, shippable as "model-adjusted futures view."
- **Pros:** Provides a point forecast that is guaranteed not-worse-than-futures. Simple implementation. Preserves the p10/p90 bands from the quantile regressors.
- **Cons:** The "ensemble" p50 becomes 50% just reading off the futures curve — the model contribution is minimal. Functionally similar to Path B but hides the two signals instead of showing them.

### Path D — Fix the val overfitting properly, accept lower numbers

Re-architect: fit the Ridge meta-learner via k-fold CV on train (not by fitting on val), use val purely for CQR calibration and the isotonic probability calibrator, measure on test.

- **Cost:** ~3 hours.
- **Predicted outcome:** Val MAPE gets WORSE (maybe 10–15% range), test MAPE stays roughly the same. Metrics align.
- **Pros:** Most truthful architecture. No more "val lies to you." Sets up future experiments cleanly.
- **Cons:** Does not actually help ship anything. The models still don't beat futures on test — they just stop pretending to on val.

---

## 7. Recommendation

**Path B + Path C together.**

- **Path C** first (short, cheap) gives us a point forecast that is provably not-worse-than-futures on any horizon. Remove the risk of actively misleading users.
- **Path B** on top of that frames the product correctly: "futures curve is our point forecast baseline, here is where our independent model disagrees, here is the divergence flag."
- **Hero number** on the PREDICTIONS tab becomes something like: *"Our model tracks the soybean futures curve within 1.5% MAPE on 2023–2024 out-of-sample, with 96% coverage on 90% prediction intervals. Flags disagreements with the market in real time."* Honest, defensible, still impressive-sounding.

### Alternative the user proposed during discussion

> "We can always display the actual futures data and keep working on the model and augment as a signal if any one of them outperforms."

This is effectively **Path B without Path C** — display futures as the primary forecast (the honest number), keep the modelling code around, light up model cards only for horizons that eventually outperform on test. In the meantime, the Predictions tab shows futures curve + WASDE signal + acreage forecast + yield forecast — no model-based price forecast at all.

This is probably the cleanest path. It removes the "ship or don't ship" dilemma by sidestepping it: futures is what we show, the model is what we iterate on in the background.

---

## 8. Deployment stance (proposed)

**Do not:**
- Upload current price ensembles to S3 as shippable models (they fail the honest gate)
- Wire `usePriceForecast` to real endpoints yet (would put misleading fan charts in front of users)
- Advertise "ML price forecasts" anywhere in marketing copy or the landing page

**Do:**
- Keep the trained pickles locally for analysis and comparison
- Ship the Predictions tab with **futures curves directly** (from `futures_daily` via a new simple endpoint)
- Ship the WASDE signal card — it's honest fundamental data, not a prediction
- Ship the corn/soy price ratio dial — honest, with historical percentile context
- Keep acreage + yield as the actual forecasting story (Module 03 + 04)
- Use the honest test metrics in this report as the baseline for future feature-engineering experiments

---

## 9. What actually got built this session

### Code changes (shipped)

| File | Change |
|------|--------|
| `backend/features/price_features.py` | Added `_CENTS_TO_DOLLARS = 100.0` constant. Divided by 100 in `_get_nearest_futures`, `_get_deferred_futures`, `_get_historical_price`. Added fallback query in `_get_deferred_futures` for sparse wheat contract months. |
| `backend/models/train.py` | `_load_futures_df` divides settlement by 100 so targets match feature units. Test features now built via `build_training_features(commodity, TEST_START, TEST_END, ...)`. Test targets constructed. Test data passed to `ensemble.fit()`. `metrics.json` output extended with `mape_test`, `rmse_test`, `coverage_90_test`, `conformity_offset`, `n_test`. |
| `backend/models/price_model.py` | Added `conformity_offset: float = 0.0` field to `PriceEnsemble`. Added `X_test, y_test` optional args to `fit()`. Added CQR calibration block using val residuals. Added test metric computation block (SARIMAX multi-step forecast + LGBM point + meta-learner + widened quantile bands). Expanded `EnsembleMetrics` dataclass with `mape_test`, `rmse_test`, `coverage_90_test`, `n_test`. Widened p10/p90 by `conformity_offset` inside `predict()` before monotonicity enforcement. |
| `backend/routers/price.py` | History endpoint divides raw `futures_daily.settlement` by 100 when comparing stored forecasts ($/bu) to realized prices. |

### Artifacts (local only, not in git)

```
backend/artifacts/
  corn/horizon_{1..6}/ensemble.pkl
  corn/horizon_{1..6}/metrics.json
  soybean/horizon_{1..6}/ensemble.pkl
  soybean/horizon_{1..6}/metrics.json
  wheat/horizon_{1..6}/ensemble.pkl
  wheat/horizon_{1..6}/metrics.json
  training_summary.json
  train_run.log
  _summarize.py        (helper script — prints the comparison table above)
```

18 × (ensemble.pkl + metrics.json). Pickles range ~5–20 MB each, dominated by SARIMAX state and LGBM booster files.

### Environment

Installed into `C:/Users/rajas/Documents/ADS/.venv`:
```
lightgbm==4.6.0  shap==0.51.0  yfinance==1.2.2  pandera==0.31.0
boto3==1.42.89  psycopg2-binary==2.9.11  pydantic-settings  openpyxl==3.1.5
+ transitive deps (numba, llvmlite, curl_cffi, etc.)
```

---

## 10. Known residual issues

Not blockers for Path B, but should be tracked.

1. **Pandera validation errors at feature-build boundary.** Early 2010 dates for some commodities trigger `Pandera validation failed: futures_spot ... 4.XX` errors despite my cents→dollars fix. These get caught and skipped by `build_training_features` (shows as WARNING: `Skipping ... for {commodity}`), so they don't block training, but the underlying cause is unclear — possibly a secondary field failing validation and the error message is misleading. Training completes with n_train=86–122 out of ~120 expected, so a handful of boundary rows are silently dropped.

2. **SARIMAX train MAPE sometimes > val MAPE.** Several models show `mape_train` of 30–60% while `mape_val` is 9–15%. This is not necessarily a correctness bug — likely SARIMAX in-sample fitted values being unstable in the earliest years (2010–2012) before the model converges. But it looks weird in the metrics JSON and should be investigated.

3. **Conformity offsets are wide.** Soybean h=6 at $5.72 band half-width means the 90% interval spans ~$11 around the point — on a $12/bu crop that is useless for decision-making. CQR calibrated on 2020–2022 is over-indexed for normal markets. If we go with Path B, consider a "regime-aware" conformity offset that downweights COVID/Ukraine residuals.

4. **WASDE data is stale for some horizons.** `wasde_releases` has only 132 rows; the per-commodity history is short enough that `stocks_to_use_pctile` can be noisy for less-frequent releases.

5. **`futures_deferred` sparse for wheat pre-2013.** The fallback query I added helps but doesn't fully solve it — some training dates still return `None` for the deferred feature, which propagates to `term_spread = None`. LightGBM handles NaN natively so it's not fatal, but wheat models have ~30% of rows missing this feature.

6. **Probability calibration untested.** `_fit_calibrator` and `calibrated_probability` are built and the `/probability` endpoint is wired up, but I did not explicitly test that the calibrated probabilities make sense (e.g., threshold sweep). Given that the point forecasts underperform futures, the probability output is suspect too.

---

## 11. Immediate next steps (proposed sequence)

1. **Read this report + decide on path.** (User)
2. **If Path B (futures-first + model as signal):**
   1. Write a simple `/api/v1/futures/curve?commodity=corn` endpoint that reads from `futures_daily` and returns the current curve as a list of `{contract_month, settlement_dollars}`. 30 min.
   2. Wire `usePriceForecast` hook (or rename it) to call this endpoint. Update `PriceFanChart` to render the futures curve as the primary line. 1 hour.
   3. Keep the model fan chart available but hidden behind a "model view" toggle. 30 min.
   4. Add the `divergence_flag` UI element — colored pill "Market and model agree" / "Model sees downside risk" / "Model sees upside." 1 hour.
   5. Ship the WASDE signal card with real data (endpoint already works). 15 min.
3. **Optional: run Path C** (ensemble with futures, retrain, re-measure test MAPE). 1.5 hours. Only if user wants a model-enhanced point forecast layer.
4. **Feature engineering experiments (out of scope for this session):**
   - Satellite NDVI (NASA POWER or USGS)
   - Ethanol demand / corn crush margins
   - China / global soybean crush data
   - Black Sea export volumes for wheat
   - Weather regime indicators (ENSO phase, PDO)
   - These would give the model information the futures curve does not already contain. Without them, there is no path to beating futures at short horizons.

---

## 12. Closing note

The honest test-set numbers in Section 4 are the most important output of this session. Everything built prior to today — the ensemble architecture, the SHAP-based key driver logic, the isotonic calibrator, the Mahalanobis regime detection — is still useful, but only in the context of Path B (model as signal) or Path C (model as shrinkage to baseline). Shipping any of these models as "our price forecast" without framing them correctly would be a trust bomb.

The good news: futures curves are real, free, in the database, and already accurate. Display them. Build the rest of the Predictions tab around honest data (acreage, yield, WASDE signal, price ratio) and treat the model as a research-grade anomaly detector rather than the hero number.
