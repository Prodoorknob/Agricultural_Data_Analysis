"""
Process MajorLandUse.csv into a JSON file for the web app.
Outputs two datasets:
  1. National composition over time (for stacked area chart)
  2. State-level change between first and last year (for bar chart)
"""
import pandas as pd
import json
import os

RAW_CSV = os.path.join(os.path.dirname(__file__), '..', 'raw_data', 'MajorLandUse.csv')
OUT_DIR = os.path.join(os.path.dirname(__file__), 'public', 'data')

# Categories we care about for the composition chart
COMPOSITION_CATEGORIES = [
    'Total cropland',
    'Grassland pasture and range',
    'Forest-use land (all)',
    'All special uses of land',
    'Land in urban areas',
    'Miscellaneous other land',
]

# Friendly labels
LABEL_MAP = {
    'Total cropland': 'Cropland',
    'Grassland pasture and range': 'Grassland & Pasture',
    'Forest-use land (all)': 'Forest',
    'All special uses of land': 'Special Uses',
    'Land in urban areas': 'Urban',
    'Miscellaneous other land': 'Other',
}

def main():
    df = pd.read_csv(RAW_CSV)
    
    # Clean Value column (remove commas if string)
    df['Value'] = pd.to_numeric(df['Value'], errors='coerce')
    
    # Values are in 1,000 acres — convert to actual acres (* 1000)
    df['value_acres'] = df['Value'] * 1000

    # ---- 1. National Composition Over Time ----
    us_total = df[df['Region or State'] == 'U.S. total']
    composition_data = []
    
    for year in sorted(us_total['Year'].unique()):
        year_data = us_total[us_total['Year'] == year]
        row = {'year': int(year)}
        for cat in COMPOSITION_CATEGORIES:
            match = year_data[year_data['Land use'] == cat]
            if not match.empty:
                row[LABEL_MAP[cat]] = int(match.iloc[0]['value_acres'])
            else:
                row[LABEL_MAP[cat]] = 0
        composition_data.append(row)
    
    # ---- 2. State-Level Change (earliest vs latest year) ----
    # Filter for actual states (not regions/totals)
    region_keywords = ['total', 'States', 'U.S.', '48 States', 'AK and HI']
    state_df = df[~df['Region or State'].isin([
        'Northeast', 'Lake States', 'Corn Belt', 'Northern Plains',
        'Appalachian', 'Southeast', 'Delta States', 'Southern Plains',
        'Mountain', 'Pacific', '48 States', 'U.S. total'
    ])]
    # Also exclude region totals (Region column ends with 'total')
    state_df = state_df[~state_df['Region'].str.contains('total', case=False, na=False)]
    
    min_year = state_df['Year'].min()
    max_year = state_df['Year'].max()
    
    change_data = []
    states = state_df['Region or State'].unique()
    
    for state in states:
        st = state_df[state_df['Region or State'] == state]
        
        # Cropland change
        crop_early = st[(st['Year'] == min_year) & (st['Land use'] == 'Total cropland')]['value_acres']
        crop_late  = st[(st['Year'] == max_year) & (st['Land use'] == 'Total cropland')]['value_acres']
        
        # Urban change
        urban_early = st[(st['Year'] == min_year) & (st['Land use'] == 'Land in urban areas')]['value_acres']
        urban_late  = st[(st['Year'] == max_year) & (st['Land use'] == 'Land in urban areas')]['value_acres']
        
        crop_change = 0
        urban_change = 0
        
        if not crop_early.empty and not crop_late.empty and crop_early.values[0] > 0:
            crop_change = ((crop_late.values[0] - crop_early.values[0]) / crop_early.values[0]) * 100
        
        if not urban_early.empty and not urban_late.empty and urban_early.values[0] > 0:
            urban_change = ((urban_late.values[0] - urban_early.values[0]) / urban_early.values[0]) * 100
        
        change_data.append({
            'state': state,
            'cropChange': round(crop_change, 1),
            'urbanChange': round(urban_change, 1),
        })
    
    # Sort by urban change descending
    change_data.sort(key=lambda x: x['urbanChange'], reverse=True)
    
    # ---- 3. State-level composition for selected year (for potential future use) ----
    # We'll include per-state data too
    state_composition = []
    for _, row in state_df.iterrows():
        cat = row['Land use']
        if cat in LABEL_MAP:
            state_composition.append({
                'state': row['Region or State'],
                'year': int(row['Year']),
                'category': LABEL_MAP[cat],
                'value': int(row['value_acres']) if pd.notna(row['value_acres']) else 0
            })

    # ---- Write Output ----
    os.makedirs(OUT_DIR, exist_ok=True)
    output = {
        'composition': composition_data,
        'stateChange': change_data,
        'stateComposition': state_composition,
    }
    
    out_path = os.path.join(OUT_DIR, 'land_use.json')
    with open(out_path, 'w') as f:
        json.dump(output, f)
    
    print(f"[OK] Wrote {out_path}")
    print(f"  - composition: {len(composition_data)} year entries")
    print(f"  - stateChange: {len(change_data)} states")
    print(f"  - stateComposition: {len(state_composition)} rows")
    
    # Quick preview
    print("\nComposition preview (first 3 years):")
    for row in composition_data[:3]:
        print(f"  {row}")
    
    print("\nTop 5 states by urban growth:")
    for row in change_data[:5]:
        print(f"  {row['state']}: Urban +{row['urbanChange']}%, Cropland {row['cropChange']}%")

if __name__ == '__main__':
    main()
