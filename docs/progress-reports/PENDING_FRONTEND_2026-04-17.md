# Pending Frontend Work — Handoff Context

**Date opened:** 2026-04-17
**Status:** All backend work is landed and verified. Overview tab is complete. Five remaining tabs, one new tab, and one cross-cutting migration. Everything below can be worked tab-by-tab against the backend that is already deployed (FastAPI on EC2, aggregates on S3, models retrained and signed).

---

## 0. Infrastructure already in place (no action needed)

- **S3 aggregates**: `s3://usda-analysis-datasets/survey_datasets/overview/`
  - `state_totals.parquet` (38 KB)
  - `state_commodity_totals.parquet` (670 KB)
  - `county_metrics/{STATE}.parquet` (50 files, ~50 KB each)
  - `land_use.parquet` (29 KB)
  - `bls_establishments.parquet` (21 KB)
- **S3 CORS**: configured (GET + HEAD, all origins). Every new parquet can be fetched directly from the browser.
- **New API endpoints** (all live):
  - `GET /api/v1/market/exports?commodity={wheat|corn|soybean}` — returns `{as_of_date, marketing_year, outstanding_sales_mt, accumulated_exports_mt, total_committed_mt, five_yr_avg_committed_mt, pct_of_5yr_avg, week_of_marketing_year}`
  - `GET /api/v1/crops/profit-history?commodity={corn|soybean|wheat|cotton|rice|peanut|sorghum|oats|barley}&state={XX}` — returns `{commodity, state, cost_source, note, points: [{year, price, price_unit, yield_value, yield_unit, revenue_per_acre, variable_cost_per_acre, total_cost_per_acre, profit_per_acre}]}`
  - `GET /api/v1/meta/models` — returns `{as_of, models: [{task, commodity, horizon, model_ver, test_metric_name, test_metric_value, baseline_metric_value, beats_baseline, gate_status, coverage, n_train, n_val, n_test, n_features, top_features, artifact_exists}], summary: {...}}`
  - `GET /api/v1/predict/acreage/price-ratio` — now returns soy/corn (≈2.67) with correct implication
- **Normalizer**: all 14 futures/price/acreage/yield endpoints accept both `soybean` and `soybeans` via `backend/routers/deps.py`. No frontend changes needed for the plural mapping; the string can be passed either way.
- **Design token**: `--section-heading` is defined in `globals.css` (both light and dark). Component `web_app/src/components/shared/SectionHeading.tsx` exists.
- **Utility**: `web_app/src/utils/overviewData.ts` has typed fetchers for every new aggregate. Pattern to follow for new utils.

---

## 1. Market tab

**File:** `web_app/src/app/(tabs)/market/page.tsx`
**Component dependencies:** `MarketHero`, `PriceHistoryChart`, `WasdeCard`, `RatioDial`, `InputCostCard`, `DxyStrip`
**Hook:** `web_app/src/hooks/useMarketData.ts`

### 1a. Soybeans plural wiring (backend already accepts both)
Nothing to do. Verify by loading the Soybeans tab and confirming the futures chart populates.

### 1b. Wheat export-pace card in the empty slot
Current behavior: when `commodity === 'wheat'`, `<RatioDial>` is hidden and the 3-column grid leaves a gap.

- Add a new card component `web_app/src/components/market/ExportPaceCard.tsx` with props: `commodity, asOfDate, marketingYear, totalCommittedMt, fiveYrAvgMt, pctOfAvg, weekOfMy`.
- Visual: big percent (e.g. `112%`) colored green/red based on `pctOfAvg >= 100`, sub-label "of 5-yr avg commitments", supporting line "Week 32 of 2025/2026 marketing year".
- Add a `fetchExportPace(commodity)` method to `useMarketData`.
- In `market/page.tsx`, render `<ExportPaceCard>` when `commodity === 'wheat'` in the slot where `<RatioDial>` would go. Also surface it for corn/soy as a fourth card later if desired.

### 1c. Ratio dial fix
Backend now returns soy/corn (≈2.67) instead of corn/soy (≈0.38). The frontend RatioDial already has thresholds at 2.2 and 2.5 and a `tenYearMin: 2.0, tenYearMax: 2.8` range, so the marker position will compute correctly without any code change. Verify: reload Market/Corn, the ratio should read ~2.67 and the bar marker should land in the right-center. The big number color logic (`zone === 'corn_favored' ? 'var(--harvest)' : ...`) already keys off `implication` from the backend.

### 1d. Hide state filter on Market tab
File: `web_app/src/components/shell/FilterRail.tsx`.
Add an early-return check analogous to `showYear`: `const showState = currentTab !== 'market';` and wrap the State `<Pill>` in `{showState && (...)}`.

---

## 2. Forecasts tab

**File:** `web_app/src/app/(tabs)/forecasts/page.tsx`
**Components:** `SeasonClock`, `AcreageCard`, `AccuracyPanel`, `YieldSeasonReview`

### 2a. Season clock yield rail contrast
File: `web_app/src/components/forecasts/SeasonClock.tsx:68`.
Replace `bg = 'var(--surface2)'` (too low contrast) with a hatched pattern via inline style: `background: 'repeating-linear-gradient(45deg, var(--muted), var(--muted) 4px, transparent 4px, transparent 8px)'` or bump to `var(--border2)` at higher opacity. Either fix must be visible in both light and dark themes.

### 2b. Acreage p10/p90 bar visualization
File: `web_app/src/components/forecasts/AcreageCard.tsx:85-93`.
Current code hardcodes `left: 10%; right: 10%` regardless of p10/p90 values. Replace with computed positions:
```
// pseudo-code
const axisMin = p50 * 0.85;   // outer axis floor
const axisMax = p50 * 1.15;   // outer axis ceiling
const range   = axisMax - axisMin;
const leftPct  = ((p10 - axisMin) / range) * 100;
const rightPct = ((axisMax - p90) / range) * 100;
```
Then `style={{ left: `${leftPct}%`, right: `${rightPct}%` }}` with a marker at p50 center.
Add a `<Term>` tooltip on the "80% interval" label explaining: "80% of the time the actual planted acreage falls between these two values, based on conformal calibration."

### 2c. Accuracy chart 1 — filter to national, pivot by commodity
File: `web_app/src/components/forecasts/AccuracyPanel.tsx`, data wiring in `forecasts/page.tsx:42`.
Currently `acreageAccuracy` array is a flat concat of all three commodities' state and national rows. Fix in two places:
1. In page.tsx, filter each commodity's accuracy array to `level === 'national'` (or `state_fips === '00'`) before concat.
2. In the chart, pivot the data by year so each commodity is a separate `<Line>`. Target shape: `[{year: 2021, corn: -3.2, soybean: +1.1, wheat: +4.5}, ...]`. Render three `<Line>` series with commodity colors (from `COMMODITY_COLORS`) and a `<Legend>`.

### 2d. Accuracy chart 2 — fetch all crops, shade area under line
File: `forecasts/page.tsx:53` fetches only `?crop=corn`.
- Fire three parallel fetches with `Promise.all` for corn, soybean, wheat yield accuracy.
- Shape of data: `[{week, corn_rrmse, soybean_rrmse, wheat_rrmse, baseline_rrmse}]` — merge by week.
- Render three `<Area>` series with low fillOpacity (0.15) plus a baseline `<Line strokeDasharray="4 3">`.
- Title: "Corn · Soybean · Wheat — yield RRMSE by season week". Keep y-axis auto-scale (0–24% is honest; do not zoom in).
- X-axis: `interval="preserveStartEnd"` plus `<Legend verticalAlign="bottom" wrapperStyle={{paddingTop: 16}} />` so week ticks and legend don't overlap.

---

## 3. Crops tab

**File:** `web_app/src/app/(tabs)/crops/page.tsx`
**Components:** `CropHeroRow`, `YieldTrendChart`, `ProfitChart`, `HarvestEfficiency`, `CommodityPicker`

### 3a. Anomaly-dot hit target
File: `web_app/src/components/crops/YieldTrendChart.tsx:129`.
Replace `<ReferenceDot r={6} ...>` with a custom SVG group containing an invisible `<circle r={12} fill="transparent" pointer-events="all">` over a visible `<circle r={6} fill="var(--negative)" stroke="var(--surface)">`. Recharts supports this via the `shape` prop on `ReferenceDot`, or wrap in a custom layer.

### 3b. Operations Census fallback
File: `crops/page.tsx:70-78`.
Current query filters to `year === year` which always returns zero for non-Census years. Change to:
1. Look up the most recent year with OPERATIONS data for the (state, commodity). Search candidates: [year, year-1, 2022, 2017, 2012, 2007, 2002] in order.
2. Surface the year used as a sub-label on the card: `unit: '(Census 2022)'` or similar.
3. If still no data, hide the card entirely (return null for that slot).
BLS QCEW parquet at `overview/bls_establishments.parquet` can serve as a secondary signal (NAICS 111 for crops, 112 for animals at state level), but it's not commodity-specific. Use it as a tertiary fallback labeled "NAICS 111 establishments (BLS QCEW)".

### 3c. Yield-trend legend + named tooltip
File: `YieldTrendChart.tsx:102`.
Change formatter from `(val: unknown) => [Number(val).toFixed(1) + ' ' + unit, '']` to `(val, name) => [Number(val).toFixed(1) + ' ' + unit, name]` so the tooltip labels each series (stateName, "National").
Add a `<Legend verticalAlign="top" align="right" iconType="plainline" />` above the chart grid.

### 3d. Profit chart — wire to real endpoint
File: `crops/page.tsx:140-149`.
Remove the placeholder formula entirely. Add a new hook/util call to `GET /api/v1/crops/profit-history?commodity={X}&state={YY}` with the current commodity and state. Response has a `points` array already shaped for the chart; map to `{year, profitPerAcre: point.profit_per_acre}` for the existing ProfitChart component.
Display the `note` field on the endpoint response below the chart if it's non-null (e.g. when a commodity has no ERS data, the chart hides and the note explains why).
When state is null (national view), pass `state=IA` as a reasonable default and add a caption noting profit is calculated with Iowa yields against US-average costs.

### 3e. Commodity picker filtered by state
File: `crops/page.tsx`, around the `<CommodityPicker>` usage.
Derive a `Set<string>` of grown-in-state commodities from `stateData` where `AREA PLANTED > 0` in the last 3 years. Pass as the `commodities` prop (filtered subset of `CROP_COMMODITIES`). For national view, pass all 11.

---

## 4. Land & Economy tab

**File:** `web_app/src/app/(tabs)/land-economy/page.tsx`
**Components:** `RevenueLeaderboard`, `FarmStructure`, `LandUseMix`, `LaborWages`

### 4a. Crop-type filter pills (Revenue Leaderboard + Boom/Decline)
File: `RevenueLeaderboard.tsx`.
Add a pill row above the chart with options: All / Field Crops / Fruits / Vegetables / Livestock / Dairy / Poultry. Values map to NASS `group_desc`: `FIELD CROPS`, `FRUIT & TREE NUTS`, `VEGETABLES`, `LIVESTOCK`, `DAIRY`, `POULTRY`. Apply the same filter to the Boom/Decline callouts below.
Data source: `state_commodity_totals.parquet` already has `group_desc` and `sector_desc` columns.

### 4b. Land Use mix — consume the new parquet
File: `land-economy/page.tsx:77-88`.
Replace the `landUseData` useMemo block to fetch `overview/land_use.parquet` (use the typed fetcher `fetchLandUse()` in `overviewData.ts`). Filter to selected state (or aggregate across states for national). Pivot to shape `[{year, cropland, pasture, forest, urban, special, other}]`.
Also add `<Legend>` to `LandUseMix.tsx` (the 5-area chart has no legend today).

### 4c. Labor Wages — fix key mismatch and add BLS overlay
File: `land-economy/page.tsx:91-100` (`laborData` useMemo).
Current bug: `d.stateWage || d.nationalWage` reads non-existent keys. `getLaborTrends()` returns rows shaped like `{year, 'National Avg': X, IN: Y, IL: Z, ...}`.
Fix:
```
const wageTrend = labor.map((d) => ({
  year: d.year,
  stateWage: stateCode ? d[stateCode] : undefined,
  nationalWage: d['National Avg'],
}));
```
Then overlay BLS QCEW avg_annual_pay from `overview/bls_establishments.parquet` (NAICS 111 for crop workers). BLS covers every state-year 2014-onwards densely, while NASS WAGE RATE is sparse.

### 4d. Operations section — key mismatch fix
File: `land-economy/page.tsx:62-73`.
One-word fix: `d.count` → `d.operations` in both the map and the filter. The `getOperationsTrend` util returns `{year, operations}` not `{year, count}`. After the fix, FarmStructure will render against NASS OPERATIONS data (dense in Census years 2002, 2007, 2012, 2017, 2022; sparse annually).
Optionally overlay BLS QCEW establishment counts (NAICS 111+112 combined) for annual cadence between Census years.

### 4e. Boom/Decline — label baseline, use Census-year denominator
File: `RevenueLeaderboard.tsx:65-72`.
Change heading from "Boom Crops" / "Decline Crops" to "Boom Crops vs 2012 Census" / "Decline Crops vs 2012 Census". Change the comparison year in `land-economy/page.tsx:50` from `year - 10` to `2012` hardcoded (or nearest Census year). Census years are stable baselines; 2014 SURVEY data is sparse.

---

## 5. Livestock tab

**File:** `web_app/src/app/(tabs)/livestock/page.tsx`

### 5a. Sanitized inventory via new aggregates
Current bug: substring match on `commodity_desc.includes('CATTLE')` matches 5 overlapping NASS sub-categories, and no `class_desc='ALL CLASSES'` filter means quarterly inventories get summed as annual.
Fix: load `overview/state_commodity_totals.parquet` (same typed fetcher as Overview tab). Filter by exact `commodity_desc` match, e.g. `r.commodity_desc === 'CATTLE'`. The aggregate already applied the tier-aware canonical aggregation in the pipeline, so inventory_head is correct (Indiana cattle will read ~800K instead of 1.1B).
For `dairy` which maps to `CATTLE` with a `class_desc='MILK COWS'` filter, keep using the raw state parquet since the aggregate rolls all cattle into one row. Either: (a) expand the aggregate to include class-disaggregated livestock rows, or (b) leave dairy reading from the raw parquet with a strict filter.

### 5b. Table layout for Production & Sales
Current: three area-chart cards.
Redesign: one table with year rows, three metric columns (Cattle Sales $, Hog Sales $, Milk Production lbs), plus YoY delta cells. Mini sparkline in the column header using the new `<Sparkline>` with year metadata.

### 5c. Sparkline tooltips and endpoint labels
File: `web_app/src/components/shared/Sparkline.tsx`.
- Add optional `years?: number[]` prop alongside `data`.
- Add a Recharts `<Tooltip>` that shows `{year}: {value}` on hover.
- Render floating first-value and last-value labels absolutely positioned above the sparkline endpoints so the reader can orient without hovering.
- Backwards-compatible: if `years` is not passed, skip the tooltip and labels.

---

## 6. New About tab

**New route:** `web_app/src/app/(tabs)/about/page.tsx`

Two parts: a static prose section written directly in the page, and a live model-metadata strip fetched from `/api/v1/meta/models`.

### 6a. Prose sections (hand-written, no data)
1. What this is (one paragraph).
2. Data sources: USDA NASS, ERS, CME via Yahoo, FRED (DXY), NOAA GHCN, NASA POWER, USDM drought, RMA insurance, FSA CRP, FAS exports, BLS QCEW. One line per source.
3. Pipeline summary: NASS ingest monthly, canonical aggregation rules (the fix from the pipeline rewrite milestone), parquets + RDS split.
4. Architecture: inline the SVG from `web_app/public/cloud-architecture-diagram.html` or iframe it.
5. Forecast models: subsection each for Price / Acreage / Yield. Target, features, ensemble, validation, gate policy.
6. Accuracy methodology: walk-forward, conformal, why the baseline is county 5-yr mean or persistence, what "EXPERIMENTAL" means.
7. Known limitations: top-15-state rollup plus multiplier, wheat_spring small-sample, conformal under-coverage finding from 2026-04-14, county drought/FAS API quirks.
8. Glossary link (`web_app/src/data/glossary.json` already exists).

### 6b. Live model metadata strip
Fetch `/api/v1/meta/models` on mount. Render a tile per model grouped by task (Price / Acreage / Yield). Each tile shows: task, commodity, horizon (for price/yield), test metric + value, baseline + value, gate status pill (pass/borderline/fail), last trained date.
When a model is retrained, the tile updates automatically without a code change.

Expected summary numbers as of 2026-04-17:
- Total: 16 models
- Price: 9 (1 pass, 1 borderline, 7 fail — long-horizon price is hard)
- Acreage: 4 (soybean pass; corn, wheat_winter borderline; wheat_spring fail)
- Yield: 3 (corn pass, soybean pass, wheat fail)

### 6c. TABS constant already updated
`web_app/src/lib/constants.ts` already has `{ id: 'about', label: 'About' }` appended. No change needed.

---

## 7. Cross-cutting: SectionHeading migration

`--section-heading` token exists. `<SectionHeading>` component exists at `web_app/src/components/shared/SectionHeading.tsx`.
Remaining work: find-and-replace every occurrence of the class string below with `<SectionHeading>{text}</SectionHeading>`.

Class string pattern (grep):
```
className="text-[11px] font-bold tracking-[0.1em] uppercase ..."
style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
```

Estimated occurrences: ~30 across all 6 tabs. Quick regex-based replacement, then visual-diff the output. Overview tab components (`HeroStrip`, `StateFingerprint`, `StoryCards`) all still use the old pattern even after the Overview rewire — catching them is included in this migration, not the per-tab work above.

---

## 8. Verification checklist after each tab

1. `preview_eval` the tab path and confirm no Rules-of-Hooks or render errors in console.
2. Take `preview_screenshot`; compare hero numbers against known-good reference (e.g. Indiana total farm sales = $14.1B).
3. `preview_network` to verify new parquet fetches (state_totals, state_commodity_totals, land_use, bls_establishments, county_metrics/XX) return 200 with CORS.
4. `preview_console_logs level=error` should be empty. `level=warn` may include Recharts dimension warnings during initial paint — those clear after first layout.

---

## 9. Known gotchas

- **Turbopack cache corruption**: do NOT `rm -rf .next` while the dev server is running. It leaves Turbopack holding onto deleted file handles and requires a server restart. Safer: stop preview first, then rm, then restart.
- **S3 parquets are cached by the browser**. After uploading new parquets, hard-reload (Ctrl+Shift+R) or bump a cache-busting query param.
- **Acreage soy/corn ratio in training feature** (`backend/features/acreage_features.py::get_november_price_ratio`) intentionally returns corn/soy (opposite of the public endpoint) because the acreage model trained on that direction. Do not change it without retraining and bumping model_ver.
- **The `year-5 → 2019` baseline in the old Overview hero** was silently producing the +15487% growth artifact. Any other tab computing growth against a sparse year will do the same. Always use `2022` (Census) or document the denominator.
- **DC has no state parquet** in S3. All scripts skip it gracefully; frontend should not try to fetch `DC.parquet`.
- **Frontend uses `soybeans` (plural) everywhere**; backend now accepts both. Never propagate `soybean` singular into frontend constants or you'll break `CROP_COMMODITIES`.

---

## 10. Suggested next-session ordering

1. Market tab (smallest diff, quickest win, all backend ready). 30-60 min.
2. Forecasts tab (mostly chart wiring against already-shipped endpoints). 60-90 min.
3. Crops tab (profit-history endpoint wiring is the big one). 60-90 min.
4. Livestock tab (table refactor + sparkline upgrade). 60 min.
5. Land & Economy tab (largest; 4 separate fixes plus new data wiring). 90-120 min.
6. About tab (prose plus meta endpoint). 90 min.
7. SectionHeading migration last (mechanical find-and-replace). 30 min.

Estimated total: one focused work session, 6–8 hours end to end.
