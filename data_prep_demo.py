"""
DEMO VERSION - Data Preparation Module
Limited to 2019-2024 data only for demonstration purposes.
Uses pre-filtered data files from partitioned_states_demo/ for lower memory usage.
"""

import os
import pandas as pd
import Agri_data_backup.data_prep as data_prep

# Override the year filter constants
DEMO_START_YEAR = 2019
DEMO_END_YEAR = 2024

# Import everything from the original data_prep
from Agri_data_backup.data_prep import *

# Override directories to use demo versions
PARTITIONED_STATES_DIR = 'partitioned_states_demo'

# Monkey-patch the module-level variable in data_prep
data_prep.PARTITIONED_STATES_DIR = 'partitioned_states_demo'

# Override file path functions to use demo files
original_get_file_path = get_file_path
original_get_state_file_path = get_state_file_path

def get_file_path(filename: str) -> str:
    """
    DEMO VERSION: Get file path for demo CSV files.
    Uses _demo suffix for CSV files.
    """
    # Check if it's a CSV file that has a demo version
    if filename.endswith('.csv') and not filename.endswith('_demo.csv'):
        demo_filename = filename.replace('.csv', '_demo.csv')
        demo_path = original_get_file_path(demo_filename)
        
        # Check if demo file exists (for local mode)
        if not data_prep.USE_S3:
            if os.path.exists(demo_path):
                return demo_path
        else:
            # For S3, assume demo file exists
            return demo_path
    
    return original_get_file_path(filename)


def get_state_file_path(state_name: str) -> str:
    """
    DEMO VERSION: Get file path using partitioned_states_demo directory.
    """
    filename = f"{PARTITIONED_STATES_DIR}/{state_name}.parquet"
    if data_prep.USE_S3:
        return f"{data_prep.S3_BUCKET_URL}/{filename}"
    else:
        return os.path.join(data_prep.DATA_DIR, filename)

# Monkey-patch the functions in the data_prep module
data_prep.get_file_path = get_file_path
data_prep.get_state_file_path = get_state_file_path

# Override load_state_data to convert state abbreviations to full names
original_load_state_data = data_prep.load_state_data

def load_state_data(state_name: str) -> pd.DataFrame:
    """
    DEMO VERSION: Converts state abbreviations to full names before loading.
    """
    # Import HEX_LAYOUT to do the conversion
    from visuals import HEX_LAYOUT
    
    # If state_name is a 2-letter code, convert to full name
    if len(state_name) == 2:
        state_row = HEX_LAYOUT[HEX_LAYOUT['state_alpha'] == state_name]
        if not state_row.empty:
            state_name = state_row['state_name'].iloc[0].upper()
    
    return original_load_state_data(state_name)

# Monkey-patch load_state_data
data_prep.load_state_data = load_state_data


# Since data files are pre-filtered to 2019-2024, no need for additional filtering
# The demo files only contain the necessary years


# Override get_available_years to return demo range
def get_available_years(df: pd.DataFrame) -> list:
    """
    DEMO VERSION: Returns years 2019-2024 only.
    """
    return list(range(DEMO_START_YEAR, DEMO_END_YEAR + 1))


print(f"[DEMO MODE] Using pre-filtered data files ({DEMO_START_YEAR}-{DEMO_END_YEAR})")
print(f"[DEMO MODE] Reading from: {PARTITIONED_STATES_DIR}/ (reduces memory by ~75%)")

