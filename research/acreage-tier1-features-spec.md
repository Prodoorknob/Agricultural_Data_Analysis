# Tier 1 Feature Sources — Acreage Model Enhancement

## Purpose
Add four new feature categories to the acreage prediction model to close the gap
with private-sector forecasts. Current model uses only futures prices, ERS costs,
fertilizer prices, and historical NASS acreage. These additions capture physical
constraints, farmer decisions, drought conditions, and demand signals that
market prices alone cannot explain.

---

## 1. CRP Expirations (Conservation Reserve Program)

### Why it matters
CRP contracts lock up cropland for 10-15 years. When contracts expire, that land
often returns to corn/soy/wheat production — a direct acreage supply signal.
Currently ~23M acres enrolled nationally; ~2-4M expire each year. The model
completely misses this land supply dynamic.

### Data source
- **Publisher:** USDA Farm Service Agency (FSA)
- **URL:** https://www.fsa.usda.gov/tools/informational/reports/conservation-statistics/crp
- **Format:** Excel/PDF tables; historical monthly summaries by state
- **Coverage:** 1986-present, state-level, monthly updates
- **Cost:** Free
- **Key fields:** Enrolled acres (by state), expiring acres, new enrollments, net change
- **Update frequency:** Monthly (enrollment reports), annual (contract expiration schedule)

### Feature design
| Feature | Description | Decision date |
|---------|-------------|---------------|
| `crp_acres_state` | Total CRP acres enrolled in the state | As of Oct 1 prior year |
| `crp_expiring_next_year` | Acres with contracts expiring in forecast year | Published Oct prior year |
| `crp_net_change_1yr` | Net CRP enrollment change (enrolled - expired) from prior year | As of Oct 1 |
| `crp_pct_cropland` | CRP acres as % of state total cropland | As of Oct 1 |

### ETL approach
- **Script:** `backend/etl/ingest_crp.py`
- **Method:** Download annual CRP summary Excel from FSA. Parse state-level
  enrolled/expiring acres. Upsert to new `crp_enrollment` table.
- **Table schema:**
  ```sql
  CREATE TABLE crp_enrollment (
      id SERIAL PRIMARY KEY,
      state_fips VARCHAR(2) NOT NULL,
      year INTEGER NOT NULL,
      enrolled_acres NUMERIC,
      expiring_acres NUMERIC,
      new_enrollment_acres NUMERIC,
      UNIQUE (state_fips, year)
  );
  ```
- **Backfill:** FSA publishes historical data back to ~2000. One-time download.
- **Schedule:** Annual (January), aligned with ERS costs refresh.
- **Complexity:** Medium — Excel parsing, inconsistent format across years.

---

## 2. Crop Insurance Elections (RMA Summary of Business)

### Why it matters
Farmers purchase crop insurance BEFORE planting. The "net acres insured" by
crop/state is a revealed-preference signal of planting intentions — essentially
a partial census of what farmers plan to grow. Coverage rates are 80-90% of
planted acres for corn/soy, making this nearly as good as a survey.

### Data source
- **Publisher:** USDA Risk Management Agency (RMA)
- **URL:** https://www.rma.usda.gov/SummaryOfBusiness/StateCountyCrop
- **Format:** ZIP files containing pipe-delimited (|) flat files, one per crop year
- **Coverage:** 1989-present, state/county/crop level, annual
- **Cost:** Free
- **Key fields:** `Net Reported Acres`, `Policies Earning Premium`, `Liability Amount`
- **Commodities:** CORN (0041), SOYBEANS (0081), WHEAT (0011) — use RMA crop codes
- **Update frequency:** Weekly during sales/reporting period (Feb-Sep), final after Oct

### Feature design
| Feature | Description | Decision date |
|---------|-------------|---------------|
| `insured_acres_state` | Net reported acres insured for this crop in state | Prior year final (Oct) |
| `insurance_coverage_ratio` | Insured acres / prior year planted acres | Derived |
| `insured_acres_yoy_change` | % change in insured acres from year before | Derived |

### ETL approach
- **Script:** `backend/etl/ingest_rma.py`
- **Method:** Download annual ZIP from RMA SoB page. Parse pipe-delimited file.
  Filter to corn (0041), soybeans (0081), wheat (0011). Aggregate to state level.
  Upsert to new `rma_insured_acres` table.
- **Table schema:**
  ```sql
  CREATE TABLE rma_insured_acres (
      id SERIAL PRIMARY KEY,
      state_fips VARCHAR(2) NOT NULL,
      commodity VARCHAR(20) NOT NULL,
      crop_year INTEGER NOT NULL,
      net_reported_acres NUMERIC,
      policies_earning NUMERIC,
      liability_amount NUMERIC,
      UNIQUE (state_fips, commodity, crop_year)
  );
  ```
- **Backfill:** Download ZIPs for 2000-2025 (26 files, ~50MB total).
- **Schedule:** Annual (February), after RMA publishes prior year final data.
- **Complexity:** Low — structured flat files, consistent format.

### Notes
- Crop insurance sales deadline is March 15 for spring crops, so the PRIOR year's
  final insured acreage is the signal available at November decision time.
- This is the closest thing to a farmer survey without actually surveying farmers.

---

## 3. Drought Severity (US Drought Monitor)

### Why it matters
Pre-planting drought status determines:
- Whether winter wheat survives (poor establishment → abandoned → acreage drops)
- Whether prevented planting claims spike (too wet/dry → forced crop switches)
- Regional planting feasibility (severe drought → fallow, shift to drought-tolerant crops)
The 2012 drought reduced corn acreage by ~3M acres. This signal is completely absent.

### Data source
- **Publisher:** National Drought Mitigation Center (UNL) / USDA / NOAA
- **REST API:** `https://usdmdataservices.unl.edu/api/StateStatistics/GetDSCI`
- **Parameters:**
  - `aoi` = state FIPS (2-digit)
  - `startdate` / `enddate` = M/D/YYYY
  - `statisticsType` = 1 (traditional)
- **Response formats:** CSV (default), JSON, XML (via Accept header)
- **Coverage:** 2000-present, weekly, state/county level
- **Cost:** Free, no API key required
- **Key metric:** DSCI (Drought Severity and Coverage Index), 0-500 scale
  - 0 = no drought, 500 = entire state in D4 (exceptional drought)

### Feature design
| Feature | Description | Decision date |
|---------|-------------|---------------|
| `dsci_nov` | DSCI value as of November 1 of prior year | Nov 1 |
| `dsci_fall_avg` | Mean DSCI over Sep-Nov of prior year | Sep-Nov avg |
| `dsci_winter_avg` | Mean DSCI over Dec-Feb (winter wheat survival) | Dec-Feb avg |
| `drought_weeks_d2plus` | Weeks in D2+ drought in prior 6 months | Rolling count |

### ETL approach
- **Script:** `backend/etl/ingest_drought.py`
- **Method:** Query REST API for each state FIPS, fetch DSCI weekly series.
  Compute Nov snapshot + seasonal averages. Upsert to `drought_index` table.
- **Table schema:**
  ```sql
  CREATE TABLE drought_index (
      id SERIAL PRIMARY KEY,
      state_fips VARCHAR(2) NOT NULL,
      year INTEGER NOT NULL,
      dsci_nov NUMERIC,
      dsci_fall_avg NUMERIC,
      dsci_winter_avg NUMERIC,
      drought_weeks_d2plus INTEGER,
      UNIQUE (state_fips, year)
  );
  ```
- **Backfill:** API supports 2000-present. Batch fetch all states × all years.
  ~50 states × 25 years = 1,250 API calls (no rate limit documented).
- **Schedule:** Weekly during growing season, monthly otherwise.
- **Complexity:** Low — clean REST API, JSON/CSV response, no auth required.

### Example API call
```
GET https://usdmdataservices.unl.edu/api/StateStatistics/GetDSCI?aoi=19&startdate=9/1/2025&enddate=11/30/2025&statisticsType=1
Accept: application/json
```

---

## 4. Export Commitments (USDA FAS Weekly Export Sales)

### Why it matters
Outstanding export sales signal demand. Large Chinese soybean purchases in
September directly influence November planting decisions. Export commitments
as of October represent the demand pipeline that farmers factor into price
expectations — a forward-looking demand signal that futures prices partially
but incompletely capture.

### Data source
- **Publisher:** USDA Foreign Agricultural Service (FAS)
- **URL:** https://apps.fas.usda.gov/export-sales/wkHistData.htm
- **Format:** CSV/Excel, weekly reports since 1990
- **Coverage:** 1990-present, weekly, by commodity and destination
- **Cost:** Free
- **Key fields:**
  - `Outstanding Sales` (commitments not yet shipped, current marketing year)
  - `Net Sales` (weekly new sales)
  - `Accumulated Exports` (shipped YTD)
- **Marketing years:** Corn/Soy: Sep 1 - Aug 31, Wheat: Jun 1 - May 31
- **Update frequency:** Weekly (Thursday 8:30 AM ET)

### Feature design
| Feature | Description | Decision date |
|---------|-------------|---------------|
| `export_outstanding_mt` | Outstanding export commitments (metric tons) as of Nov 1 | Nov 1 |
| `export_outstanding_pct_usda` | Outstanding as % of USDA full-year export projection | Derived |
| `export_pace_vs_5yr` | Current MY export pace vs 5-year average (%) | Nov 1 |
| `export_yoy_change` | % change in outstanding vs same week prior year | Derived |

### ETL approach
- **Script:** `backend/etl/ingest_export_sales.py`
- **Method:** Download weekly historical CSV from FAS. Filter to corn/soybeans/wheat.
  Extract the report closest to November 1 each year. Compute outstanding
  commitments and pace metrics. Upsert to `export_commitments` table.
- **Table schema:**
  ```sql
  CREATE TABLE export_commitments (
      id SERIAL PRIMARY KEY,
      commodity VARCHAR(20) NOT NULL,
      marketing_year INTEGER NOT NULL,
      as_of_date DATE NOT NULL,
      outstanding_sales_mt NUMERIC,
      accumulated_exports_mt NUMERIC,
      net_sales_mt NUMERIC,
      UNIQUE (commodity, marketing_year, as_of_date)
  );
  ```
- **Backfill:** Historical CSVs available 1990-present. Bulk download + parse.
- **Schedule:** Weekly (aligned with FAS release), but only the Nov 1 snapshot
  matters for the acreage model.
- **Complexity:** Medium — CSV format varies slightly across years, need to handle
  marketing year boundaries, unit conversions (some in bushels, some in metric tons).

---

## Integration into Feature Builder

### Changes to `backend/features/acreage_features.py`

Add 4 new query functions (with `@lru_cache`):
```python
@lru_cache(maxsize=256)
def _query_crp_expiring(state_fips: str, year: int) -> float | None:
    """CRP acres expiring in forecast year."""

@lru_cache(maxsize=256)
def _query_insured_acres(state_fips: str, commodity: str, year: int) -> float | None:
    """Prior year net reported insured acres."""

@lru_cache(maxsize=256)
def _query_drought_dsci(state_fips: str, year: int) -> float | None:
    """DSCI as of November 1 of prior year."""

@lru_cache(maxsize=256)
def _query_export_outstanding(commodity: str, year: int) -> float | None:
    """Outstanding export commitments as of Nov 1."""
```

### New features added to `FEATURE_COLS`:
```python
FEATURE_COLS = [
    # ... existing 15 features ...
    # Tier 1 additions:
    "crp_expiring_acres",        # CRP supply signal
    "crp_pct_cropland",          # CRP structural signal
    "insured_acres_prior",       # Insurance revealed preference
    "insured_acres_yoy_change",  # Insurance momentum
    "dsci_nov",                  # Drought at decision time
    "dsci_fall_avg",             # Seasonal drought context
    "export_outstanding_pct",    # Demand pipeline signal
    "export_pace_vs_5yr",        # Demand momentum
]
```

### Expected feature count: 15 existing + 8 new = 23 features

---

## Implementation Priority

| Source | Effort | Impact | Priority |
|--------|--------|--------|----------|
| Drought Monitor | 1 day | High (direct physical constraint) | 1 |
| RMA Insured Acres | 1 day | High (closest to farmer survey) | 2 |
| CRP Expirations | 1-2 days | Medium (structural, slow-moving) | 3 |
| FAS Export Sales | 1-2 days | Medium (demand signal, partially in futures) | 4 |

### Total estimated effort: 5-7 days

---

## Migration

Single Alembic migration `003_tier1_feature_tables.py` adding all 4 tables.
Run after ETL scripts are tested locally.

## Cron Integration

Add to `pipeline/cron_runner.sh`:
```bash
--weekly-drought    # Drought monitor DSCI refresh
--annual-crp        # CRP enrollment/expiration data (January)
--annual-rma        # RMA insured acres (February)
--weekly-exports    # FAS export sales (Thursday)
```
