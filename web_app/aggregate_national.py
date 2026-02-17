
import pandas as pd
import os
import glob
import warnings

# Suppress warnings
warnings.filterwarnings('ignore')

# Paths relative to script
FINAL_DATA_DIR = os.path.join(os.getcwd(), 'final_data')
OUTPUT_FILE = os.path.join(FINAL_DATA_DIR, 'NATIONAL.parquet')

def aggregate():
    print("Starting Comprehensive National Aggregation...")
    
    if not os.path.exists(FINAL_DATA_DIR):
        print(f"Error: {FINAL_DATA_DIR} not found.")
        return

    # List sum state parquet files
    # Exclude previously generated NATIONAL.parquet
    state_files = glob.glob(os.path.join(FINAL_DATA_DIR, "*.parquet"))
    state_files = [f for f in state_files if "NATIONAL.parquet" not in f]
    
    if not state_files:
        print("No state files found to aggregate.")
        return
        
    print(f"Found {len(state_files)} state files.")
    
    # Define columns to keep/group
    # Crucial: Include 'state_alpha' and 'agg_level_desc'
    read_cols = [
        'source_desc', 'sector_desc', 'group_desc', 'commodity_desc', 
        'statisticcat_desc', 'unit_desc', 'year', 'domain_desc',
        'state_alpha', 'agg_level_desc', 'value_num'
    ]
    
    group_cols_base = [
        'source_desc', 'sector_desc', 'group_desc', 'commodity_desc', 
        'statisticcat_desc', 'unit_desc', 'year', 'domain_desc'
    ]
    
    all_data = []
    
    print("Reading and Filtering State Files...")
    for f in state_files:
        try:
            df = pd.read_parquet(f, engine='pyarrow')
            
            # Ensure columns exist
            missing_cols = [c for c in read_cols if c not in df.columns]
            if missing_cols:
                # Some files might miss columns if schema varies?
                # skipping for safety or check if critical
                continue

            df = df[read_cols]
            
            # 1. Start with valid numeric values
            df = df.dropna(subset=['value_num'])
            
            # 2. Filter for State Level Data ONLY (exclude County if present)
            # This prevents double counting when we sum states
            df = df[df['agg_level_desc'] == 'STATE']
            
            # 3. Filter out "Total" Commodities (User Request)
            # Remove rows where commodity_desc contains "TOTAL"
            # e.g., "FIELD CROP TOTALS", "VEGETABLE TOTALS"
            df = df[~df['commodity_desc'].str.contains('TOTAL', case=False, na=False)]
            
            if not df.empty:
                all_data.append(df)
                
        except Exception as e:
            print(f"Error reading {f}: {e}")
            
    if not all_data:
        print("No valid data loaded after filtering.")
        return

    print("Concatenating Data...")
    combined = pd.concat(all_data, ignore_index=True)
    
    print(f"Total Rows Loaded: {len(combined)}")
    
    # Debug: Check for Land/Labor metrics
    land_audit = combined[combined['statisticcat_desc'].isin(['AREA PLANTED', 'AREA HARVESTED', 'AG LAND', 'CROPLAND', 'WAGE RATE'])]
    print("Data Audit - Row Counts for Key Metrics:")
    print(land_audit['statisticcat_desc'].value_counts().head(10))

    # --- Aggregation Logic ---
    
    # Filter Ratio Metrics for Summing
    non_ratio_mask = (
        ~combined['unit_desc'].astype(str).str.contains('/', na=False) &
        ~combined['statisticcat_desc'].isin(['YIELD', 'PRICE RECEIVED', 'EXPENSE / OPERATION', 'ASSET / OPERATION', 'WAGE RATE'])
    )
    # Note: WAGE RATE ($ / HOUR) is a ratio, so we can't sum it across states to get National Avg.
    # We need a WEIGHTED average for national, or just take the 'US' row if it exists?
    # Since we are aggregating from State data (because original National file was missing metrics), 
    # we can't easily calculate weighted avg without weights (e.g. number of workers).
    # For now, we unfortunately will skip summing ratios.
    
    df_for_summing = combined[non_ratio_mask]

    # 1. State Level Aggregates (The "Map" Data)
    # Group by base cols + state_alpha
    # This seemingly just reconstructs the input since input is unique by these keys?
    # But safe to group in case multiple rows exist.
    print("Generating State-Level Aggregates (Map Data)...")
    state_agg = df_for_summing.groupby(group_cols_base + ['state_alpha'], as_index=False)['value_num'].sum()
    state_agg['agg_level_desc'] = 'STATE'
    
    # 2. National Level Aggregates (The "Overview" Data)
    # Sum of all states
    print("Generating National-Level Aggregates...")
    national_agg = df_for_summing.groupby(group_cols_base, as_index=False)['value_num'].sum()
    national_agg['state_alpha'] = 'US'
    national_agg['agg_level_desc'] = 'NATIONAL'
    
    # 3. Combine
    print("combining...")
    final_df = pd.concat([state_agg, national_agg], ignore_index=True)
    
    final_df['Value'] = final_df['value_num'].astype(str)
    
    print(f"Writing {len(final_df)} rows to {OUTPUT_FILE}...")
    final_df.to_parquet(OUTPUT_FILE, engine='pyarrow', compression='snappy', index=False)
    
    print("Comprehensive National Aggregation Complete.")

if __name__ == "__main__":
    aggregate()
