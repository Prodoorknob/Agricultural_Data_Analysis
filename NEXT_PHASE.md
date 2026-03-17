# Phase 3: Web App Improvements (Peruse-AI Feedback)

## Overview

Use [peruse-ai](https://github.com/Prodoorknob/peruse-ai) to autonomously evaluate the deployed dashboard and generate structured feedback across UX, data, and bug dimensions.

## Prerequisites

1. **Deploy the Next.js app** to a publicly accessible URL (Vercel recommended)
2. **Ollama running locally** with `qwen2.5-vl:7b` or `qwen3-vl:6b` model
3. **peruse-ai installed**: `pip install peruse-ai && playwright install chromium`

## Step 1: Deploy to Vercel

The app already has Vercel detection in `web_app/src/app/api/data/route.ts`.

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy from web_app directory
cd web_app
vercel --prod
```

Set root directory to `web_app/` in Vercel dashboard settings.

## Step 2: Run Peruse-AI Focus Group

```bash
peruse focus-group \
  --url "https://your-app.vercel.app" \
  --task "Thoroughly explore this agricultural data dashboard. Navigate all 6 views \
    (Dashboard, Crops, Livestock, Land & Area, Labor, Economics). Select different \
    states (IN, CA, TX) and years (2022, 2018, 2010). Evaluate data presentation, \
    chart clarity, navigation flow, filter usability, and overall user experience. \
    Note any missing data, broken interactions, or confusing elements." \
  --personas "a senior UX designer with 15 years experience designing data-heavy dashboards,\
              a data analyst who uses USDA agricultural data daily for research papers,\
              an agricultural researcher studying state-level crop production trends,\
              a WCAG 2.1 accessibility auditor evaluating color contrast and keyboard navigation" \
  --reports all \
  --max-steps 50 \
  --no-headless \
  --output ./peruse_feedback \
  --verbose
```

This generates 4 sub-directories under `./peruse_feedback/`, each containing:
- `data_insights.md` - What data the agent found and how it was presented
- `ux_review.md` - Layout, navigation, interaction critique
- `bug_report.md` - Console errors, failed requests, broken elements

## Step 3: Categorize Feedback

After collecting reports, categorize findings into:

| Priority | Category | Action |
|----------|----------|--------|
| P0 | Crashes / data loss | Fix immediately |
| P1 | Broken interactions | Fix in this phase |
| P2 | UX pain points | Fix in this phase |
| P3 | Accessibility gaps | Fix in this phase |
| P4 | Enhancement ideas | Add to Phase 4 backlog |

## Pre-Identified Issues (From Code Review)

These issues were identified during code review and should be validated/expanded by peruse-ai findings.

### Performance
- [ ] Full `NATIONAL.parquet` fetched on every page load (`page.tsx:91`)
  - **Fix**: Use Athena queries for national aggregates instead of full parquet download
- [ ] `filterData()` rebuilds a `Map` on every filter change (`processData.ts`)
  - **Fix**: Move to `useMemo` with stable keys, or pre-compute on data load
- [ ] No loading skeletons or progressive disclosure
  - **Fix**: Add `LoadingSkeleton.tsx` component

### UX
- [ ] Search bar is non-functional (`page.tsx:247` - no onChange handler)
  - **Fix**: Implement `SearchOverlay.tsx` for commodity/state search
- [ ] Notification bell is decorative only (`page.tsx:253`)
  - **Fix**: Either remove it or wire it to real data update notifications
- [ ] No mobile navigation (`hidden lg:flex` with no hamburger alternative)
  - **Fix**: Add `MobileNav.tsx` hamburger menu
- [ ] No error boundaries - fetch failures crash silently
  - **Fix**: Add `ErrorBoundary.tsx` wrapper

### Accessibility
- [ ] Color-only chart differentiation (no patterns for colorblind users)
  - **Fix**: Add pattern fills or texture overlays to chart areas
- [ ] Missing `aria-label` on interactive map/chart elements
  - **Fix**: Add aria attributes to USMap, StateSingleMap click targets
- [ ] Green-on-dark text (`#19e63c` on `#0f1117`) may fail WCAG at small sizes
  - **Fix**: Verify contrast ratios, offer high-contrast toggle

### Data Gaps
- [ ] `getLandUseComposition()` returns empty array (stub in `processData.ts:264`)
  - **Fix**: Implement using Athena query or existing parquet data
- [ ] `getLandUseChange()` returns empty array (stub in `processData.ts:268`)
  - **Fix**: Implement using Athena query
- [ ] `fetchLandUseData()` and `fetchLaborData()` both just re-fetch NATIONAL.parquet
  - **Fix**: Wire to Athena with appropriate metric filters

## Step 4: Implementation

After prioritizing, implement fixes starting with P0/P1 items. Planned new components:

| Component | Purpose |
|-----------|---------|
| `LoadingSkeleton.tsx` | Chart loading shimmer states |
| `ErrorBoundary.tsx` | Graceful error display with retry |
| `MobileNav.tsx` | Hamburger menu for responsive layout |
| `SearchOverlay.tsx` | Search commodities, states, metrics |

## Step 5: Verify

1. Re-run peruse-ai after fixes to compare before/after
2. Run Lighthouse audit: `npx lighthouse https://your-app.vercel.app --view`
3. Check WCAG compliance: `npx pa11y https://your-app.vercel.app`


---

# Phase 4: Future Feature Outlines

## 4.1 Price Forecasting

**Goal**: Show predicted commodity prices alongside historical data.

**Data Source**: USDA QuickStats `PRICE RECEIVED` statistics (already available in pipeline).

**Architecture**:
```
pipeline/forecasting/train_model.py  --> S3 model artifacts
Lambda function (predict.py)         --> API Gateway --> /api/forecast
ForecastChart.tsx                     --> Renders historical + predicted + confidence intervals
```

**Model Options**:
- **ARIMA/SARIMA**: Good for seasonal commodities. Lightweight, runs in Lambda.
- **Facebook Prophet**: Better with holidays/events. Slightly heavier but still Lambda-compatible.
- **Linear Regression**: Simplest baseline. Good for initial MVP.

**New Files**:
- `pipeline/forecasting/train_model.py` - Train on historical price data
- `pipeline/forecasting/predict.py` - Lambda handler for predictions
- `web_app/src/components/ForecastChart.tsx` - Chart with historical + forecast bands
- `web_app/src/app/api/forecast/route.ts` - API endpoint (proxy to Lambda or direct)

**Frontend**:
- Add "Forecast" toggle to Economics dashboard
- Historical line (solid) + forecast line (dashed) + confidence band (shaded)
- Commodity selector, horizon selector (3mo, 6mo, 12mo)

## 4.2 Additional Economic Indicators

**Sources**:
- [USDA ERS](https://www.ers.usda.gov/data-products/) - Farm income, food prices, trade data
- CBOT/CME commodity futures (free delayed data via Yahoo Finance API)
- [BEA](https://www.bea.gov/data) - GDP contribution from agriculture

**Integration**:
- Add new pipeline scripts for each source
- New Athena table `economic_indicators` in `usda_agricultural` database
- New dashboard section in Economics view

## 4.3 Weather/Climate Data

**Source**: [NOAA Climate Data Online API](https://www.ncdc.noaa.gov/cdo-web/webservices/v2) (free, API key required)

**Data Points**:
- Monthly precipitation by state
- Average temperature by state
- Palmer Drought Severity Index (PDSI)
- Growing degree days

**Integration**:
- Overlay weather on crop yield charts (dual-axis: yield + rainfall)
- Correlation analysis: show R-squared between weather and yield
- New component: `ClimateDashboard.tsx` or toggle on Crops view

## 4.4 Export/Download Capabilities

**Formats**: CSV, Excel (.xlsx), PDF

**Implementation**:
```typescript
// web_app/src/utils/exportData.ts
export function exportCSV(data: any[], filename: string): void
export function exportExcel(data: any[], filename: string): void
export function exportChartPDF(chartRef: RefObject, filename: string): void
```

**Dependencies**: `xlsx` for Excel, `html2canvas` + `jspdf` for PDF charts.

**UX**: Download button on each dashboard card/chart. Bulk export via Athena for large datasets.

## 4.5 State Comparison Tool

**Goal**: Side-by-side comparison of 2-5 states across any metric.

**Architecture**:
- New `COMPARE` view mode in `page.tsx` ViewMode type
- Uses Athena `/api/athena/compare` endpoint (already built in Phase 2)
- Component: `ComparisonDashboard.tsx`

**Features**:
- State multi-selector (pick 2-5 states)
- Metric selector (Area Harvested, Yield, Production, Revenue)
- Commodity filter
- Year range slider
- Side-by-side line charts, ranking tables, delta (% change) cards

## 4.6 Data Quality Dashboard

**Goal**: Surface data completeness and freshness information.

**Features**:
- Show which states have complete data vs gaps
- Highlight Census-only metrics (available for 2012, 2017, 2022 only)
- Show last update date per state/sector
- Pipeline health: last ingestion success, next scheduled run
