import pandas as pd

# Load the raw CSV file
file_path = r'C:\Users\rajas\Documents\VS_Code\Agricultural_Data_Analysis\raw_data\nass_crops_field_crops.csv'

print("=" * 80)
print("Exploring Raw CSV for PCT OF MKTG YEAR data")
print("=" * 80)

# Read just a sample first to see columns
df_sample = pd.read_csv(file_path, nrows=1000)

print("\n--- All Columns ---")
print(df_sample.columns.tolist())

# Now filter to PCT OF MKTG YEAR data specifically
print("\n\n--- Filtering to PCT OF MKTG YEAR Sales ---")
df_full = pd.read_csv(file_path)

pct_data = df_full[
    (df_full['unit_desc'] == 'PCT OF MKTG YEAR') & 
    (df_full['statisticcat_desc'] == 'SALES')
].copy()

print(f"\nTotal PCT OF MKTG YEAR SALES rows: {len(pct_data)}")

# Check for time-related columns
time_cols = ['reference_period_desc', 'week_ending', 'begin_code', 'end_code', 
             'freq_desc', 'month', 'period']
available_time_cols = [c for c in time_cols if c in pct_data.columns]

print(f"\nTime-related columns available: {available_time_cols}")

# Show sample data with time columns
if available_time_cols:
    print("\n--- Sample PCT OF MKTG YEAR data with time information ---")
    cols_to_show = ['year', 'state_name', 'commodity_desc', 'Value'] + available_time_cols
    cols_to_show = [c for c in cols_to_show if c in pct_data.columns]
    
    # Get corn data specifically
    corn_pct = pct_data[pct_data['commodity_desc'] == 'CORN'].copy()
    print(f"\nCORN PCT OF MKTG YEAR rows: {len(corn_pct)}")
    
    if len(corn_pct) > 0:
        print("\nSample CORN data:")
        print(corn_pct[cols_to_show].head(20).to_string())
        
        # Check unique values for time columns
        for col in available_time_cols:
            if col in corn_pct.columns:
                print(f"\n--- Unique {col} values (first 20) ---")
                unique_vals = corn_pct[col].unique()[:20]
                print(unique_vals)
        
        # Check if we have enough info to map periods
        if 'reference_period_desc' in corn_pct.columns:
            print("\n--- Reference Period Distribution ---")
            print(corn_pct['reference_period_desc'].value_counts().head(20))
else:
    print("\nNO time-related columns found!")
    print("\n--- Available columns ---")
    print(pct_data.columns.tolist())

# Also check if the data has specific month/period breakdown
if 'reference_period_desc' not in pct_data.columns:
    # Check what columns DO exist
    print("\n\n--- Checking all column names for patterns ---")
    all_cols = pct_data.columns.tolist()
    period_cols = [c for c in all_cols if any(x in c.lower() for x in ['period', 'month', 'week', 'date', 'time', 'begin', 'end', 'ref'])]
    print(f"Columns with period/time keywords: {period_cols}")
