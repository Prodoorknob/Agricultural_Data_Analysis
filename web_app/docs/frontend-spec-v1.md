# FieldPulse — Frontend Specification v1

**Status:** Build-ready · all sections locked, all open items resolved
**Paired docs:** [`design-system-v1.html`](./design-system-v1.html) · [`../../UI/backend_analysis.txt`](../../UI/backend_analysis.txt) · [`../../research/`](../../research/)
**Last updated:** 2026-04-14

---

## How to use this document

This is the source-of-truth spec for every page, band, element, and narrative on the FieldPulse frontend. It is organized so each section can be iterated on independently. When refining a section, reference it by its numeric ID (e.g. "let's refine §5.2.C — Market Band C: Supply/demand context").

- **§0** — Anchoring decisions. Read first. These constrain everything downstream.
- **§1** — Information architecture. Tab list, ordering, and routing.
- **§2** — Cross-cutting systems. Header, filters, glossary, citations, exports, captions, state management, API surface, responsive, loading states, theme.
- **§3** — Seasonal behavior model.
- **§4** — Narrative formation mechanisms.
- **§5** — Per-page specs. One subsection per tab (§5.1–§5.6).
- **§6** — Build sequence.
- **§7** — Open questions awaiting decision.
- **§8** — Revision log.

Per-page specs follow a consistent template: **Purpose → Hero question → Band-by-band layout → Data sources → Cross-page flows → Open items**. If a page spec deviates from that template, it's a bug in the spec.

---

## §0 · Anchoring decisions

These are the constraints every other section inherits.

### §0.1 · What we are cutting

| Cut | Reason |
|---|---|
| Price ML forecast module | No trained artifacts on disk. Frontend currently returns mocks. Shipping silent mocks is the biggest credibility risk. |
| p10/p50/p90 price fan charts | Depend on the cut module. |
| Price probability gauges ("60% chance corn exceeds $X") | Depend on the cut module. |
| SHAP key-driver narratives for price | Depend on the cut module. |
| Wheat spring acreage forecast | Fails deployment gate (Test MAPE 4.92% vs 4.17% baseline). |
| Wheat yield forecast late-season | Inconsistent (Test RRMSE 25%+). |
| Search bar | Non-functional affordance. Remove until real. |
| Notifications bell | Non-functional affordance. Remove until real. |

### §0.2 · What replaces the price module

Raw CME futures daily settle prices (from `futures_daily`, already backfilled via Yahoo Finance). No forecasting. The Market tab (§5.2) is built entirely on real market data plus supply/demand context:

- `futures_daily` — daily settles, nearby + deferred contracts (corn, soy, wheat)
- `wasde_releases` — monthly supply/demand reports with stocks-to-use + surprise sign
- `ers_production_costs` + `ers_fertilizer_prices` — input cost reality
- `dxy_daily` — dollar index for macro context
- Corn/soy price ratio — computed from futures, the farmer-decision dial

Nothing on this tab is a prediction. Every chart is an observation.

### §0.3 · What we keep as "prediction"

Two narrow, gated forecast surfaces:

**Acreage forecasts** — corn, soybean, wheat_winter. Top 15 states + national rollup. Test MAPE 4.51%–6.26%. All three pass deployment gates at test-time. Gets `BETA` label on corn only (gate was borderline tight — 6.26% vs 6.24% baseline).

**County yield forecasts** — corn, soybean only (wheat hidden). 20-week season. Confidence tiers: weeks 1–7 low, 8–15 medium, 16–20 high. RRMSE 17–18% early-season, improving through the season. Weeks 1–7 carry an explicit "directional only" warning.

### §0.4 · Core truth the UI must tell

We are a **historical + market-data explorer** with **two narrow forecast surfaces that actually work**. Every element must be one of:

1. **Historical fact** — 25 years of NASS QuickStats, labeled with source + vintage
2. **Live market data** — daily futures, WASDE, DXY, labeled with timestamp
3. **Forecast** — acreage or county yield, always shown next to its track record

No silent mocks. No fake confidence. No "predictions" without an accuracy panel within scrolling distance. Trust is the product.

### §0.5 · Audience stance

The FieldPulse design system (v1) prioritizes farmers, then analysts, then discoverers. We are relaxing this: the product serves **farmers, analysts, and curious users equally**. That changes three things:

- Captions can be moderately analytic (percentiles, "above the 5-yr average") without being jargon-heavy
- We keep a hover glossary so curious users aren't lost (§2.3)
- We keep all the export/permalink affordances analysts need (§2.5)
- We do not change the warm visual language or the plain-English voice

---

## §1 · Information architecture

Six tabs, ordered by "what decision does this help me make today."

| # | Tab | Hero question | Primary data spine | Module |
|---|---|---|---|---|
| 1 | **Overview** | "Where does my state stand in U.S. ag right now?" | NASS rollups + choropleth + story cards | `§5.1` |
| 2 | **Market** | "What is the price of my crop doing, and why?" | CME futures + WASDE + DXY + ratios + input costs | `§5.2` |
| 3 | **Forecasts** | "What will be planted / what will my county yield?" | Acreage ensemble + county yield ensemble | `§5.3` |
| 4 | **Crops** | "How has this commodity performed over 25 years?" | County/state yield, condition, progress, anomalies | `§5.4` |
| 5 | **Land & Economy** | "Who grows what, for how much, and at what cost?" | Revenue, operations, wages, land use, urban sprawl | `§5.5` |
| 6 | **Livestock** | "What is happening on the animal side?" | Cattle, hogs, dairy, poultry inventories/sales | `§5.6` |

### §1.1 · Routing

All tabs use Next.js App Router segments with URL-encoded filter state:

```
/overview?state=IN
/market?state=IN&commodity=corn&range=6M
/forecasts?state=IN&section=acreage
/crops?state=IN&commodity=corn&year=2024
/land-economy?state=IN&section=land-use
/livestock?state=IN&species=cattle
```

URL is the single source of truth for shareable state. See §2.5 for permalink behavior.

### §1.2 · Why this order (and why it differs from the design system's farmer-priority ordering)

The design system leads with "Market Outlook" (Price Forecasts) because that was the hero product. With §0.1 in force, that tab is dead. The new leading tab is Overview because:

1. First-time users need orientation before they can use any other tab
2. The choropleth is our best at-a-glance instrument
3. Every story card on Overview deep-links into another tab with filters pre-applied — Overview functions as a table of contents for people who don't know what "Forecasts" means

Market moves to #2 because futures change daily and it's what a user returning to the product will check most often.

---

## §2 · Cross-cutting systems

### §2.1 · Header (two layers)

**Layer 1 — Nav bar.** Sticky, `--surface` background, 56px tall, `--shadow-sm` on scroll.

- Left: logo mark (28px green square with "F") + "FieldPulse" wordmark in Plus Jakarta Sans 15px/700
- Center/right: tab links in the order from §1. Active tab gets a `--field` underline (2px) and weight 600.
- Far right: theme toggle (sun/moon icon, no label). 44px touch target.
- Removed vs old design: search bar, notifications bell.

**Layer 2 — Filter rail.** `--surface2` background, 44px tall, sits under the nav.

- **State pill** — the only global filter. Selecting a state persists across every tab.
- **Year pill** — per-tab default, resets when switching tabs via a `VIEW_FILTER_DEFAULTS` map.
- **Commodity pill** — only visible on Market, Forecasts, and Crops.
- Right side: data freshness strip with a live dot and three timestamps (NASS vintage, futures timestamp, WASDE last-release date).

### §2.2 · Filter behavior rules

1. **State is global.** Setting a state on any tab (including by clicking the choropleth on Overview) updates the URL and the filter rail, and carries to every other tab.
2. **Commodity and year are per-tab.** Switching tabs does not carry these. `VIEW_FILTER_DEFAULTS` defines what each tab reverts to.
3. **Market Outlook default.** When no state is selected, the Market tab shows national-level futures (state is only used for basis, which is national if unset).
4. **Seasonal defaults override static defaults.** See §3 for the month-by-month default overrides.

#### `VIEW_FILTER_DEFAULTS` (locked)

```typescript
const LATEST_NASS_YEAR = 2024;  // updated when new NASS vintage lands
const CURRENT_YEAR = new Date().getFullYear();

const VIEW_FILTER_DEFAULTS: Record<Tab, FilterDefaults> = {
  overview:       { year: LATEST_NASS_YEAR, commodity: null,   section: null },
  market:         { year: null,             commodity: 'corn', section: null },
  forecasts:      { year: CURRENT_YEAR,     commodity: 'corn', section: 'acreage' },
  crops:          { year: LATEST_NASS_YEAR, commodity: 'corn', section: null },
  'land-economy': { year: LATEST_NASS_YEAR, commodity: null,   section: 'revenue' },
  livestock:      { year: LATEST_NASS_YEAR, commodity: null,   section: 'cattle' },
};
```

Market gets `year: null` because it shows live daily futures — time range is controlled by the range chips (`1M · 6M · 1Y · 5Y · MAX`) in §5.2.B, not the year filter. State is **not** in this map — it is global and persists across tab switches.

### §2.3 · Hover glossary

Every jargon term in the UI gets a dotted underline. Hovering shows a small popover card (no modal) with a one-sentence definition. The glossary is a single JSON map consumed by a `<Term>` component.

#### Glossary component contract

```typescript
// web_app/src/data/glossary.json
type Glossary = Record<string, string>;
// Key: term (lowercase for lookup), Value: one-sentence definition

// <Term> component behavior:
// - Renders children with a dotted underline (1px dashed var(--text3))
// - On hover: shows a popover card (var(--surface), var(--shadow-md), radius-md, max-width 320px)
//   with the definition in Plus Jakarta Sans 13px var(--text2)
// - On touch (mobile): tap opens, second tap or tap-away closes
// - If the term is not in the glossary map: renders as plain text, no underline, no error
// - Popover positioning: prefer below-right, flip if near viewport edge
```

Initial glossary (ship with 20 terms):

| Term | Definition |
|---|---|
| WASDE | USDA's monthly World Agricultural Supply & Demand Estimates report. Drives futures reactions. |
| Stocks-to-use | Ending stocks divided by total use. A tightness gauge — lower values mean more price pressure. |
| Basis | Local cash price minus the nearest futures price. Measures local supply/demand. |
| Bu/acre | Bushels per acre — the standard yield unit for grains. Corn national average is around 180. |
| p10 / p50 / p90 | An 80% confidence range. Actual outcomes fall between p10 and p90 about 80% of the time. |
| MAPE | Mean Absolute Percent Error. How far off a forecast is on average. Lower is better. |
| RRMSE | Relative Root Mean Squared Error. A percent-based error metric for yield forecasts. |
| Marketing year | The 12-month window used to track a crop's supply/demand (corn: Sep–Aug; wheat: Jun–May). |
| Nearby contract | The futures contract closest to delivery — the most liquid and most referenced price. |
| Deferred contract | A futures contract further out in time. Used to understand forward expectations. |
| Backwardation | Nearby prices higher than deferred — signals tight current supply. |
| Contango | Deferred prices higher than nearby — the more common state for grains. |
| DXY | The U.S. Dollar Index. Stronger dollar usually pressures U.S. grain exports. |
| DSCI | Drought Severity & Coverage Index (0–500 scale) from the U.S. Drought Monitor. |
| CCI | Crop Condition Index, derived from NASS weekly Good/Excellent ratings. |
| Prospective Plantings | USDA's March 31 survey-based forecast of what farmers intend to plant. |
| CRP | Conservation Reserve Program — cropland paid to stay idle. Expirations free up land for planting. |
| Production cost per bushel | Total cost of producing one bushel — fertilizer, seed, labor, fuel, land, capital. From USDA ERS. |
| Corn/soy ratio | November soybean futures ÷ December corn futures. Drives planting mix — below 2.2 favors soy. |
| Walk-forward backtest | Training only on data available at the time, re-testing each year, to simulate real forecasting. |

### §2.4 · Citation blocks

Every chart has a one-line citation beneath it in JetBrains Mono 11px, `--text3`:

```
Source: USDA NASS QuickStats · Marketing year 2024 · Updated Apr 2026 · methodology ↗
```

The methodology link opens a **sidebar drawer**, not a new page. Drawer content per chart includes: data source, vintage, computation notes, known caveats.

### §2.5 · Export, permalink, embed

Every chart exposes a three-icon trio on hover (top-right corner of the chart frame):

- **Download** → PNG + CSV (or JSON for table-heavy charts)
- **Permalink** → copies the current URL with filter state to clipboard
- **Embed** → opens a small modal with an `<iframe>` snippet for analysts

Permalink grammar:

```
/{tab}?state={STATE}&commodity={COMMODITY}&year={YEAR}&range={RANGE}&section={SECTION}
```

All fields optional, all tab-interpreted. Missing fields use `VIEW_FILTER_DEFAULTS`.

#### v1 scope (locked)

Ship **Download** (PNG via `html-to-image` + CSV) and **Permalink** (copy URL to clipboard) in v1. **Embed** (`<iframe>` snippet) is deferred — it requires each band to have a standalone route, which is post-v1 work. The embed icon is hidden until then.

### §2.6 · Caption template layer

Every chart renders a one-sentence caption directly under its title, generated at render time from the data. Not hand-written — a small library of templates with named slots.

**Tone policy (locked):** *Push technical insight when the opportunity is there.* Plain English is the floor, not the ceiling. If a chart has a percentile, a z-score, a confidence interval, a regime classification, or a historical ranking, the caption should include it — as long as the technical term is either self-explanatory or covered by the hover glossary (§2.3).

**Layering rule:** a caption should ideally do three things in one sentence:
1. State the plain fact ("Indiana corn yields are up 3% YoY")
2. Anchor it technically ("— in the 78th percentile of the 25-year record")
3. Imply a meaning ("a top-quartile year but below 2017's record")

You don't need all three every time, but aim for two. Don't dumb down.

Example templates:

```
"{state} {commodity} yields have {direction} {pct}% since {start_year} ({percentile}th percentile of the 25-year record)."
"Biggest dip: {anomaly_year} ({delta}%, {narrative}) — {sigma}σ below trend."
"At {price}, margin per {unit} is {margin} — the {superlative} since {year} (10-year range: ${low}–${high})."
"USDA raised {metric} from {old} to {new} ({surprise_pp} pp surprise, {percentile_label})."
"{state}'s {metric} is {delta}% {comparison} the national average, ranking #{rank} of 50."
```

Captions are the single biggest legibility unlock. The data already has the answers — we verbalize them with teeth.

#### Implementation contract (locked)

Captions are **runtime**, not pre-computed. A single `captionTemplates.ts` file exports a `generateCaption(templateId: string, data: Record<string, string | number>)` function. Each chart component calls it with its own data after rendering. Templates are keyed by band ID (e.g., `'overview-hero-sales'`, `'market-price-history'`). The function performs slot interpolation and returns a plain string. No markdown, no HTML — just text rendered in Plus Jakarta Sans 13px `--text2` underneath the chart title.

### §2.7 · Source-of-truth strip (footer)

A thin strip at the bottom of every page in JetBrains Mono 10px, `--text3`:

```
NASS QuickStats: current through 2024 · CME Futures: Apr 14 2026 (live) · WASDE: Mar 11 2026 (next: Apr 11) · Drought Monitor: week of Apr 8 2026
```

One source of truth, visible on every page. Farmers glance at it for freshness. Analysts verify it before citing.

### §2.8 · BETA label policy (locked)

A pill labeled **`EXPERIMENTAL`** is used sparingly and honestly. Three things currently earn it:

1. Corn acreage forecast (§5.3.B) — gate was borderline (+0.02pp over baseline)
2. Wheat_winter acreage forecast (§5.3.B) — first two weeks of release window each year
3. County yield forecast weeks 1–7 (§5.3.C) — wide error bars

**Pill text:** `EXPERIMENTAL`
**Hover tooltip:** `Experimental — see accuracy modal`
**Click behavior:** opens the accuracy modal for the associated forecast (not a scroll — a modal, so users can read the track record without losing their place in the forecast card).
**Styling:** `--surface2` background, `--harvest-dark` text, `--harvest-subtle` border, JetBrains Mono 10px/700, `--radius-full`.

### §2.9 · State management architecture (locked)

URL is the single source of truth for all filter state. No React Context for filters.

#### Rules

1. **URL params** encode the full filter state for any given page view. Every shareable link reproduces the exact view.
2. **`useFilters()` hook** wraps `useSearchParams()` (Next.js App Router). Provides `{ state, year, commodity, section, range }` as typed values, plus setter functions that call `router.push()` with updated params.
3. **Tab switching** calls `router.push('/{tab}?state={currentState}')` — preserving the global state param but resetting commodity/year/section to `VIEW_FILTER_DEFAULTS` for the target tab.
4. **`localStorage`** stores exactly one thing: `fieldpulse_state` — the user's last-picked state code (e.g., `'IN'`). Read on first visit to pre-fill the state filter. Written whenever the user changes state. This is the "remember my state" feature from §5.1.
5. **No server state for filters.** All filter state lives in the URL. The backend receives filter values as query params on each API call.

#### `useFilters()` hook contract

```typescript
interface Filters {
  state: string | null;       // 2-letter code or null (national)
  year: number | null;        // null on Market (uses range instead)
  commodity: string | null;   // 'corn' | 'soybean' | 'wheat' | ... | null
  section: string | null;     // sub-section within a tab
  range: string | null;       // '1M' | '6M' | '1Y' | '5Y' | 'MAX' (Market only)
}

interface UseFiltersReturn {
  filters: Filters;
  setState: (code: string | null) => void;   // updates URL + localStorage
  setYear: (year: number | null) => void;
  setCommodity: (c: string | null) => void;
  setSection: (s: string | null) => void;
  setRange: (r: string) => void;
  switchTab: (tab: Tab) => void;             // navigates + applies VIEW_FILTER_DEFAULTS
}
```

### §2.10 · API surface map (locked)

Three data sources, each with a clear role. The frontend **never** talks to RDS directly.

| Source | Role | Tabs that use it | Latency |
|---|---|---|---|
| **S3 parquet → hyparquet** (browser-side) | 25 years of NASS QuickStats — yield, area, sales, operations, condition, progress, livestock, land use, wages | Overview, Crops, Land & Economy, Livestock | ~200–800ms (parquet download + parse) |
| **Next.js `/api/athena`** | Complex cross-state SQL aggregations, rankings, peer comparisons | Overview story cards, peer comparisons, any query that needs to join across states | ~2–8s (Athena cold start), cached 5 min |
| **FastAPI `/api/v1/predict/*`** | All RDS-backed data: futures, WASDE, DXY, input costs, forecasts, accuracy tables | Market (all bands), Forecasts (all bands) | ~100–500ms |

#### FastAPI endpoint inventory (for frontend consumption)

**Price / Market data** (`/api/v1/predict/price`):
- `GET /` — price forecast (cut in §0.1, do not call)
- `GET /probability` — price probability (cut in §0.1, do not call)
- `GET /wasde-signal?commodity={c}` — latest WASDE balance sheet + surprise direction
- `GET /history?commodity={c}` — historical forecast vs actual (cut, but the endpoint exists)

**Acreage** (`/api/v1/predict/acreage`):
- `GET /?commodity={c}&year={y}&level={national|state}&state_fips={fips}` — single forecast
- `GET /states?commodity={c}&year={y}` — all-states breakdown
- `GET /accuracy?commodity={c}` — walk-forward test results (§5.3.D)
- `GET /price-ratio` — corn/soy ratio + historical percentile + implication

**Yield** (`/api/v1/predict/yield`):
- `GET /?fips={fips}&crop={c}&year={y}` — single county forecast
- `GET /map?crop={c}&week={w}&year={y}` — all-county choropleth data
- `GET /history?fips={fips}&crop={c}` — county forecast history

**Market data endpoints** — all implemented in `backend/routers/market.py` (registered at `/api/v1/market`):

| Endpoint | Method + Path | Params | Response |
|---|---|---|---|
| Futures time series | `GET /api/v1/market/futures` | `commodity`, `start?`, `end?` | `FuturesTimeSeriesResponse` — nearby contract daily settles, up to 2000 points |
| Forward curve | `GET /api/v1/market/curve` | `commodity`, `as_of?` | `ForwardCurveResponse` — next 6 delivery months |
| DXY time series | `GET /api/v1/market/dxy` | `start?`, `end?` | `DxyTimeSeriesResponse` — daily USD index |
| Production costs | `GET /api/v1/market/costs` | `commodity` | `ProductionCostResponse` — latest ERS cost + current futures + margin |
| Fertilizer prices | `GET /api/v1/market/fertilizer` | `limit?` (default 4) | `FertilizerPriceResponse[]` — quarterly ammonia/DAP/potash |

**Yield accuracy endpoint** — added to existing yield router:

| Endpoint | Method + Path | Params | Response |
|---|---|---|---|
| Yield accuracy agg | `GET /api/v1/predict/yield/accuracy` | `crop`, `split?` (default "test") | `YieldAccuracyWeekItem[]` — weekly avg RRMSE + coverage + baseline |

**5-year seasonal price average** — computed client-side from the futures time series (no dedicated endpoint needed). The frontend requests 5 years of data via `/market/futures?start=...` and averages by week-of-year.

All 6 endpoints are implemented and registered. No Wave 3 build dependency remains.

### §2.11 · Responsive breakpoints (locked)

| Token | Width | Target |
|---|---|---|
| `sm` | < 640px | Phone — charts readable, single-column, filter rail collapses to bottom sheet |
| `md` | 640–1024px | Tablet landscape — **primary design target** (farmer-in-cab scenario) |
| `lg` | 1025–1440px | Desktop — full density, side-by-side bands |
| `xl` | > 1440px | Wide monitor — content maxes at 1400px, centered with `--bg` gutters |

#### Layout collapse rules

| Band pattern | `lg`+ | `md` | `sm` |
|---|---|---|---|
| 60/40 split (e.g., §5.1.B map + fingerprint) | Side-by-side | Stacked (map full-width, fingerprint below) | Stacked |
| 3-wide cards (e.g., §5.2.C context row) | 3 columns | 2 + 1 | 1 column |
| 4-wide KPI row (e.g., §5.4.B) | 4 columns | 2 × 2 grid | 2 × 2 grid |
| Sidebar + main (e.g., §5.3.C yield panel) | Side-by-side | Sidebar becomes bottom drawer | Bottom drawer |
| Left section rail (§5.5) | Fixed left rail | Converts to horizontal top tabs | Horizontal top tabs |

#### Filter rail collapse

On `sm` breakpoint: the filter rail (Layer 2 of §2.1) collapses to a single pill labeled "Filters" that opens a bottom sheet with all filter controls. The state pill remains visible in the collapsed bar as a shortcut.

### §2.12 · Loading, error, and empty states (locked)

Every band has three non-data states. A `<BandShell>` wrapper component handles all three and renders children only when data is ready.

#### Loading

Skeleton shimmer matching the band's layout shape. No spinner.

- Background: `--surface2`
- Shimmer: `--muted` highlight sweeping left-to-right, 1.5s ease-in-out infinite
- For KPI cards: rectangular blocks matching Barlow Condensed 48px line height
- For charts: a single shimmering rectangle at the chart's expected height
- For maps: shimmering rectangle with faint state outlines (static SVG underlay)

#### Error

Inline error card within the band — never a full-page error, never a modal.

- Left border: 3px `--negative`
- Background: `--soil-tint`
- Icon: warning triangle in `--negative`
- Text: one sentence describing what failed, Plus Jakarta Sans 14px `--text`
- Action: "Retry" button (`--field` outline style). On click, re-triggers the data fetch for that band only.
- If multiple bands fail simultaneously, each shows its own error independently.

#### Empty

Muted placeholder text centered in the band area.

- Text: Plus Jakarta Sans 14px `--text3`, centered
- Pattern: "No {data type} available for {state} in {year}."
- If a filter change could fix it: append "Try selecting a different state or year."
- If data is structurally absent (e.g., no livestock data for a crop-only state): "Livestock data is not reported for {state}."

### §2.13 · Theme toggle (locked)

- **Default: light.** The design system is light-first. A farmer checks this on a tablet in bright sunlight.
- **Toggle:** sun/moon icon in the header far-right (§2.1), 44px touch target. No label.
- **Mechanism:** `data-theme="dark"` attribute on `<html>`. Toggled via a `useTheme()` hook that reads/writes `localStorage` key `fieldpulse_theme` (`'light'` | `'dark'`).
- **System preference:** on first visit with no localStorage value, respect `prefers-color-scheme`. After the user clicks the toggle, their explicit choice overrides system preference permanently.
- **Token wiring:** all components use CSS custom properties exclusively. Dark mode overrides are defined in the design system CSS under `[data-theme='dark']`. No component-level dark mode logic.
- **Dark mode tokens** (from `design-system-v1.html`):

```css
[data-theme='dark'] {
  --bg:        #141413;
  --surface:   #1C1C19;
  --surface2:  #252520;
  --border:    rgba(255, 255, 255, 0.08);
  --border2:   rgba(255, 255, 255, 0.14);
  --text:      #F0EDE8;
  --text2:     #A8A296;
  --text3:     #6B6560;
  --muted:     #3D3A34;
  --field:     #52B788;
  --field-light: #6BC99D;
  --field-dark:  #40916C;
  --field-subtle: rgba(82, 183, 136, 0.10);
  --field-tint:  rgba(82, 183, 136, 0.08);
  --harvest:     #D4A017;
  --harvest-light: #E0B630;
  --harvest-dark:  #B8860B;
  --harvest-subtle: rgba(212, 160, 23, 0.10);
  --harvest-tint:  rgba(212, 160, 23, 0.08);
  --positive:  #52B788;
  --negative:  #E05A4F;
  --warning:   #D4A017;
  --info:      #5BA3D9;
}
```

---

## §3 · Seasonal behavior model

Agriculture is cyclical. The UI should reflect what matters *right now*. A single function `getAgSeason(date)` returns one of six phases. Every component can subscribe and promote/demote its own content.

### §3.1 · Season phases

| Phase | Months | What matters |
|---|---|---|
| `pre-plant` | Jan–Feb | Planting intentions, acreage decisions, input costs, price ratios |
| `planting` | Mar–Apr | USDA Prospective Plantings (Mar 31), planting progress, acreage finalization |
| `early-growth` | May–Jun | Emergence, planting completion, early crop condition, drought monitoring |
| `mid-season` | Jul–Aug | Crop condition, yield forecasts gaining confidence, weather stress |
| `harvest` | Sep–Oct | Harvest progress, final yield forecasts, market selling decisions |
| `post-harvest` | Nov–Dec | Year recaps, revenue outcomes, carryover stocks, next year planning |

#### `getAgSeason()` implementation contract (locked)

```typescript
type AgSeason = 'pre-plant' | 'planting' | 'early-growth' | 'mid-season' | 'harvest' | 'post-harvest';

// Pure function, no side effects. Month is 0-indexed (JS Date convention).
function getAgSeason(date: Date = new Date()): AgSeason {
  const month = date.getMonth();
  if (month <= 1) return 'pre-plant';      // Jan–Feb
  if (month <= 3) return 'planting';        // Mar–Apr
  if (month <= 5) return 'early-growth';    // May–Jun
  if (month <= 7) return 'mid-season';      // Jul–Aug
  if (month <= 9) return 'harvest';         // Sep–Oct
  return 'post-harvest';                    // Nov–Dec
}
```

#### `useAgSeason()` hook contract

```typescript
interface SeasonOverrides {
  overviewHeroMetric: string;
  marketDefaultCommodity: string;
  forecastsFeaturedBand: string;
  overviewRotatingCard: string;
}

interface UseAgSeasonReturn {
  season: AgSeason;
  month: number;                    // 0-indexed current month
  overrides: SeasonOverrides;       // current month's row from §3.2 table
}

// Re-evaluates once per day (memoized on date string, not per-render).
// Components call useAgSeason() directly — no Context provider needed
// since the value changes at most once per day.
```

#### Seasonal visibility mechanism

The `<BandShell>` wrapper (§2.12) accepts an optional `visibleSeasons` prop:

```typescript
interface BandShellProps {
  // ... loading/error/empty props from §2.12
  visibleSeasons?: AgSeason[];     // if set, band renders only during these seasons
  dormantMessage?: string;         // shown outside visible seasons, e.g. "Yield forecasts return May 19"
  dormantSummary?: React.ReactNode; // compact summary of last completed cycle (§3.3 rule)
}
```

When the current season is outside `visibleSeasons`, BandShell renders the `dormantSummary` (if provided) plus the `dormantMessage` in `--text3`. A dormant band is never empty — it always shows the most recent completed cycle summary plus a "returns {month}" marker.

### §3.2 · Seasonal default overrides

| Month | Overview hero metric | Market default commodity | Forecasts featured band | Overview rotating story card |
|---|---|---|---|---|
| Jan | 5yr revenue growth | corn | Acreage — coming soon | "Last year's revenue recap" |
| Feb | Total sales | corn | Acreage — live | "What USDA will say March 31" |
| Mar | Total sales | corn | Acreage — live | "USDA Prospective Plantings" |
| Apr | Total sales | corn | Acreage — final | "Planting kicks off" |
| May | Area planted | corn | Yield — live, low confidence | "Emergence watch" |
| Jun | Area planted | corn | Yield — live, medium confidence | "Condition check" |
| Jul | Crop condition % G/E | corn | Yield — live, medium confidence | "Condition check" |
| Aug | Crop condition % G/E | soy | Yield — live, high confidence | "Pro Farmer tour" |
| Sep | Harvest progress % | soy | Yield — live, high confidence | "Harvest progress" |
| Oct | Harvest progress % | corn | Yield — live, high confidence | "Harvest progress" |
| Nov | Total sales | corn | Dormant | "Revenue recap" |
| Dec | Total sales | corn | Dormant | "Year in review" |

### §3.3 · Seasonal visibility toggles

Some bands are hidden outside their phase. Implemented via `<BandShell visibleSeasons={[...]}>`  (§3.1).

| Band | `visibleSeasons` | Dormant behavior |
|---|---|---|
| Crop progress / condition (§5.4.E) | `['early-growth', 'mid-season', 'harvest']` | "Crop conditions return May" + last season's final G/E % |
| Yield forecast panel (§5.3.C) | `['early-growth', 'mid-season', 'harvest']` | "Yield forecasts return May 19" + last season's final county yield |
| Acreage forecast panel (§5.3.B) | `['pre-plant', 'planting']` live; all other seasons show "final" | Outside planting: locked to most recent forecast with "Final for {year}" badge |
| Planting-intentions story card (§5.1.C rotating) | `['pre-plant', 'planting']` | Replaced by the seasonal rotating card from §3.2 |

A dormant band is never empty — it renders a compact summary of the most recent completed cycle plus a visible "returns {month}" marker.

---

## §4 · Narrative formation mechanisms

The backend analysis flags that we have the ingredients for great stories but nothing ties them together. Four mechanisms close that gap.

### §4.1 · Auto-captions under every chart

See §2.6. Every chart reads itself to the user in one sentence.

### §4.2 · Story cards on Overview

Pre-computed narratives that deep-link into filtered views. Each card is a single SQL query over the existing data. Ship list:

1. **"The Corn Belt's shifting geography"** — state-level acres change 2001 → 2024
2. **"Where labor got expensive fastest"** — state wage growth % leaderboard
3. **"Farmland winners & losers"** — urban sprawl vs cropland change scatter (teaser)
4. **"Crops that disappeared"** — steepest operations decline since 2001
5. **"The 5 states doing more with less"** — yield up, area down, revenue up

Plus a rotating seasonal 4th card driven by §3.2.

### §4.3 · Cross-tab breadcrumb narratives

Clicks carry context. Examples:

- Click a 2012 drought anomaly marker on Crops → opens a focused overlay pulling WASDE + DSCI + crop progress data from 2012
- Click the corn/soy ratio dial on Market → scrolls to the Acreage section of Forecasts
- Click "margin is thin" caption on Market input cost card → deep-links to Forecasts (showing how farmers are reacting)
- Click a county on the yield forecast choropleth → opens that county's 25-year history on Crops

These micro-narratives stitch the product into one story instead of six dashboards.

### §4.4 · Track-record-next-to-forecast

No forecast is ever displayed without its accuracy record within scrolling distance. This is a narrative, not a disclaimer. "Here is what we predict, here is what we got right and wrong last year, decide for yourself." See §5.3.D for the accuracy panel.

---

## §5 · Per-page specs

Template per page: **Purpose → Hero question → Bands → Data sources → Cross-page flows → Open items**.

---

### §5.1 · Overview

**Purpose.** Entry point, orientation, story hub. Default landing page.

**Hero question.** *"Where does my state stand in U.S. ag right now?"*

**Default state (locked).** National aggregate on first visit. A prominent non-dismissable-but-non-blocking "Pick your state" affordance sits top-right of Band A (Barlow 16px pill with `--field-subtle` background). Once a state is picked, the choice is persisted in `localStorage` and restored on subsequent visits — the prompt hides. Users can always reset to national from the filter rail.

#### §5.1.A · Band A — Hero strip (full width, ~220px tall)

Three hero KPIs in Barlow Condensed 48px, each with a one-sentence plain-English caption underneath.

| KPI | Source | Caption example |
|---|---|---|
| **[State name]** · $X.X B total farm cash receipts, YYYY | NASS sales $ aggregated | "Indiana ranks #9 by total farm sales, up 18% since 2015." |
| **X.X M acres planted** across N commodities | NASS area planted sum | "Down 380K acres from 2020 — driven mostly by reduced winter wheat." |
| **Top crop: Corn, $X.X B** | NASS ranked by sales | "Corn has been Indiana's #1 crop every year in our 25-year record." |

Bottom of band: source citation line per §2.4.

#### §5.1.B · Band B — Map + State fingerprint (split 60/40)

**Left 60% — US choropleth.** Built on existing Deck.gl + MapLibre GL stack with the warm→green gradient (`--map-1` through `--map-10`).

- Default metric: total farm sales $ per state, latest year
- Metric toggle chips above map: `Sales $` · `Yield (top crop)` · `Operations count` · `Avg wage` · `5yr growth %`
- Hover card: state name (Barlow 20px), metric value, YoY delta, rank
- **Click behavior:** sets the global state filter. Does not navigate away. The rest of the Overview page re-renders for that state. The map is a filter, not a nav.
- Legend: horizontal gradient bar bottom-left with min/max annotations (e.g. `$0.8B ← → $62.3B`)

**Right 40% — State fingerprint card stack.**

1. **Revenue mix donut** — top 6 crops + "all others" by $ value, colored with commodity chart palette. Center shows total. Caption: "Corn and soybeans drive 71% of Indiana's ag revenue."
2. **Planted area sparkline strip** — 5 sparklines, one per top commodity, 25 years, no axes, Barlow end value, delta badge. Ultra-compact.
3. **Peer comparison bar** — selected state vs 4 peer states (auto-picked by output-value proximity) on a single metric (default: yield of top crop). Horizontal bars. Caption: "Indiana's corn yield is 4% below Iowa but 11% above Ohio."

#### §5.1.C · Band C — Story cards (3 wide + 1 rotating)

Pre-computed narratives per §4.2. Each card: Barlow headline number, one-sentence hook, `→ Explore` link that deep-links with filters.

Base three (always visible):

1. "Where labor got expensive fastest" → Land & Economy, Labor section
2. "Farmland winners & losers" → Land & Economy, Land use section
3. "Crops that disappeared" → Crops tab, preset commodity

Fourth card rotates by season per §3.2.

#### §5.1 · Data sources

- `quickstats_data` parquet: sales $, area planted, operations, wage
- Pre-computed state rollups (national table or derived in-client)
- `web_app/src/data/peerStates.json` — static peer state lookup (see below)
- `web_app/public/stories.json` — pre-computed story cards (see below)

#### §5.1 · Cross-page flows

- Map click → sets global state filter, no navigation
- Story card click → navigates to target tab with filter state encoded in URL
- KPI click (hero band) → nothing (hero is informational only — they already drive filters)

#### §5.1 · Resolved decisions

**Peer states — LOCKED: static lookup.** `web_app/src/data/peerStates.json` maps each state code to its 4 nearest peers by total farm cash receipts. Pre-computed from the latest NASS vintage. Recomputed annually when new data lands. Shape:

```typescript
// peerStates.json
type PeerStates = Record<string, string[]>;
// e.g. { "IN": ["OH", "IL", "MO", "WI"], "CA": ["TX", "IA", "NE", "MN"], ... }
```

**Story card refresh — LOCKED: on each NASS release.** A pipeline script computes the 5 base stories + 1 seasonal rotating card, writes `web_app/public/stories.json`. Runs as part of the monthly cron (15th). Frontend fetches this static JSON — no runtime SQL for story cards. Shape:

```typescript
interface StoryCard {
  id: string;                      // e.g. 'shifting-geography'
  headline: string;                // Barlow number/phrase
  hook: string;                    // one-sentence hook
  targetTab: Tab;                  // deep-link destination
  targetFilters: Partial<Filters>; // pre-applied filters on click
  seasonal: boolean;               // true = only visible per §3.2
  visibleSeasons?: AgSeason[];     // if seasonal, when to show
}

// stories.json is an array of 5–6 StoryCard objects
```

**Map hover card — LOCKED: text only.** Hover card shows: state name (Barlow 20px), metric value (JetBrains Mono 16px), YoY delta chip, rank (e.g., "#9 of 50"). No sparklines — too small to convey meaningful information at hover-card scale.

#### §5.1 · Data contracts per band

**Band A — Hero strip:**
```typescript
// Source: S3 parquet, state-level rollup
interface OverviewHeroData {
  stateName: string;
  totalSales: number;            // $ total farm cash receipts, latest year
  totalSalesYear: number;
  salesRank: number;             // rank among 50 states
  salesGrowthPct: number;        // vs 5 years ago
  totalAcresPlanted: number;
  commodityCount: number;        // distinct commodities with >0 acres
  acresDelta: number;            // vs prior year
  acresDeltaDriver: string;      // commodity driving the biggest change
  topCrop: string;               // commodity with highest sales $
  topCropSales: number;
  topCropStreak: number;         // consecutive years as #1 (for caption)
}
```

**Band B — Map (left 60%):**
```typescript
// Source: S3 parquet, all-states rollup for the selected metric
interface MapDataPoint {
  stateCode: string;             // 2-letter
  stateName: string;
  value: number;                 // metric value
  yoyDelta: number;              // % change vs prior year
  rank: number;
}
// Metric toggled by chips: 'sales' | 'yield' | 'operations' | 'wage' | 'growth5yr'
```

**Band B — State fingerprint (right 40%):**
```typescript
// Source: S3 parquet, single-state filtered
interface StateFingerprint {
  revenueMix: { commodity: string; sales: number; color: string }[];  // top 6 + "Other"
  totalRevenue: number;
  sparklines: { commodity: string; years: number[]; values: number[] }[];  // top 5, 25 years
  peerComparison: {
    state: string;
    value: number;
  }[];  // selected state + 4 peers from peerStates.json, single metric
  peerMetric: string;
  peerUnit: string;
}
```

**Band C — Story cards:**
```typescript
// Source: web_app/public/stories.json (static, pre-computed)
// Shape: StoryCard[] as defined above
```

---

### §5.2 · Market

**Purpose.** Replaces the killed Price Forecast tab with 100% honest market data. Futures + supply/demand context + input costs.

**Hero question.** *"What is the price of my crop doing, and why?"*

#### §5.2.A · Band A — Commodity selector & hero quote (~180px)

- Commodity segmented control (corn / soy / wheat), sticky under the filter rail. Active commodity takes its chart palette color.
- Hero block:
  - **Barlow 64px harvest-gold**: current settle price, e.g. `$4.71` with subscript `/bu CBOT May 2026`
  - Delta chip row: `▲ 0.8% today · ▼ 2.1% 1w · ▲ 6.3% 1mo · ▼ 4.0% YTD`. Positive chips use `--field`, negative use `--negative`.
  - Right of hero: unlabeled mini-sparkline of last 90 days of daily settle, Barlow end-value label
  - Bottom caption: "Nearby contract: May 2026. Next WASDE: April 11. Last settle: Apr 14 4:00 PM CT."

No forecast. Not a single p10/p90. Just the market.

#### §5.2.B · Band B — Price history chart (full width, ~380px)

- X axis: daily, zoomable. Y axis: $/bu (left), volume optional (right, toggle).
- Primary line: daily settle for the selected commodity, colored with the commodity chart palette.
- Range chips above chart: `1M · 6M · 1Y · 5Y · MAX (2000→now)`
- Overlay toggles (stacked pills, max 3 active at once):
  - **WASDE release markers** — vertical ticks on release dates; click opens the WASDE card below
  - **5-year seasonal average** — dashed gray line at the seasonal mean price for each week of year
  - **Previous marketing year** — thin `--harvest-light` overlay
  - **Deferred contract curve** — shaded area showing forward-curve settles across delivery months
- Caption: "Corn futures are 6% above their 5-year average for mid-April. The last WASDE (March 11) was neutral on U.S. stocks."
- **Term structure strip** below the chart: horizontal bars for each delivery month from nearby → 12 months out, with settle price labeled. Visualizes backwardation/contango without explaining the words.

#### §5.2.C · Band C — Supply/demand context row (3 cards, each ~320px tall)

Three equal-width cards. Each has a one-sentence caption and a source badge.

##### §5.2.C.1 — WASDE balance sheet card

- Header: "Latest WASDE · March 11, 2026" in Plus Jakarta 16/700
- Three stacked stat rows: `Ending stocks`, `Stocks-to-use`, `World supply`. Each row shows:
  - Value (mono, large)
  - Mini delta vs prior release
  - Percentile bar showing the 10-year range with a marker for the current value
- Direction pill at bottom: **Supportive / Pressuring / Neutral** (we avoid Bloomberg's "bullish/bearish" vocabulary). Colored with `--positive` / `--negative` / `--text2`. Computed from percentile position + surprise sign.
- Caption: "USDA raised 2025/26 corn stocks-to-use from 10.2% to 10.8% — a pressuring shift for price."

##### §5.2.C.2 — Corn/Soy ratio dial (conditional)

Visible only when commodity is corn or soy.

- Barlow 48px value, e.g. `2.41`
- Horizontal gauge underneath showing the 10-year range of the ratio at April with:
  - Color zones: `<2.2` = "soy favored" (`--soil`), `2.2–2.5` = "balanced" (`--text3`), `>2.5` = "corn favored" (`--harvest`)
  - A prominent marker for today's value
- Caption: "At 2.41 the ratio is in the balanced zone. Historically ratios below 2.2 have shifted 2–4M acres to soybeans."
- This is the farmer-decision dial surfaced as a first-class element, per the backend analysis §3.

##### §5.2.C.3 — Input cost card

- Three rows: Anhydrous ammonia $/ton · DAP $/ton · Diesel $/gal. Each with value + quarterly trend arrow.
- **Top metric in Barlow 32px**: production cost per bushel, e.g. `$4.12/bu`. This is the headline analysts miss.
- Caption: "Corn production cost is $4.12/bu. At today's $4.71 futures price, margin per bushel is $0.59 — the thinnest since 2016."
- This card does the profit margin math the backend analysis flags as the biggest missed opportunity. We don't need a price forecast to tell someone their margins are thin — futures + ERS cost does it with total transparency.

#### §5.2.D · Band D — Basis tracker (collapsed by default)

State-level basis (local cash − nearest futures) where we have data. Per §7, local cash ingestion is deferred to Wave 3.5 — until then this band shows:

> *"Basis data coming. We're ingesting USDA AMS local cash reports next."*

When active:
- Line chart, 3-year history, per-state dropdown
- Caption: "Indiana corn basis is −$0.28, typical for April."

#### §5.2.E · Band E — Macro context strip (thin, ~120px)

- DXY 1-year line chart
- Text callout: "The dollar has strengthened 4% in 3 months — historically a headwind for U.S. grain exports."

This is as far as we go with macro. No interest rates, no inflation, no oil.

#### §5.2 · Data sources

- `futures_daily` — primary price line, forward curve, term structure
- `wasde_releases` — Band C.1 and overlay markers on Band B
- `ers_production_costs` + `ers_fertilizer_prices` — Band C.3
- `dxy_daily` — Band E
- Static 5-year seasonal averages — computed once, cached in client

#### §5.2 · Cross-page flows

- Click WASDE marker on Band B → expands Band C.1 with full balance sheet
- Click commodity name in any caption → scrolls or re-filters internally (same tab)
- Click "margin is thin" caption on Band C.3 → Forecasts tab acreage section (to show how planting reacts)
- Click the corn/soy ratio → Forecasts tab acreage section with ratio highlighted

#### §5.2 · Resolved decisions

**WASDE vocabulary — LOCKED: both.** Primary label uses plain English (`Supportive` / `Pressuring` / `Neutral`). Hover tooltip shows the industry equivalent (`Bullish` / `Bearish` / `Neutral`) so analysts can match vocabulary to their Bloomberg/Reuters sources. Revisit after user feedback — if farmers find the plain-English terms confusing in context, swap to industry terms with plain-English tooltips.

**WASDE percentile window — LOCKED: rolling 10-year.** The percentile bar in §5.2.C.1 compares today's stocks-to-use against the most recent 10 years of WASDE releases. Rolling ensures the benchmark stays relevant as market regimes shift.

**Forward curve — LOCKED: next 6 delivery months.** The term structure strip in §5.2.B shows 6 delivery months forward from nearby. Covers a full marketing year without cluttering the visualization.

**Delta chip windows — LOCKED: 1D / 1W / 1M / YTD.** Four chips in the hero block (§5.2.A). These are the four windows a farmer or analyst checks daily. Longer windows are served by the price history chart with its range chips.

**Basis tracker — LOCKED: deferred to Wave 3.5.** Per §7.3. Band D ships as a stub with: "Basis data coming — we're ingesting USDA AMS local cash reports. Expected: summer 2026." Start forward-only ingest in parallel with Wave 3 build.

#### §5.2 · Data contracts per band

**Band A — Hero quote:**
```typescript
// Source: FastAPI GET /api/v1/market/futures (new endpoint, Wave 3 dependency)
interface MarketHeroData {
  commodity: string;
  nearbyContract: string;         // e.g. "May 2026"
  settlePrice: number;            // $/bu
  settleDate: string;             // ISO date of last settle
  settleTime: string;             // e.g. "4:00 PM CT"
  delta1d: number;                // % change
  delta1w: number;
  delta1m: number;
  deltaYtd: number;
  sparkline90d: { date: string; price: number }[];  // last 90 daily settles
  nextWasdeDate: string;          // ISO date of next WASDE release
}
```

**Band B — Price history chart:**
```typescript
// Source: FastAPI GET /api/v1/market/futures?commodity={c}&start={date}&end={date}
interface FuturesTimeSeries {
  date: string;                   // ISO date
  settle: number;                 // $/bu, nearby contract
  volume?: number;                // optional toggle
}

// Overlay: 5-year seasonal average (computed client-side from full time series)
// Overlay: WASDE markers from GET /api/v1/predict/price/wasde-signal
// Overlay: forward curve from GET /api/v1/market/curve?commodity={c}

interface ForwardCurvePoint {
  contractMonth: string;          // e.g. "Jul 2026"
  settle: number;                 // $/bu
}
// 6 points for the term structure strip
```

**Band C.1 — WASDE balance sheet card:**
```typescript
// Source: FastAPI GET /api/v1/predict/price/wasde-signal?commodity={c}
// Response shape already defined in §2.10 endpoint inventory.
// Additional fields needed for the card UI:
interface WasdeCardData {
  releaseDate: string;
  endingStocks: number;
  stocksToUse: number;
  stocksToUsePctile: number;      // 0–100, rolling 10-year
  priorMonthStu: number | null;
  stuDelta: number | null;        // change from prior
  worldSupply: number | null;
  surpriseDirection: 'supportive' | 'pressuring' | 'neutral';
  surpriseDirectionIndustry: 'bullish' | 'bearish' | 'neutral';  // for tooltip
}
```

**Band C.2 — Corn/Soy ratio dial:**
```typescript
// Source: FastAPI GET /api/v1/predict/acreage/price-ratio
// Response shape already defined. UI needs:
interface RatioDialData {
  ratio: number;                  // e.g. 2.41
  tenYearMin: number;             // for gauge range
  tenYearMax: number;
  percentile: number;             // 0–100
  zone: 'soy_favored' | 'balanced' | 'corn_favored';  // <2.2 / 2.2–2.5 / >2.5
  asOfDate: string;
}
```

**Band C.3 — Input cost card:**
```typescript
// Source: FastAPI GET /api/v1/market/costs?commodity={c} (new endpoint)
//       + FastAPI GET /api/v1/market/fertilizer (new endpoint)
interface InputCostData {
  commodity: string;
  productionCostPerBu: number;    // headline metric
  currentFuturesPrice: number;    // for margin calc
  marginPerBu: number;            // futures - cost
  marginContext: string;          // e.g. "thinnest since 2016"
  fertilizer: {
    anhydrousAmmonia: { price: number; unit: string; qoqTrend: 'up' | 'down' | 'flat' };
    dap: { price: number; unit: string; qoqTrend: 'up' | 'down' | 'flat' };
    potash: { price: number; unit: string; qoqTrend: 'up' | 'down' | 'flat' };
  };
}
```

**Band D — Basis tracker (Wave 3.5 stub):**
```typescript
// No data contract yet. Renders stub message only.
```

**Band E — Macro context (DXY):**
```typescript
// Source: FastAPI GET /api/v1/market/dxy?start={date}&end={date} (new endpoint)
interface DxyTimeSeries {
  date: string;
  value: number;                  // DXY index value
}
// 1-year of daily values. Caption computes 3-month change client-side.
```

---

### §5.3 · Forecasts

**Purpose.** The product's differentiated moat. Also the highest-risk tab, so every forecast sits next to its track record.

**Hero question.** *"What will be planted, and what will my county yield?"*

#### §5.3.A · Band A — Season clock (~140px)

A horizontal 12-month strip showing the ag calendar with the current month highlighted. Two rails overlaid:

- **Acreage forecast rail** — active Feb 1 → Mar 31. Green when live, `--surface2` when dormant.
- **Yield forecast rail** — active May 19 → Oct 31 (per crop). Color-coded by confidence tier (pink / amber / green).
- **USDA release markers** — Prospective Plantings (Mar 31), WASDE (12th monthly), Final Crop Production (Jan 12)

Caption: "Today is April 14. Acreage forecasts are finalized. Yield forecasts begin May 19 for corn and soy."

This is the seasonal-awareness principle made literal.

#### §5.3.B · Band B — Acreage forecast panel

Three stacked commodity cards (corn, soybean, wheat_winter). Wheat spring is hidden — a single footnote reads: "Wheat spring forecasts require more training data (5-state sample insufficient)."

Per commodity card structure (same template so they're directly comparable):

1. **Header** — commodity name + chart-palette dot, e.g. `CORN` in Barlow 22px
2. **Barlow 56px** — national forecast acres, e.g. `87.9M acres`
3. **YoY delta chip** — e.g. `▼ 2.1M vs 2025`
4. **p10–p90 interval bar** — horizontal range with a tick at p50. Label: "80% interval: 85.3–90.6M"
5. **Key driver sentence** — SHAP-style, pulled from the model's top feature: "The biggest driver: 2025 corn/soy ratio at planting (2.38 — mild soy tilt)."
6. **USDA comparison strip** — "USDA Prospective Plantings (Mar 31): 95.3M. Our forecast is 7.8% below." Signed delta colored.
7. **Top 5 state breakdown** — horizontal bar list: IL 11.2M, IA 13.5M, IN 5.4M, NE 9.7M, MN 8.3M. Each with a delta chip.
8. **Track record row** — "Test MAPE: 6.26% · 5yr-avg baseline: 6.24% · Δ +0.02pp". Add `BETA` pill if gate is tight.
9. **Citation row** — "Model trained 2026-04-11 · 24 features · state-panel walk-forward · NASS + CME + ERS + USDM + RMA + FSA + FAS"

#### §5.3.C · Band C — County yield forecast panel

Only surfaces `early-growth` through `harvest` per §3.3. Outside those months, a dormant summary card shows the most recent completed season and a "returns May 19" marker.

When active:

1. **Crop sub-tabs** — Corn · Soybean. Wheat hidden.
2. **Week slider** — weeks 1 → 20, with confidence-tier coloring under the track (pink → amber → green). Current week marked.
3. **Main view** — real Deck.gl `GeoJsonLayer` county choropleth (not the state simplification). Metric: forecasted yield p50, bu/acre. Warm→green gradient. Hover card: county name, p10/p50/p90, confidence tier, vs 5-year county average.
4. **Sidebar (right, 360px)** — selected-county detail stack:
   - Barlow 48px yield forecast (p50)
   - Small p10–p90 range bar
   - Confidence tier pill, e.g. `MEDIUM CONFIDENCE · RRMSE ±17% this week · directional only`
   - Sparkline of week-over-week forecast evolution this season
   - Caption: "Tippecanoe County corn yield forecast is 198 bu/acre — above the 5-year county average of 191."

#### §5.3.D · Band D — Season-by-season accuracy panel (collapsible, default open)

This is the trust-builder. Two side-by-side small multiples:

- **Acreage accuracy chart** — line chart of test MAPE by year 2020–2025, per commodity, with 5yr-avg baseline overlaid
- **Yield accuracy chart** — small multiples by crop, showing weekly RRMSE evolution across the season, with county-mean baseline shown as a second band

Caption: "Our acreage model beats the 5-year average baseline for soybeans every year since 2020. Corn is a coin flip — use with caution."

Without this panel, the whole tab is theater. With it, analysts can cite us.

#### §5.3 · Data sources

- `acreage_forecasts` — Band B current values
- `acreage_accuracy` — Band D acreage chart (**note:** currently unpopulated per backend analysis; populating this is a build blocker for Forecasts)
- `yield_forecasts` — Band C current values
- Yield accuracy table — equivalent of acreage_accuracy; needs to exist
- `artifacts/acreage/{commodity}/metrics.json` — training-time metrics for track record
- `artifacts/yield/{crop}/week_{week}/metrics.json` — per-week training metrics

#### §5.3 · Cross-page flows

- Click a county on the yield choropleth → opens that county's 25-year history on Crops tab, commodity preserved
- Click "USDA comparison" link on a commodity card → modal with side-by-side private-firm comparison (Reuters / Bloomberg / Farm Futures / AgMarket.Net), per backend analysis §5
- Click the "ratio 2.38" highlighted phrase → Market tab Band C corn/soy ratio dial
- Click `EXPERIMENTAL` pill → opens accuracy modal (§2.8), not scroll to Band D

#### §5.3 · Resolved decisions

**Accuracy tables — LOCKED: both deployed.** `acreage_accuracy` (796 rows) and `yield_accuracy` (290,441 rows) populated on prod RDS as of 2026-04-15. See §7.4 for full deployment log. No longer a blocker.

**Default county — LOCKED: no pre-selected county.** On first visit, the yield choropleth shows all counties colored by p50 yield with no county selected. The sidebar shows national/state aggregate stats. County selection activates only when the user clicks the map. If a state is selected, the map zooms to that state's bounds. If no state is selected, the map shows the full U.S. at county resolution.

**Static-data backfill status — LOCKED: methodology drawer only.** Model coverage info ("2,834 of 3,109 ag counties have soil data") lives inside the methodology drawer opened by the "methodology ↗" link in the citation block (§2.4). No prominent warning on the main forecast surface — technical coverage gaps don't warrant undermining user confidence when the model already handles missing soil data gracefully (falls back to state-average AWC).

#### §5.3 · Data contracts per band

**Band A — Season clock:**
```typescript
// No API call. Computed from getAgSeason() + static calendar data.
interface SeasonClockData {
  currentMonth: number;             // 0-indexed
  season: AgSeason;
  acreageRail: {
    startMonth: 1;                  // Feb (0-indexed)
    endMonth: 3;                    // Apr
    status: 'live' | 'finalized' | 'dormant';
  };
  yieldRail: {
    startMonth: 4;                  // May
    endMonth: 9;                    // Oct
    status: 'live' | 'dormant';
    confidenceTier: 'low' | 'medium' | 'high' | null;
  };
  usdaMarkers: {
    label: string;                  // e.g. "Prospective Plantings"
    month: number;
    day: number;
  }[];
}
```

**Band B — Acreage forecast panel (per commodity card):**
```typescript
// Source: FastAPI GET /api/v1/predict/acreage/?commodity={c}&level=national
//       + GET /api/v1/predict/acreage/states?commodity={c}
//       + GET /api/v1/predict/acreage/price-ratio
//       + artifacts/{commodity}/metrics.json (for track record row)
interface AcreageCardData {
  commodity: string;
  forecastAcres: number;           // national p50, millions
  p10: number;
  p90: number;
  yoyDelta: number;                // vs prior year, millions
  yoyDeltaPct: number;
  keyDriver: string | null;        // SHAP top feature, human-readable
  usdaProspective: number | null;  // USDA Mar 31 value, millions
  usdaDeltaPct: number | null;     // model vs USDA
  topStates: {
    stateFips: string;
    stateName: string;
    forecastAcres: number;
    deltaPct: number | null;
  }[];                             // top 5 by forecast acres
  testMape: number;                // from metrics.json
  baselineMape: number;            // 5yr-avg baseline
  deltaVsBaseline: number;         // pp difference
  isExperimental: boolean;         // true if gate was borderline
  modelTrainDate: string;          // ISO date
  featureCount: number;
  citationSources: string;         // e.g. "NASS + CME + ERS + USDM + RMA + FSA + FAS"
}
```

**Band C — County yield forecast panel:**
```typescript
// Source: FastAPI GET /api/v1/predict/yield/map?crop={c}&week={w}
//       + GET /api/v1/predict/yield/?fips={f}&crop={c} (on county click)
// Map data shape: YieldMapResponse (already defined in §2.10)
// County detail shape: YieldForecastResponse (already defined in §2.10)

// Additional: week-over-week evolution for the sidebar sparkline
interface WeekEvolution {
  week: number;
  p50: number;
}
// Source: multiple calls to GET /api/v1/predict/yield/?fips={f}&crop={c}
// with varying week param, or a batch endpoint (TBD — may be client-side cached)
```

**Band D — Accuracy panel:**
```typescript
// Acreage accuracy chart:
// Source: FastAPI GET /api/v1/predict/acreage/accuracy?commodity={c}
// Response: AcreageAccuracyItem[] (already defined in §2.10)
// Chart: line of model_vs_actual_pct by forecast_year, per commodity
//        + 5yr-avg baseline overlaid as dashed horizontal line

// Yield accuracy chart:
// Source: direct SQL or new endpoint (TBD — may need new FastAPI route)
interface YieldAccuracyWeek {
  crop: string;
  week: number;
  avgRrmse: number;               // AVG(pct_error) across counties for that week
  avgCoverage: number;            // AVG(in_interval) — fraction within p10–p90
  baselineRrmse: number;          // county 5yr mean baseline
}
// Small multiples: one per crop, x=week (1–20), y=RRMSE, with baseline band
```

---

### §5.4 · Crops

**Purpose.** 25-year deep history of a single commodity. Our strongest tab by a wide margin — the backend analysis says so and it's right.

**Hero question.** *"How has this commodity actually performed over 25 years?"*

#### §5.4.A · Band A — Commodity picker (top rail)

Pill selector: Corn · Soybeans · Wheat · Cotton · Hay · Rice · Sorghum · Barley · Oats · Peanuts · Tobacco. One commodity at a time. Selected pill takes the commodity's chart-palette color. Single-select, touch-friendly.

#### §5.4.B · Band B — Hero KPI row (4 cards)

Each card in `--surface`, Barlow 36px number, one-sentence plain-English caption.

| KPI | Caption example |
|---|---|
| **Yield this year** (state value, delta vs 5yr avg, state rank) | "181 bu/acre — Indiana's 3rd-best on record." |
| **Area planted** (acres, YoY delta) | "5.4M acres — down 2% from last year." |
| **Operations count** (farms growing this commodity) | "48,300 operations — down 12% since 2010." |
| **Total sales** ($B, YoY, share of state ag revenue) | "$4.8B, 38% of Indiana's total farm sales." |

#### §5.4.C · Band C — Yield trend chart with anomaly flags (full width, ~420px)

- Line chart, 25 years, state line + national line (dashed)
- **Anomaly years circled and labeled** — this is the existing feature, promoted to the centerpiece
- Each anomaly has a small popover with pre-computed context: "2012: Midwest drought, DSCI peaked at 410 in July, national yield −29%"
- Caption: "Indiana corn yields have grown 32% since 2001. Biggest dip: 2012 (−29%, the Midwest drought)."
- Source citation per §2.4

#### §5.4.D · Band D — Profitability & harvest efficiency (two cards side by side)

##### §5.4.D.1 — Profit per acre over time

- Line chart, 25 years, simple formula: `(yield × futures price) − production cost`
- Uses nearby December futures settle at harvest as proxy for realized price
- Caption: "Corn profit per acre has ranged from $45 (2015) to $380 (2012)."

##### §5.4.D.2 — Harvest efficiency

- Multi-year bar chart of `(harvested ÷ planted) × 100`
- Small callout box explaining multi-harvest (hay runs >100% because of multiple cuttings)
- Linked glossary term "multi-harvest"
- Caption: "Corn harvest efficiency has averaged 92% over 25 years in Indiana."

#### §5.4.E · Band E — Crop progress + condition strip (seasonal, visible `early-growth`–`harvest` only)

Two compact charts from NASS weekly releases:

1. **Crop progress** — stacked area over the season: emerged, silking, dough, dent, mature, harvested. Prior-year overlay as a dashed line.
2. **Crop condition** — Good/Excellent % line chart with a 5-year average envelope. Caption: "Condition is tracking 4 points above the 5-year average."

#### §5.4.F · Band F — County drill-down (below the fold)

- Small choropleth of the selected state at county level (from the 870K county records)
- Metric toggle: yield · operations · area planted
- Click a county → mini-card with county history sparkline

#### §5.4 · Data sources

- `quickstats_data` parquet: yield, area, operations, sales, progress, condition
- `futures_daily` — for profit-per-acre calculation in §5.4.D.1
- `ers_production_costs` — for profit-per-acre calculation
- Pre-computed anomaly flags (existing feature in current codebase — promote to primary surface)

#### §5.4 · Cross-page flows

- Click an anomaly year → side drawer with WASDE + drought + progress snapshot for that year (from `anomalyContext.json`)
- Click the profit chart → Market tab pre-filtered to that commodity, historical range toggled
- Click a county in §5.4.F → Forecasts tab yield panel zoomed to that county (if season is active)

#### §5.4 · Resolved decisions

**Anomaly popover content — LOCKED: pre-computed JSON.** `web_app/src/data/anomalyContext.json` keyed by `{commodity}_{year}` (e.g., `corn_2012`). Generated by the same pipeline script that produces story cards. Shape:

```typescript
interface AnomalyContext {
  commodity: string;
  year: number;
  yieldDeltaPct: number;          // national yield vs trend, e.g. -29
  dsciPeak: number | null;        // peak DSCI value that year (0–500)
  dsciPeakMonth: string | null;   // e.g. "July"
  wasdeSurprise: string | null;   // e.g. "USDA cut stocks-to-use 2.1pp"
  narrative: string;              // one-sentence summary for the popover
}

// anomalyContext.json is Record<string, AnomalyContext>
// Key format: "{commodity}_{year}", e.g. "corn_2012"
```

Runtime pulls from drought/WASDE tables would add latency for data that changes at most annually. This is static reference content.

**Profit chart realized price — LOCKED: December nearby futures settle on October 1.** This is the price a farmer would reference at harvest-time sell decisions. Annual averages smooth away the signal. October 1 is concrete, reproducible, and aligns with the `harvest` season phase. For wheat (Jun–May marketing year), use July contract settle on June 1.

**County drill-down default metric — LOCKED: yield.** Most universal, most compared, most interesting at county resolution. Operations count and area planted are secondary toggles in the metric chip row.

#### §5.4 · Data contracts per band

**Band A — Commodity picker:**
```typescript
// No data fetch. Static list of 11 commodities with chart-palette colors.
const CROP_COMMODITIES = [
  { id: 'corn', label: 'Corn', color: '--chart-corn' },
  { id: 'soybeans', label: 'Soybeans', color: '--chart-soy' },
  { id: 'wheat', label: 'Wheat', color: '--chart-wheat' },
  { id: 'cotton', label: 'Cotton', color: '--chart-cotton' },
  { id: 'hay', label: 'Hay', color: '--chart-hay' },
  { id: 'rice', label: 'Rice', color: '--sky' },
  { id: 'sorghum', label: 'Sorghum', color: '--soil' },
  { id: 'barley', label: 'Barley', color: '--harvest-light' },
  { id: 'oats', label: 'Oats', color: '--text3' },
  { id: 'peanuts', label: 'Peanuts', color: '--soil-light' },
  { id: 'tobacco', label: 'Tobacco', color: '--harvest-dark' },
] as const;
```

**Band B — Hero KPI row:**
```typescript
// Source: S3 parquet, single state + commodity filtered
interface CropHeroData {
  yieldThisYear: number;
  yieldUnit: string;              // "bu/acre", "lbs/acre", etc.
  yield5yrAvg: number;
  yieldDeltaVs5yr: number;        // %
  yieldStateRank: number;         // rank among states for this crop
  yieldRecordYear: number;        // year of state's all-time best
  areaPlanted: number;
  areaYoyDelta: number;           // %
  operationsCount: number;
  operationsDeltaSince2010: number; // %
  totalSales: number;
  salesYoyDelta: number;           // %
  salesShareOfState: number;       // % of total state ag revenue
}
```

**Band C — Yield trend with anomaly flags:**
```typescript
// Source: S3 parquet (yield series) + anomalyContext.json (flags)
interface YieldTrendPoint {
  year: number;
  stateYield: number;
  nationalYield: number;
  isAnomaly: boolean;              // flagged if |delta vs trend| > 1.5σ
}
// 25 data points (2001–latest). Anomaly context loaded from anomalyContext.json on click.
```

**Band D.1 — Profit per acre:**
```typescript
// Source: S3 parquet (yield) + FastAPI futures_daily (Oct 1 settle) + FastAPI ers_production_costs
interface ProfitPoint {
  year: number;
  yieldBuAcre: number;
  harvestPrice: number;            // Dec futures settle on Oct 1
  productionCostPerAcre: number;   // from ERS
  profitPerAcre: number;           // (yield × price) − cost
}
```

**Band D.2 — Harvest efficiency:**
```typescript
// Source: S3 parquet (harvested vs planted)
interface HarvestEfficiency {
  year: number;
  planted: number;
  harvested: number;
  efficiencyPct: number;           // (harvested / planted) × 100
}
```

**Band E — Crop progress + condition (seasonal):**
```typescript
// Source: S3 parquet, NASS weekly releases
interface CropProgress {
  week: string;                    // ISO week or date
  emerged: number;                 // % of area
  silking: number;
  dough: number;
  dent: number;
  mature: number;
  harvested: number;
  priorYearHarvested: number;      // for overlay
}

interface CropCondition {
  week: string;
  goodExcellentPct: number;
  fiveYearAvgPct: number;          // for envelope
}
```

**Band F — County drill-down:**
```typescript
// Source: S3 county parquet (870K records)
interface CountyMetric {
  fips: string;
  countyName: string;
  value: number;                   // yield, operations, or area (per metric toggle)
  stateCode: string;
}
// Filtered to selected state + commodity + latest year
// GeoJSON: state county boundaries (static asset)
```

---

### §5.5 · Land & Economy

**Purpose.** Consolidates the old Economics, Land, and Labor tabs into one destination. Four sub-sections reachable via a left-side section rail (not sub-tabs — analysts scroll).

**Hero question.** *"Who grows what, for how much, and at what cost?"*

#### §5.5.A · Section 1 — Revenue leaderboards

- Table + bar chart: top commodities by state by sales $, with 10-year growth %
- **"Boom crops"** callout — fastest-growing commodities by 10-year revenue growth %
- **"Decline crops"** callout — steepest operational loss commodities
- CSV export button

#### §5.5.B · Section 2 — Operations & farm structure

- Operations count over time (line chart)
- Average farm size, computed as `total acres ÷ operations count` (line chart)
- Land in farms, stacked by use
- Caption: "Indiana lost 4,200 farms since 2015 but average farm size rose 8% — consolidation, not decline."

#### §5.5.C · Section 3 — Land use mix

- Stacked area of cropland / pasture / forest / urban / other, state-level, 25 years
- **Urban sprawl vs cropland-loss scatter** — states as dots, x = cropland change %, y = urban change %. Quadrant labels: "Losing both" / "Sprawling into cropland" / "Growing both" / "Neither growing"
- This is the analyst hook the backend analysis calls out. Give it a prominent share/embed button.
- Caption for scatter: "32 states lost cropland to urban growth between 2001 and 2022. The steepest trade-off: Texas, Arizona, North Carolina."

#### §5.5.D · Section 4 — Labor & wages

- State avg wage over time + national baseline + auto-selected peer states (CA/TX/IA as default peers)
- Wage growth ranking bar chart (top 10 states)
- Caption: "Indiana farm wages grew 42% over 10 years, 6pp faster than the national average."

#### §5.5 · Data sources

- `quickstats_data` parquet: sales, operations, area, wage
- Land use composition (already computed for existing Land tab)
- Urban sprawl series (already computed)
- Peer state mapping (static)

#### §5.5 · Cross-page flows

- Click a commodity in §5.5.A leaderboard → Crops tab, commodity preset
- Click a state point in §5.5.C scatter → sets global state filter, stays on tab
- Click "consolidation" narrative → Overview tab for the selected state

#### §5.5 · Resolved decisions

**Section rail — LOCKED: left rail on `lg`+, horizontal top tabs on `md` and below.** Per §2.11 collapse rules. The four sections (Revenue, Operations, Land use, Labor) become four horizontal pill tabs on tablet/mobile.

**Land use "Other" — LOCKED: keep.** NASS categories bucketed as: cropland / pasture & range / forest & woodland / urban & built-up / Other (water + miscellaneous). Clean enough for a stacked area chart. Tooltip on "Other" explains what it contains.

**Wage peer states — LOCKED: reuse `peerStates.json` from §5.1.** One static lookup table for the whole app. Peers by farm cash receipts are a reasonable proxy for wage comparison — structurally similar ag economies.

#### §5.5 · Data contracts per section

**Section 1 — Revenue leaderboards:**
```typescript
// Source: S3 parquet, single state, all commodities
interface RevenueLeaderboard {
  commodity: string;
  sales: number;                   // $ latest year
  sales10yrAgo: number;
  growthPct10yr: number;
}
// Sorted by sales DESC. "Boom crops" = top 3 by growthPct10yr.
// "Decline crops" = bottom 3 by operations count change.
```

**Section 2 — Operations & farm structure:**
```typescript
// Source: S3 parquet, single state, 25 years
interface FarmStructurePoint {
  year: number;
  operationsCount: number;
  totalAcres: number;
  avgFarmSize: number;             // totalAcres / operationsCount
  landInFarms: number;
}
```

**Section 3 — Land use mix:**
```typescript
// Source: S3 parquet, land use categories
interface LandUsePoint {
  year: number;
  cropland: number;                // acres
  pasture: number;
  forest: number;
  urban: number;
  other: number;
}

// Urban sprawl scatter (all states):
interface SprawlScatterPoint {
  stateCode: string;
  stateName: string;
  croplandChangePct: number;       // 2001→latest
  urbanChangePct: number;          // 2001→latest
  quadrant: 'losing-both' | 'sprawling-into-cropland' | 'growing-both' | 'neither';
}
```

**Section 4 — Labor & wages:**
```typescript
// Source: S3 parquet, state + national + peer states
interface WageTrendPoint {
  year: number;
  stateWage: number;
  nationalWage: number;
  peerWages: Record<string, number>;  // keyed by state code
}

interface WageRankItem {
  stateCode: string;
  stateName: string;
  wageGrowthPct10yr: number;
}
// Top 10 by growth for the ranking bar chart.
```

---

### §5.6 · Livestock

**Purpose.** Completeness. The animal side of NASS data with less depth than crops but full state coverage.

**Hero question.** *"What is happening on the animal side?"*

#### §5.6.A · Band A — Inventory snapshot

Six KPI cards — first row of 4 prominent, second row of 2 smaller:
- **Row 1:** Cattle head (total) · Hogs head (total) · Dairy cows · Broilers
- **Row 2:** Layers · Turkeys

Each card: Barlow 36px value (row 1) or 28px (row 2), 5-year sparkline, YoY delta chip, plain-English caption.

#### §5.6.B · Band B — Production & sales

Per-state line charts for:
- Milk production (lbs)
- Cattle on feed
- Egg production
- Broiler production (lbs)

Captions per chart. Each chart shows state line + national dashed line, 25 years.

#### §5.6.C · Band C — Regional concentration map

Livestock density choropleth. Species toggle: cattle · hogs · dairy · broilers · layers · turkeys. Same warm→green gradient as Overview. Hover card with state + count + rank.

#### §5.6 · Data sources

- `quickstats_data` parquet: livestock inventory, production, sales

#### §5.6 · Cross-page flows

- Click a state on §5.6.C → sets global state filter, stays on tab
- Click a species KPI card → filters Bands B and C to that species

#### §5.6 · Resolved decisions

**Poultry depth — LOCKED: broilers + layers + turkeys.** Data exists in NASS QuickStats. Poultry is a major sector in GA, AR, AL — completeness matters. All three appear in the Band A KPI inventory (replacing single "Broilers" card with a poultry sub-group) and in the Band C species toggle.

**Dairy sub-page — LOCKED: keep integrated.** Milk production + dairy cow inventory in Band B is sufficient for v1. Dairy-heavy states (WI, CA, ID) get full coverage through the existing bands. A dedicated dairy deep-dive is a post-v1 addition if usage warrants it.

#### §5.6 · Data contracts per band

**Band A — Inventory snapshot:**
```typescript
// Source: S3 parquet, single state, latest year
interface LivestockKPI {
  species: string;               // 'cattle' | 'hogs' | 'dairy' | 'broilers' | 'layers' | 'turkeys'
  label: string;                 // display name
  headCount: number;
  unit: string;                  // "head", "1,000 head", etc.
  sparkline5yr: number[];        // 5 annual values for mini-sparkline
  yoyDeltaPct: number;
}
// 6 KPI cards. First 4 prominent (cattle, hogs, dairy, broilers).
// Layers + turkeys as smaller secondary cards below.
```

**Band B — Production & sales:**
```typescript
// Source: S3 parquet, single state, 25 years
interface LivestockProductionPoint {
  year: number;
  stateValue: number;
  nationalValue: number;
  unit: string;                  // "lbs", "head", "dozen eggs"
}
// One series per chart (milk, cattle on feed, eggs, broiler production).
```

**Band C — Regional concentration map:**
```typescript
// Source: S3 parquet, all states, latest year, filtered by species toggle
interface LivestockMapPoint {
  stateCode: string;
  stateName: string;
  headCount: number;
  rank: number;
}
// Same MapDataPoint shape as Overview map, different metric.
```

---

## §6 · Build sequence

Recommended waves. Each wave is independently shippable — no wave depends on a later wave for value.

### Wave 1 — Shell + Overview

Goal: A usable product with one great page and full plumbing.

- Design tokens wired from FieldPulse CSS
- Header (§2.1) + filter rail (§2.1/§2.2)
- URL routing (§1.1)
- Glossary component + initial 20 terms (§2.3)
- Citation block component (§2.4)
- Source-of-truth footer strip (§2.7)
- Caption template library (§2.6)
- Overview page complete (§5.1) with map, fingerprint, and 3 static story cards
- Export/permalink/embed trio (§2.5)

### Wave 2 — Crops

Goal: Our strongest content, deepest history, full 25-year story for any commodity.

- Commodity picker (§5.4.A)
- Hero KPI row (§5.4.B)
- Yield trend with anomaly flags (§5.4.C) — promote existing feature to primary surface
- Profit per acre chart (§5.4.D.1) — new join: futures × yield − cost
- Harvest efficiency (§5.4.D.2)
- Crop progress / condition strip (§5.4.E)
- County drill-down (§5.4.F)

### Wave 3 — Market

Goal: Replace the killed price forecast tab with 100% honest market data.

- Commodity selector + hero quote (§5.2.A)
- Price history chart with WASDE markers (§5.2.B)
- WASDE balance card (§5.2.C.1)
- Corn/soy ratio dial (§5.2.C.2)
- Input cost card (§5.2.C.3) — new
- Macro DXY strip (§5.2.E)
- Defer: Basis tracker (§5.2.D) to Wave 3.5

### Wave 4 — Forecasts

Goal: The differentiated moat, with full accuracy disclosure.

- Season clock (§5.3.A)
- Acreage panel with 3 commodity cards (§5.3.B)
- USDA comparison modal (§5.3.B)
- County yield panel with real Deck.gl `GeoJsonLayer` choropleth (§5.3.C)
- **Accuracy panel (§5.3.D) — blocker.** Populate `acreage_accuracy` and the yield accuracy equivalent first; without it the tab cannot ship.

### Wave 5 — Land & Economy + Livestock

Goal: Completeness. Deep backstop of NASS history for analysts.

- Land & Economy page (§5.5) with four sections
- Livestock page (§5.6) with three bands

### Do not ship (for now)

- Search bar (until real)
- Notifications bell (until real)
- Price forecast cards (until models exist)
- Wheat spring acreage forecast (until data sample grows)
- Wheat yield forecast late-season (until model stabilizes)

---

## §7 · Open questions

Decisions to lock in before we go deeper into any single section.

### §7.1 · Default state on first visit — **LOCKED**

**Decision:** National aggregate on first visit, with a "Pick your state" prompt in Overview Band A. State choice is persisted in `localStorage`. See §5.1 for the exact prompt placement and behavior.

### §7.2 · BETA label phrasing — **LOCKED**

**Decision:** Pill text is `EXPERIMENTAL`. Hover tooltip reads "Experimental — see accuracy modal". Clicking opens a modal with the relevant track record. See §2.8 for full styling.

### §7.3 · Basis tracker — data scale & wave placement

**Data scale estimate.** USDA AMS publishes daily local cash grain bids from ~200–400 reporting elevators across 3 main grains. Realistic scale:

| Dimension | Count |
|---|---|
| Reporting locations | ~300 |
| Commodities | 3 (corn, soy, wheat) |
| Trading days / year | ~252 |
| Historical depth (via AMS Market News API) | ~2–5 years forward-only |
| Rows / year, fully loaded | ~50K–100K |
| Total table size at 5-year depth | ~250K–500K rows |

In Postgres this is tiny — under 100MB with indexes. The hard part is **not size**, it's **historical depth**: the AMS Market News API (LPGMN) only serves recent data. Deeper history requires scraping state-level AMS reports or paying DTN/Barchart. Realistic v1 scope is "forward-only starting from ingest date" with 2–5 years of history if we can pull archives.

**Decision:** Defer to **Wave 3.5**. Ship Market tab (Wave 3) without Band D. Start ingest in parallel so when Wave 3.5 arrives we have a few months of real data. Band D stub copy until then: *"Basis data coming — we're ingesting USDA AMS local cash reports. Expected: summer 2026."*

### §7.4 · Accuracy table population — **DEPLOYED (2026-04-15)**

All three work items implemented AND the deployment sequence has been executed against prod RDS. `acreage_accuracy` holds 796 rows (215 with model + USDA comparison), `yield_accuracy` holds 290,441 rows across 60 crop-week models. Frontend §5.3.D accuracy panel has everything it needs. See CLAUDE.md "Frontend Spec v1 + Accuracy Table Pipeline (§7.4) · Deployment executed" section for schema bugs caught mid-run, the NASS vocabulary fix for Prospective Plantings, and the interval coverage calibration finding.

#### §7.4.A — What we have

**Acreage:**
- 4 trained ensembles on disk — `backend/artifacts/acreage/{corn,soybean,wheat_winter,wheat_spring}/ensemble.pkl`
- Aggregate metrics per commodity in `metrics.json`: train/val/test MAPE, RMSE, coverage, baseline comparisons, CV stats, top features. ~30 fields.
- Walk-forward eval is performed during training but **per-(year, state) test predictions are not persisted** — they exist in memory during `train_and_save()` and are discarded after aggregate metrics are computed.
- `acreage_forecasts` table populated by `acreage_inference.py` for the current forecast year only (forward-looking).
- `acreage_accuracy` table: schema exists (§5.3.D), **empty**.

**Yield:**
- 60 trained models on disk — `backend/artifacts/yield/{corn,soybean,wheat}/week_{1..20}/model.pkl` + 60 `metrics.json` files.
- Aggregate metrics per (crop, week) include test RRMSE, bias, coverage, baselines.
- Per-(year, fips, crop, week) test predictions are **not persisted** — same as acreage.
- `yield_forecasts` table populated by `yield_inference.py` for the current forecast year.
- **There is no `yield_accuracy` table schema at all** — needs to be created.

#### §7.4.B — What we need to build

Three concrete work items:

**WI-1 · Acreage walk-forward persistence.** ✅ **Implemented 2026-04-14.**
- `train_and_save()` now returns a 3-tuple `(ensemble, metrics, predictions_df)` capturing per-row val + test predictions
- `train_commodity()` in `train_acreage.py` unpacks and calls `persist_acreage_accuracy()` when `--persist-accuracy` flag is set
- Upserts include `model_forecast`, `usda_june_actual` (from training data), `model_vs_actual_pct`
- Run: `python -m backend.models.train_acreage --persist-accuracy`

**WI-2 · USDA Prospective Plantings backfill.** ✅ **Implemented 2026-04-14.**
- `backend/etl/ingest_prospective_plantings.py` with two modes: `--api` (NASS QuickStats) and `--csv PATH` (manual fallback)
- Upserts `usda_prospective`, then runs second-pass `UPDATE` computing `model_vs_usda_pct` where `model_forecast` is already populated
- `usda_june_actual` now comes from WI-1 (no separate backfill needed)
- Run: `python -m backend.etl.ingest_prospective_plantings --api --year-start 2000`

**WI-3 · Yield accuracy table + persistence.** ✅ **Implemented 2026-04-14.**
- **Alembic migration `005_yield_accuracy.py`** creates `yield_accuracy` with all intended columns plus a `split` column (`val`|`test`). Indexes on `(crop, forecast_year)` and `(crop, week)`.
- **`YieldAccuracy`** ORM model appended to `db_tables.py`.
- `train_single_model(capture_predictions=True)` captures per-row val + test predictions; metrics.json writes still exclude the prediction payload to keep artifacts small.
- `persist_yield_accuracy()` upserts in 5K-row chunks when `--persist-accuracy` CLI flag is set.
- Run: `alembic upgrade head && python -m backend.models.train_yield --persist-accuracy`

#### §7.4.C — Total effort

| Work item | Scope | Backfill data |
|---|---|---|
| WI-1 Acreage persistence | ~40 LOC | Re-run training (minutes) |
| WI-2 Prospective Plantings | ~100 LOC + NASS pull | ~450 rows |
| WI-3 Yield accuracy | Migration + ~60 LOC | Re-run training + ~500K row backfill |

None of this is research. It's all mechanical piping on top of work that's already done. Wave 4 (Forecasts tab) is the right moment to cut these three PRs — they can land in parallel with the frontend Forecasts work, not ahead of it.

#### §7.4.D — What the frontend needs from these tables

For §5.3.D (accuracy panel):
- **Acreage chart:** `SELECT forecast_year, commodity, model_vs_actual_pct FROM acreage_accuracy WHERE state_fips = '00' (national)` — a handful of rows per commodity.
- **Yield chart:** `SELECT crop, week, forecast_year, AVG(pct_error), AVG(in_interval) FROM yield_accuracy GROUP BY crop, week, forecast_year` — small aggregation, can be materialized view if slow.

The frontend contract is simple and both tables are shaped to produce it directly.

### §7.5 · WASDE vocabulary

Options:
- Bullish / Bearish / Neutral (industry standard, unfamiliar to non-traders)
- Supportive / Pressuring / Neutral (plain English, unfamiliar to traders)
- Both (industry term as primary, plain English as tooltip)

Recommendation: **Both**. Primary label uses plain English; hover shows "bullish/bearish" so analysts can match vocabularies to their sources.

### §7.6 · Caption tone — **LOCKED**

**Decision:** Push technical insight when the opportunity presents. Plain English is the floor, not the ceiling. Captions should ideally layer plain fact + technical anchor + implied meaning in one sentence. See §2.6 for the tone policy and template library.

### §7.7 · Tablet vs desktop density

The design system calls for tablet-first density. With the farmer-primary rule relaxed, do we:
- Keep tablet-first density everywhere
- Allow denser desktop layouts with collapsing behavior on tablet
- Build two layouts

Recommendation: **Tablet-first density with desktop improvements**. One layout that's dense enough for desktop analysts and readable on iPad. Avoid two layouts — maintenance cost.

---

## §8 · Revision log

| Date | Section | Change | Note |
|---|---|---|---|
| 2026-04-14 | all | Initial draft | Paired with `design-system-v1.html`. Awaiting section-by-section refinement. |
| 2026-04-14 | §7.1, §5.1 | Locked default state = national-first with "Pick your state" prompt | Persisted in localStorage |
| 2026-04-14 | §7.2, §2.8 | Locked BETA pill → `EXPERIMENTAL` + "see accuracy modal" hover | Click opens modal, not scroll |
| 2026-04-14 | §7.6, §2.6 | Locked caption tone → push technical when opportunity presents | Plain English is floor, not ceiling |
| 2026-04-14 | §7.3 | Scoped basis tracker data size (~250K–500K rows) | Forward-only ingest, deferred to Wave 3.5 |
| 2026-04-14 | §7.4 | Scoped accuracy table work into 3 WIs with LOC estimates | Models trained — this is piping, not research |
| 2026-04-14 | §7.4 | All 3 WIs implemented (WI-1 acreage persistence, WI-2 Prospective Plantings ETL, WI-3 yield_accuracy table + persistence) | Wave 4 blocker cleared. Deployment sequence in CLAUDE.md |
| 2026-04-15 | §7.4 | Deployment executed. 215 acreage_accuracy rows + 290,441 yield_accuracy rows populated on prod RDS. Mid-run fixes: migrations 006/007 (schema) + NASS reference_period_desc filter | Forecasts tab §5.3.D accuracy panel is live-data ready |
| 2026-04-15 | §2.2 | Locked VIEW_FILTER_DEFAULTS with concrete TypeScript map | Market gets year:null (uses range chips), state is global |
| 2026-04-15 | §2.3 | Added glossary component contract (Term component, JSON schema) | Case-insensitive lookup, graceful fallback |
| 2026-04-15 | §2.5 | Locked v1 export scope: Download (PNG+CSV) + Permalink. Embed deferred to post-v1 | Embed requires standalone band routes |
| 2026-04-15 | §2.6 | Locked caption generation as runtime (captionTemplates.ts), not pre-computed | Slot interpolation, plain text output |
| 2026-04-15 | §2.9 | New: State management architecture. URL-first, useFilters() hook, no React Context for filters | localStorage only stores last-picked state |
| 2026-04-15 | §2.10 | New: API surface map. 3 sources (S3 parquet, Athena, FastAPI) + 5 new Market endpoints needed for Wave 3 | FastAPI is sole gateway to RDS |
| 2026-04-15 | §2.11 | New: Responsive breakpoints (sm/md/lg/xl) + layout collapse rules | md (tablet) is primary design target |
| 2026-04-15 | §2.12 | New: Loading/error/empty states with BandShell wrapper pattern | Skeleton shimmer, inline errors, muted empty text |
| 2026-04-15 | §2.13 | New: Theme toggle spec. Light default, data-theme attribute, full dark token set | Respects prefers-color-scheme on first visit |
| 2026-04-15 | §3.1 | Locked getAgSeason() + useAgSeason() contracts. Planting corrected to Mar–Apr (was Mar–May). May moves to early-growth | BandShell visibleSeasons prop for seasonal bands |
| 2026-04-15 | §3.3 | Converted visibility toggles to concrete BandShell visibleSeasons table | Dormant behavior specified per band |
| 2026-04-15 | §5.1 | Resolved all 3 open items: static peer lookup, NASS-release story refresh, text-only hover card. Added data contracts per band | All decisions locked with TypeScript shapes |
| 2026-04-15 | §5.4 | Resolved all 3 open items: pre-computed anomaly JSON, Oct 1 futures as realized price, yield as default county metric. Added data contracts per band | Profit chart uses harvest-time price, not annual avg |
| 2026-04-15 | §5.2 | Resolved all 5 open items: both vocabularies, rolling 10yr, 6 forward months, 1D/1W/1M/YTD deltas, basis deferred. Added data contracts per band | 5 new FastAPI endpoints needed for Wave 3 |
| 2026-04-15 | §5.3 | Resolved all 4 open items: accuracy tables deployed, no default county, backfill status in drawer only. Added data contracts per band | All blockers cleared |
| 2026-04-15 | §5.5 | Resolved all 3 open items: left rail collapses to tabs, "Other" kept, reuse peerStates.json. Added data contracts per section | Revenue, operations, land use, labor all have shapes |
| 2026-04-15 | §5.6 | Resolved both open items: full poultry (broilers+layers+turkeys), dairy stays integrated. Added data contracts per band | 6 KPI cards, expanded species toggle |
| 2026-04-15 | App A | Complete component inventory: ~55 components, 5 hooks, 6 static data files, 6 pages. Organized by wave. | Includes file paths, data hooks, and key props |
| 2026-04-15 | App B | Data contract summary: all contracts inline in page specs. Fetch strategy table. 6 new FastAPI endpoints cataloged. | Build-ready — no gaps remain |
| 2026-04-15 | all | Status changed from "Draft" to "Build-ready" | All 15+ open items resolved, all data contracts written |
| 2026-04-15 | §2.10, App B | 6 new FastAPI endpoints implemented: market/futures, market/curve, market/dxy, market/costs, market/fertilizer, yield/accuracy | Zero backend build dependencies remain |

---

## Appendix A · Component inventory

Organized by build wave. Each component lists its source section, data hook, and key props. All components use CSS custom properties from the design system — no inline color values.

### Shared / cross-cutting (Wave 1)

| Component | File | Props | Notes |
|---|---|---|---|
| `<AppShell>` | `components/layout/AppShell.tsx` | `children` | Root layout: nav bar + filter rail + main content + footer strip |
| `<NavBar>` | `components/layout/NavBar.tsx` | `activeTab` | §2.1 Layer 1. Logo + tab links + theme toggle. Sticky, 56px. |
| `<FilterRail>` | `components/layout/FilterRail.tsx` | `filters, onFilterChange` | §2.1 Layer 2. State/year/commodity pills + freshness strip. Collapses on `sm`. |
| `<FilterPill>` | `components/ui/FilterPill.tsx` | `label, value, options, onChange` | Reusable dropdown pill for state/year/commodity/section selectors. |
| `<BandShell>` | `components/ui/BandShell.tsx` | `loading, error, empty, visibleSeasons?, dormantMessage?, dormantSummary?, children` | §2.12 + §3.1. Handles loading/error/empty/seasonal-dormant states. |
| `<KpiCard>` | `components/ui/KpiCard.tsx` | `label, value, unit, delta?, deltaLabel?, caption?, size?` | Barlow number + delta chip + caption. Sizes: `'hero'` (48px), `'standard'` (36px), `'compact'` (28px). |
| `<DeltaChip>` | `components/ui/DeltaChip.tsx` | `value, format?` | Colored +/- chip. `--positive` or `--negative`. JetBrains Mono 13px. |
| `<Term>` | `components/ui/Term.tsx` | `children` | §2.3 glossary hover. Dotted underline + popover. |
| `<Citation>` | `components/ui/Citation.tsx` | `source, vintage, updated, methodologyContent?` | §2.4. JetBrains Mono 11px strip under every chart. Methodology link opens drawer. |
| `<ChartFrame>` | `components/ui/ChartFrame.tsx` | `title, caption?, citation, children` | Wrapper: title + caption + chart content + citation + export trio. |
| `<ExportTrio>` | `components/ui/ExportTrio.tsx` | `chartRef, csvData?, title?` | §2.5. Download PNG + CSV, permalink copy. Appears on hover top-right of ChartFrame. |
| `<SourceStrip>` | `components/layout/SourceStrip.tsx` | none (reads timestamps from context) | §2.7. Thin footer on every page. |
| `<ThemeToggle>` | `components/ui/ThemeToggle.tsx` | none | §2.13. Sun/moon icon, 44px target. |
| `<MethodologyDrawer>` | `components/ui/MethodologyDrawer.tsx` | `open, onClose, content` | Side drawer for citation methodology links. |
| `<ExperimentalPill>` | `components/ui/ExperimentalPill.tsx` | `onClick` | §2.8. `EXPERIMENTAL` pill with hover tooltip + click → accuracy modal. |
| `<AccuracyModal>` | `components/ui/AccuracyModal.tsx` | `open, onClose, commodity?, crop?` | Modal showing track record for the associated forecast. |
| `<SeasonClock>` | `components/ui/SeasonClock.tsx` | `season, month` | §5.3.A. 12-month horizontal strip with rails + USDA markers. Reusable. |

### Hooks (Wave 1)

| Hook | File | Returns | Notes |
|---|---|---|---|
| `useFilters()` | `hooks/useFilters.ts` | `UseFiltersReturn` (§2.9) | URL-based filter state. Single source of truth. |
| `useAgSeason()` | `hooks/useAgSeason.ts` | `UseAgSeasonReturn` (§3.1) | Current season + monthly overrides. Memoized on date. |
| `useTheme()` | `hooks/useTheme.ts` | `{ theme, toggleTheme }` | §2.13. Reads/writes `localStorage` + `data-theme` attr. |
| `useParquetData()` | `hooks/useParquetData.ts` | `{ data, loading, error }` | Fetches + parses S3 parquet via hyparquet. Caches 1hr. |
| `useFastAPI()` | `hooks/useFastAPI.ts` | `{ data, loading, error, refetch }` | Generic FastAPI fetch wrapper. Base URL from env var. |

### Wave 1 — Overview (`/overview`)

| Component | File | Band | Data hook |
|---|---|---|---|
| `<OverviewPage>` | `app/overview/page.tsx` | — | Orchestrates all bands |
| `<HeroStrip>` | `components/overview/HeroStrip.tsx` | A | `useParquetData('state_rollup')` |
| `<StatePrompt>` | `components/overview/StatePrompt.tsx` | A | Reads `localStorage` for prior selection |
| `<USChoropleth>` | `components/maps/USChoropleth.tsx` | B left | `useParquetData('all_states')` + Deck.gl + MapLibre |
| `<StateFingerprint>` | `components/overview/StateFingerprint.tsx` | B right | `useParquetData('state')` |
| `<RevenueDonut>` | `components/overview/RevenueDonut.tsx` | B right | Receives data from parent |
| `<SparklineStrip>` | `components/overview/SparklineStrip.tsx` | B right | Receives data from parent |
| `<PeerBar>` | `components/overview/PeerBar.tsx` | B right | `peerStates.json` + `useParquetData` |
| `<StoryCardGrid>` | `components/overview/StoryCardGrid.tsx` | C | Fetches `stories.json` |
| `<StoryCard>` | `components/overview/StoryCard.tsx` | C | Receives `StoryCard` props |

### Wave 2 — Crops (`/crops`)

| Component | File | Band | Data hook |
|---|---|---|---|
| `<CropsPage>` | `app/crops/page.tsx` | — | Orchestrates all bands |
| `<CommodityPicker>` | `components/ui/CommodityPicker.tsx` | A | Static list. Reused on Market + Forecasts. |
| `<CropHeroRow>` | `components/crops/CropHeroRow.tsx` | B | `useParquetData('state', commodity)` |
| `<YieldTrendChart>` | `components/crops/YieldTrendChart.tsx` | C | `useParquetData('state')` + `anomalyContext.json` |
| `<AnomalyPopover>` | `components/crops/AnomalyPopover.tsx` | C | `anomalyContext.json` lookup |
| `<ProfitChart>` | `components/crops/ProfitChart.tsx` | D.1 | `useParquetData` + `useFastAPI('/market/futures')` + `useFastAPI('/market/costs')` |
| `<HarvestEfficiencyChart>` | `components/crops/HarvestEfficiencyChart.tsx` | D.2 | `useParquetData('state')` |
| `<CropProgressStrip>` | `components/crops/CropProgressStrip.tsx` | E | `useParquetData('state')`. Seasonal via BandShell. |
| `<CropConditionChart>` | `components/crops/CropConditionChart.tsx` | E | `useParquetData('state')` |
| `<CountyDrilldown>` | `components/crops/CountyDrilldown.tsx` | F | `useParquetData('county')` + state GeoJSON |
| `<StateChoropleth>` | `components/maps/StateChoropleth.tsx` | F | Deck.gl county-level within a single state |

### Wave 3 — Market (`/market`)

| Component | File | Band | Data hook |
|---|---|---|---|
| `<MarketPage>` | `app/market/page.tsx` | — | Orchestrates all bands |
| `<MarketHero>` | `components/market/MarketHero.tsx` | A | `useFastAPI('/market/futures')` |
| `<PriceHistoryChart>` | `components/market/PriceHistoryChart.tsx` | B | `useFastAPI('/market/futures')` + WASDE markers |
| `<TermStructureStrip>` | `components/market/TermStructureStrip.tsx` | B | `useFastAPI('/market/curve')` |
| `<WasdeCard>` | `components/market/WasdeCard.tsx` | C.1 | `useFastAPI('/predict/price/wasde-signal')` |
| `<RatioDial>` | `components/market/RatioDial.tsx` | C.2 | `useFastAPI('/predict/acreage/price-ratio')` |
| `<InputCostCard>` | `components/market/InputCostCard.tsx` | C.3 | `useFastAPI('/market/costs')` + `useFastAPI('/market/fertilizer')` |
| `<BasisStub>` | `components/market/BasisStub.tsx` | D | None. Static stub message. |
| `<DxyStrip>` | `components/market/DxyStrip.tsx` | E | `useFastAPI('/market/dxy')` |

### Wave 4 — Forecasts (`/forecasts`)

| Component | File | Band | Data hook |
|---|---|---|---|
| `<ForecastsPage>` | `app/forecasts/page.tsx` | — | Orchestrates all bands |
| `<AcreagePanel>` | `components/forecasts/AcreagePanel.tsx` | B | Renders 3 `<AcreageCard>` |
| `<AcreageCard>` | `components/forecasts/AcreageCard.tsx` | B | `useFastAPI('/predict/acreage')` + `useFastAPI('/predict/acreage/states')` |
| `<IntervalBar>` | `components/ui/IntervalBar.tsx` | B, C | p10–p90 horizontal range. Reusable. |
| `<YieldPanel>` | `components/forecasts/YieldPanel.tsx` | C | Orchestrates map + sidebar. Seasonal via BandShell. |
| `<CountyYieldMap>` | `components/maps/CountyYieldMap.tsx` | C | `useFastAPI('/predict/yield/map')` + county GeoJSON |
| `<WeekSlider>` | `components/forecasts/WeekSlider.tsx` | C | Week 1–20 with confidence-tier coloring. |
| `<CountyDetailSidebar>` | `components/forecasts/CountyDetailSidebar.tsx` | C | `useFastAPI('/predict/yield')` on county click |
| `<AccuracyPanel>` | `components/forecasts/AccuracyPanel.tsx` | D | `useFastAPI('/predict/acreage/accuracy')` + yield accuracy endpoint |
| `<AcreageAccuracyChart>` | `components/forecasts/AcreageAccuracyChart.tsx` | D | Recharts line per commodity |
| `<YieldAccuracyChart>` | `components/forecasts/YieldAccuracyChart.tsx` | D | Recharts small multiples per crop × week |

### Wave 5 — Land & Economy (`/land-economy`) + Livestock (`/livestock`)

| Component | File | Section/Band | Data hook |
|---|---|---|---|
| `<LandEconomyPage>` | `app/land-economy/page.tsx` | — | Section rail + 4 sections |
| `<SectionRail>` | `components/ui/SectionRail.tsx` | — | Left nav rail (`lg`+) / top tabs (`md`−). Reusable. |
| `<RevenueSection>` | `components/land-economy/RevenueSection.tsx` | §5.5.A | `useParquetData('state')` |
| `<OperationsSection>` | `components/land-economy/OperationsSection.tsx` | §5.5.B | `useParquetData('state')` |
| `<LandUseSection>` | `components/land-economy/LandUseSection.tsx` | §5.5.C | `useParquetData('state')` + all-states for scatter |
| `<SprawlScatter>` | `components/land-economy/SprawlScatter.tsx` | §5.5.C | `useParquetData('all_states')` |
| `<LaborSection>` | `components/land-economy/LaborSection.tsx` | §5.5.D | `useParquetData('state')` + `peerStates.json` |
| `<LivestockPage>` | `app/livestock/page.tsx` | — | Orchestrates 3 bands |
| `<LivestockKpiRow>` | `components/livestock/LivestockKpiRow.tsx` | A | `useParquetData('state')` |
| `<ProductionCharts>` | `components/livestock/ProductionCharts.tsx` | B | `useParquetData('state')` |
| `<LivestockMap>` | `components/maps/LivestockMap.tsx` | C | `useParquetData('all_states')` + species toggle |

### Static data files

| File | Source | Refresh cadence |
|---|---|---|
| `src/data/glossary.json` | Hand-authored | On spec change |
| `src/data/peerStates.json` | Pipeline script | Annually (new NASS vintage) |
| `src/data/anomalyContext.json` | Pipeline script | Annually |
| `src/data/captionTemplates.ts` | Hand-authored | On spec change |
| `public/stories.json` | Pipeline script | Monthly (15th, with NASS cron) |
| `public/us-counties.json` | us-atlas topojson → GeoJSON | Static (one-time) |

**Total: ~55 components, 5 hooks, 6 static data files, 6 pages.**

## Appendix B · Data contract summary

All data contracts are now defined inline within their respective page specs:

| Page | Section | Location in spec |
|---|---|---|
| Overview | §5.1 Band A–C | §5.1 "Data contracts per band" |
| Market | §5.2 Band A–E | §5.2 "Data contracts per band" |
| Forecasts | §5.3 Band A–D | §5.3 "Data contracts per band" |
| Crops | §5.4 Band A–F | §5.4 "Data contracts per band" |
| Land & Economy | §5.5 Sections 1–4 | §5.5 "Data contracts per section" |
| Livestock | §5.6 Band A–C | §5.6 "Data contracts per band" |

**Data fetch strategy per source:**

| Source | Hook | Cache | Error handling |
|---|---|---|---|
| S3 parquet | `useParquetData(file, filters)` | 1hr in-memory (parquet binary) | BandShell error state, retry button |
| Athena | `useAthenaQuery(params)` | 5min server-side LRU | BandShell error state, retry button |
| FastAPI | `useFastAPI(path, params)` | None (data is live) | BandShell error state. 503 = "Models loading, try again in a moment." |
| Static JSON | Direct `import` or `fetch` | Bundled or 1hr | Silent fallback to empty (non-critical) |

**FastAPI endpoints — all implemented (no build dependencies remain):**

| Endpoint | Path | Router file | Tables |
|---|---|---|---|
| Futures time series | `GET /api/v1/market/futures` | `routers/market.py` | `futures_daily` |
| Forward curve | `GET /api/v1/market/curve` | `routers/market.py` | `futures_daily` |
| DXY time series | `GET /api/v1/market/dxy` | `routers/market.py` | `dxy_daily` |
| Production costs | `GET /api/v1/market/costs` | `routers/market.py` | `ers_production_costs` + `futures_daily` |
| Fertilizer prices | `GET /api/v1/market/fertilizer` | `routers/market.py` | `ers_fertilizer_prices` |
| Yield accuracy agg | `GET /api/v1/predict/yield/accuracy` | `routers/yield_forecast.py` | `yield_accuracy` |

Pydantic response schemas: `FuturesTimeSeriesResponse`, `ForwardCurveResponse`, `DxyTimeSeriesResponse`, `ProductionCostResponse`, `FertilizerPriceResponse`, `YieldAccuracyWeekItem` — all in `backend/models/schemas.py`.

## Appendix C · Accessibility checklist (to be completed at each wave ship gate)

- [ ] All interactive elements 44px minimum touch target
- [ ] Color contrast AA minimum on text + AAA on primary CTAs
- [ ] Keyboard navigation for all tabs, filters, map interactions
- [ ] Screen reader labels on every chart + meaningful alt text on data images
- [ ] No color-only encoding (every color-coded state has a secondary visual marker)
- [ ] Dark mode tested against full page, not individual components
