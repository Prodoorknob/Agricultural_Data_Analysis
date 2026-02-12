import pandas as pd

# Load the parquet file
file_path = 'sample_aws_data/NATIONAL_SUMMARY_LANDUSE.parquet'
df = pd.read_parquet(file_path)

# Print info
print("\n--- SCHEMA ---")
print(df.info())

# Print sample rows
print("\n--- HEAD ---")
print(df.head(10))

# Print value counts for state and metric
print("\n--- VALUE COUNTS ---")
if 'state_name' in df.columns:
    print("\nStates:", df['state_name'].unique())
if 'commodity_desc' in df.columns:
    print("\nCommodities:", df['commodity_desc'].unique())
if 'statisticcat_desc' in df.columns:
    print("\nStatistic Categories:", df['statisticcat_desc'].unique())
