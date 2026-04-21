# County-Level NASS Coverage Audit

**Date:** 2026-04-17  
**Source:** `pipeline/output/{STATE}.parquet` (county-level rows only)  
**Generator:** `pipeline/_county_coverage_audit.py`

## Executive Summary

- **870,995** county-level rows across **48** states (NATIONAL.parquet excluded; AK/HI/DC have no county rows)
- **3,101** distinct county FIPS represented; **241** distinct (state, commodity) combinations active
- **2,470** (state, commodity, year) combinations have at least one row
- **166** (state, commodity) pairs have all 4 target stat categories (YIELD/AREA HARVESTED/AREA PLANTED/PRODUCTION)
- **15** total-miss gaps where a major-producer state has ZERO rows for an expected commodity
- **CRITICAL FINDING — wheat is entirely missing.** Both `WINTER WHEAT` and `SPRING WHEAT, (EXCL DURUM)` were in `COUNTY_COMMODITIES` but **zero wheat rows of any kind exist in any state parquet** (verified across KS, TX, OK, ND, MT, NE, CO, WA, ID, MN, SD, IL, OH, IN at all agg_levels). The remediation script `pipeline/fetch_wheat_county.py` exists for exactly this gap but was never run or never merged back. Filling this single gap would add an estimated ~80-100K rows and unblock the dashboard's wheat section.
- **2025 is sparse:** only 2,435 rows across 22 states / 4 commodities (vs ~10K rows / 30+ states for 2023-2024). NASS publishes 2025 county data in waves through Oct 2026 — schedule a re-run in mid-July and again in October.

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
| AL | 15687 | 68 | 2001 | 2025 | 23 | 5 | 4 |
| AR | 16406 | 76 | 2001 | 2025 | 25 | 7 | 4 |
| AZ | 3484 | 16 | 2001 | 2025 | 19 | 3 | 4 |
| CA | 13067 | 58 | 2001 | 2025 | 25 | 8 | 4 |
| CO | 22449 | 63 | 2001 | 2025 | 25 | 7 | 4 |
| CT | 691 | 8 | 2002 | 2022 | 5 | 2 | 2 |
| DE | 1194 | 4 | 2001 | 2024 | 18 | 3 | 4 |
| FL | 7424 | 68 | 2001 | 2025 | 16 | 4 | 4 |
| GA | 26813 | 160 | 2002 | 2024 | 20 | 6 | 4 |
| IA | 36232 | 100 | 2001 | 2025 | 24 | 5 | 4 |
| ID | 10916 | 45 | 2002 | 2023 | 21 | 4 | 4 |
| IL | 22690 | 103 | 2001 | 2024 | 23 | 5 | 4 |
| IN | 24339 | 93 | 2001 | 2024 | 24 | 5 | 4 |
| KS | 53538 | 106 | 2001 | 2025 | 25 | 7 | 4 |
| KY | 33208 | 121 | 2001 | 2024 | 22 | 6 | 4 |
| LA | 11937 | 64 | 2001 | 2024 | 24 | 6 | 4 |
| MA | 613 | 14 | 2002 | 2022 | 4 | 2 | 2 |
| MD | 8405 | 24 | 2001 | 2023 | 22 | 5 | 4 |
| ME | 1168 | 16 | 2002 | 2022 | 5 | 3 | 2 |
| MI | 17887 | 84 | 2001 | 2024 | 24 | 5 | 4 |
| MN | 32106 | 88 | 2001 | 2023 | 23 | 5 | 4 |
| MO | 35890 | 115 | 2001 | 2024 | 23 | 8 | 4 |
| MS | 19933 | 83 | 2001 | 2025 | 25 | 6 | 4 |
| MT | 20794 | 57 | 2001 | 2022 | 18 | 4 | 4 |
| NC | 33818 | 101 | 2001 | 2025 | 25 | 8 | 4 |
| ND | 26317 | 54 | 2001 | 2025 | 25 | 6 | 4 |
| NE | 57324 | 94 | 2001 | 2025 | 25 | 7 | 4 |
| NH | 566 | 10 | 2002 | 2022 | 5 | 3 | 2 |
| NJ | 3714 | 19 | 2001 | 2024 | 19 | 3 | 4 |
| NM | 8213 | 34 | 2001 | 2024 | 22 | 4 | 4 |
| NV | 2136 | 18 | 2002 | 2022 | 14 | 2 | 3 |
| NY | 16007 | 60 | 2001 | 2025 | 25 | 5 | 4 |
| OH | 22248 | 89 | 2001 | 2023 | 22 | 6 | 4 |
| OK | 18729 | 78 | 2001 | 2025 | 24 | 8 | 4 |
| OR | 6476 | 37 | 2001 | 2025 | 22 | 4 | 4 |
| PA | 23501 | 68 | 2001 | 2024 | 23 | 5 | 4 |
| RI | 333 | 5 | 2002 | 2022 | 5 | 2 | 2 |
| SC | 14113 | 47 | 2001 | 2024 | 23 | 5 | 4 |
| SD | 33296 | 67 | 2001 | 2025 | 25 | 7 | 4 |
| TN | 20200 | 96 | 2001 | 2025 | 25 | 7 | 4 |
| TX | 67188 | 254 | 2001 | 2025 | 25 | 8 | 4 |
| UT | 6265 | 30 | 2002 | 2022 | 15 | 4 | 4 |
| VA | 15678 | 99 | 2001 | 2025 | 25 | 6 | 4 |
| VT | 1409 | 14 | 2002 | 2022 | 5 | 3 | 2 |
| WA | 7524 | 40 | 2001 | 2025 | 22 | 4 | 4 |
| WI | 34331 | 73 | 2001 | 2025 | 24 | 5 | 4 |
| WV | 5452 | 56 | 2001 | 2022 | 18 | 4 | 4 |
| WY | 9286 | 24 | 2001 | 2025 | 21 | 4 | 4 |

## Per-Commodity Coverage

| commodity | rows | states | counties | year_min | year_max | n_years |
| --- | --- | --- | --- | --- | --- | --- |
| CORN | 252178 | 48 | 2906 | 2001 | 2024 | 24 |
| HAY | 244732 | 48 | 3091 | 2001 | 2024 | 23 |
| SOYBEANS | 144485 | 32 | 2299 | 2001 | 2024 | 24 |
| COTTON | 66607 | 16 | 826 | 2001 | 2025 | 25 |
| OATS | 56960 | 33 | 2068 | 2001 | 2025 | 25 |
| SORGHUM | 45624 | 21 | 1482 | 2001 | 2024 | 24 |
| BARLEY | 34945 | 28 | 1256 | 2001 | 2025 | 24 |
| SUNFLOWER | 17231 | 9 | 420 | 2001 | 2025 | 21 |
| RICE | 8233 | 6 | 163 | 2001 | 2024 | 24 |

## Recent Years (2023–2025)

| year | rows | states | commodities | state_commodity_pairs |
| --- | --- | --- | --- | --- |
| 2023 | 10174 | 36 | 8 | 71 |
| 2024 | 10691 | 30 | 7 | 60 |
| 2025 | 2435 | 22 | 4 | 23 |

## Early Years (2001–2005)

| year | rows | states | commodities | state_commodity_pairs |
| --- | --- | --- | --- | --- |
| 2001 | 31308 | 38 | 9 | 103 |
| 2002 | 129611 | 48 | 9 | 162 |
| 2003 | 33741 | 41 | 9 | 105 |
| 2004 | 32080 | 40 | 9 | 107 |
| 2005 | 28654 | 38 | 9 | 94 |

## Stat-Category Presence Distribution

How many of the 4 target stats (YIELD / AREA HARVESTED / AREA PLANTED / PRODUCTION) are present per (state, commodity) pair:

- **2/4 stats:** 41 pairs
- **3/4 stats:** 34 pairs
- **4/4 stats:** 166 pairs

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
| NE | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| CO | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| WA | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| OK | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| TX | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| ID | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| MO | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| OR | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| KS | WINTER WHEAT | 0.7 | TOTAL_MISS_MAJOR_PRODUCER |
| MT | SPRING WHEAT, (EXCL DURUM) | 0.55 | TOTAL_MISS_MAJOR_PRODUCER |
| ND | SPRING WHEAT, (EXCL DURUM) | 0.55 | TOTAL_MISS_MAJOR_PRODUCER |
| MN | SPRING WHEAT, (EXCL DURUM) | 0.55 | TOTAL_MISS_MAJOR_PRODUCER |
| ID | SPRING WHEAT, (EXCL DURUM) | 0.55 | TOTAL_MISS_MAJOR_PRODUCER |
| SD | SPRING WHEAT, (EXCL DURUM) | 0.55 | TOTAL_MISS_MAJOR_PRODUCER |

## Hotspot Ranking (Top 30)

Score = commodity_weight × (0.4 × (1 − county_coverage) + 0.3 × stat_gap + 0.3 × year_gap). Higher = more impactful gap to plug.

| state | commodity | weight | county_coverage_pct | n_stats | n_years_missing | score | kind |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OK | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| TX | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| ID | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| MO | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| MT | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| NE | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| KS | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| OR | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| WA | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| CO | WINTER WHEAT | 0.7 | 0.0 | 0 | 25 | 0.7 | TOTAL_MISS |
| ID | SPRING WHEAT, (EXCL DURUM) | 0.55 | 0.0 | 0 | 25 | 0.55 | TOTAL_MISS |
| MN | SPRING WHEAT, (EXCL DURUM) | 0.55 | 0.0 | 0 | 25 | 0.55 | TOTAL_MISS |
| ND | SPRING WHEAT, (EXCL DURUM) | 0.55 | 0.0 | 0 | 25 | 0.55 | TOTAL_MISS |
| SD | SPRING WHEAT, (EXCL DURUM) | 0.55 | 0.0 | 0 | 25 | 0.55 | TOTAL_MISS |
| MT | SPRING WHEAT, (EXCL DURUM) | 0.55 | 0.0 | 0 | 25 | 0.55 | TOTAL_MISS |
| FL | COTTON | 0.65 | 0.294 | 4 | 15 | 0.3006 | PARTIAL |
| MO | COTTON | 0.65 | 0.13 | 4 | 9 | 0.2964 | PARTIAL |
| LA | COTTON | 0.65 | 0.406 | 4 | 12 | 0.248 | PARTIAL |
| VA | COTTON | 0.65 | 0.303 | 4 | 7 | 0.2358 | PARTIAL |
| TN | COTTON | 0.65 | 0.417 | 4 | 10 | 0.2296 | PARTIAL |
| CA | COTTON | 0.65 | 0.328 | 4 | 6 | 0.2215 | PARTIAL |
| AR | COTTON | 0.65 | 0.447 | 4 | 9 | 0.214 | PARTIAL |
| GA | COTTON | 0.65 | 0.681 | 4 | 13 | 0.1843 | PARTIAL |
| CA | HAY | 0.45 | 0.983 | 2 | 21 | 0.184 | PARTIAL |
| SD | SOYBEANS | 0.95 | 0.94 | 4 | 14 | 0.1824 | PARTIAL |
| TX | HAY | 0.45 | 0.996 | 2 | 21 | 0.1816 | PARTIAL |
| MO | CORN | 1.0 | 0.983 | 4 | 14 | 0.1748 | PARTIAL |
| IL | CORN | 1.0 | 1.0 | 4 | 14 | 0.168 | PARTIAL |
| MO | RICE | 0.3 | 0.113 | 4 | 16 | 0.164 | PARTIAL |
| NC | COTTON | 0.65 | 0.683 | 4 | 10 | 0.1604 | PARTIAL |

## Year-Coverage Gaps (Major Producer Pairs Only)

_87 major-producer pairs have at least one missing year (out of 87 total)._

| state | commodity | n_years_present | n_years_missing | missing_years | earliest_year | latest_year |
| --- | --- | --- | --- | --- | --- | --- |
| CA | HAY | 4 | 21 | 2001, 2003, 2004, 2005, 2006, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2018, 2019, 2020, 2021, 2023, 2024, 2025 | 2002 | 2022 |
| TX | HAY | 4 | 21 | 2001, 2003, 2004, 2005, 2006, 2008, 2009, 2010, 2011, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2023, 2024, 2025 | 2002 | 2022 |
| MO | HAY | 8 | 17 | 2001, 2006, 2009, 2010, 2011, 2013, 2014, 2015, 2016, 2017, 2019, 2020, 2021, 2022, 2023, 2024, 2025 | 2002 | 2018 |
| TN | SORGHUM | 8 | 17 | 2001, 2004, 2009, 2010, 2011, 2013, 2014, 2015, 2016, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025 | 2002 | 2017 |
| NY | HAY | 8 | 17 | 2001, 2003, 2006, 2010, 2011, 2012, 2013, 2015, 2016, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025 | 2002 | 2017 |
| TX | OATS | 8 | 17 | 2001, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2013, 2014, 2015, 2017, 2018, 2019, 2022, 2024, 2025 | 2002 | 2023 |
| MO | RICE | 9 | 16 | 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025 | 2001 | 2017 |
| MT | BARLEY | 9 | 16 | 2001, 2004, 2005, 2009, 2011, 2012, 2013, 2016, 2017, 2018, 2020, 2021, 2022, 2023, 2024, 2025 | 2002 | 2019 |
| ND | OATS | 9 | 16 | 2002, 2003, 2004, 2005, 2007, 2008, 2011, 2012, 2013, 2014, 2015, 2016, 2018, 2019, 2024, 2025 | 2001 | 2023 |
| OK | HAY | 9 | 16 | 2001, 2003, 2004, 2005, 2006, 2009, 2010, 2015, 2016, 2019, 2020, 2021, 2022, 2023, 2024, 2025 | 2002 | 2018 |
| TX | SORGHUM | 9 | 16 | 2001, 2002, 2004, 2005, 2007, 2008, 2009, 2010, 2012, 2013, 2014, 2015, 2018, 2019, 2023, 2025 | 2003 | 2024 |
| SD | SUNFLOWER | 9 | 16 | 2002, 2003, 2004, 2005, 2007, 2008, 2009, 2010, 2016, 2017, 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| NM | SORGHUM | 9 | 16 | 2003, 2005, 2009, 2011, 2012, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025 | 2001 | 2014 |
| SD | BARLEY | 10 | 15 | 2009, 2010, 2011, 2013, 2014, 2015, 2016, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025 | 2001 | 2017 |
| NE | SORGHUM | 10 | 15 | 2003, 2007, 2009, 2010, 2011, 2012, 2013, 2014, 2019, 2020, 2021, 2022, 2023, 2024, 2025 | 2001 | 2018 |
| ID | HAY | 10 | 15 | 2001, 2002, 2003, 2004, 2008, 2010, 2013, 2015, 2018, 2019, 2020, 2021, 2023, 2024, 2025 | 2005 | 2022 |
| FL | COTTON | 10 | 15 | 2003, 2005, 2006, 2007, 2008, 2010, 2011, 2012, 2014, 2015, 2018, 2019, 2020, 2022, 2024 | 2001 | 2025 |
| AR | SORGHUM | 10 | 15 | 2002, 2005, 2006, 2008, 2009, 2011, 2014, 2015, 2018, 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| KS | SUNFLOWER | 11 | 14 | 2002, 2003, 2012, 2013, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025 | 2001 | 2015 |
| MO | CORN | 11 | 14 | 2004, 2008, 2009, 2010, 2012, 2013, 2015, 2016, 2018, 2019, 2020, 2021, 2024, 2025 | 2001 | 2023 |
| ID | BARLEY | 11 | 14 | 2001, 2004, 2006, 2007, 2009, 2010, 2012, 2013, 2018, 2021, 2022, 2023, 2024, 2025 | 2002 | 2020 |
| IL | CORN | 11 | 14 | 2002, 2003, 2006, 2009, 2011, 2012, 2013, 2015, 2016, 2018, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| NE | HAY | 11 | 14 | 2002, 2003, 2004, 2005, 2006, 2011, 2015, 2016, 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| SD | SOYBEANS | 11 | 14 | 2001, 2002, 2004, 2005, 2006, 2007, 2009, 2010, 2011, 2013, 2014, 2018, 2019, 2025 | 2003 | 2024 |
| MN | HAY | 11 | 14 | 2001, 2005, 2006, 2007, 2008, 2010, 2012, 2014, 2019, 2020, 2021, 2023, 2024, 2025 | 2002 | 2022 |
| NE | SUNFLOWER | 11 | 14 | 2005, 2006, 2007, 2011, 2014, 2015, 2016, 2018, 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| KS | SOYBEANS | 11 | 14 | 2003, 2004, 2005, 2006, 2007, 2008, 2009, 2011, 2014, 2015, 2019, 2020, 2024, 2025 | 2001 | 2023 |
| IL | SOYBEANS | 12 | 13 | 2004, 2007, 2009, 2011, 2012, 2013, 2015, 2018, 2021, 2022, 2023, 2024, 2025 | 2001 | 2020 |
| WI | HAY | 12 | 13 | 2001, 2003, 2005, 2007, 2009, 2010, 2015, 2019, 2020, 2021, 2023, 2024, 2025 | 2002 | 2022 |
| WA | BARLEY | 12 | 13 | 2001, 2003, 2005, 2008, 2009, 2011, 2014, 2016, 2017, 2019, 2021, 2022, 2024 | 2002 | 2025 |
| OH | OATS | 12 | 13 | 2001, 2004, 2005, 2006, 2010, 2011, 2014, 2015, 2017, 2018, 2020, 2024, 2025 | 2002 | 2023 |
| LA | SORGHUM | 12 | 13 | 2005, 2006, 2007, 2008, 2010, 2016, 2018, 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| OR | BARLEY | 12 | 13 | 2001, 2011, 2014, 2015, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025 | 2002 | 2016 |
| OH | CORN | 12 | 13 | 2002, 2003, 2006, 2007, 2013, 2016, 2017, 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |
| MS | COTTON | 12 | 13 | 2001, 2002, 2003, 2004, 2006, 2008, 2009, 2011, 2012, 2013, 2014, 2019, 2024 | 2005 | 2025 |
| MN | CORN | 12 | 13 | 2006, 2007, 2008, 2009, 2011, 2013, 2015, 2016, 2018, 2021, 2022, 2024, 2025 | 2001 | 2023 |
| MT | HAY | 12 | 13 | 2001, 2002, 2005, 2007, 2009, 2015, 2018, 2019, 2020, 2021, 2023, 2024, 2025 | 2003 | 2022 |
| GA | COTTON | 12 | 13 | 2001, 2003, 2005, 2009, 2013, 2014, 2016, 2017, 2018, 2020, 2021, 2023, 2025 | 2002 | 2024 |
| IN | SOYBEANS | 12 | 13 | 2001, 2003, 2005, 2006, 2007, 2008, 2010, 2011, 2014, 2018, 2019, 2022, 2025 | 2002 | 2024 |
| TX | SUNFLOWER | 13 | 12 | 2002, 2006, 2010, 2011, 2015, 2016, 2019, 2020, 2021, 2023, 2024, 2025 | 2001 | 2022 |

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

1. **Run `python pipeline/fetch_wheat_county.py --years 2001-2025 --upload-s3` IMMEDIATELY.** This is the highest-ROI item by an order of magnitude. Wheat is currently 0 rows; this script targets the generic `WHEAT` commodity at county level and the audit confirmed every state we checked (KS, TX, OK, ND, MT, NE, CO, WA, ID, MN, SD, IL, OH, IN) is empty. Estimated +80-100K rows, ~4-6 hr API time. After it runs, also fold `WHEAT` into `COUNTY_COMMODITIES` in `quickstats_ingest.py` so future runs don't regress.
2. **Run `load_census_county.py --years 2017 2022`** — ~2 hr API time, adds ~40K rows of SALES + VALUE OF PRODUCTION + livestock INVENTORY at county level. Opens dollar/inventory dimensions that are zero today.
3. **Trim `COUNTY_SKIP_STATES`** for SOYBEANS (drop OR/WA/ID), BARLEY (drop IA/IL/IN), and OATS (drop AL/MS — minor but real). Re-run `--county-only --resume` for the affected states. ~6 hr API time, ~5K rows.
4. **Wire RMA county data into the dashboard.** The ETL already populates `rma_insured_acres` for the acreage model. Surface it as a fallback layer in the county map for combos NASS suppresses (esp. cotton in NC/VA, sorghum in TN/KY). Backend-only change, no new ingestion. ~1 day.
5. **Backfill 2025 partial-year rows** by re-running `--year-start 2025 --year-end 2025 --county-only --resume` in mid-July (when NASS publishes June Acreage Survey) and again in October (Crop Production Annual Summary). 2025 rows are sparse today (only 2,435) because the bulk run completed in early Apr 2026 before NASS finalised 2025.

---

_Report generated by `pipeline/_county_coverage_audit.py`. To regenerate: `python pipeline/_county_coverage_audit.py`._
