import pandas as pd

# Check what SALES data has $ unit
state_file = 'web_app/final_data/IN.parquet'
df = pd.read_parquet(state_file)

corn_data = df[df['commodity_desc'] == 'CORN'].copy()
sales_data = corn_data[corn_data['statisticcat_desc'] == 'SALES'].copy()

# Filter to $ only
sales_dollar = sales_data[sales_data['unit_desc'] == '$'].copy()

print("=" * 80)
print("CORN SALES with unit_desc = '$'")
print("=" * 80)

print(f"\nTotal rows: {len(sales_dollar)}")

if 'source_desc' in sales_dollar.columns:
    print("\n--- By Source ---")
    print(sales_dollar['source_desc'].value_counts())
    
    print("\n--- By Year and Source ---")
    by_year_source = sales_dollar.groupby(['year', 'source_desc']).agg({
        'value_num': 'sum'
    }).reset_index()
    
    pivot = by_year_source.pivot(index='year', columns='source_desc', values='value_num').fillna(0)
    print(pivot)
    
    print("\n--- Years with SURVEY data ---")
    survey_years = sales_dollar[sales_dollar['source_desc'] == 'SURVEY']['year'].unique()
    print(sorted(survey_years))
    
    print("\n--- Years with CENSUS data ---")
    census_years = sales_dollar[sales_dollar['source_desc'] == 'CENSUS']['year'].unique()
    print(sorted(census_years))
