# County-Level Ingestion Implementation

## quickstats_ingest.py
- [x] Add US_STATE_CODES constant
- [x] Add COUNTY_COMMODITIES, COUNTY_STAT_CATS, COUNTY_REQUEST_DELAY constants
- [ ] Add fetch_county_data() function with ThreadPoolExecutor
- [ ] Update enrich_dataframe() to skip county rows
- [ ] Update run_ingestion() to accept/run county phase
- [ ] Update CLI args (--include-county, --county-only)

## incremental_check.py
- [ ] Add COUNTY agg_level to check params for recent years

## validate_data.py
- [ ] Add county FIPS format validation check
- [ ] Add county row count check

## load_census_county.py (new)
- [ ] Create one-time Census-of-Ag county loader script

## aws_setup.sh
- [ ] Add county_fips as Glue table secondary sort key
