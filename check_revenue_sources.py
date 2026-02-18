import pandas as pd
import os

# Check revenue/sales data sources
print("=" * 80)
print("CHECKING REVENUE DATA SOURCES")
print("=" * 80)

# Check state files
state_file = 'web_app/final_data/IN.parquet'
if os.path.exists(state_file):
    print(f"\n\n--- CHECKING {state_file} ---")
    df = pd.read_parquet(state_file)
    
    # Check for CORN specifically
    corn_data = df[df['commodity_desc'] == 'CORN'].copy()
    
    if len(corn_data) > 0:
        print(f"\nTotal CORN rows: {len(corn_data)}")
        
        # Check sales/revenue data
        sales_data = corn_data[corn_data['statisticcat_desc'] == 'SALES'].copy()
        print(f"\nCORN SALES rows: {len(sales_data)}")
        
        if len(sales_data) > 0:
            print("\n--- SALES Data Sources ---")
            if 'source_desc' in sales_data.columns:
                print(sales_data['source_desc'].value_counts())
            else:
                print("No source_desc column found")
            
            print("\n--- SALES Unit Descriptions ---")
            if 'unit_desc' in sales_data.columns:
                print(sales_data['unit_desc'].value_counts())
            
            print("\n--- Sample SALES rows ---")
            cols_to_show = ['year', 'source_desc', 'statisticcat_desc', 'unit_desc', 'value_num']
            cols_to_show = [c for c in cols_to_show if c in sales_data.columns]
            print(sales_data[cols_to_show].sort_values('year').tail(20))
        
        # Check for VALUE or other revenue measures
        print("\n\n--- ALL statisticcat_desc for CORN ---")
        if 'statisticcat_desc' in corn_data.columns:
            print(corn_data['statisticcat_desc'].value_counts())
        
        # Check which years have which source_desc
        if 'source_desc' in corn_data.columns and len(sales_data) > 0:
            print("\n--- SALES by Year and Source ---")
            sales_by_year_source = sales_data.groupby(['year', 'source_desc']).size().unstack(fill_value=0)
            print(sales_by_year_source)

# Also check national file
national_file = 'web_app/final_data/NATIONAL.parquet'
if os.path.exists(national_file):
    print(f"\n\n--- CHECKING {national_file} ---")
    df_nat = pd.read_parquet(national_file)
    
    corn_nat = df_nat[df_nat['commodity_desc'] == 'CORN'].copy()
    if len(corn_nat) > 0:
        sales_nat = corn_nat[corn_nat['statisticcat_desc'] == 'SALES'].copy()
        print(f"\nNATIONAL CORN SALES rows: {len(sales_nat)}")
        
        if len(sales_nat) > 0 and 'source_desc' in sales_nat.columns:
            print("\n--- SALES Data Sources (National) ---")
            print(sales_nat['source_desc'].value_counts())
            
            print("\n--- SALES by Year and Source (National) ---")
            sales_by_year_source = sales_nat.groupby(['year', 'source_desc']).size().unstack(fill_value=0)
            print(sales_by_year_source)

print("\n" + "=" * 80)
print("DONE")
print("=" * 80)
