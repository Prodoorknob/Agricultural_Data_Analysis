
import pandas as pd
import os
import shutil
import numpy as np

# Config
RAW_DATA_DIR = r"C:\Users\rajas\Documents\VS_Code\Agricultural_Data_Analysis\raw_data"
OUTPUT_DIR = os.path.join(os.getcwd(), 'processed_data')

# Files to process
FILES = [
    "nass_crops_field_crops.csv",
    "nass_quickstats_data_Economics.csv",
    # "nass_quickstats_data_animals_products.csv", # Already processed
    "nass_crops_fruit_tree.csv",
    "nass_crops_vegetables.csv",
    "nass_crops_horticulture.csv"
]

# Columns to keep (adjust as needed based on inspection)
KEEP_COLS = [
    'source_desc', 'sector_desc', 'group_desc', 'commodity_desc', 
    'statisticcat_desc', 'unit_desc', 'domain_desc', 'agg_level_desc', 
    'state_alpha', 'year', 'Value'
]

def clean_value(val):
    if pd.isna(val):
        return 0.0
    val_str = str(val).strip().replace(',', '')
    if val_str in ['(D)', '(Z)', '-', '(NA)', '(S)', 'nan']:
        return 0.0
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def process_file(filename):
    filepath = os.path.join(RAW_DATA_DIR, filename)
    if not os.path.exists(filepath):
        print(f"Skipping {filename} (File not found)")
        return

    print(f"Processing {filename}...")
    
    # Process in chunks
    chunk_size = 50000 
    chunk_iter = pd.read_csv(filepath, chunksize=chunk_size, low_memory=False)

    for i, chunk in enumerate(chunk_iter):
        # Filter for STATE and NATIONAL level only
        # Lowercase check for robustness
        mask = chunk['agg_level_desc'].str.upper().isin(['STATE', 'NATIONAL'])
        filtered = chunk[mask].copy()

        if filtered.empty:
            continue

        # Keep specific columns
        # Ensure columns exist
        available_cols = [c for c in KEEP_COLS if c in filtered.columns]
        filtered = filtered[available_cols]

        # Clean Value
        filtered['value_num'] = filtered['Value'].apply(clean_value)
        filtered['year'] = pd.to_numeric(filtered['year'], errors='coerce').fillna(0).astype('int16')
        
        # Determine Partition Key (State)
        # Using state_alpha. If missing (NATIONAL), use 'US'
        filtered['partition_key'] = filtered['state_alpha'].fillna('US')
        
        # Explicitly force US for National rows to avoid ambiguity
        filtered.loc[filtered['agg_level_desc'] == 'NATIONAL', 'partition_key'] = 'US'

        # Write partitioned data
        # We append to partitioned dataset
        filtered.to_parquet(
            OUTPUT_DIR,
            partition_cols=['partition_key'],
            engine='pyarrow',
            compression='snappy',
            index=False,
            existing_data_behavior='overwrite_or_ignore' 
        )
        
        if i % 10 == 0:
            print(f"  Processed {i} chunks...")

def main():
    if os.path.exists(OUTPUT_DIR):
        print(f"Cleaning output directory: {OUTPUT_DIR}")
        # Be careful here in production, but for dev it's fine to clean slate
        # shutil.rmtree(OUTPUT_DIR) 
        # Actually let's NOT delete, merging appended parquets is tricky if we delete.
        # But to_parquet with partition_cols appends new files into folders.
        pass
    else:
        os.makedirs(OUTPUT_DIR)

    for file in FILES:
        process_file(file)

    print("Processing complete.")

if __name__ == "__main__":
    main()
