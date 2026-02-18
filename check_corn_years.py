import pandas as pd

df = pd.read_parquet('final_data/IN.parquet')
print(f'Total rows: {len(df)}')
print(f'Years: {sorted(df["year"].unique())}')

corn = df[df['commodity_desc'] == 'CORN']
print(f'\n\nTotal CORN rows: {len(corn)}')
print(f'CORN years: {sorted(corn["year"].unique())}')

print('\n\nCORN data by year:')
corn_by_year = corn.groupby('year').size()
print(corn_by_year)

print('\n\nChecking for CORN SALES data:')
corn_sales = corn[(corn['statisticcat_desc'] == 'SALES') & (corn['unit_desc'] == '$')]
print(f'Total CORN SALES rows: {len(corn_sales)}')
print(f'CORN SALES years: {sorted(corn_sales["year"].unique())}')

if len(corn_sales) > 0:
    print('\n\nSample CORN SALES data:')
    cols = ['year', 'commodity_desc', 'statisticcat_desc', 'unit_desc', 'value_num', 'source_desc']
    print(corn_sales[cols].tail(10))

print('\n\n2022 Sector breakdown:')
print(df[df['year'] == 2022]['sector_desc'].value_counts())
