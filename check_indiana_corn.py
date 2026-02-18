import pandas as pd

df = pd.read_parquet('final_data/IN.parquet')
print(f'Total rows: {len(df)}')
print(f'Years: {sorted(df["year"].unique())}')

corn_2022 = df[(df['year'] == 2022) & (df['commodity_desc'] == 'CORN')]
print(f'\nCORN 2022 rows: {len(corn_2022)}')

if len(corn_2022) > 0:
    print('\nSample CORN 2022 data:')
    cols = ['year', 'commodity_desc', 'statisticcat_desc', 'unit_desc', 'value_num', 'source_desc']
    print(corn_2022[cols].head(20))
    
    print('\n\nUnique stat categories for CORN 2022:')
    print(corn_2022['statisticcat_desc'].value_counts())
    
    print('\n\nUnique sources for CORN 2022:')
    print(corn_2022['source_desc'].value_counts())
else:
    print('\nNo CORN data found for 2022!')
    print('\nChecking what commodities exist for 2022:')
    print(df[df['year'] == 2022]['commodity_desc'].unique()[:20])
