"""
data_prep.py - Data Loading and Preprocessing for USDA Agricultural Dashboard

This module loads and preprocesses USDA agricultural data from multiple CSV sources:
- NASS QuickStats (crops, livestock, economics)
- Major Land Use (MLU)
- Biotech adoption data

ASSUMPTIONS AND NOTES:
- Data can be loaded from local `survey_datasets` folder OR from S3 bucket
- Set USE_S3=True and configure S3_BUCKET_URL to load from cloud
- NASS QuickStats Value column may contain: commas, (D), (Z), (NA), (X) - cleaned to numeric
- MajorLandUse.csv has columns: Region or State, Year, Land use, Value, Units
- BiotechCropsAllTables2024.csv has columns: Attribute, State, Year, Value, Table (encoding='latin-1')
- CACHING: For t2.micro or memory-constrained environments, uses in-memory cache

You can edit the DATA_DIR path or S3 settings below to match your file structure.
"""

import os
import re
import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional, List
from io import StringIO
from functools import lru_cache
import pickle
import hashlib

# ============================================================================
# CACHING CONFIGURATION - For memory-constrained environments (e.g., t2.micro)
# ============================================================================

# Enable caching: Set to True on t2.micro/limited RAM environments
ENABLE_CACHING = os.environ.get('ENABLE_CACHING', 'True').lower() == 'true'

# Cache directory for pickle files (uses temp storage on EC2)
CACHE_DIR = os.environ.get('CACHE_DIR', '/tmp/dashboard_cache')

# Create cache directory if it doesn't exist
if ENABLE_CACHING and not os.path.exists(CACHE_DIR):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
    except Exception as e:
        print(f"Warning: Could not create cache directory {CACHE_DIR}: {e}")
        ENABLE_CACHING = False

# In-memory cache for DataFrames (key -> DataFrame)
_DATA_CACHE = {}

def _get_cache_key(filepath: str, **kwargs) -> str:
    """Generate a unique cache key based on filepath and parameters."""
    key_str = filepath + str(sorted(kwargs.items()))
    return hashlib.md5(key_str.encode()).hexdigest()

def _load_from_cache(cache_key: str) -> Optional[pd.DataFrame]:
    """Load DataFrame from in-memory cache."""
    if cache_key in _DATA_CACHE:
        return _DATA_CACHE[cache_key].copy()
    return None

def _save_to_cache(cache_key: str, df: pd.DataFrame) -> None:
    """Save DataFrame to in-memory cache."""
    if ENABLE_CACHING:
        _DATA_CACHE[cache_key] = df.copy()

def clear_cache():
    """Clear all cached data. Useful for freeing memory."""
    global _DATA_CACHE
    _DATA_CACHE.clear()
    print("Cache cleared")

# ============================================================================
# CONFIGURATION - Edit these paths as needed
# ============================================================================

# S3 Configuration - Set USE_S3=True to load data from S3 bucket
# IMPORTANT: This uses PUBLIC S3 URLs (HTTPS) - NO AWS CREDENTIALS REQUIRED
# The S3 bucket must have public read access enabled for these files
#
# DATA STRATEGY: State-partitioned parquet files for on-demand loading
# - Only loads data for the selected state (reduces memory usage)
# - National summaries cached globally (loaded once, reused)
# - MajorLandUse.csv loaded separately as needed
#
# FILES REQUIRED IN S3 (58 total):
#   - partitioned_states/*.parquet (50 state files)
#   - partitioned_states/NATIONAL_SUMMARY_CROPS.parquet
#   - partitioned_states/NATIONAL_SUMMARY_LABOR.parquet
#   - partitioned_states/NATIONAL_SUMMARY_LANDUSE.parquet
#   - MajorLandUse.csv
#
# See S3_UPLOAD_GUIDE.md for detailed upload instructions
USE_S3 = os.environ.get('USE_S3', 'False').lower() == 'true'

# Your S3 bucket URL (public access) - base path to survey_datasets folder
# Override via environment variable: export S3_BUCKET_URL="https://your-bucket.s3.region.amazonaws.com/path"
S3_BUCKET_URL = os.environ.get(
    'S3_BUCKET_URL', 
    'https://usda-analysis-datasets.s3.us-east-2.amazonaws.com/survey_datasets'
)

# Local data directory (used when USE_S3=False)
DATA_DIR = os.path.join(os.path.dirname(__file__), "survey_datasets")

# ============================================================================
# STATE-LEVEL PARTITIONING CONFIGURATION
# ============================================================================

# Use state-level partitioned data for on-demand loading
USE_PARTITIONED_DATA = os.environ.get('USE_PARTITIONED_DATA', 'True').lower() == 'true'

# Directory for state-level partitioned files
PARTITIONED_STATES_DIR = 'partitioned_states'

# In-memory cache for loaded states
_STATE_DATA_CACHE = {}

# Cache for national summary data (loaded once, reused across all states)
_NATIONAL_LABOR_CACHE = None
_NATIONAL_LANDUSE_CACHE = None
_NATIONAL_CROPS_CACHE = None


def get_file_path(filename: str) -> str:
    """
    Get the full path/URL for a data file.
    Returns S3 URL if USE_S3=True, otherwise local path.
    
    NOTE: When USE_S3=True, this returns public HTTPS URLs that pandas
    can read directly without any AWS credentials or boto3.
    
    Examples:
        Local:  C:/path/to/survey_datasets/MajorLandUse.csv
        S3:     https://bucket.s3.region.amazonaws.com/survey_datasets/MajorLandUse.csv
    
    Args:
        filename: Relative filename (e.g., 'MajorLandUse.csv')
        
    Returns:
        Full path or HTTPS URL
    """
    if USE_S3:
        return f"{S3_BUCKET_URL}/{filename}"
    else:
        return os.path.join(DATA_DIR, filename)


def get_state_file_path(state_name: str) -> str:
    """
    Get the full path/URL for a state-level partitioned file.
    
    Supports both state data files and national summary files:
    - State files: INDIANA.parquet, CALIFORNIA.parquet, etc.
    - National files: NATIONAL_SUMMARY_CROPS.parquet, NATIONAL_SUMMARY_LABOR.parquet, etc.
    
    Examples:
        Local:  survey_datasets/partitioned_states/INDIANA.parquet
        S3:     https://bucket.s3.region.amazonaws.com/survey_datasets/partitioned_states/INDIANA.parquet
    
    Args:
        state_name: Name of the state or national summary file
                   (e.g., 'CALIFORNIA', 'INDIANA', 'NATIONAL_SUMMARY_CROPS')
        
    Returns:
        S3 URL or local path to the state's parquet file
    """
    filename = f"{PARTITIONED_STATES_DIR}/{state_name}.parquet"
    if USE_S3:
        return f"{S3_BUCKET_URL}/{filename}"
    else:
        return os.path.join(DATA_DIR, filename)


def load_national_labor_summary() -> pd.DataFrame:
    """
    Load pre-aggregated labor wage data for all states.
    Cached on first load to avoid repeated file I/O.
    
    Returns:
        DataFrame with columns: year, state_alpha, state_name, wage_rate, data_source
    """
    global _NATIONAL_LABOR_CACHE
    if _NATIONAL_LABOR_CACHE is not None:
        return _NATIONAL_LABOR_CACHE
    
    try:
        filepath = get_state_file_path('NATIONAL_SUMMARY_LABOR')
        _NATIONAL_LABOR_CACHE = pd.read_parquet(filepath)
        print(f"Loaded national labor summary: {len(_NATIONAL_LABOR_CACHE)} records")
        return _NATIONAL_LABOR_CACHE
    except Exception as e:
        print(f"Warning: Could not load national labor summary: {e}")
        return pd.DataFrame()


def load_national_landuse_summary() -> pd.DataFrame:
    """
    Load pre-aggregated land use data for all states.
    Cached on first load.
    
    Returns:
        DataFrame with columns: state_name, year, total_cropland, land_in_urban_areas
    """
    global _NATIONAL_LANDUSE_CACHE
    if _NATIONAL_LANDUSE_CACHE is not None:
        return _NATIONAL_LANDUSE_CACHE
    
    try:
        filepath = get_state_file_path('NATIONAL_SUMMARY_LANDUSE')
        _NATIONAL_LANDUSE_CACHE = pd.read_parquet(filepath)
        print(f"Loaded national land use summary: {len(_NATIONAL_LANDUSE_CACHE)} records")
        return _NATIONAL_LANDUSE_CACHE
    except Exception as e:
        print(f"Warning: Could not load national land use summary: {e}")
        return pd.DataFrame()


def load_national_crops_summary() -> pd.DataFrame:
    """
    Load pre-aggregated crop data for all states (for boom crops national comparison).
    Cached on first load.
    
    Returns:
        DataFrame with columns: state_alpha, state_name, commodity_desc, year, 
                                statisticcat_desc, value_num
    """
    global _NATIONAL_CROPS_CACHE
    if _NATIONAL_CROPS_CACHE is not None:
        return _NATIONAL_CROPS_CACHE
    
    try:
        filepath = get_state_file_path('NATIONAL_SUMMARY_CROPS')
        _NATIONAL_CROPS_CACHE = pd.read_parquet(filepath)
        print(f"Loaded national crops summary: {len(_NATIONAL_CROPS_CACHE)} records")
        return _NATIONAL_CROPS_CACHE
    except Exception as e:
        print(f"Warning: Could not load national crops summary: {e}")
        return pd.DataFrame()


def read_csv_file(filepath: str, **kwargs) -> pd.DataFrame:
    """
    Read a CSV file from either local path or S3 URL.
    
    CACHING: Automatically caches results in memory to avoid re-reading large files.
    For t2.micro/limited RAM, this dramatically reduces memory pressure on repeated requests.
    
    MEMORY-CONSCIOUS: Pandas reads from URLs via streaming (chunked HTTP requests),
    so large files don't need to be fully downloaded before parsing begins.
    
    NO AWS CREDENTIALS NEEDED: When filepath is an HTTPS URL to a public S3 object,
    pandas uses standard HTTP requests - no boto3, no IAM, no access keys required.
    
    Args:
        filepath: Local path or S3 HTTPS URL
        **kwargs: Additional arguments to pass to pd.read_csv
        
    Returns:
        DataFrame (from cache if available, otherwise freshly loaded)
    """
    try:
        # Check cache first
        cache_key = _get_cache_key(filepath, **kwargs)
        cached_df = _load_from_cache(cache_key)
        if cached_df is not None:
            return cached_df
        
        # Read from source (pandas can read from HTTPS URLs directly)
        df = pd.read_csv(filepath, **kwargs)
        
        # Save to cache for future requests
        _save_to_cache(cache_key, df)
        
        return df
    except Exception as e:
        print(f"  Error reading {filepath}: {e}")
        raise

# File paths - adjust if your file names differ
NASS_FILES = {
    'commodities': 'nass_crops_commodities.csv',
    'field_crops': 'nass_crops_field_crops.csv',
    'fruit_tree': 'nass_crops_fruit_tree.csv',
    'horticulture': 'nass_crops_horticulture.csv',
    'vegetables': 'nass_crops_vegetables.csv',
    'animals': 'nass_quickstats_data_animals_products.csv',
    'economics': 'nass_quickstats_data_Economics.csv',
}

MLU_FILE = 'MajorLandUse.csv'
BIOTECH_FILE = 'BiotechCropsAllTables2024.csv'

# Columns to keep from NASS QuickStats for efficiency
NASS_KEEP_COLS = [
    'source_desc', 'sector_desc', 'group_desc', 'commodity_desc', 'class_desc',
    'prodn_practice_desc', 'util_practice_desc', 'statisticcat_desc', 'unit_desc',
    'short_desc', 'domain_desc', 'domaincat_desc', 'agg_level_desc',
    'state_fips_code', 'state_alpha', 'state_name',
    'county_code', 'county_name', 'year', 'Value', 'CV (%)'
]

# Statistic categories we care about most
RELEVANT_STAT_CATS = [
    'AREA HARVESTED', 'AREA PLANTED', 'PRODUCTION', 'YIELD',
    'PRICE RECEIVED', 'SALES', 'OPERATIONS', 
    'EXPENSE', 'WAGE RATE', 'WORKERS', 'ASSET VALUE',
    'INVENTORY', 'HEAD', 'AREA', 'AREA OPERATED'
]

# State alpha to FIPS mapping (50 states + DC)
STATE_FIPS_MAP = {
    'AL': '01', 'AK': '02', 'AZ': '04', 'AR': '05', 'CA': '06', 'CO': '08',
    'CT': '09', 'DE': '10', 'DC': '11', 'FL': '12', 'GA': '13', 'HI': '15',
    'ID': '16', 'IL': '17', 'IN': '18', 'IA': '19', 'KS': '20', 'KY': '21',
    'LA': '22', 'ME': '23', 'MD': '24', 'MA': '25', 'MI': '26', 'MN': '27',
    'MS': '28', 'MO': '29', 'MT': '30', 'NE': '31', 'NV': '32', 'NH': '33',
    'NJ': '34', 'NM': '35', 'NY': '36', 'NC': '37', 'ND': '38', 'OH': '39',
    'OK': '40', 'OR': '41', 'PA': '42', 'RI': '44', 'SC': '45', 'SD': '46',
    'TN': '47', 'TX': '48', 'UT': '49', 'VT': '50', 'VA': '51', 'WA': '53',
    'WV': '54', 'WI': '55', 'WY': '56'
}

# State name to alpha mapping
STATE_NAME_TO_ALPHA = {
    'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR', 'California': 'CA',
    'Colorado': 'CO', 'Connecticut': 'CT', 'Delaware': 'DE', 'Florida': 'FL', 'Georgia': 'GA',
    'Hawaii': 'HI', 'Idaho': 'ID', 'Illinois': 'IL', 'Indiana': 'IN', 'Iowa': 'IA',
    'Kansas': 'KS', 'Kentucky': 'KY', 'Louisiana': 'LA', 'Maine': 'ME', 'Maryland': 'MD',
    'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN', 'Mississippi': 'MS', 'Missouri': 'MO',
    'Montana': 'MT', 'Nebraska': 'NE', 'Nevada': 'NV', 'New Hampshire': 'NH', 'New Jersey': 'NJ',
    'New Mexico': 'NM', 'New York': 'NY', 'North Carolina': 'NC', 'North Dakota': 'ND', 'Ohio': 'OH',
    'Oklahoma': 'OK', 'Oregon': 'OR', 'Pennsylvania': 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC',
    'South Dakota': 'SD', 'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT', 'Vermont': 'VT',
    'Virginia': 'VA', 'Washington': 'WA', 'West Virginia': 'WV', 'Wisconsin': 'WI', 'Wyoming': 'WY',
    'District of Columbia': 'DC'
}


# ============================================================================
# VALUE CLEANING FUNCTIONS
# ============================================================================

def clean_nass_value(val) -> Optional[float]:
    """
    Clean NASS QuickStats 'Value' column to numeric.
    
    Handles:
    - Commas in numbers (e.g., "1,234,567")
    - NASS special codes: (D), (Z), (NA), (X), (S), (L), (H) -> NaN
    - Whitespace and other edge cases
    
    Args:
        val: Raw value from the Value column
        
    Returns:
        Float value or None/NaN if not parseable
    """
    if pd.isna(val):
        return np.nan
    
    val_str = str(val).strip()
    
    # Check for NASS special codes (withheld, not available, etc.)
    if re.match(r'^\s*\([DZNAXSLH]\)\s*$', val_str, re.IGNORECASE):
        return np.nan
    
    # Check for other non-numeric patterns
    if val_str in ['', '-', '--', 'NA', 'N/A', 'null', 'None']:
        return np.nan
    
    # Remove commas and try to convert to float
    try:
        clean_val = val_str.replace(',', '')
        return float(clean_val)
    except (ValueError, TypeError):
        return np.nan


def clean_value_column(df: pd.DataFrame, value_col: str = 'Value', 
                       output_col: str = 'value_num') -> pd.DataFrame:
    """
    Apply value cleaning to a DataFrame, creating a new numeric column.
    
    Args:
        df: DataFrame with Value column
        value_col: Name of the column to clean
        output_col: Name for the new numeric column
        
    Returns:
        DataFrame with new numeric column added
    """
    df = df.copy()
    df[output_col] = df[value_col].apply(clean_nass_value)
    return df


def filter_totals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter out TOTALS commodities to avoid double-counting.
    
    TOTALS include aggregated categories like 'FIELD CROP TOTALS', 'ANIMAL TOTALS',
    'DAIRY PRODUCT TOTALS', etc. which would duplicate individual crop/animal data.
    
    Args:
        df: DataFrame with commodity_desc column
        
    Returns:
        DataFrame with TOTALS rows removed
    """
    if 'commodity_desc' not in df.columns:
        return df
    
    # Filter out any commodity that contains 'TOTAL'
    return df[~df['commodity_desc'].str.contains('TOTAL', case=False, na=False)].copy()


def filter_extreme_yoy_changes(df: pd.DataFrame, value_cols: list = None, 
                                threshold: float = 10.0) -> pd.DataFrame:
    """
    Filter out data points with extreme year-over-year changes (>1000% by default).
    
    This helps remove data quality issues like unit conversion errors or
    reporting mistakes that show up as unrealistic spikes.
    
    Args:
        df: DataFrame with year, commodity_desc, and value columns
        value_cols: List of value columns to check (defaults to revenue and area)
        threshold: Multiplier threshold (10.0 = 1000% increase)
        
    Returns:
        DataFrame with extreme outliers removed
    """
    if df.empty or 'year' not in df.columns or 'commodity_desc' not in df.columns:
        return df
    
    if value_cols is None:
        value_cols = ['revenue_usd', 'area_harvested_acres', 'area_planted_acres', 'production']
    
    # Only check columns that exist
    value_cols = [col for col in value_cols if col in df.columns]
    
    if not value_cols:
        return df
    
    df = df.copy()
    df = df.sort_values(['commodity_desc', 'year'])
    
    # Mark rows to keep
    keep_mask = pd.Series([True] * len(df), index=df.index)
    
    for col in value_cols:
        # Calculate year-over-year ratio for each commodity
        df['_prev_value'] = df.groupby('commodity_desc')[col].shift(1)
        df['_yoy_ratio'] = df[col] / df['_prev_value']
        
        # Flag extreme increases (>1000% = ratio > 10)
        # Also flag extreme decreases (>90% drop = ratio < 0.1)
        extreme_mask = (df['_yoy_ratio'] > threshold) | (df['_yoy_ratio'] < 1.0/threshold)
        
        # Only flag if both current and previous values are substantial (not near zero)
        substantial_mask = (df[col] > 1) & (df['_prev_value'] > 1)
        
        keep_mask &= ~(extreme_mask & substantial_mask & df[col].notna())
    
    # Clean up temporary columns
    df = df.drop(columns=['_prev_value', '_yoy_ratio'], errors='ignore')
    
    removed_count = (~keep_mask).sum()
    if removed_count > 0:
        print(f"  Filtered {removed_count} rows with extreme YoY changes (>{threshold}x)")
    
    return df[keep_mask]


# ============================================================================
# DATA LOADING FUNCTIONS
# ============================================================================

def load_nass_file(filepath: str, sample_frac: Optional[float] = None) -> pd.DataFrame:
    """
    Load a single NASS QuickStats CSV file with cleaning.
    
    Args:
        filepath: Path to the CSV file (local or S3 URL)
        sample_frac: If set, randomly sample this fraction of rows (for large files)
        
    Returns:
        Cleaned DataFrame
    """
    filename = os.path.basename(filepath) if not filepath.startswith('http') else filepath.split('/')[-1]
    print(f"Loading: {filename}...")
    
    # First read just headers to determine available columns
    try:
        if USE_S3:
            # For S3, read small sample to get columns
            header_df = read_csv_file(filepath, nrows=0)
        else:
            header_df = pd.read_csv(filepath, nrows=0)
        available_cols = header_df.columns.tolist()
    except Exception as e:
        print(f"  Error reading headers: {e}")
        return pd.DataFrame()
    
    use_cols = [c for c in NASS_KEEP_COLS if c in available_cols]
    
    df = read_csv_file(filepath, usecols=use_cols, low_memory=False)
    
    if sample_frac is not None and sample_frac < 1.0:
        df = df.sample(frac=sample_frac, random_state=42)
    
    # Clean the Value column
    df = clean_value_column(df)
    
    # Standardize state FIPS
    if 'state_fips_code' in df.columns:
        df['state_fips_code'] = df['state_fips_code'].astype(str).str.zfill(2)
    
    # Create FIPS code (state + county)
    if 'county_code' in df.columns:
        df['county_code'] = df['county_code'].astype(str).str.zfill(3)
        df['fips'] = df['state_fips_code'] + df['county_code']
    
    print(f"  Loaded {len(df):,} rows")
    return df


def load_state_data(state_name: str) -> pd.DataFrame:
    """
    Load all data for a specific state from state-level partitioned file.
    This loads all years (2001-2025) and all datasets for the given state.
    
    CACHING: Results are cached in memory to avoid re-reading from disk/S3.
    Each state file is typically < 3 MB, so caching 10-20 states is very memory-efficient.
    
    Args:
        state_name: Name of the state in uppercase (e.g., 'CALIFORNIA', 'INDIANA')
        
    Returns:
        DataFrame with all data for the state, or empty DataFrame if not found
    """
    # Check cache first
    if state_name in _STATE_DATA_CACHE:
        return _STATE_DATA_CACHE[state_name].copy()
    
    try:
        filepath = get_state_file_path(state_name)
        print(f"Loading state data: {state_name}...")
        print(f"  USE_S3: {USE_S3}")
        print(f"  File path: {filepath}")
        
        # Read parquet file (works with both local paths and S3 URLs)
        df = pd.read_parquet(filepath)
        
        # Clean the Value column if not already numeric
        if 'Value' in df.columns and df['Value'].dtype == 'object':
            df = clean_value_column(df)
        
        # Standardize state FIPS if present
        if 'state_fips_code' in df.columns:
            df['state_fips_code'] = df['state_fips_code'].astype(str).str.zfill(2)
        
        # Create FIPS code (state + county) if needed
        if 'county_code' in df.columns and 'state_fips_code' in df.columns:
            df['county_code'] = df['county_code'].astype(str).str.zfill(3)
            df['fips'] = df['state_fips_code'] + df['county_code']
        
        # Cache for future use
        _STATE_DATA_CACHE[state_name] = df.copy()
        
        print(f"  Loaded {len(df):,} rows for {state_name}")
        return df
        
    except FileNotFoundError:
        print(f"  Warning: State file not found for {state_name}")
        print(f"  Attempted path: {filepath}")
        return pd.DataFrame()
    except Exception as e:
        print(f"  Error loading state data for {state_name}: {e}")
        print(f"  Error type: {type(e).__name__}")
        print(f"  Attempted path: {filepath}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def clear_state_cache():
    """Clear cached state data. Useful for freeing memory."""
    global _STATE_DATA_CACHE
    _STATE_DATA_CACHE.clear()
    print("State data cache cleared")


def process_state_data(state_name: str) -> Dict[str, pd.DataFrame]:
    """
    Load and process data for a specific state into the format expected by visualizations.
    
    This function:
    1. Loads the state's raw data from the partitioned file
    2. Aggregates it into state_crop_year format
    3. Computes state totals
    4. Loads land use and labor data if available
    5. Returns a dictionary matching the structure from prepare_all_data()
    
    Args:
        state_name: State name in uppercase (e.g., 'CALIFORNIA', 'INDIANA')
        
    Returns:
        Dictionary with keys: 'nass_raw', 'state_crop_year', 'state_totals', 'landuse', 'labor', 'farm_operations'
    """
    result = {}
    
    # Load raw state data (NASS crops/animals/economics)
    state_df = load_state_data(state_name)
    
    if state_df.empty:
        print(f"Warning: No data found for {state_name}")
        return {
            'nass_raw': pd.DataFrame(),
            'state_crop_year': pd.DataFrame(),
            'state_totals': pd.DataFrame(),
            'landuse': pd.DataFrame(),
            'labor': pd.DataFrame(),
            'farm_operations': pd.DataFrame(),
            'biotech': pd.DataFrame()
        }
    
    result['nass_raw'] = state_df
    
    # Aggregate to state × crop × year format
    state_crop_year = aggregate_state_crop_year(state_df)
    result['state_crop_year'] = state_crop_year
    
    # Compute state totals
    if not state_crop_year.empty:
        result['state_totals'] = compute_state_totals(state_crop_year)
    else:
        result['state_totals'] = pd.DataFrame()
    
    # Load land use data for this state (from full MLU dataset - small file)
    try:
        mlu_df = load_major_land_use()
        if not mlu_df.empty and 'state_name' in mlu_df.columns:
            state_mlu = mlu_df[mlu_df['state_name'].str.upper() == state_name]
            result['landuse'] = aggregate_state_year_landuse(state_mlu)
        else:
            result['landuse'] = pd.DataFrame()
    except Exception as e:
        print(f"  Warning: Could not load land use data for {state_name}: {e}")
        result['landuse'] = pd.DataFrame()
    
    # Extract labor data from the state partition (Economics dataset already loaded)
    # Labor data is in Economics dataset with commodity_desc='LABOR'
    try:
        if not state_df.empty and 'dataset_source' in state_df.columns:
            economics_df = state_df[state_df['dataset_source'] == 'nass_economics'].copy()
            if not economics_df.empty and 'commodity_desc' in economics_df.columns:
                labor_df = economics_df[economics_df['commodity_desc'] == 'LABOR'].copy()
                
                if not labor_df.empty and 'statisticcat_desc' in labor_df.columns:
                    # Aggregate by year and statistic category
                    labor_by_year = []
                    for year, year_group in labor_df.groupby('year'):
                        row = {
                            'year': int(year),
                            'state_alpha': year_group['state_alpha'].iloc[0] if 'state_alpha' in year_group.columns else None,
                            'state_name': year_group['state_name'].iloc[0] if 'state_name' in year_group.columns else None,
                            'data_source': 'USDA_NASS'
                        }
                        
                        # Extract wage rate
                        wage_rows = year_group[year_group['statisticcat_desc'].str.contains('WAGE RATE', case=False, na=False)]
                        if not wage_rows.empty:
                            row['wage_rate'] = wage_rows['value_num'].mean()
                        
                        # Extract workers
                        worker_rows = year_group[year_group['statisticcat_desc'].str.contains('WORKERS', case=False, na=False)]
                        if not worker_rows.empty:
                            row['workers'] = worker_rows['value_num'].sum()
                        
                        # Extract hours
                        hours_rows = year_group[year_group['statisticcat_desc'].str.contains('TIME WORKED', case=False, na=False)]
                        if not hours_rows.empty:
                            row['hours_per_week'] = hours_rows['value_num'].mean()
                        
                        labor_by_year.append(row)
                    
                    result['labor'] = pd.DataFrame(labor_by_year) if labor_by_year else pd.DataFrame()
                    print(f"  Extracted labor data: {len(result['labor'])} year records")
                else:
                    result['labor'] = pd.DataFrame()
            else:
                result['labor'] = pd.DataFrame()
        else:
            result['labor'] = pd.DataFrame()
    except Exception as e:
        print(f"  Warning: Could not extract labor data from partition: {e}")
        result['labor'] = pd.DataFrame()
    
    # Extract farm operations from the state partition (Economics dataset already loaded)
    try:
        if not state_df.empty and 'dataset_source' in state_df.columns:
            economics_df = state_df[state_df['dataset_source'] == 'nass_economics'].copy()
            if not economics_df.empty and 'commodity_desc' in economics_df.columns:
                # Filter to SURVEY source only to avoid census year double-counting (2002, 2007, 2012, 2017, 2022)
                if 'source_desc' in economics_df.columns:
                    economics_df = economics_df[economics_df['source_desc'] == 'SURVEY']
                
                ops_df = economics_df[
                    (economics_df['commodity_desc'] == 'FARM OPERATIONS') &
                    (economics_df['statisticcat_desc'] == 'OPERATIONS')
                ].copy()
                
                if not ops_df.empty:
                    # Aggregate by year
                    ops_by_year = ops_df.groupby('year').agg({
                        'value_num': 'sum',
                        'state_alpha': 'first',
                        'state_name': 'first'
                    }).reset_index()
                    ops_by_year = ops_by_year.rename(columns={'value_num': 'total_operations'})
                    result['farm_operations'] = ops_by_year
                    print(f"  Extracted operations data: {len(result['farm_operations'])} year records")
                else:
                    result['farm_operations'] = pd.DataFrame()
            else:
                result['farm_operations'] = pd.DataFrame()
        else:
            result['farm_operations'] = pd.DataFrame()
    except Exception as e:
        print(f"  Warning: Could not extract farm operations from partition: {e}")
        result['farm_operations'] = pd.DataFrame()
    
    result['biotech'] = pd.DataFrame()
    
    return result


def load_all_nass_data(sample_frac: Optional[float] = None,
                       files_to_load: Optional[List[str]] = None,
                       survey_only: bool = True) -> pd.DataFrame:
    """
    Load and combine all NASS QuickStats CSV files.
    
    Args:
        sample_frac: If set, sample this fraction from each file (for testing)
        files_to_load: List of file keys to load (e.g., ['field_crops', 'vegetables'])
                      If None, loads all files
        survey_only: If True, filter to source_desc='SURVEY' only to avoid 
                     double-counting with CENSUS data during census years
                     (2002, 2007, 2012, 2017, 2022). Default True.
    
    Returns:
        Combined DataFrame with all NASS data
    """
    dfs = []
    
    if files_to_load is None:
        files_to_load = list(NASS_FILES.keys())
    
    for key in files_to_load:
        if key not in NASS_FILES:
            print(f"Warning: Unknown file key '{key}', skipping")
            continue
        
        filepath = get_file_path(NASS_FILES[key])
        
        # Check if file exists (only for local files)
        if not USE_S3 and not os.path.exists(filepath):
            print(f"Warning: File not found: {filepath}")
            continue
        
        try:
            df = load_nass_file(filepath, sample_frac)
            df['data_source'] = key
            
            # Filter to SURVEY only if requested and source_desc column exists
            if survey_only and 'source_desc' in df.columns:
                before_count = len(df)
                df = df[df['source_desc'] == 'SURVEY']
                print(f"    Filtered to SURVEY only: {before_count:,} -> {len(df):,} rows")
            
            dfs.append(df)
        except Exception as e:
            print(f"Warning: Error loading {key}: {e}")
            continue
    
    if not dfs:
        return pd.DataFrame()
    
    combined = pd.concat(dfs, ignore_index=True)
    print(f"\nTotal combined rows: {len(combined):,}")
    return combined


def load_major_land_use() -> pd.DataFrame:
    """
    Load and process the Major Land Use (MLU) dataset.
    
    Returns:
        DataFrame with columns: state_name, state_alpha, year, land_use_type, acres
    """
    filepath = get_file_path(MLU_FILE)
    print(f"Loading: {MLU_FILE}...")
    
    df = read_csv_file(filepath)
    
    # Rename columns for consistency
    df = df.rename(columns={
        'Region or State': 'state_name',
        'Year': 'year',
        'Land use': 'land_use_type',
        'Value': 'acres'
    })
    
    # Filter to state-level data only (exclude regional aggregates)
    # Regional names typically contain "total" or "Region"
    df = df[~df['state_name'].str.contains('total|Region|United States', case=False, na=False)]
    
    # Map state names to alpha codes
    df['state_alpha'] = df['state_name'].map(STATE_NAME_TO_ALPHA)
    
    # Convert acres to numeric (already clean in this file)
    df['acres'] = pd.to_numeric(df['acres'], errors='coerce')
    
    # Multiply by 1000 since units are "1,000 acres"
    df['acres'] = df['acres'] * 1000
    
    # Filter to years 2004-2024
    if 'year' in df.columns:
        df = df[(df['year'] >= 2004) & (df['year'] <= 2024)]
        print(f"  Filtered to years 2004-2024")
    
    print(f"  Loaded {len(df):,} rows")
    return df


# ============================================================================
# BIOTECH FUNCTIONS - REMOVED (not used in sample data deployment)
# ============================================================================

# load_biotech_data() and aggregate_biotech_state_crop_year() removed

# ============================================================================
# LABOR DATA LOADING
# ============================================================================

def load_labor_data() -> pd.DataFrame:
    """
    Load LABOR data from the Economics dataset (SURVEY data only).
    Extracts wage rates and worker counts by state and year.
    
    NOTE: Filters to source_desc='SURVEY' to avoid double-counting
    with CENSUS data during census years (2002, 2007, 2012, 2017, 2022).
    
    Returns:
        DataFrame with columns: state_alpha, state_name, year, wage_rate, workers
    """
    filepath = get_file_path(NASS_FILES.get('economics', 'nass_quickstats_data_Economics.csv'))
    print(f"Loading LABOR data from Economics file (SURVEY only)...")
    
    # Check if file exists (only for local files)
    if not USE_S3 and not os.path.exists(filepath):
        print(f"  Warning: Economics file not found at {filepath}")
        return pd.DataFrame()
    
    # Read only necessary columns for efficiency
    try:
        df = read_csv_file(filepath, low_memory=False)
    except Exception as e:
        print(f"  Error reading file: {e}")
        return pd.DataFrame()
    
    # Filter to LABOR commodity and SURVEY source only
    # This avoids double-counting in census years (2002, 2007, 2012, 2017, 2022)
    labor_df = df[(df['commodity_desc'] == 'LABOR') & (df['source_desc'] == 'SURVEY')].copy()
    
    if labor_df.empty:
        print("  No LABOR data found")
        return pd.DataFrame()
    
    # Clean values
    labor_df = clean_value_column(labor_df)
    
    # Filter to years 2004-2024
    if 'year' in labor_df.columns:
        labor_df = labor_df[(labor_df['year'] >= 2004) & (labor_df['year'] <= 2024)]
    
    # Filter to state-level data
    if 'agg_level_desc' in labor_df.columns:
        labor_df = labor_df[labor_df['agg_level_desc'] == 'STATE']
    
    # Pivot to get wage rate and workers as columns
    result_rows = []
    
    for (state, year), group in labor_df.groupby(['state_alpha', 'year']):
        row = {
            'state_alpha': state,
            'year': year,
            'state_name': group['state_name'].iloc[0] if 'state_name' in group.columns else None
        }
        
        # Get wage rate (average across all types)
        wage = group[group['statisticcat_desc'] == 'WAGE RATE']['value_num'].mean()
        row['wage_rate'] = wage
        
        # Get workers (sum)
        workers = group[group['statisticcat_desc'] == 'WORKERS']['value_num'].sum()
        row['workers'] = workers
        
        # Get time worked
        hours = group[group['statisticcat_desc'] == 'TIME WORKED']['value_num'].mean()
        row['hours_per_week'] = hours
        
        result_rows.append(row)
    
    result_df = pd.DataFrame(result_rows)
    print(f"  Loaded {len(result_df):,} state-year labor records from USDA NASS")
    return result_df


def load_bls_wage_data() -> pd.DataFrame:
    """
    Load BLS (Bureau of Labor Statistics) agricultural wage data.
    
    This provides comprehensive state-level wage data from 2001-2024 for all 50 states,
    which supplements the limited USDA NASS data (only CA, FL, HI after 2010).
    
    Source: BLS Occupational Employment and Wage Statistics (OEWS)
    Primary Occupation: 45-2092 - Farmworkers and Laborers, Crop, Nursery, and Greenhouse
    
    Returns:
        DataFrame with columns: state_alpha, state_name, year, wage_rate, data_source
    """
    filepath = get_file_path('bls_agricultural_wages.csv')
    print(f"Loading BLS agricultural wage data...")
    
    # Check if file exists (only for local files)
    if not USE_S3 and not os.path.exists(filepath):
        print(f"  Warning: BLS data file not found at {filepath}")
        print(f"  Run 'python stitch_bls_files.py' to extract BLS data from zip files")
        return pd.DataFrame()
    
    try:
        df = read_csv_file(filepath)
        
        # If we have multiple occupation codes, focus on the primary farmworker occupation
        # 45-2092: Farmworkers and Laborers, Crop, Nursery, and Greenhouse
        if 'occupation_code' in df.columns:
            primary_occ = df[df['occupation_code'] == '45-2092'].copy()
            if len(primary_occ) > 0:
                df = primary_occ
                print(f"  Filtered to primary occupation (45-2092): {len(df):,} records")
        
        # Rename columns to match our standard format
        df = df.rename(columns={
            'hourly_wage': 'wage_rate'
        })
        
        # Ensure data_source column exists and is properly marked
        if 'data_source' not in df.columns:
            df['data_source'] = 'BLS_OEWS'
        else:
            # Standardize to BLS_OEWS (covers both ACTUAL and derived)
            df['data_source'] = 'BLS_OEWS'
        
        print(f"  Loaded {len(df):,} state-year records from BLS")
        print(f"  Years: {df['year'].min()} - {df['year'].max()}")
        print(f"  States: {df['state_alpha'].nunique()}")
        
        return df
        
    except Exception as e:
        print(f"  Error reading BLS data: {e}")
        return pd.DataFrame()


def load_combined_labor_data() -> pd.DataFrame:
    """
    Load and combine labor wage data from multiple sources:
    1. USDA NASS Farm Labor Survey (limited states after 2010)
    2. BLS OEWS Agricultural Wages (all states, 2003-2024)
    
    The BLS data provides comprehensive coverage where USDA NASS data is limited.
    
    Returns:
        DataFrame with columns: state_alpha, state_name, year, wage_rate, 
                               workers, hours_per_week, data_source
    """
    print("Loading combined labor data from USDA NASS and BLS...")
    
    # Load USDA NASS data
    nass_df = load_labor_data()
    if not nass_df.empty:
        nass_df['data_source'] = 'USDA_NASS'
    
    # Load BLS data
    bls_df = load_bls_wage_data()
    
    if nass_df.empty and bls_df.empty:
        print("  Warning: No labor data available from either source")
        return pd.DataFrame()
    
    if bls_df.empty:
        print("  Using USDA NASS data only")
        return nass_df
    
    if nass_df.empty:
        print("  Using BLS data only")
        return bls_df
    
    # Combine the datasets
    # For state-years where both have data, prefer USDA NASS (more specific to farm labor)
    # For state-years where only BLS has data, use BLS
    
    # Create a key for matching
    nass_df['_key'] = nass_df['state_alpha'] + '_' + nass_df['year'].astype(str)
    bls_df['_key'] = bls_df['state_alpha'] + '_' + bls_df['year'].astype(str)
    
    # Find BLS records that don't have NASS equivalents
    nass_keys = set(nass_df['_key'])
    bls_only = bls_df[~bls_df['_key'].isin(nass_keys)].copy()
    
    # Add missing columns to BLS data
    for col in ['workers', 'hours_per_week']:
        if col not in bls_only.columns:
            bls_only[col] = np.nan
    
    # Combine: NASS data + BLS data for missing state-years
    combined = pd.concat([
        nass_df.drop(columns=['_key']),
        bls_only.drop(columns=['_key', 'occupation_code', 'occupation_title', 'annual_wage'], errors='ignore')
    ], ignore_index=True)
    
    # Sort by state and year
    combined = combined.sort_values(['state_alpha', 'year']).reset_index(drop=True)
    
    nass_count = len(combined[combined['data_source'] == 'USDA_NASS'])
    bls_count = len(combined[combined['data_source'] == 'BLS_OEWS'])
    
    print(f"  Combined: {len(combined):,} total records")
    print(f"    - USDA NASS: {nass_count:,} records")
    print(f"    - BLS OEWS:  {bls_count:,} records (supplemental)")
    
    return combined


def load_farm_operations_data() -> pd.DataFrame:
    """
    Load FARM OPERATIONS data from the Economics dataset (SURVEY data only).
    Extracts total farm operations count by state and year.
    
    NOTE: Filters to source_desc='SURVEY' to avoid double-counting
    with CENSUS data during census years (2002, 2007, 2012, 2017, 2022).
    
    Returns:
        DataFrame with columns: state_alpha, state_name, year, total_operations
    """
    filepath = get_file_path(NASS_FILES.get('economics', 'nass_quickstats_data_Economics.csv'))
    print(f"Loading FARM OPERATIONS data from Economics file (SURVEY only)...")
    
    # Check if file exists (only for local files)
    if not USE_S3 and not os.path.exists(filepath):
        print(f"  Warning: Economics file not found at {filepath}")
        return pd.DataFrame()
    
    try:
        df = read_csv_file(filepath, low_memory=False)
    except Exception as e:
        print(f"  Error reading file: {e}")
        return pd.DataFrame()
    
    # Filter to FARM OPERATIONS with OPERATIONS statistic and SURVEY source only
    # This avoids double-counting in census years (2002, 2007, 2012, 2017, 2022)
    ops_df = df[
        (df['commodity_desc'] == 'FARM OPERATIONS') & 
        (df['statisticcat_desc'] == 'OPERATIONS') &
        (df['source_desc'] == 'SURVEY')
    ].copy()
    
    if ops_df.empty:
        print("  No FARM OPERATIONS data found")
        return pd.DataFrame()
    
    # Clean values
    ops_df = clean_value_column(ops_df)
    
    # Filter to years 2004-2024
    if 'year' in ops_df.columns:
        ops_df = ops_df[(ops_df['year'] >= 2004) & (ops_df['year'] <= 2024)]
    
    # Filter to state-level data
    if 'agg_level_desc' in ops_df.columns:
        ops_df = ops_df[ops_df['agg_level_desc'] == 'STATE']
    
    # Aggregate by state and year (sum all operation types)
    result = ops_df.groupby(['state_alpha', 'year']).agg({
        'value_num': 'sum',
        'state_name': 'first'
    }).reset_index()
    
    result = result.rename(columns={'value_num': 'total_operations'})
    
    print(f"  Loaded {len(result):,} state-year operations records")
    return result


# ============================================================================
# AGGREGATION FUNCTIONS
# ============================================================================

def aggregate_state_crop_year(nass_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate NASS data to state × crop × year level.
    
    Computes:
    - area_harvested_acres: from AREA HARVESTED
    - area_planted_acres: from AREA PLANTED  
    - production: from PRODUCTION
    - yield_per_acre: from YIELD (average)
    - revenue_usd: from SALES or PRICE RECEIVED * PRODUCTION
    - operations: from OPERATIONS
    
    Args:
        nass_df: Cleaned NASS DataFrame
        
    Returns:
        Aggregated DataFrame
    """
    # Filter out TOTALS to avoid double-counting
    df = filter_totals(nass_df)
    
    # Filter to years 2004-2024 only
    if 'year' in df.columns:
        df = df[(df['year'] >= 2004) & (df['year'] <= 2024)].copy()
        print(f"  Filtered to years 2004-2024")
    
    # Filter to SURVEY source only to avoid census year double-counting
    if 'source_desc' in df.columns:
        df = df[df['source_desc'] == 'SURVEY'].copy()
    
    # Filter to state-level aggregations only
    if 'agg_level_desc' in df.columns:
        df = df[df['agg_level_desc'] == 'STATE'].copy()
    else:
        # If agg_level_desc is missing, assume all data is state-level
        df = df.copy()
    
    if df.empty:
        print("Warning: No state-level data found in aggregate_state_crop_year")
        print(f"  Input columns: {nass_df.columns.tolist()}")
        if 'agg_level_desc' in nass_df.columns:
            print(f"  Agg levels present: {nass_df['agg_level_desc'].unique().tolist()}")
        return pd.DataFrame()
    
    # Check required columns exist
    required_cols = ['state_alpha', 'state_name', 'commodity_desc', 'year', 'sector_desc', 'statisticcat_desc', 'value_num']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        print(f"Warning: Missing required columns: {missing_cols}")
        print(f"  Available columns: {df.columns.tolist()}")
        return pd.DataFrame()
    
    # Get commodity list
    commodities = df['commodity_desc'].unique()
    
    results = []
    
    for stat_cat in df['statisticcat_desc'].unique():
        # Filter to this statistic category
        cat_df = df[df['statisticcat_desc'] == stat_cat]
        
        # Aggregate by state, crop, year (include group_desc for filtering)
        group_cols = ['state_alpha', 'state_name', 'commodity_desc', 'year', 'sector_desc']
        if 'group_desc' in cat_df.columns:
            group_cols.append('group_desc')
        
        agg_df = cat_df.groupby(group_cols).agg({
            'value_num': 'sum',
            'unit_desc': 'first'
        }).reset_index()
        
        agg_df['statistic'] = stat_cat
        results.append(agg_df)
    
    if not results:
        return pd.DataFrame()
    
    long_df = pd.concat(results, ignore_index=True)
    
    # Determine pivot index columns based on available columns
    pivot_index = ['state_alpha', 'state_name', 'commodity_desc', 'year', 'sector_desc']
    if 'group_desc' in long_df.columns:
        pivot_index.append('group_desc')
    
    # Pivot to get metrics as columns
    pivot_df = long_df.pivot_table(
        index=pivot_index,
        columns='statistic',
        values='value_num',
        aggfunc='sum'
    ).reset_index()
    
    # Flatten column names
    pivot_df.columns = [c if isinstance(c, str) else c for c in pivot_df.columns]
    
    # Rename columns to standardized names
    column_mapping = {
        'AREA HARVESTED': 'area_harvested_acres',
        'AREA PLANTED': 'area_planted_acres',
        'PRODUCTION': 'production',
        'YIELD': 'yield_per_acre',
        'SALES': 'revenue_usd',
        'PRICE RECEIVED': 'price_received',
        'OPERATIONS': 'operations'
    }
    
    for old_name, new_name in column_mapping.items():
        if old_name in pivot_df.columns:
            pivot_df = pivot_df.rename(columns={old_name: new_name})
    
    # Compute operations per 1000 acres
    if 'operations' in pivot_df.columns and 'area_harvested_acres' in pivot_df.columns:
        pivot_df['ops_per_1k_acres'] = (
            pivot_df['operations'] / pivot_df['area_harvested_acres'] * 1000
        ).replace([np.inf, -np.inf], np.nan)
    
    # Filter extreme year-over-year changes (data quality filter)
    pivot_df = filter_extreme_yoy_changes(pivot_df, threshold=10.0)
    
    print(f"Aggregated state×crop×year: {len(pivot_df):,} rows")
    return pivot_df


def aggregate_state_year_landuse(mlu_df: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot Major Land Use data to state × year with land use types as columns.
    
    Args:
        mlu_df: Cleaned MLU DataFrame
        
    Returns:
        DataFrame with columns for each land use type
    """
    pivot_df = mlu_df.pivot_table(
        index=['state_alpha', 'state_name', 'year'],
        columns='land_use_type',
        values='acres',
        aggfunc='sum'
    ).reset_index()
    
    # Flatten and clean column names
    pivot_df.columns = [
        c.lower().replace(' ', '_').replace('-', '_') 
        if isinstance(c, str) else c 
        for c in pivot_df.columns
    ]
    
    # Compute urban share if we have the data
    if 'land_in_urban_areas' in pivot_df.columns and 'total_land' in pivot_df.columns:
        pivot_df['urban_share'] = pivot_df['land_in_urban_areas'] / pivot_df['total_land']
    
    if 'total_cropland' in pivot_df.columns and 'total_land' in pivot_df.columns:
        pivot_df['cropland_share'] = pivot_df['total_cropland'] / pivot_df['total_land']
    
    print(f"Aggregated state×year land use: {len(pivot_df):,} rows")
    return pivot_df


# ============================================================================
# STATE TOTALS COMPUTATION
# ============================================================================

def compute_state_totals(state_crop_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute state-level totals across all crops for a given year.
    
    Args:
        state_crop_df: State × crop × year DataFrame
        
    Returns:
        State × year totals DataFrame
    """
    numeric_cols = state_crop_df.select_dtypes(include=[np.number]).columns.tolist()
    numeric_cols = [c for c in numeric_cols if c not in ['year']]
    
    totals = state_crop_df.groupby(['state_alpha', 'state_name', 'year', 'sector_desc']).agg({
        col: 'sum' for col in numeric_cols if col in state_crop_df.columns
    }).reset_index()
    
    # Count unique crops
    crop_counts = state_crop_df.groupby(['state_alpha', 'year'])['commodity_desc'].nunique().reset_index()
    crop_counts = crop_counts.rename(columns={'commodity_desc': 'num_crops'})
    
    totals = totals.merge(crop_counts, on=['state_alpha', 'year'], how='left')
    
    return totals


# ============================================================================
# DATA PREPARATION PIPELINE
# ============================================================================

def prepare_all_data(sample_frac: Optional[float] = None,
                     nass_files: Optional[List[str]] = None) -> Dict[str, pd.DataFrame]:
    """
    Main data preparation function that loads and processes all datasets.
    
    Args:
        sample_frac: Fraction of NASS data to sample (for faster testing)
        nass_files: List of NASS file keys to load (None = all)
    
    Returns:
        Dictionary with prepared DataFrames:
        - 'nass_raw': Raw combined NASS data
        - 'state_crop_year': Aggregated state × crop × year
        - 'state_totals': State-level totals
        - 'landuse': Pivoted land use data
        - 'labor': Combined labor data (USDA NASS + BLS OEWS)
        - 'farm_operations': Farm operations data
    """
    print("=" * 60)
    print("LOADING AND PREPARING DATA")
    print("=" * 60)
    
    # Print data source information
    if USE_S3:
        print(f"📡 Data Source: S3 Bucket")
        print(f"   URL: {S3_BUCKET_URL}")
    else:
        print(f"📁 Data Source: Local Files")
        print(f"   Path: {DATA_DIR}")
    print()
    
    result = {}
    
    # Load NASS data
    if nass_files is None:
        # Default to smaller files for faster loading
        nass_files = ['commodities', 'field_crops', 'vegetables', 'fruit_tree', 
                      'horticulture', 'animals', 'economics']
    
    nass_df = load_all_nass_data(sample_frac=sample_frac, files_to_load=nass_files)
    result['nass_raw'] = nass_df
    
    # Aggregate NASS to state × crop × year
    if not nass_df.empty:
        state_crop_year = aggregate_state_crop_year(nass_df)
        result['state_crop_year'] = state_crop_year
        
        # Compute state totals
        if not state_crop_year.empty:
            result['state_totals'] = compute_state_totals(state_crop_year)
    
    # Load and process land use data
    try:
        mlu_df = load_major_land_use()
        result['landuse'] = aggregate_state_year_landuse(mlu_df)
    except Exception as e:
        print(f"Warning: Could not load land use data: {e}")
        result['landuse'] = pd.DataFrame()
    
    # NOTE: Biotech data loading removed per B3 requirements (Yield & Technology view removed)
    # Previously loaded biotech_df and aggregate_biotech_state_crop_year
    result['biotech'] = pd.DataFrame()
    
    # Load combined labor data (USDA NASS + BLS OEWS)
    # BLS provides comprehensive state-level coverage where USDA is limited
    try:
        result['labor'] = load_combined_labor_data()
    except Exception as e:
        print(f"Warning: Could not load labor data: {e}")
        result['labor'] = pd.DataFrame()
    
    # Load farm operations data
    try:
        result['farm_operations'] = load_farm_operations_data()
    except Exception as e:
        print(f"Warning: Could not load farm operations data: {e}")
        result['farm_operations'] = pd.DataFrame()
    
    print("=" * 60)
    print("DATA PREPARATION COMPLETE")
    print("=" * 60)
    
    return result


def get_available_years(df: pd.DataFrame) -> List[int]:
    """Get sorted list of unique years from a DataFrame."""
    if 'year' in df.columns:
        return sorted(df['year'].dropna().unique().astype(int).tolist())
    return []


def get_available_crops(df: pd.DataFrame, sector: Optional[str] = None) -> List[str]:
    """Get sorted list of unique commodities from a DataFrame."""
    if 'commodity_desc' not in df.columns:
        return []
    
    filtered = df
    if sector and 'sector_desc' in df.columns:
        filtered = df[df['sector_desc'] == sector]
    
    return sorted(filtered['commodity_desc'].dropna().unique().tolist())


def get_available_states(df: pd.DataFrame) -> List[str]:
    """Get sorted list of unique state alpha codes from a DataFrame."""
    if 'state_alpha' in df.columns:
        valid_states = [s for s in df['state_alpha'].dropna().unique() if s in STATE_FIPS_MAP]
        return sorted(valid_states)
    return []


# ============================================================================
# QUICK DATA LOADING FOR SMALLER DATASETS
# ============================================================================

def load_sample_data() -> Dict[str, pd.DataFrame]:
    """
    Load a small sample of data for quick testing.
    Uses only commodities file with 10% sampling.
    """
    return prepare_all_data(
        sample_frac=0.1,
        nass_files=['commodities', 'field_crops']
    )


def load_crops_only() -> Dict[str, pd.DataFrame]:
    """
    Load only crop-related data (no animals/economics) for faster loading.
    """
    return prepare_all_data(
        sample_frac=None,
        nass_files=['commodities', 'field_crops', 'vegetables', 'fruit_tree', 'horticulture']
    )


# ============================================================================
# MAIN - For testing
# ============================================================================

if __name__ == "__main__":
    # Test loading with sample
    data = load_sample_data()
    
    print("\n" + "=" * 60)
    print("LOADED DATASETS:")
    print("=" * 60)
    for key, df in data.items():
        if isinstance(df, pd.DataFrame):
            print(f"  {key}: {df.shape}")
            print(f"    Columns: {list(df.columns)[:10]}...")
