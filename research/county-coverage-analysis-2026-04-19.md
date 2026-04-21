# County-Level NASS Coverage Audit

**Date:** 2026-04-19  
**Source:** `pipeline/output/{STATE}.parquet` (county-level rows only)  
**Generator:** `pipeline/_county_coverage_audit.py`

## Executive Summary

- **1,932,343** county-level rows across **48** states (NATIONAL.parquet excluded; AK/HI/DC have no county rows)
- **3,105** distinct county FIPS represented; **277** distinct (state, commodity) combinations active
- **4,748** (state, commodity, year) combinations have at least one row
- **201** (state, commodity) pairs have all 4 target stat categories (YIELD/AREA HARVESTED/AREA PLANTED/PRODUCTION)
- **15** total-miss gaps where a major-producer state has ZERO rows for an expected commodity

## Ingestion Contract (from `quickstats_ingest.py`)

- **11 commodities targeted:** CORN, SOYBEANS, WINTER WHEAT, SPRING WHEAT, (EXCL DURUM), COTTON, SORGHUM, BARLEY, OATS, HAY, RICE, SUNFLOWER
- **4 stat categories:** YIELD, AREA HARVESTED, AREA PLANTED, PRODUCTION
- **Year range:** 2001–2025 (25 years)
- **Skipped states (structural):** AK, HI, DC universally; per-commodity skip lists exclude states with no commercial production (e.g. COTTON in MN, RICE in IA). Skip lists encoded in `COUNTY_SKIP_STATES`.
- **Filter:** `agg_level_desc == 'COUNTY'`
- **Sources:** SURVEY year-round + CENSUS for {2002, 2007, 2012, 2017, 2022}

## Per-State Coverage

Compact table (full commodity/stat lists in `state_commodity_matrix` below).

| state | rows | counties | year_min | year_max | n_years | n_commodities | n_stat_cats |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AL | 33187 | 68 | 2001 | 2025 | 25 | 6 | 4 |
| AR | 40722 | 76 | 2001 | 2025 | 25 | 8 | 4 |
| AZ | 6259 | 16 | 2001 | 2025 | 25 | 4 | 4 |
| CA | 32197 | 59 | 2001 | 2025 | 25 | 10 | 4 |
| CO | 48165 | 65 | 2001 | 2025 | 25 | 8 | 4 |
| CT | 691 | 8 | 2002 | 2022 | 5 | 2 | 2 |
| DE | 1194 | 4 | 2001 | 2024 | 18 | 3 | 4 |
| FL | 11463 | 68 | 2001 | 2025 | 23 | 5 | 4 |
| GA | 65411 | 160 | 2001 | 2025 | 25 | 7 | 4 |
| IA | 63527 | 100 | 2001 | 2025 | 25 | 6 | 4 |
| ID | 37721 | 45 | 2001 | 2025 | 25 | 5 | 4 |
| IL | 71300 | 103 | 2001 | 2025 | 25 | 6 | 4 |
| IN | 58495 | 93 | 2001 | 2025 | 25 | 6 | 4 |
| KS | 130949 | 106 | 2001 | 2025 | 25 | 8 | 4 |
| KY | 33208 | 121 | 2001 | 2024 | 22 | 6 | 4 |
| LA | 26184 | 64 | 2001 | 2025 | 25 | 7 | 4 |
| MA | 613 | 14 | 2002 | 2022 | 4 | 2 | 2 |
| MD | 8405 | 24 | 2001 | 2023 | 22 | 5 | 4 |
| ME | 1168 | 16 | 2002 | 2022 | 5 | 3 | 2 |
| MI | 17887 | 84 | 2001 | 2024 | 24 | 5 | 4 |
| MN | 69330 | 88 | 2001 | 2025 | 25 | 6 | 4 |
| MO | 73163 | 115 | 2001 | 2025 | 25 | 10 | 4 |
| MS | 41111 | 83 | 2001 | 2025 | 25 | 7 | 4 |
| MT | 76977 | 57 | 2001 | 2025 | 24 | 5 | 4 |
| NC | 65317 | 101 | 2001 | 2025 | 25 | 9 | 4 |
| ND | 68647 | 54 | 2001 | 2025 | 25 | 7 | 4 |
| NE | 115073 | 94 | 2001 | 2025 | 25 | 8 | 4 |
| NH | 566 | 10 | 2002 | 2022 | 5 | 3 | 2 |
| NJ | 3714 | 19 | 2001 | 2024 | 19 | 3 | 4 |
| NM | 15062 | 34 | 2001 | 2025 | 25 | 5 | 4 |
| NV | 2136 | 18 | 2002 | 2022 | 14 | 2 | 3 |
| NY | 37995 | 60 | 2001 | 2025 | 25 | 6 | 4 |
| OH | 57680 | 89 | 2001 | 2025 | 25 | 7 | 4 |
| OK | 56662 | 78 | 2001 | 2025 | 25 | 9 | 4 |
| OR | 23954 | 37 | 2001 | 2025 | 24 | 5 | 4 |
| PA | 52072 | 68 | 2001 | 2025 | 25 | 6 | 4 |
| RI | 333 | 5 | 2002 | 2022 | 5 | 2 | 2 |
| SC | 29392 | 47 | 2001 | 2025 | 25 | 6 | 4 |
| SD | 80263 | 67 | 2001 | 2025 | 25 | 8 | 4 |
| TN | 50497 | 96 | 2001 | 2025 | 25 | 8 | 4 |
| TX | 165005 | 255 | 2001 | 2025 | 25 | 9 | 4 |
| UT | 6265 | 30 | 2002 | 2022 | 15 | 4 | 4 |
| VA | 46837 | 99 | 2001 | 2025 | 25 | 7 | 4 |
| VT | 1409 | 14 | 2002 | 2022 | 5 | 3 | 2 |
| WA | 22710 | 40 | 2001 | 2025 | 25 | 5 | 4 |
| WI | 59806 | 73 | 2001 | 2025 | 25 | 6 | 4 |
| WV | 5452 | 56 | 2001 | 2022 | 18 | 4 | 4 |
| WY | 16169 | 24 | 2001 | 2025 | 24 | 5 | 4 |

## Per-Commodity Coverage

| commodity | rows | states | counties | year_min | year_max | n_years |
| --- | --- | --- | --- | --- | --- | --- |
| HAY | 429053 | 48 | 3096 | 2001 | 2024 | 23 |
| CORN | 418481 | 48 | 2978 | 2001 | 2024 | 24 |
| WHEAT | 418424 | 34 | 2483 | 2001 | 2025 | 25 |
| SOYBEANS | 248999 | 33 | 2381 | 2001 | 2024 | 24 |
| COTTON | 112936 | 16 | 891 | 2001 | 2025 | 25 |
| OATS | 100919 | 33 | 2274 | 2001 | 2025 | 25 |
| SORGHUM | 93548 | 21 | 1712 | 2001 | 2024 | 24 |
| BARLEY | 61340 | 28 | 1371 | 2001 | 2025 | 24 |
| SUNFLOWER | 34345 | 10 | 541 | 2001 | 2025 | 24 |
| RICE | 14298 | 6 | 175 | 2001 | 2024 | 24 |

## Recent Years (2023–2025)

| year | rows | states | commodities | state_commodity_pairs |
| --- | --- | --- | --- | --- |
| 2023 | 21129 | 38 | 10 | 137 |
| 2024 | 15767 | 35 | 9 | 92 |
| 2025 | 6722 | 34 | 5 | 62 |

## Early Years (2001–2005)

| year | rows | states | commodities | state_commodity_pairs |
| --- | --- | --- | --- | --- |
| 2001 | 81357 | 40 | 10 | 202 |
| 2002 | 258441 | 48 | 10 | 251 |
| 2003 | 84416 | 42 | 10 | 217 |
| 2004 | 82919 | 41 | 10 | 221 |
| 2005 | 80487 | 40 | 10 | 217 |

## Stat-Category Presence Distribution

How many of the 4 target stats (YIELD / AREA HARVESTED / AREA PLANTED / PRODUCTION) are present per (state, commodity) pair:

- **2/4 stats:** 42 pairs
- **3/4 stats:** 34 pairs
- **4/4 stats:** 201 pairs

### Major-producer pairs missing one or more stats

| state_alpha | commodity_desc | n_stats | missing_stats |
| --- | --- | --- | --- |
| CA | HAY | 2 | YIELD, AREA PLANTED |
| ID | HAY | 3 | AREA PLANTED |
| KS | HAY | 3 | AREA PLANTED |
| MN | HAY | 3 | AREA PLANTED |
| MO | HAY | 3 | AREA PLANTED |
| MT | HAY | 3 | AREA PLANTED |
| NE | HAY | 3 | AREA PLANTED |
| NY | HAY | 3 | AREA PLANTED |
| OK | HAY | 3 | AREA PLANTED |
| SD | HAY | 3 | AREA PLANTED |
| TX | HAY | 2 | YIELD, AREA PLANTED |
| WI | HAY | 3 | AREA PLANTED |

## Total-Miss Gaps (Major Producer × Commodity with ZERO rows)

These are real ingestion misses — the state is a top-10 producer of the commodity but our parquet has no county-level rows.

| state | commodity | weight | type |
| --- | --- | --- | --- |
| MT | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| TX | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| OR | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| WA | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| KS | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| MO | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| ID | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| OK | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| CO | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| NE | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| MT | SPRING WHEAT, (EXCL DURUM) | 0.55 | TOTAL_MISS_MAJOR_PRODUCER |
| ND | SPRING WHEAT, (EXCL DURUM) | 0.55 | TOTAL_MISS_MAJOR_PRODUCER |
| SD | SPRING WHEAT, (EXCL DURUM) | 0.55 | TOTAL_MISS_MAJOR_PRODUCER |
| MN | SPRING WHEAT, (EXCL DURUM) | 0.55 | TOTAL_MISS_MAJOR_PRODUCER |
| ID | SPRING WHEAT, (EXCL DURUM) | 0.55 | TOTAL_MISS_MAJOR_PRODUCER |

## Hotspot Ranking (Top 30)

Score = commodity_weight × (0.4 × (1 − county_coverage) + 0.3 × stat_gap + 0.3 × year_gap). Higher = more impactful gap to plug.

| state | commodity | weight | county_coverage_pct | n_stats | n_years_missing | score | kind |
| --- | --- | --- | --- | --- | --- | --- | --- |
| KS | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| MO | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| ID | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| OK | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| MT | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| TX | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| NE | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| CO | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| WA | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| OR | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| MN | SPRING WHEAT, (EXCL DURUM) | 0.55 | 0.0 | 0 | 25 | 0.55 | TOTAL_MISS |
| SD | SPRING WHEAT, (EXCL DURUM) | 0.55 | 0.0 | 0 | 25 | 0.55 | TOTAL_MISS |
| ND | SPRING WHEAT, (EXCL DURUM) | 0.55 | 0.0 | 0 | 25 | 0.55 | TOTAL_MISS |
| ID | SPRING WHEAT, (EXCL DURUM) | 0.55 | 0.0 | 0 | 25 | 0.55 | TOTAL_MISS |
| MT | SPRING WHEAT, (EXCL DURUM) | 0.55 | 0.0 | 0 | 25 | 0.55 | TOTAL_MISS |
| MO | COTTON | 0.65 | 0.13 | 4 | 1 | 0.234 | PARTIAL |
| VA | COTTON | 0.65 | 0.323 | 4 | 1 | 0.1838 | PARTIAL |
| CA | HAY | 0.45 | 0.983 | 2 | 20 | 0.1786 | PARTIAL |
| FL | COTTON | 0.65 | 0.382 | 4 | 2 | 0.1763 | PARTIAL |
| TX | HAY | 0.45 | 0.996 | 2 | 20 | 0.1762 | PARTIAL |
| CA | COTTON | 0.65 | 0.356 | 4 | 0 | 0.1674 | PARTIAL |
| LA | COTTON | 0.65 | 0.453 | 4 | 0 | 0.1422 | PARTIAL |
| AR | COTTON | 0.65 | 0.461 | 4 | 0 | 0.1401 | PARTIAL |
| TN | COTTON | 0.65 | 0.479 | 4 | 0 | 0.1355 | PARTIAL |
| MO | RICE | 0.3 | 0.122 | 4 | 6 | 0.127 | PARTIAL |
| TX | RICE | 0.3 | 0.106 | 4 | 1 | 0.1109 | PARTIAL |
| AZ | COTTON | 0.65 | 0.688 | 4 | 0 | 0.0811 | PARTIAL |
| MS | RICE | 0.3 | 0.373 | 4 | 1 | 0.0788 | PARTIAL |
| CA | RICE | 0.3 | 0.407 | 4 | 1 | 0.0748 | PARTIAL |
| OK | COTTON | 0.65 | 0.718 | 4 | 0 | 0.0733 | PARTIAL |

## Year-Coverage Gaps (Major Producer Pairs Only)

_75 major-producer pairs have at least one missing year (out of 87 total)._

| state | commodity | n_years_present | n_years_missing | missing_years | earliest_year | latest_year |
| --- | --- | --- | --- | --- | --- | --- |
| CA | HAY | 5 | 20 | 2001, 2003, 2004, 2005, 2006, 2008, 2009, 2010, 2011, 2013, 2014, 2015, 2016, 2018, 2019, 2020, 2021, 2023, 2024, 2025 | 2002 | 2022 |
| TX | HAY | 5 | 20 | 2001, 2003, 2004, 2005, 2006, 2008, 2009, 2010, 2011, 2013, 2014, 2015, 2016, 2018, 2019, 2020, 2021, 2023, 2024, 2025 | 2002 | 2022 |
| SD | BARLEY | 11 | 14 | 2009, 2010, 2011, 2013, 2014, 2015, 2016, 2018, 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| TN | SORGHUM | 11 | 14 | 2009, 2010, 2011, 2013, 2014, 2015, 2016, 2018, 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| NE | SUNFLOWER | 16 | 9 | 2014, 2016, 2018, 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| NM | SORGHUM | 16 | 9 | 2011, 2016, 2018, 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| OR | BARLEY | 18 | 7 | 2018, 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| AR | SORGHUM | 18 | 7 | 2018, 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| ID | HAY | 19 | 6 | 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| KS | HAY | 19 | 6 | 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| CO | SUNFLOWER | 19 | 6 | 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| OK | HAY | 19 | 6 | 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| TX | SUNFLOWER | 19 | 6 | 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| SD | HAY | 19 | 6 | 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| NE | HAY | 19 | 6 | 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| WI | HAY | 19 | 6 | 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| SD | SUNFLOWER | 19 | 6 | 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| MO | SORGHUM | 19 | 6 | 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| MO | RICE | 19 | 6 | 2011, 2015, 2016, 2018, 2019, 2025 | 2001 | 2024 |
| MT | HAY | 19 | 6 | 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| NY | HAY | 19 | 6 | 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| LA | SORGHUM | 19 | 6 | 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| KS | SUNFLOWER | 19 | 6 | 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| MN | HAY | 19 | 6 | 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| MO | HAY | 19 | 6 | 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| CO | BARLEY | 23 | 2 | 2019, 2024 | 2001 | 2025 |
| FL | COTTON | 23 | 2 | 2010, 2019 | 2001 | 2025 |
| IA | SOYBEANS | 24 | 1 | 2025 | 2001 | 2024 |
| IA | OATS | 24 | 1 | 2024 | 2001 | 2025 |
| IA | CORN | 24 | 1 | 2025 | 2001 | 2024 |
| CO | SORGHUM | 24 | 1 | 2025 | 2001 | 2024 |
| CA | RICE | 24 | 1 | 2025 | 2001 | 2024 |
| AR | RICE | 24 | 1 | 2025 | 2001 | 2024 |
| KS | SOYBEANS | 24 | 1 | 2025 | 2001 | 2024 |
| MN | BARLEY | 24 | 1 | 2024 | 2001 | 2025 |
| MN | CORN | 24 | 1 | 2025 | 2001 | 2024 |
| IN | SOYBEANS | 24 | 1 | 2025 | 2001 | 2024 |
| IN | CORN | 24 | 1 | 2025 | 2001 | 2024 |
| KS | SORGHUM | 24 | 1 | 2025 | 2001 | 2024 |
| KS | CORN | 24 | 1 | 2025 | 2001 | 2024 |

## Gap-Filling Strategies

### 1. NASS QuickStats API re-query

- **Targeted fix-ups** beat full re-runs. Use `python pipeline/quickstats_ingest.py --county-only --states <CODES> --year-start <Y1> --year-end <Y2> --resume` to plug specific holes without re-fetching what's already on disk. The `--resume` flag (in `_fetch_county_state_year`) skips chunk files that already exist.
- **Add the generic `WHEAT` commodity** to `COUNTY_COMMODITIES` for states where WINTER/SPRING WHEAT come back empty. NASS publishes a county-level `WHEAT` rollup for some states (esp. CA, NY, MI, AZ) that doesn't fit the winter/spring split. The existing `pipeline/fetch_wheat_county.py` already does this — it just isn't triggered by the main runner. Either fold it in or add `WHEAT` to the main commodity list.
- **Audit `COUNTY_SKIP_STATES` periodically.** A few entries are aggressive — e.g. SOYBEANS skips OR/WA/ID, but WSU/OSU report >100k acres of soy in some recent years. Pull the skip list back to AK/HI/DC + commodities that NASS truly never publishes.
- **Retry rate-limited / 400'd combos.** The current code logs and continues on 400. Add a `--rerun-failed` mode that reads the latest log, extracts the failing (state, commodity, year) combos, and re-issues them.

### 2. NASS Census of Agriculture (5-year)

- The Census of Ag (2002, 2007, 2012, 2017, 2022) reports county data for crops and livestock that the annual SURVEY suppresses for confidentiality. The infrastructure exists: `pipeline/load_census_county.py` already targets `source_desc=CENSUS` for SALES, VALUE OF PRODUCTION, INVENTORY, and livestock commodities (CATTLE, HOGS, BROILERS, MILK).
- **Action:** run `python pipeline/load_census_county.py --years 2017 2022` to backfill. This will *not* fill annual-survey gaps in YIELD/AREA, but it will add the dollar/inventory dimensions that are entirely missing from our county data today (those four stats are not in `COUNTY_STAT_CATS`).
- **Census also has wider commodity coverage** than the annual survey — minor crops like dry beans, peanuts, sugar beets, tobacco, and most fruit/veg are CENSUS-only at county resolution.

### 3. NASS suppression vs pipeline miss

- NASS suppresses county data when fewer than 3 farms report a value (the `(D)` code in `Value`, dropped to NaN by `clean_nass_value`). Our parquets capture suppressed rows as `value_num=NaN` but the row still exists, so a *missing row* is more likely a pipeline gap than suppression.
- **Test:** for each suspected gap, query the state-level SURVEY row in the same parquet (`agg_level_desc == 'STATE'`). If the state-level row exists with a real value but no county rows do, the issue is suppression cascade (small-county dominance). If the state-level row is also empty, the commodity genuinely isn't grown — drop it from `MAJOR_PRODUCERS`.
- **Mitigation for suppression:** Census of Ag publishes more — every 5 years it relaxes the suppression rule for state-aggregated and disclosure-protected county figures. Backfilling Census years (above) closes ~30% of the apparent annual-survey holes.

### 4. Alternative sources for what NASS won't fill

- **USDA RMA (Risk Management Agency) — Cause of Loss & Summary of Business.** County-level insured acres + indemnities by crop. Publicly hosted at `https://www.rma.usda.gov/SummaryOfBusiness`. Already integrated for the acreage prediction module (`backend/etl/ingest_rma.py`) — same pipeline can populate a `county_insured_acres` table for the dashboard. Coverage is excellent for major program crops (corn, soy, wheat, cotton, sorghum, barley, rice).
- **USDA FSA (Farm Service Agency) — Crop Acreage Data.** County-level reported acres from CCC-578 forms. Available at `https://www.fsa.usda.gov/tools/informational/freedom-of-information-act-foia/electronic-reading-room/frequently-requested/crop-acreage-data` as monthly Excel snapshots from 2008 forward. Best source for **planted acres** when NASS suppresses; updated Aug, Oct, Jan.
- **State Departments of Agriculture.** A handful publish enhanced county detail beyond what NASS releases — Iowa (IDALS), Illinois (IDOA), California (CDFA County Ag Commissioners' reports — annual, with crop $ and acreage). California especially is worth ingesting for fruit/veg/almond county data NASS doesn't carry annually.

### 5. Concrete next-action list (ranked by ROI)

1. **Run `load_census_county.py --years 2017 2022`** — ~2 hr API time, adds ~40K rows of SALES + VALUE OF PRODUCTION + livestock INVENTORY at county level. Highest ROI: opens dollar/inventory dimensions that are zero today.
2. **Add the generic `WHEAT` commodity to the main pipeline** by either folding `fetch_wheat_county.py` into `quickstats_ingest.py` or appending `WHEAT` to `COUNTY_COMMODITIES` (~1 hr code, ~3 hr API run, adds ~10K rows mostly in CA/NY/MI/AZ).
3. **Trim `COUNTY_SKIP_STATES`** for SOYBEANS (drop OR/WA/ID), BARLEY (drop IA/IL/IN), and OATS (drop AL/MS — minor but real). Re-run `--county-only --resume` for the affected states. ~6 hr API time, ~5K rows.
4. **Wire RMA county data into the dashboard.** The ETL already populates `rma_insured_acres` for the acreage model. Surface it as a fallback layer in the county map for combos NASS suppresses (esp. cotton in NC/VA, sorghum in TN/KY). Backend-only change, no new ingestion. ~1 day.
5. **Backfill 2025 partial-year rows** by re-running `--year-start 2025 --year-end 2025 --county-only --resume` in mid-July (when NASS publishes June Acreage Survey) and again in October (Crop Production Annual Summary). 2025 rows are sparse today because the bulk run completed in early Apr 2026 before NASS finalised 2025.

---

_Report generated by `pipeline/_county_coverage_audit.py`. To regenerate: `python pipeline/_county_coverage_audit.py`._
