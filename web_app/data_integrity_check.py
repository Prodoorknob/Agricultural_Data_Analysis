"""
Data Integrity Audit for Agricultural Data Analysis Dashboard
Checks:
  1. Census vs Survey duplication
  2. Logical anomalies (harvested > planted)
  3. Duplicate rows
  4. Missing/null values
  5. Data coverage (year range, commodity counts)
  6. State-level vs National-level consistency
"""
import pandas as pd
import pyarrow.parquet as pq
import os
import glob
import sys

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

DATA_DIR = os.path.join(os.path.dirname(__file__), 'final_data')
REPORT = []

def log(msg):
    REPORT.append(msg)
    print(msg)

def hr():
    log("=" * 80)

def main():
    hr()
    log("DATA INTEGRITY AUDIT REPORT")
    log(f"Generated: {pd.Timestamp.now()}")
    hr()
    
    # ---- Load NATIONAL.parquet ----
    nat_path = os.path.join(DATA_DIR, 'NATIONAL.parquet')
    if not os.path.exists(nat_path):
        log(f"ERROR: {nat_path} not found!")
        return
    
    df = pd.read_parquet(nat_path)
    log(f"\n[SOURCE FILE] NATIONAL.parquet")
    log(f"  Total rows: {len(df):,}")
    log(f"  Columns: {list(df.columns)}")
    log(f"  Year range: {df['year'].min()} - {df['year'].max()}")
    log(f"  Unique states: {df['state_alpha'].nunique()} ({sorted(df['state_alpha'].unique())[:10]}...)")
    
    # ===========================================================
    # CHECK 1: Census vs Survey Duplication
    # ===========================================================
    hr()
    log("\n[CHECK 1] CENSUS vs SURVEY DUPLICATION")
    hr()
    
    if 'source_desc' in df.columns:
        source_counts = df['source_desc'].value_counts()
        log(f"  Source distribution:")
        for src, cnt in source_counts.items():
            log(f"    {src}: {cnt:,} rows ({cnt/len(df)*100:.1f}%)")
        
        # Check for same commodity+year+state having BOTH Census and Survey
        if 'CENSUS' in df['source_desc'].values and 'SURVEY' in df['source_desc'].values:
            key_cols = ['commodity_desc', 'year', 'state_alpha', 'statisticcat_desc']
            available_keys = [c for c in key_cols if c in df.columns]
            
            census_keys = df[df['source_desc'] == 'CENSUS'][available_keys].drop_duplicates()
            survey_keys = df[df['source_desc'] == 'SURVEY'][available_keys].drop_duplicates()
            
            overlap = census_keys.merge(survey_keys, on=available_keys, how='inner')
            log(f"\n  WARNING: {len(overlap):,} key combinations have BOTH Census AND Survey data!")
            if len(overlap) > 0:
                log(f"  This could cause DOUBLE-COUNTING in aggregations.")
                log(f"  Sample overlapping keys:")
                log(f"{overlap.head(10).to_string(index=False)}")
                
                # Show the actual double-counted values
                sample = overlap.head(3)
                for _, row in sample.iterrows():
                    mask = True
                    for col in available_keys:
                        mask = mask & (df[col] == row[col])
                    dupes = df[mask][['source_desc', 'value_num'] + available_keys]
                    log(f"\n  Example duplicate:")
                    log(f"  {dupes.to_string(index=False)}")
        else:
            log(f"  OK: Only one source type found. No Census/Survey overlap risk.")
    else:
        log(f"  WARNING: 'source_desc' column not in data. Cannot check for Census/Survey duplication.")
        log(f"  This means the ETL pipeline may have already filtered, OR the column was dropped.")
    
    # ===========================================================
    # CHECK 2: Area Harvested > Area Planted (Logical Anomaly)
    # ===========================================================
    hr()
    log("\n[CHECK 2] AREA HARVESTED > AREA PLANTED ANOMALIES")
    hr()
    
    if 'statisticcat_desc' in df.columns:
        planted_df = df[df['statisticcat_desc'] == 'AREA PLANTED']
        harvested_df = df[df['statisticcat_desc'] == 'AREA HARVESTED']
        
        log(f"  Total AREA PLANTED rows: {len(planted_df):,}")
        log(f"  Total AREA HARVESTED rows: {len(harvested_df):,}")
        
        # Join on commodity + year + state
        join_keys = ['commodity_desc', 'year', 'state_alpha']
        available_join = [c for c in join_keys if c in df.columns]
        
        planted_agg = planted_df.groupby(available_join)['value_num'].sum().reset_index()
        planted_agg.rename(columns={'value_num': 'planted'}, inplace=True)
        
        harvested_agg = harvested_df.groupby(available_join)['value_num'].sum().reset_index()
        harvested_agg.rename(columns={'value_num': 'harvested'}, inplace=True)
        
        comparison = planted_agg.merge(harvested_agg, on=available_join, how='inner')
        
        # Check where harvested > planted
        anomalies = comparison[comparison['harvested'] > comparison['planted']]
        anomalies = anomalies.copy()
        anomalies['ratio'] = anomalies['harvested'] / anomalies['planted']
        
        log(f"\n  Comparison rows (joined): {len(comparison):,}")
        log(f"  Anomalies (harvested > planted): {len(anomalies):,} ({len(anomalies)/max(len(comparison),1)*100:.1f}%)")
        
        if len(anomalies) > 0:
            log(f"\n  Top anomalies by ratio:")
            top_anomalies = anomalies.sort_values('ratio', ascending=False).head(15)
            log(f"  {top_anomalies.to_string(index=False)}")
            
            # Check for aggregate level (summing across commodities per year)
            log(f"\n  Checking aggregate level (all crops summed per year):")
            agg_planted = planted_df.groupby('year')['value_num'].sum()
            agg_harvested = harvested_df.groupby('year')['value_num'].sum()
            agg_compare = pd.DataFrame({'planted': agg_planted, 'harvested': agg_harvested}).dropna()
            agg_anomalies = agg_compare[agg_compare['harvested'] > agg_compare['planted']]
            if len(agg_anomalies) > 0:
                log(f"  WARNING: {len(agg_anomalies)} years have total harvested > total planted!")
                log(f"  {agg_anomalies.to_string()}")
            else:
                log(f"  OK: No year-level aggregate anomalies.")
    
    # ===========================================================
    # CHECK 3: Exact Duplicate Rows
    # ===========================================================
    hr()
    log("\n[CHECK 3] EXACT DUPLICATE ROWS")
    hr()
    
    dupes = df.duplicated()
    log(f"  Exact duplicate rows: {dupes.sum():,} ({dupes.sum()/len(df)*100:.2f}%)")
    
    if 'statisticcat_desc' in df.columns and 'commodity_desc' in df.columns:
        key_cols = [c for c in ['source_desc', 'commodity_desc', 'year', 'state_alpha', 
                                'statisticcat_desc', 'unit_desc', 'domain_desc'] if c in df.columns]
        key_dupes = df.duplicated(subset=key_cols, keep=False)
        groups = df[key_dupes].groupby(key_cols).size()
        multi = groups[groups > 1]
        log(f"  Key-duplicate groups (same key, multiple rows): {len(multi):,}")
        if len(multi) > 0:
            log(f"  This means the same measurement appears multiple times.")
            log(f"  Sample key-duplicates:")
            log(f"  {multi.head(10).to_string()}")
    
    # ===========================================================
    # CHECK 4: Null / Missing Values
    # ===========================================================
    hr()
    log("\n[CHECK 4] NULL / MISSING VALUES")
    hr()
    
    null_counts = df.isnull().sum()
    for col, cnt in null_counts.items():
        if cnt > 0:
            log(f"  {col}: {cnt:,} nulls ({cnt/len(df)*100:.1f}%)")
    
    # Check value_num specifically
    if 'value_num' in df.columns:
        zero_vals = (df['value_num'] == 0).sum()
        neg_vals = (df['value_num'] < 0).sum()
        log(f"\n  value_num == 0: {zero_vals:,}")
        log(f"  value_num < 0: {neg_vals:,}")
    
    # ===========================================================
    # CHECK 5: Data Coverage
    # ===========================================================
    hr()
    log("\n[CHECK 5] DATA COVERAGE")
    hr()
    
    if 'year' in df.columns:
        years = sorted(df['year'].unique())
        log(f"  Years present: {years}")
        log(f"  Year gaps: {[y for y in range(min(years), max(years)+1) if y not in years]}")
    
    if 'commodity_desc' in df.columns:
        top_commodities = df['commodity_desc'].value_counts().head(20)
        log(f"\n  Top 20 commodities by row count:")
        for comm, cnt in top_commodities.items():
            log(f"    {comm}: {cnt:,}")
    
    if 'statisticcat_desc' in df.columns:
        metrics = df['statisticcat_desc'].value_counts()
        log(f"\n  Available metrics:")
        for m, cnt in metrics.items():
            log(f"    {m}: {cnt:,}")
    
    if 'sector_desc' in df.columns:
        sectors = df['sector_desc'].value_counts()
        log(f"\n  Sectors:")
        for s, cnt in sectors.items():
            log(f"    {s}: {cnt:,}")
    
    # ===========================================================
    # CHECK 6: State-Level vs National Consistency
    # ===========================================================
    hr()
    log("\n[CHECK 6] STATE vs NATIONAL CONSISTENCY")
    hr()
    
    if 'agg_level_desc' in df.columns:
        agg_levels = df['agg_level_desc'].value_counts()
        log(f"  Aggregation levels:")
        for lvl, cnt in agg_levels.items():
            log(f"    {lvl}: {cnt:,}")
        
        # For a sample commodity+year+metric, check if sum(states) == national
        if 'AREA HARVESTED' in df['statisticcat_desc'].values:
            test_commodity = 'CORN'
            test_year = df['year'].max()
            
            state_sum = df[
                (df['commodity_desc'] == test_commodity) & 
                (df['year'] == test_year) & 
                (df['statisticcat_desc'] == 'AREA HARVESTED') & 
                (df['state_alpha'] != 'US')
            ]['value_num'].sum()
            
            national_val = df[
                (df['commodity_desc'] == test_commodity) & 
                (df['year'] == test_year) & 
                (df['statisticcat_desc'] == 'AREA HARVESTED') & 
                (df['state_alpha'] == 'US')
            ]['value_num'].sum()
            
            log(f"\n  Consistency check: {test_commodity}, {test_year}, AREA HARVESTED")
            log(f"    Sum of states: {state_sum:,.0f}")
            log(f"    National total: {national_val:,.0f}")
            if national_val > 0:
                diff_pct = abs(state_sum - national_val) / national_val * 100
                log(f"    Difference: {diff_pct:.1f}%")
                if diff_pct > 5:
                    log(f"    WARNING: State sum differs significantly from national total!")
                else:
                    log(f"    OK: Within 5% tolerance.")
    
    # ===========================================================
    # CHECK 7: Domain-Level Duplication
    # ===========================================================
    hr()
    log("\n[CHECK 7] DOMAIN-LEVEL DUPLICATION")
    hr()
    
    if 'domain_desc' in df.columns:
        domain_counts = df['domain_desc'].value_counts()
        log(f"  Domain distribution:")
        for d, cnt in domain_counts.items():
            log(f"    {d}: {cnt:,}")
        
        # Check if domain=TOTAL and granular domains both exist for same key
        if len(domain_counts) > 1:
            total_rows = df[df['domain_desc'] == 'TOTAL']
            non_total_rows = df[df['domain_desc'] != 'TOTAL']
            
            if len(total_rows) > 0 and len(non_total_rows) > 0:
                key_cols = [c for c in ['commodity_desc', 'year', 'state_alpha', 'statisticcat_desc'] if c in df.columns]
                total_keys = total_rows[key_cols].drop_duplicates()
                non_total_keys = non_total_rows[key_cols].drop_duplicates()
                overlap = total_keys.merge(non_total_keys, on=key_cols, how='inner')
                log(f"\n  Keys with BOTH domain=TOTAL and granular domains: {len(overlap):,}")
                if len(overlap) > 0:
                    log(f"  WARNING: If not filtered properly, domain=TOTAL + granular = DOUBLE COUNTING")
                    log(f"  The filterData() function uses: (d.domain_desc === 'TOTAL' || !d.domain_desc)")
                    log(f"  This CORRECTLY keeps only TOTAL domain rows (the aggregated view).")
    
    # ===========================================================
    # CHECK 8: filterData() Simulation
    # ===========================================================
    hr()
    log("\n[CHECK 8] SIMULATING filterData() LOGIC")
    hr()
    
    # Simulate the frontend's filterData function
    filtered = df.copy()
    original = len(filtered)
    
    # Step 1: Source filter
    if 'source_desc' in filtered.columns:
        source_mask = (
            filtered['source_desc'].isna() | 
            (filtered['source_desc'] == 'SURVEY') |
            (filtered['commodity_desc'] == 'FARM OPERATIONS') |
            (filtered['commodity_desc'].isin(['CORN', 'SOYBEANS', 'WHEAT', 'COTTON']) & 
             (filtered['statisticcat_desc'] == 'SALES'))
        )
        after_source = source_mask.sum()
        log(f"  After source filter (SURVEY + exceptions): {after_source:,} / {original:,} ({after_source/original*100:.1f}%)")
        filtered = filtered[source_mask]
    
    # Step 2: Remove totals
    if 'commodity_desc' in filtered.columns:
        before = len(filtered)
        total_mask = ~filtered['commodity_desc'].str.contains('TOTAL', case=False, na=False)
        class_mask = ~filtered['commodity_desc'].str.contains('ALL CLASSES', case=False, na=False)
        filtered = filtered[total_mask & class_mask]
        log(f"  After removing TOTAL/ALL CLASSES commodities: {len(filtered):,} (removed {before - len(filtered):,})")
    
    # Step 3: Domain filter
    if 'domain_desc' in filtered.columns:
        before = len(filtered)
        domain_mask = (filtered['domain_desc'] == 'TOTAL') | filtered['domain_desc'].isna()
        filtered = filtered[domain_mask]
        log(f"  After domain filter (TOTAL only): {len(filtered):,} (removed {before - len(filtered):,})")
    
    log(f"\n  Final filtered dataset: {len(filtered):,} rows ({len(filtered)/original*100:.1f}% of original)")
    
    # Re-check harvested > planted after filtering
    if 'statisticcat_desc' in filtered.columns:
        p = filtered[filtered['statisticcat_desc'] == 'AREA PLANTED']
        h = filtered[filtered['statisticcat_desc'] == 'AREA HARVESTED']
        
        p_agg = p.groupby('year')['value_num'].sum()
        h_agg = h.groupby('year')['value_num'].sum()
        
        compare = pd.DataFrame({'planted': p_agg, 'harvested': h_agg}).dropna()
        bad_years = compare[compare['harvested'] > compare['planted']]
        
        log(f"\n  Post-filter aggregate check (harvested > planted by year):")
        if len(bad_years) > 0:
            log(f"  WARNING: {len(bad_years)} years still have harvested > planted after filtering!")
            log(f"  {bad_years.to_string()}")
        else:
            log(f"  OK: No year-level anomalies after filtering.")
    
    # ===========================================================
    # SUMMARY
    # ===========================================================
    hr()
    log("\n[SUMMARY]")
    hr()
    log("Review the checks above for any WARNINGs.")
    log("Key areas to investigate:")
    log("  1. Census/Survey overlap -> filterData() keeps SURVEY only (+ exceptions)")
    log("  2. Harvested > Planted -> May be normal for some crops (e.g., multi-harvest crops)")
    log("  3. Key duplicates -> aggregate_national.py should deduplicate via groupby sum")
    log("  4. Domain duplication -> filterData() keeps domain_desc='TOTAL' only")
    
    # Save report
    report_path = os.path.join(os.path.dirname(__file__), 'data_integrity_report.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(REPORT))
    log(f"\nReport saved to: {report_path}")

if __name__ == '__main__':
    main()
