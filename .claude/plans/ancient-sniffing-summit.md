# Steps 7 & 8: API Implementation + Frontend Predictions Dashboard

## Context
The commodity price forecasting module has completed Steps 1-6 (backend skeleton, DB migration, ETL scripts, feature engineering, model training). Steps 7-8 implement the live API endpoints and a new PREDICTIONS tab in the frontend dashboard.

---

## Step 7: API Implementation

### 7a. Model loading at startup (`backend/main.py`)
- In the `lifespan()` context manager, load all 18 ensemble models from `backend/artifacts/{commodity}/horizon_{N}/ensemble.pkl`
- Store in `app.state.models` dict keyed by `(commodity, horizon)` tuple
- Fallback: if local artifacts missing, download from S3 (`models/price/` prefix)
- Log which models loaded and which are missing

### 7b. Fill in stub endpoints (`backend/routers/price.py`)
Access models via `request.app.state.models`.

**GET `/` → `get_price_forecast`**
- Load ensemble from `app.state.models[(commodity, horizon_months)]`
- Call `build_price_features(commodity, date.today(), horizon_months)`
- Call `ensemble.predict(features_df)` → get p10/p50/p90/key_driver/regime_anomaly/divergence_flag
- Compute `horizon_month` as YYYY-MM string from today + horizon_months offset
- Persist forecast to `price_forecasts` table (upsert on run_date+commodity+horizon+model_ver)
- Return `PriceForecastResponse`

**GET `/probability` → `get_price_probability`**
- Load ensemble, build features
- Call `ensemble.predict_probability(features_df, threshold_price)`
- Return `ProbabilityResponse`

**GET `/wasde-signal` → `get_wasde_signal`**
- Query `wasde_releases` for the two most recent releases for this commodity
- Calculate surprise (current STU - prior STU), direction (>0.02 bearish, <-0.02 bullish, else neutral)
- Calculate percentile: rank current STU against all historical STU for this commodity
- Generate `historical_context` text string
- Return `WasdeSignalResponse`

**GET `/history` → `get_price_history`**
- Query `price_forecasts` filtered by commodity + horizon_months, ordered by run_date
- For each forecast, look up actual realized price from `futures_daily` at the horizon_month
- Calculate `error_pct = (actual - p50) / p50 * 100`
- Return `list[PriceForecastHistoryItem]`

### 7c. Add Request dependency
- Add `from starlette.requests import Request` to price.py
- Pass `request: Request` to endpoints that need model access

### Files modified:
- `backend/main.py` — lifespan model loading
- `backend/routers/price.py` — all 4 endpoints

---

## Step 8: Frontend Predictions Dashboard

### 8a. New hook: `web_app/src/hooks/usePriceForecast.ts`
- Custom hook that fetches from backend API (default `http://localhost:8000/api/v1/predict/price`)
- Functions: `fetchForecast(commodity, horizon)`, `fetchProbability(commodity, threshold, horizon)`, `fetchWasdeSignal(commodity)`, `fetchHistory(commodity, horizon)`
- Returns `{ forecast, probability, wasdeSignal, history, loading, error }`
- Backend URL configurable via env var `NEXT_PUBLIC_PREDICTION_API_URL`

### 8b. New component: `web_app/src/components/PredictionsDashboard.tsx`
Single file containing the main dashboard and all sub-components (PriceFanChart, ProbabilityGauge, KeyDriverCallout, WasdeSignalCard, PriceRegimeAlert). Keeping in one file matches the existing pattern where dashboards are self-contained.

**Layout (top to bottom):**
1. **Header row**: Commodity selector (corn/soybean/wheat), Horizon selector (1-6 months)
2. **Alert banner** (PriceRegimeAlert): Only shown when `regime_anomaly=true`. Red bg, warning icon.
3. **KPI row** (3 cards): p50 forecast price, divergence flag indicator, key driver callout
4. **Main chart** (PriceFanChart): Recharts AreaChart showing p10/p50/p90 fan across horizons 1-6. Uses palette.revenue for p50 line, gradient fill for p10-p90 band.
5. **Two-column row**:
   - Left: ProbabilityGauge — large % display with threshold slider input
   - Right: WasdeSignalCard — stocks-to-use ratio, percentile bar, surprise direction arrow
6. **History section**: LineChart of past p50 forecasts vs actual realized prices

**Styling**: Follow existing dashboard patterns — dark cards (`bgCard`), `border` borders, `textPrimary`/`textSecondary` text colors, Recharts with `chartDefaults`.

### 8c. Wire into page.tsx (`web_app/src/app/page.tsx`)
- Add `'PREDICTIONS'` to `ViewMode` type (line 21)
- Add to `VIEW_FILTER_DEFAULTS` (line 36)
- Add to nav labels array (line 216) with label "Predictions"
- Add conditional render block after ECONOMICS (after line 640)
- Import PredictionsDashboard

### Files created:
- `web_app/src/hooks/usePriceForecast.ts`
- `web_app/src/components/PredictionsDashboard.tsx`

### Files modified:
- `web_app/src/app/page.tsx`

---

## Verification
1. **Backend**: Run `cd backend && python -c "from backend.routers.price import router; print('Router OK')"` to verify imports
2. **Frontend**: Run `cd web_app && npx tsc --noEmit` to check TypeScript compilation
3. **Visual**: Start dev server, navigate to Predictions tab, verify components render with loading states (API may not be running locally)
