import * as d3 from 'd3-array';

export interface CropData {
    state_alpha: string;
    year: number;
    commodity_desc: string;
    value_num?: number;
    Value?: string | number;
    statisticcat_desc?: string;
    [key: string]: any;
}

export function cleanValue(val: any): number {
    if (typeof val === 'number') return val;
    if (!val) return 0;
    const str = String(val).trim();
    if (/^\([A-Z]\)$/i.test(str)) return 0;
    if (['-', '--', 'NA', 'N/A', 'null', 'None'].includes(str)) return 0;
    try {
        return parseFloat(str.replace(/,/g, ''));
    } catch (e) {
        return 0;
    }
}

/**
 * Enhanced Filter: Source + Totals + Valid Data
 */
export function filterData(data: any[]): any[] {
    if (!data || data.length === 0) return [];

    return data.filter(d =>
        // 1. Source: Survey or Farm Operations Exception
        (!d.source_desc || d.source_desc === 'SURVEY' || d.commodity_desc === 'FARM OPERATIONS' ||
            (['CORN', 'SOYBEANS', 'WHEAT', 'COTTON'].includes(d.commodity_desc) && d.statisticcat_desc === 'SALES')) &&

        // 2. Remove Totals (User Requirement)
        !d.commodity_desc?.includes('TOTAL') &&
        !d.commodity_desc?.includes('ALL CLASSES') &&

        // 3. Remove Domain Totals (if granular data is available)
        // Usually we WANT domain=TOTAL for state aggregates
        (d.domain_desc === 'TOTAL' || !d.domain_desc)
    );
}

// Re-export filterSource for backward compatibility (maps to filterData now)
export const filterSource = filterData;
export const filterTotals = filterData;

export function getTopCrops(data: any[], year: number, metric: string = 'AREA HARVESTED') {
    const filtered = filterData(data).filter(d =>
        d.year === year &&
        (metric === 'SALES' ? ['SALES', 'PRODUCTION', 'VALUE'].includes(d.statisticcat_desc) : d.statisticcat_desc === metric) &&
        (metric === 'SALES' ? d.unit_desc === '$' : true)
    );

    const commodityGroups = d3.group(filtered, d => d.commodity_desc);
    const rolledUp: [string, number][] = [];

    commodityGroups.forEach((rows, commodity) => {
        let relevantRows = rows;
        if (metric === 'SALES') {
            const hasSales = rows.some(r => r.statisticcat_desc === 'SALES');
            if (hasSales) relevantRows = rows.filter(r => r.statisticcat_desc === 'SALES');
            else {
                const hasProduction = rows.some(r => r.statisticcat_desc === 'PRODUCTION');
                if (hasProduction) relevantRows = rows.filter(r => r.statisticcat_desc === 'PRODUCTION');
                else relevantRows = rows.filter(r => r.statisticcat_desc === 'VALUE');
            }
        }
        const value = d3.sum(relevantRows, d => cleanValue(d.value_num || d.Value));
        if (value > 0) rolledUp.push([commodity, value]);
    });

    return rolledUp.sort((a, b) => b[1] - a[1]).slice(0, 10).map(([commodity, value]) => ({ commodity, value }));
}

export function getTrendData(data: any[], metric: string, topCommodities: string[]) {
    const filtered = filterData(data).filter(d =>
        (metric === 'SALES' ? ['SALES', 'PRODUCTION', 'VALUE'].includes(d.statisticcat_desc) : d.statisticcat_desc === metric) &&
        topCommodities.includes(d.commodity_desc) &&
        (metric === 'SALES' ? d.unit_desc === '$' : true)
    );

    const yearGroups = d3.group(filtered, d => d.year);
    const trendData: any[] = [];

    yearGroups.forEach((rows, year) => {
        const yearObj: any = { year };
        topCommodities.forEach(commodity => {
            const cropRows = rows.filter(r => r.commodity_desc === commodity);
            let relevantRows = cropRows;
            if (metric === 'SALES') {
                const hasSales = cropRows.some(r => r.statisticcat_desc === 'SALES');
                if (hasSales) relevantRows = cropRows.filter(r => r.statisticcat_desc === 'SALES');
                else {
                    const hasProduction = cropRows.some(r => r.statisticcat_desc === 'PRODUCTION');
                    if (hasProduction) relevantRows = cropRows.filter(r => r.statisticcat_desc === 'PRODUCTION');
                    else relevantRows = cropRows.filter(r => r.statisticcat_desc === 'VALUE');
                }
            }
            yearObj[commodity] = d3.sum(relevantRows, r => cleanValue(r.value_num || r.Value));
        });
        trendData.push(yearObj);
    });

    return trendData.sort((a, b) => a.year - b.year);
}

export function getMapData(data: any[], year: number, metric: string): Record<string, number> {
    const mapData: Record<string, number> = {};
    const filtered = filterData(data).filter(d =>
        Number(d.year) === year &&
        d.statisticcat_desc &&
        d.statisticcat_desc.toUpperCase() === metric &&
        d.state_alpha && d.state_alpha !== 'US' // Exclude US total from map
    );

    filtered.forEach(d => {
        const state = d.state_alpha;
        const val = cleanValue(d.value_num || d.Value);
        mapData[state] = (mapData[state] || 0) + val;
    });

    return mapData;
}

export function getBoomCrops(data: any[], metric: string, endYear: number, startYear: number) {
    const cleanData = filterData(data);
    const getYearValues = (y: number) => {
        const filtered = cleanData.filter(d =>
            d.year === y &&
            (metric === 'SALES' ? ['SALES', 'PRODUCTION', 'VALUE'].includes(d.statisticcat_desc) : d.statisticcat_desc === metric) &&
            (metric === 'SALES' ? d.unit_desc === '$' : true)
        );
        const commodityGroups = d3.group(filtered, d => d.commodity_desc);
        const results: [string, number][] = [];
        commodityGroups.forEach((rows, commodity) => {
            let relevantRows = rows;
            if (metric === 'SALES') {
                // Same priority logic
                const hasSales = rows.some(r => r.statisticcat_desc === 'SALES');
                if (hasSales) relevantRows = rows.filter(r => r.statisticcat_desc === 'SALES');
                else {
                    const hasProduction = rows.some(r => r.statisticcat_desc === 'PRODUCTION');
                    if (hasProduction) relevantRows = rows.filter(r => r.statisticcat_desc === 'PRODUCTION');
                    else relevantRows = rows.filter(r => r.statisticcat_desc === 'VALUE');
                }
            }
            results.push([commodity, d3.sum(relevantRows, d => cleanValue(d.value_num || d.Value))]);
        });
        return results;
    };

    const startValues = new Map(getYearValues(startYear));
    const endValues = new Map(getYearValues(endYear));
    const growth: any[] = [];

    endValues.forEach((endVal, commodity) => {
        const startVal = startValues.get(commodity);
        if (startVal && startVal > 10000 && endVal > 0) {
            const pctChange = ((endVal - startVal) / startVal) * 100;
            growth.push({ commodity, growth: pctChange, start: startVal, end: endVal });
        }
    });

    return growth.sort((a, b) => b.growth - a.growth).slice(0, 10);
}

export function getLandUseTrends(data: any[]) {
    const relevant = filterData(data).filter(d =>
        ['AREA PLANTED', 'AREA HARVESTED'].includes(d.statisticcat_desc)
    );

    // Step 1: Find crops that have BOTH AREA PLANTED and AREA HARVESTED data
    const plantedCrops = new Set(
        relevant.filter(d => d.statisticcat_desc === 'AREA PLANTED').map(d => d.commodity_desc)
    );
    const harvestedCrops = new Set(
        relevant.filter(d => d.statisticcat_desc === 'AREA HARVESTED').map(d => d.commodity_desc)
    );
    const bothCrops = new Set([...plantedCrops].filter(c => harvestedCrops.has(c)));

    // Step 2: Only keep rows for crops with BOTH metrics
    const paired = relevant.filter(d => bothCrops.has(d.commodity_desc));

    // Step 3: Detect multi-harvest crops (harvested/planted ratio > 1.5 in majority of years)
    const multiHarvestCrops: string[] = [];
    bothCrops.forEach(crop => {
        const cropRows = paired.filter(d => d.commodity_desc === crop);
        const years = [...new Set(cropRows.map(d => d.year))];
        let multiCount = 0;
        years.forEach(y => {
            const p = d3.sum(cropRows.filter(r => r.year === y && r.statisticcat_desc === 'AREA PLANTED'), r => cleanValue(r.value_num || r.Value));
            const h = d3.sum(cropRows.filter(r => r.year === y && r.statisticcat_desc === 'AREA HARVESTED'), r => cleanValue(r.value_num || r.Value));
            if (p > 0 && h / p > 1.5) multiCount++;
        });
        if (years.length > 0 && multiCount / years.length > 0.5) {
            multiHarvestCrops.push(crop);
        }
    });

    // Step 4: Aggregate by year
    const yearGroups = d3.group(paired, d => d.year);
    const trends: any[] = [];

    yearGroups.forEach((rows, year) => {
        const planted = d3.sum(rows.filter(r => r.statisticcat_desc === 'AREA PLANTED'), r => cleanValue(r.value_num || r.Value));
        const harvested = d3.sum(rows.filter(r => r.statisticcat_desc === 'AREA HARVESTED'), r => cleanValue(r.value_num || r.Value));
        if (planted > 0 || harvested > 0) trends.push({ year, planted, harvested });
    });

    const sorted = trends.sort((a, b) => a.year - b.year);

    // Attach metadata for UI consumption
    (sorted as any).multiHarvestCrops = multiHarvestCrops;
    (sorted as any).pairedCropCount = bothCrops.size;
    (sorted as any).excludedCropCount = harvestedCrops.size - bothCrops.size;

    return sorted;
}

export function getLandUseComposition(data: any[]) {
    // Current data source lacks National totals for Cropland/Urban
    // Trying fallback to AG LAND Asset Value? NO.
    // Return empty for now to avoid crashes.
    return [];
}

export function getLandUseChange(data: any[]) {
    // Data unavailable in current ETL pipeline
    return [];
}

export function getLaborTrends(data: any[], selectedState: string = 'INDIANA') {
    // Fix: Explicitly filter for WAGE RATE
    const wageData = filterData(data).filter(d => d.statisticcat_desc === 'WAGE RATE');
    const cleanState = selectedState ? String(selectedState).toUpperCase() : 'INDIANA';

    const yearGroups = d3.group(wageData, d => d.year);
    const trends: any[] = [];

    yearGroups.forEach((rows, year) => {
        const row: any = { year };

        // 1. National Avg (look for US row)
        const national = rows.find(d => d.state_alpha === 'US');
        if (national) {
            row['National Avg'] = cleanValue(national.value_num || national.Value);
        } else {
            // Fallback: Average of all states
            const vals = rows.filter(d => d.state_alpha !== 'US').map(d => cleanValue(d.value_num || d.Value));
            if (vals.length) row['National Avg'] = d3.mean(vals);
        }

        // 2. Selected State
        // Ensure we check state_alpha correctly (codes involved)
        // selectedState coming from UI is usually Code (IN)
        const selected = rows.find(d => d.state_alpha === cleanState);
        if (selected) row[cleanState] = cleanValue(selected.value_num || selected.Value);

        // 3. Comparison States
        ['CA', 'FL', 'HI'].forEach(st => {
            const comp = rows.find(d => d.state_alpha === st);
            if (comp) row[st] = cleanValue(comp.value_num || comp.Value);
        });

        trends.push(row);
    });

    return trends.sort((a, b) => a.year - b.year);
}

export function getOperationsTrend(data: any[]) {
    const opsData = filterData(data).filter(d =>
        d.commodity_desc === 'FARM OPERATIONS' && d.statisticcat_desc === 'OPERATIONS'
    );
    const yearGroups = d3.group(opsData, d => d.year);
    const trends: any[] = [];
    yearGroups.forEach((rows, year) => {
        const totalOps = d3.sum(rows, d => cleanValue(d.value_num || d.Value));
        trends.push({ year, operations: totalOps });
    });
    return trends.sort((a, b) => a.year - b.year);
}

// ─── Anomaly Detection ──────────────────────────────────────────
/**
 * Detect anomaly years where a value dips below (mean - 1 * stddev).
 * Returns array of { year, value, meanVal, threshold } for flagged years.
 */
export function detectAnomalies(
    yearValues: { year: number; value: number }[],
    sensitivity: number = 1.0
): { year: number; value: number; meanVal: number; threshold: number }[] {
    if (yearValues.length < 3) return [];
    const vals = yearValues.map(d => d.value).filter(v => v > 0);
    if (vals.length < 3) return [];

    const meanVal = d3.mean(vals) || 0;
    const stdDev = Math.sqrt(d3.mean(vals.map(v => (v - meanVal) ** 2)) || 0);
    const threshold = meanVal - sensitivity * stdDev;

    return yearValues
        .filter(d => d.value > 0 && d.value < threshold)
        .map(d => ({ year: d.year, value: d.value, meanVal, threshold }));
}

// ─── Revenue for a Single Commodity ──────────────────────────────
/**
 * Extract SALES / revenue data for a single commodity over time.
 */
export function getRevenueForCommodity(data: any[], commodity: string) {
    // Filter to SALES in $ only (use d3.max per year to pick the total, avoiding sub-domain dupes)
    const filtered = filterData(data).filter(d =>
        d.commodity_desc === commodity &&
        d.statisticcat_desc === 'SALES' &&
        d.unit_desc === '$'
    );

    const yearGroups = d3.group(filtered, d => d.year);
    const trends: { year: number; revenue: number }[] = [];

    yearGroups.forEach((rows, year) => {
        // Use max rather than sum to get the national total (avoid sub-domain duplicates)
        const revenue = d3.max(rows, r => cleanValue(r.value_num || r.Value)) || 0;
        if (revenue > 0) trends.push({ year, revenue });
    });

    return trends.sort((a, b) => a.year - b.year);
}

// ─── Area Planted for a Single Commodity ─────────────────────────
/**
 * Extract AREA PLANTED data for a single commodity over time.
 */
export function getAreaPlantedForCommodity(data: any[], commodity: string) {
    const filtered = filterData(data).filter(d =>
        d.commodity_desc === commodity &&
        d.statisticcat_desc === 'AREA PLANTED'
    );

    const yearGroups = d3.group(filtered, d => d.year);
    const trends: { year: number; areaPlanted: number }[] = [];

    yearGroups.forEach((rows, year) => {
        const area = d3.sum(rows, r => cleanValue(r.value_num || r.Value));
        if (area > 0) trends.push({ year, areaPlanted: area });
    });

    return trends.sort((a, b) => a.year - b.year);
}

// ─── Unified Commodity Story ─────────────────────────────────────
/**
 * Returns a unified dataset for the "story" view of a single commodity.
 * Merges yield, production, area harvested, area planted, and revenue into
 * one array keyed by year. Also detects anomaly dip years for yield.
 */
export function getCommodityStory(data: any[], commodity: string) {
    const cropsData = filterData(data).filter(d =>
        d.commodity_desc === commodity && d.sector_desc === 'CROPS'
    );

    const yearGroups = d3.group(cropsData, d => d.year);
    const mergedMap = new Map<number, any>();

    yearGroups.forEach((rows, year) => {
        const production = d3.sum(
            rows.filter(r => r.statisticcat_desc === 'PRODUCTION'),
            r => cleanValue(r.value_num || r.Value)
        );
        const yieldVal = d3.mean(
            rows.filter(r => r.statisticcat_desc === 'YIELD'),
            r => cleanValue(r.value_num || r.Value)
        ) || 0;
        const areaHarvested = d3.sum(
            rows.filter(r => r.statisticcat_desc === 'AREA HARVESTED'),
            r => cleanValue(r.value_num || r.Value)
        );
        const areaPlanted = d3.sum(
            rows.filter(r => r.statisticcat_desc === 'AREA PLANTED'),
            r => cleanValue(r.value_num || r.Value)
        );
        // Revenue: use only $ SALES, take max per year to get the aggregate total
        const salesRows = rows.filter(r =>
            r.statisticcat_desc === 'SALES' &&
            r.unit_desc === '$'
        );
        const revenue = d3.max(salesRows, r => cleanValue(r.value_num || r.Value)) || 0;

        const prodUnit = rows.find(r => r.statisticcat_desc === 'PRODUCTION')?.unit_desc || '';
        const yieldUnit = rows.find(r => r.statisticcat_desc === 'YIELD')?.unit_desc || '';

        mergedMap.set(year, {
            year,
            production,
            yield: yieldVal,
            areaHarvested,
            areaPlanted,
            revenue,
            prodUnit,
            yieldUnit,
        });
    });

    // Merge in revenue from non-CROPS sector (SALES might be under ECONOMICS)
    const revData = getRevenueForCommodity(data, commodity);
    revData.forEach(r => {
        const existing = mergedMap.get(r.year);
        if (existing) {
            if (existing.revenue === 0) existing.revenue = r.revenue;
        } else {
            mergedMap.set(r.year, {
                year: r.year, production: 0, yield: 0,
                areaHarvested: 0, areaPlanted: 0, revenue: r.revenue,
                prodUnit: '', yieldUnit: '',
            });
        }
    });

    // Also merge area planted if not already found under sector CROPS
    const plantedData = getAreaPlantedForCommodity(data, commodity);
    plantedData.forEach(p => {
        const existing = mergedMap.get(p.year);
        if (existing && existing.areaPlanted === 0) {
            existing.areaPlanted = p.areaPlanted;
        }
    });

    const story = Array.from(mergedMap.values()).sort((a, b) => a.year - b.year);

    // Detect yield anomalies
    const yieldPairs = story.filter(d => d.yield > 0).map(d => ({ year: d.year, value: d.yield }));
    const anomalies = detectAnomalies(yieldPairs);
    const anomalyYears = new Set(anomalies.map(a => a.year));

    // Tag each data point
    story.forEach(d => {
        d.isAnomaly = anomalyYears.has(d.year);
    });

    return { story, anomalies, anomalyYears: Array.from(anomalyYears) };
}
