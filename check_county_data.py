import pandas as pd

# Check if we have county-level data
state_file = 'web_app/final_data/IN.parquet'
df = pd.read_parquet(state_file)

print("=" * 80)
print("Checking for County-Level Data")
print("=" * 80)

# Check for county columns
county_cols = [c for c in df.columns if 'county' in c.lower()]
print(f"\nCounty-related columns: {county_cols}")

# Check agg_level_desc values
if 'agg_level_desc' in df.columns:
    print("\n--- Aggregation Levels ---")
    print(df['agg_level_desc'].value_counts())

# If we have county data, show samples
if county_cols:
    for col in county_cols:
        print(f"\n--- {col} values (first 20) ---")
        unique_vals = df[col].dropna().unique()[:20]
        print(unique_vals)
    
    # Show sample county data
    print("\n--- Sample County Data ---")
    county_data = df[df['agg_level_desc'] == 'COUNTY'] if 'agg_level_desc' in df.columns else df[df[county_cols[0]].notna()]
    if len(county_data) > 0:
        print(f"Total county-level rows: {len(county_data)}")
        cols_to_show = ['year', 'commodity_desc', 'statisticcat_desc', 'value_num'] + county_cols
        cols_to_show = [c for c in cols_to_show if c in county_data.columns]
        print(county_data[cols_to_show].head(10).to_string())
    else:
        print("No county-level data found")
