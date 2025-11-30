"""
data_prep.py - Data Loading and Preprocessing for USDA Agricultural Dashboard

This module loads and preprocesses USDA agricultural data from multiple CSV sources:
- NASS QuickStats (crops, livestock, economics)
- Major Land Use (MLU)
- Biotech adoption data

ASSUMPTIONS AND NOTES:
- All CSVs are in the `survey_datasets` folder relative to this file
- NASS QuickStats Value column may contain: commas, (D), (Z), (NA), (X) - cleaned to numeric
- MajorLandUse.csv has columns: Region or State, Year, Land use, Value, Units
- BiotechCropsAllTables2024.csv has columns: Attribute, State, Year, Value, Table (encoding='latin-1')

You can edit the DATA_DIR path below to match your file structure.
"""

import os
import re
import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional, List

# ============================================================================
# CONFIGURATION - Edit these paths as needed
# ============================================================================
DATA_DIR = os.path.join(os.path.dirname(__file__), "survey_datasets")

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


# ============================================================================
# DATA LOADING FUNCTIONS
# ============================================================================

def load_nass_file(filepath: str, sample_frac: Optional[float] = None) -> pd.DataFrame:
    """
    Load a single NASS QuickStats CSV file with cleaning.
    
    Args:
        filepath: Path to the CSV file
        sample_frac: If set, randomly sample this fraction of rows (for large files)
        
    Returns:
        Cleaned DataFrame
    """
    print(f"Loading: {os.path.basename(filepath)}...")
    
    # Read only columns we need for efficiency
    available_cols = pd.read_csv(filepath, nrows=0).columns.tolist()
    use_cols = [c for c in NASS_KEEP_COLS if c in available_cols]
    
    df = pd.read_csv(filepath, usecols=use_cols, low_memory=False)
    
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


def load_all_nass_data(sample_frac: Optional[float] = None,
                       files_to_load: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Load and combine all NASS QuickStats CSV files.
    
    Args:
        sample_frac: If set, sample this fraction from each file (for testing)
        files_to_load: List of file keys to load (e.g., ['field_crops', 'vegetables'])
                      If None, loads all files
    
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
            
        filepath = os.path.join(DATA_DIR, NASS_FILES[key])
        if os.path.exists(filepath):
            df = load_nass_file(filepath, sample_frac)
            df['data_source'] = key
            dfs.append(df)
        else:
            print(f"Warning: File not found: {filepath}")
    
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
    filepath = os.path.join(DATA_DIR, MLU_FILE)
    print(f"Loading: {MLU_FILE}...")
    
    df = pd.read_csv(filepath)
    
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
    
    print(f"  Loaded {len(df):,} rows")
    return df


def load_biotech_data() -> pd.DataFrame:
    """
    Load and process the Biotech Crops adoption dataset.
    
    Returns:
        DataFrame with columns: state_name, state_alpha, year, crop, attribute, pct_adopted
    """
    filepath = os.path.join(DATA_DIR, BIOTECH_FILE)
    print(f"Loading: {BIOTECH_FILE}...")
    
    df = pd.read_csv(filepath, encoding='latin-1')
    
    # Rename columns
    df = df.rename(columns={
        'State': 'state_name',
        'Year': 'year',
        'Attribute': 'attribute',
        'Value': 'pct_adopted'
    })
    
    # Map state names to alpha codes
    df['state_alpha'] = df['state_name'].map(STATE_NAME_TO_ALPHA)
    
    # Parse crop type from attribute
    def extract_crop(attr):
        attr_lower = attr.lower()
        if 'corn' in attr_lower:
            return 'CORN'
        elif 'soybean' in attr_lower:
            return 'SOYBEANS'
        elif 'cotton' in attr_lower:
            return 'COTTON'
        else:
            return 'OTHER'
    
    # Parse biotech trait type
    def extract_trait(attr):
        attr_lower = attr.lower()
        if 'bt only' in attr_lower or 'insect-resistant' in attr_lower:
            return 'bt_only'
        elif 'ht only' in attr_lower or 'herbicide-tolerant' in attr_lower:
            return 'ht_only'
        elif 'stacked' in attr_lower:
            return 'stacked'
        elif 'all ge' in attr_lower:
            return 'all_ge'
        else:
            return 'other'
    
    df['crop'] = df['attribute'].apply(extract_crop)
    df['trait_type'] = df['attribute'].apply(extract_trait)
    
    # Convert percentage to numeric
    df['pct_adopted'] = pd.to_numeric(df['pct_adopted'], errors='coerce')
    
    print(f"  Loaded {len(df):,} rows")
    return df


def load_labor_data() -> pd.DataFrame:
    """
    Load LABOR data from the Economics dataset.
    Extracts wage rates and worker counts by state and year.
    
    Returns:
        DataFrame with columns: state_alpha, state_name, year, wage_rate, workers
    """
    filepath = os.path.join(DATA_DIR, NASS_FILES.get('economics', 'nass_quickstats_data_Economics.csv'))
    print(f"Loading LABOR data from Economics file...")
    
    if not os.path.exists(filepath):
        print(f"  Warning: Economics file not found at {filepath}")
        return pd.DataFrame()
    
    # Read only necessary columns for efficiency
    try:
        df = pd.read_csv(filepath, low_memory=False)
    except Exception as e:
        print(f"  Error reading file: {e}")
        return pd.DataFrame()
    
    # Filter to LABOR commodity
    labor_df = df[df['commodity_desc'] == 'LABOR'].copy()
    
    if labor_df.empty:
        print("  No LABOR data found")
        return pd.DataFrame()
    
    # Clean values
    labor_df = clean_value_column(labor_df)
    
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
    print(f"  Loaded {len(result_df):,} state-year labor records")
    return result_df


def load_farm_operations_data() -> pd.DataFrame:
    """
    Load FARM OPERATIONS data from the Economics dataset.
    Extracts total farm operations count by state and year.
    
    Returns:
        DataFrame with columns: state_alpha, state_name, year, total_operations
    """
    filepath = os.path.join(DATA_DIR, NASS_FILES.get('economics', 'nass_quickstats_data_Economics.csv'))
    print(f"Loading FARM OPERATIONS data from Economics file...")
    
    if not os.path.exists(filepath):
        print(f"  Warning: Economics file not found at {filepath}")
        return pd.DataFrame()
    
    try:
        df = pd.read_csv(filepath, low_memory=False)
    except Exception as e:
        print(f"  Error reading file: {e}")
        return pd.DataFrame()
    
    # Filter to FARM OPERATIONS with OPERATIONS statistic
    ops_df = df[
        (df['commodity_desc'] == 'FARM OPERATIONS') & 
        (df['statisticcat_desc'] == 'OPERATIONS')
    ].copy()
    
    if ops_df.empty:
        print("  No FARM OPERATIONS data found")
        return pd.DataFrame()
    
    # Clean values
    ops_df = clean_value_column(ops_df)
    
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
    # Filter to state-level aggregations only
    df = nass_df[nass_df['agg_level_desc'] == 'STATE'].copy()
    
    if df.empty:
        print("Warning: No state-level data found")
        return pd.DataFrame()
    
    # Get commodity list
    commodities = df['commodity_desc'].unique()
    
    results = []
    
    for stat_cat in df['statisticcat_desc'].unique():
        # Filter to this statistic category
        cat_df = df[df['statisticcat_desc'] == stat_cat]
        
        # Aggregate by state, crop, year
        agg_df = cat_df.groupby(
            ['state_alpha', 'state_name', 'commodity_desc', 'year', 'sector_desc']
        ).agg({
            'value_num': 'sum',
            'unit_desc': 'first'
        }).reset_index()
        
        agg_df['statistic'] = stat_cat
        results.append(agg_df)
    
    if not results:
        return pd.DataFrame()
    
    long_df = pd.concat(results, ignore_index=True)
    
    # Pivot to get metrics as columns
    pivot_df = long_df.pivot_table(
        index=['state_alpha', 'state_name', 'commodity_desc', 'year', 'sector_desc'],
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


def aggregate_biotech_state_crop_year(biotech_df: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot biotech data to state × crop × year with trait types as columns.
    
    Args:
        biotech_df: Cleaned biotech DataFrame
        
    Returns:
        DataFrame with columns: state_alpha, crop, year, pct_bt, pct_ht, pct_stacked, pct_all_ge
    """
    pivot_df = biotech_df.pivot_table(
        index=['state_alpha', 'state_name', 'crop', 'year'],
        columns='trait_type',
        values='pct_adopted',
        aggfunc='mean'
    ).reset_index()
    
    # Rename columns
    rename_map = {
        'bt_only': 'pct_bt',
        'ht_only': 'pct_ht', 
        'stacked': 'pct_stacked',
        'all_ge': 'pct_all_ge'
    }
    pivot_df = pivot_df.rename(columns=rename_map)
    
    print(f"Aggregated biotech state×crop×year: {len(pivot_df):,} rows")
    return pivot_df


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
        - 'biotech': Pivoted biotech data
        - 'state_crop_biotech': State × crop × year with biotech joined
    """
    print("=" * 60)
    print("LOADING AND PREPARING DATA")
    print("=" * 60)
    
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
    
    # Load and process biotech data
    try:
        biotech_df = load_biotech_data()
        result['biotech'] = aggregate_biotech_state_crop_year(biotech_df)
    except Exception as e:
        print(f"Warning: Could not load biotech data: {e}")
        result['biotech'] = pd.DataFrame()
    
    # Join biotech to state × crop × year for relevant crops
    if 'state_crop_year' in result and not result.get('biotech', pd.DataFrame()).empty:
        merged = result['state_crop_year'].merge(
            result['biotech'],
            on=['state_alpha', 'year'],
            how='left',
            suffixes=('', '_biotech')
        )
        # Only keep biotech data where crop matches
        mask = merged['commodity_desc'].str.upper() == merged['crop']
        merged.loc[~mask, ['pct_bt', 'pct_ht', 'pct_stacked', 'pct_all_ge']] = np.nan
        result['state_crop_biotech'] = merged.drop(columns=['crop', 'state_name_biotech'], errors='ignore')
    
    # Load labor data (wage rates, workers)
    try:
        result['labor'] = load_labor_data()
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
