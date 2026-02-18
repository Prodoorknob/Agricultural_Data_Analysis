import pandas as pd

state_file = 'web_app/final_data/IN.parquet'
df = pd.read_parquet(state_file)

corn_data = df[df['commodity_desc'] == 'CORN'].copy()

# Get PCT OF MKTG YEAR data
pct_mktg = corn_data[
    (corn_data['statisticcat_desc'] == 'SALES') & 
    (corn_data['unit_desc'] == 'PCT OF MKTG YEAR')
].copy()

print("=" * 80)
print("PCT OF MKTG YEAR Analysis")
print("=" * 80)

print(f"\nTotal rows: {len(pct_mktg)}")

# Check what additional columns might help
print("\n--- Available columns ---")
cols_of_interest = ['year', 'commodity_desc', 'class_desc', 'prodn_practice_desc', 
                    'util_practice_desc', 'freq_desc', 'begin_code', 'end_code',
                    'reference_period_desc', 'week_ending', 'value_num', 'CV']
available_cols = [c for c in cols_of_interest if c in pct_mktg.columns]
print(available_cols)

# Sample rows
print("\n--- Sample PCT OF MKTG YEAR rows (2021) ---")
sample = pct_mktg[pct_mktg['year'] == 2021][available_cols].head(15)
print(sample.to_string())

# Check if there's reference_period or time period info
if 'reference_period_desc' in pct_mktg.columns:
    print("\n--- Reference Periods ---")
    print(pct_mktg['reference_period_desc'].value_counts().head(20))

if 'week_ending' in pct_mktg.columns:
    print("\n--- Week Ending (sample) ---")
    print(pct_mktg[pct_mktg['year'] == 2021]['week_ending'].value_counts().head(10))

# Now check if we have PRODUCTION and PRICE RECEIVED data for the same years
print("\n\n" + "=" * 80)
print("Can we calculate revenue from PCT OF MKTG YEAR?")
print("=" * 80)

# Check for production data
production = corn_data[corn_data['statisticcat_desc'] == 'PRODUCTION'].copy()
print(f"\nPRODUCTION rows: {len(production)}")
if len(production) > 0:
    print("Sample production (2021):")
    prod_2021 = production[production['year'] == 2021][['year', 'value_num', 'unit_desc']].head(5)
    print(prod_2021.to_string())

# Check for price data
price = corn_data[corn_data['statisticcat_desc'] == 'PRICE RECEIVED'].copy()
print(f"\n\nPRICE RECEIVED rows: {len(price)}")
if len(price) > 0:
    print("Sample prices (2021):")
    price_cols = ['year', 'value_num', 'unit_desc']
    if 'reference_period_desc' in price.columns:
        price_cols.insert(1, 'reference_period_desc')
    price_2021 = price[price['year'] == 2021][price_cols].head(10)
    print(price_2021.to_string())

print("\n\n" + "=" * 80)
print("Calculation Example")
print("=" * 80)

# Try to calculate for a specific year
year = 2021
corn_2021 = corn_data[corn_data['year'] == year].copy()

# Get total production
prod_total = corn_2021[corn_2021['statisticcat_desc'] == 'PRODUCTION']['value_num'].max()
prod_unit = corn_2021[corn_2021['statisticcat_desc'] == 'PRODUCTION']['unit_desc'].iloc[0] if len(corn_2021[corn_2021['statisticcat_desc'] == 'PRODUCTION']) > 0 else None

# Get average price for the year
avg_price = corn_2021[corn_2021['statisticcat_desc'] == 'PRICE RECEIVED']['value_num'].mean()
price_unit = corn_2021[corn_2021['statisticcat_desc'] == 'PRICE RECEIVED']['unit_desc'].iloc[0] if len(corn_2021[corn_2021['statisticcat_desc'] == 'PRICE RECEIVED']) > 0 else None

print(f"\nYear: {year}")
print(f"Total Production: {prod_total:,.0f} {prod_unit}" if prod_total else "N/A")
print(f"Average Price: ${avg_price:.2f} {price_unit}" if avg_price and not pd.isna(avg_price) else "N/A")

if prod_total and avg_price and not pd.isna(avg_price):
    total_revenue_estimate = prod_total * avg_price
    print(f"\nEstimated Total Revenue: ${total_revenue_estimate:,.2f}")
    
    # Now show what PCT values mean
    print("\n--- What PCT OF MKTG YEAR values represent ---")
    pct_2021 = pct_mktg[pct_mktg['year'] == year].copy()
    for idx, row in pct_2021.head(3).iterrows():
        pct = row['value_num']
        estimated_sales = (pct / 100) * total_revenue_estimate
        print(f"  {pct}% of marketing year = ${estimated_sales:,.2f} in that period")
