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
    if (!val) return NaN;
    const str = String(val).trim();
    if (str === '' || str === '0') return 0;
    // USDA suppression codes: (D)=Withheld, (Z)=<half unit, (S)=too few reports, etc.
    if (/^\([A-Z]\)$/i.test(str)) return NaN;
    if (['-', '--', 'NA', 'N/A', 'null', 'None'].includes(str)) return NaN;
    try {
        const parsed = parseFloat(str.replace(/,/g, ''));
        return isNaN(parsed) ? NaN : parsed;
    } catch (e) {
        return NaN;
    }
}

/**
 * Enhanced Filter: Source + Totals + Valid Data
 */
export function filterData(data: any[]): any[] {
    if (!data || data.length === 0) return [];

    // Step 1: Apply non-source filters (totals, domain)
    const basicFiltered = data.filter(d =>
        // Source: Survey or Farm Operations Exception or Revenue Data Exception
        (!d.source_desc || d.source_desc === 'SURVEY' || d.commodity_desc === 'FARM OPERATIONS' ||
            // Allow CENSUS revenue data (SALES with $ unit) for crops where SURVEY lacks dollar revenue
            (d.statisticcat_desc === 'SALES' && d.unit_desc === '$')) &&

        // Remove Totals (User Requirement)
        !d.commodity_desc?.includes('TOTAL') &&
        !d.commodity_desc?.includes('ALL CLASSES') &&

        // Remove Domain Totals — keep only domain=TOTAL for aggregates
        (d.domain_desc === 'TOTAL' || !d.domain_desc)
    );

    // Step 2: Deduplicate Census/Survey overlap — prefer SURVEY when both exist
    const keyMap = new Map<string, any[]>();
    basicFiltered.forEach(d => {
        const key = `${d.state_alpha || ''}|${d.year || ''}|${d.commodity_desc || ''}|${d.statisticcat_desc || ''}|${d.unit_desc || ''}`;
        if (!keyMap.has(key)) keyMap.set(key, []);
        keyMap.get(key)!.push(d);
    });

    const result: any[] = [];
    keyMap.forEach((rows) => {
        const hasSurvey = rows.some(r => r.source_desc === 'SURVEY');
        const hasCensus = rows.some(r => r.source_desc === 'CENSUS');
        if (hasSurvey && hasCensus) {
            // Overlap detected: keep only SURVEY rows
            result.push(...rows.filter(r => r.source_desc === 'SURVEY'));
        } else {
            result.push(...rows);
        }
    });

    return result;
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
        if (!isNaN(val)) {
            mapData[state] = (mapData[state] || 0) + val;
        }
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

    // Use median of start-year values as threshold to exclude tiny/niche crops
    const allStartVals = Array.from(startValues.values()).filter(v => v > 0).sort((a, b) => a - b);
    const medianThreshold = allStartVals.length > 0
        ? allStartVals[Math.floor(allStartVals.length / 2)]
        : 10000;
    // Use at least 10k and at most the median to balance inclusivity
    const minThreshold = Math.max(10000, medianThreshold * 0.25);

    endValues.forEach((endVal, commodity) => {
        const startVal = startValues.get(commodity);
        if (startVal && startVal > minThreshold && endVal > 0) {
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

// Region-based agricultural peer comparison for labor wages
const LABOR_REGION_PEERS: Record<string, string[]> = {
    // Corn Belt
    'IA': ['IL', 'NE', 'MN'], 'IL': ['IA', 'IN', 'MO'], 'IN': ['OH', 'IL', 'KY'],
    'OH': ['IN', 'MI', 'PA'], 'MO': ['IL', 'IA', 'KS'],
    // Great Plains
    'KS': ['NE', 'OK', 'CO'], 'NE': ['IA', 'KS', 'SD'], 'ND': ['SD', 'MN', 'MT'],
    'SD': ['ND', 'NE', 'MN'], 'OK': ['KS', 'TX', 'AR'],
    // Southeast
    'GA': ['AL', 'SC', 'FL'], 'AL': ['GA', 'MS', 'TN'], 'MS': ['AL', 'AR', 'LA'],
    'NC': ['SC', 'VA', 'GA'], 'SC': ['NC', 'GA', 'VA'],
    // West
    'CA': ['WA', 'OR', 'AZ'], 'WA': ['OR', 'CA', 'ID'], 'OR': ['WA', 'CA', 'ID'],
    'TX': ['OK', 'KS', 'NM'], 'CO': ['KS', 'NE', 'WY'],
    // Northeast
    'NY': ['PA', 'NJ', 'VT'], 'PA': ['NY', 'OH', 'NJ'], 'WI': ['MN', 'IA', 'MI'],
    'MN': ['WI', 'IA', 'ND'], 'MI': ['OH', 'WI', 'IN'],
    // Other
    'FL': ['GA', 'AL', 'SC'], 'AR': ['MO', 'MS', 'OK'], 'LA': ['MS', 'AR', 'TX'],
    'MT': ['ND', 'WY', 'ID'], 'ID': ['WA', 'OR', 'MT'], 'AZ': ['CA', 'NM', 'CO'],
};

export function getLaborTrends(data: any[], selectedState: string = 'INDIANA') {
    const wageData = filterData(data).filter(d => d.statisticcat_desc === 'WAGE RATE');
    const cleanState = selectedState ? String(selectedState).toUpperCase() : 'INDIANA';

    // Pick region-appropriate comparison states
    const comparisonStates = LABOR_REGION_PEERS[cleanState] || ['CA', 'TX', 'IA'];

    const yearGroups = d3.group(wageData, d => d.year);
    const trends: any[] = [];

    yearGroups.forEach((rows, year) => {
        const row: any = { year };

        // 1. National Avg (look for US row)
        const national = rows.find(d => d.state_alpha === 'US');
        if (national) {
            row['National Avg'] = cleanValue(national.value_num || national.Value);
        } else {
            const vals = rows.filter(d => d.state_alpha !== 'US')
                .map(d => cleanValue(d.value_num || d.Value))
                .filter(v => !isNaN(v));
            if (vals.length) row['National Avg'] = d3.mean(vals);
        }

        // 2. Selected State
        const selected = rows.find(d => d.state_alpha === cleanState);
        if (selected) row[cleanState] = cleanValue(selected.value_num || selected.Value);

        // 3. Region comparison states (dynamic)
        comparisonStates.forEach(st => {
            const comp = rows.find(d => d.state_alpha === st);
            if (comp) row[st] = cleanValue(comp.value_num || comp.Value);
        });

        trends.push(row);
    });

    // Attach comparison states as metadata for the UI to read
    const sorted = trends.sort((a, b) => a.year - b.year);
    (sorted as any).comparisonStates = comparisonStates;
    return sorted;
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

// ─── Crop Condition Trends ───────────────────────────────────────
/**
 * Extracts weekly CONDITION data for crops.
 * Returns percentage distribution for each condition level per year.
 * CONDITION data has values like GOOD=45, FAIR=30, etc. (% of crop in each state)
 */
export function getCropConditionTrends(data: any[], commodity?: string) {
    const condData = filterData(data).filter(d =>
        d.statisticcat_desc === 'CONDITION' &&
        d.sector_desc === 'CROPS' &&
        (!commodity || d.commodity_desc === commodity)
    );

    if (!condData.length) return [];

    // Group by year and unit_desc (which contains the condition level)
    const yearGroups = d3.group(condData, d => d.year);
    const trends: any[] = [];

    yearGroups.forEach((rows, year) => {
        const conditionLevels: Record<string, number[]> = {
            'EXCELLENT': [], 'GOOD': [], 'FAIR': [], 'POOR': [], 'VERY POOR': []
        };

        rows.forEach(r => {
            const val = cleanValue(r.value_num || r.Value);
            if (isNaN(val)) return;

            // Try to extract condition level from unit_desc
            // USDA stores as 'PCT EXCELLENT', 'PCT GOOD', etc. or bare 'EXCELLENT'
            const unitDesc = String(r.unit_desc || '').toUpperCase().trim();
            let level = '';

            if (unitDesc.startsWith('PCT ')) {
                level = unitDesc.replace('PCT ', '').trim();
            } else if (conditionLevels[unitDesc] !== undefined) {
                level = unitDesc;
            }

            if (conditionLevels[level] !== undefined) {
                conditionLevels[level].push(val);
            }
        });

        // Average across weeks/states for each level
        const entry: any = { year };
        let hasData = false;
        Object.entries(conditionLevels).forEach(([level, vals]) => {
            const avg = vals.length > 0 ? (d3.mean(vals) || 0) : 0;
            entry[level.toLowerCase().replace(/ /g, '_')] = Math.round(avg);
            if (avg > 0) hasData = true;
        });

        if (hasData) trends.push(entry);
    });

    return trends.sort((a, b) => a.year - b.year);
}

// ─── Crop Progress Trends ────────────────────────────────────────
/**
 * Extracts PROGRESS data (planting, harvesting progress %) by year.
 * Returns latest year's weekly progress if available, otherwise annual summary.
 */
export function getCropProgressSummary(data: any[]) {
    const progData = filterData(data).filter(d =>
        d.statisticcat_desc === 'PROGRESS' &&
        d.sector_desc === 'CROPS'
    );

    if (!progData.length) return [];

    // Summarize: which crop has what progress % by year
    const yearGroups = d3.group(progData, d => d.year);
    const trends: any[] = [];

    yearGroups.forEach((rows, year) => {
        const commodityGroups = d3.group(rows, d => d.commodity_desc);
        const yearEntry: any = { year, crops: [] };

        commodityGroups.forEach((cRows, commodity) => {
            const vals = cRows
                .map(r => cleanValue(r.value_num || r.Value))
                .filter(v => !isNaN(v) && v > 0);

            if (vals.length === 0) return;

            // Use median as a "typical progress pace" — avoids trivial 100% from year-end reports
            const sorted = vals.sort((a, b) => a - b);
            const median = sorted[Math.floor(sorted.length / 2)];
            const latest = sorted[sorted.length - 1];

            yearEntry.crops.push({
                commodity,
                progress: Math.round(median),
                latest: Math.round(latest),
                reportCount: vals.length,
            });
        });

        if (yearEntry.crops.length > 0) {
            yearEntry.crops.sort((a: any, b: any) => b.progress - a.progress);
            trends.push(yearEntry);
        }
    });

    return trends.sort((a, b) => a.year - b.year);
}
