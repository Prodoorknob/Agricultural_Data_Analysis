
import pandas as pd
import os
import sys

RAW_DATA_DIR = r"C:\Users\rajas\Documents\VS_Code\Agricultural_Data_Analysis\raw_data"
FILENAME = "nass_crops_field_crops.csv"

def inspect():
    filepath = os.path.join(RAW_DATA_DIR, FILENAME)
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return

    print(f"Inspecting {FILENAME}...")
    
    # Process in chunks
    chunk_size = 50000 
    chunk_iter = pd.read_csv(filepath, chunksize=chunk_size, low_memory=False)

    found_national = False
    
    for i, chunk in enumerate(chunk_iter):
        if 'agg_level_desc' in chunk.columns:
            national_rows = chunk[chunk['agg_level_desc'] == 'NATIONAL']
            if not national_rows.empty:
                print(f"Found {len(national_rows)} NATIONAL rows in chunk {i}")
                print("State Alpha Sample:", national_rows['state_alpha'].unique().tolist())
                found_national = True
                break # Found some, that's enough to prove existence
        
        if i % 10 == 0:
            print(f"Scanned {i*chunk_size} rows...")
            
    if not found_national:
        print("Scanned entire file. No NATIONAL rows found.")
    
if __name__ == "__main__":
    inspect()
