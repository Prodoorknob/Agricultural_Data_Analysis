
import pandas as pd
import os
import shutil

PROCESSED_DIR = os.path.join(os.getcwd(), 'processed_data')
FINAL_DIR = os.path.join(os.getcwd(), 'final_data')

def consolidate():
    if not os.path.exists(FINAL_DIR):
        os.makedirs(FINAL_DIR)

    # Get all partition directories
    partitions = [d for d in os.listdir(PROCESSED_DIR) if d.startswith("partition_key=")]
    
    print(f"Found {len(partitions)} state partitions.")

    for part_dir in partitions:
        state_code = part_dir.split("=")[1]
        
        # Handle special cases if needed
        filename = f"{state_code}.parquet"
        if state_code == 'US':
            filename = "NATIONAL.parquet"
            
        input_path = os.path.join(PROCESSED_DIR, part_dir)
        output_path = os.path.join(FINAL_DIR, filename)
        
        print(f"Consolidating {state_code} -> {filename}...")
        
        try:
            # Read partitioned dataset (schema handling is automatic with PyArrow engine)
            df = pd.read_parquet(input_path, engine='pyarrow')
            
            # Sort by year/commodity for better compression/access
            if 'year' in df.columns and 'commodity_desc' in df.columns:
                df = df.sort_values(['year', 'commodity_desc'])
            
            # Additional cleanup if needed (e.g. drop duplicates)
            df = df.drop_duplicates()

            # Write single file
            df.to_parquet(output_path, engine='pyarrow', compression='snappy', index=False)
            print(f"  Saved {filename}: {len(df)} rows")
            
        except Exception as e:
            print(f"Error processing {state_code}: {e}")

    print("Consolidation complete.")

if __name__ == "__main__":
    consolidate()
