import pandas as pd

print("=" * 80)
print("Comparing Raw vs Processed PCT OF MKTG YEAR Data")
print("=" * 80)

# Check raw data
raw_file = r'C:\Users\rajas\Documents\VS_Code\Agricultural_Data_Analysis\raw_data\nass_crops_field_crops.csv'
df_raw = pd.read_csv(raw_file, low_memory=False)

raw_pct = df_raw[
    (df_raw['unit_desc'] == 'PCT OF MKTG YEAR') & 
    (df_raw['statisticcat_desc'] == 'SALES') &
    (df_raw['commodity_desc'] == 'CORN') &
    (df_raw['state_name'] == 'INDIANA')
].copy()

print(f"\n--- RAW DATA ---")
print(f"Total CORN PCT rows for Indiana: {len(raw_pct)}")
if len(raw_pct) > 0:
    print("\nColumns available:")
    cols_of_interest = ['year', 'reference_period_desc', 'Value', 'source_desc', 'begin_code', 'end_code']
    print([c for c in cols_of_interest if c in raw_pct.columns])
    
    print("\nSample (2021):")
    sample_2021 = raw_pct[raw_pct['year'] == 2021][cols_of_interest].head(12)
    print(sample_2021.to_string())

# Check processed data
processed_file = r'C:\Users\rajas\Documents\VS_Code\Agricultural_Data_Analysis\web_app\final_data\IN.parquet'
df_processed = pd.read_parquet(processed_file)

proc_pct = df_processed[
    (df_processed['unit_desc'] == 'PCT OF MKTG YEAR') & 
    (df_processed['statisticcat_desc'] == 'SALES') &
    (df_processed['commodity_desc'] == 'CORN')
].copy()

print(f"\n\n--- PROCESSED DATA (Parquet) ---")
print(f"Total CORN PCT rows for Indiana: {len(proc_pct)}")
print("\nColumns available:")
print(proc_pct.columns.tolist())

if 'reference_period_desc' in proc_pct.columns:
    print("\n✓ reference_period_desc IS PRESENT in processed data")
    print("\nSample (2021):")
    sample_2021 = proc_pct[proc_pct['year'] == 2021][['year', 'reference_period_desc', 'value_num', 'source_desc']].head(12)
    print(sample_2021.to_string())
else:
    print("\n✗ reference_period_desc was DROPPED during processing")

print("\n\n" + "=" * 80)
print("CONCLUSION")
print("=" * 80)

if 'reference_period_desc' in proc_pct.columns:
    print("\n✓ The time period information IS available in the processed data!")
    print("✓ You CAN calculate monthly revenue estimates using:")
    print("  1. Monthly PCT OF MKTG YEAR values")
    print("  2. Total annual production")
    print("  3. Monthly price data (PRICE RECEIVED)")
    print("\nThis would give you monthly revenue trends for SURVEY years!")
else:
    print("\n✗ The time period information was lost during data processing.")
    print("Check the data_prep.py script to see which columns are kept/dropped.")
