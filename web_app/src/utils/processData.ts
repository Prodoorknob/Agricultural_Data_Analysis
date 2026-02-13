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

/**
 * Clean value string to number.
 * Handles commas, and NASS specific codes (D), (Z) etc.
 */
export function cleanValue(val: any): number {
    if (typeof val === 'number') return val;
    if (!val) return 0;

    const str = String(val).trim();

    // NASS codes for withheld/zero
    if (/^\([A-Z]\)$/i.test(str)) return 0;
    if (['-', '--', 'NA', 'N/A', 'null', 'None'].includes(str)) return 0;

    try {
        return parseFloat(str.replace(/,/g, ''));
    } catch (e) {
        return 0;
    }
}

/**
 * Filter out totals
 */
export function filterTotals(data: any[]) {
    return data.filter(d =>
        !d.commodity_desc?.includes('TOTAL') &&
        !d.commodity_desc?.includes('ALL CLASSES')
    );
}

/**
 * Get Top 10 crops by value for a specific year and metric
 */
export function getTopCrops(
    data: any[],
    year: number,
    metric: string = 'AREA HARVESTED'
) {
    // Filter by year and metric
    const filtered = data.filter(d =>
        d.year === year &&
        d.statisticcat_desc === metric &&
        d.commodity_desc &&
        !['TOTAL', 'ALL CLASSES'].includes(d.commodity_desc)
    );

    // Group by commodity and sum values
    // Uses d3.rollups to sum
    const rolledUp = d3.rollups(
        filtered,
        v => d3.sum(v, d => cleanValue(d.value_num || d.Value)),
        d => d.commodity_desc
    );

    // Sort descending and take top 10
    return rolledUp
        .sort((a, b) => b[1] - a[1])
        .slice(0, 10)
        .map(([commodity, value]) => ({ commodity, value }));
}

/**
 * Get trend data for specific commodities over time
 */
export function getTrendData(
    data: any[],
    metric: string,
    topCommodities: string[]
) {
    // Filter for the specific metric and selected commodities
    const filtered = data.filter(d =>
        d.statisticcat_desc === metric &&
        topCommodities.includes(d.commodity_desc)
    );

    // Group by year
    const yearGroups = d3.group(filtered, d => d.year);

    const trendData: any[] = [];

    yearGroups.forEach((rows, year) => {
        const yearObj: any = { year };

        // For each commodity, sum up the value for that year
        topCommodities.forEach(commodity => {
            const cropRows = rows.filter(r => r.commodity_desc === commodity);
            const total = d3.sum(cropRows, r => cleanValue(r.value_num || r.Value));
            yearObj[commodity] = total;
        });

        trendData.push(yearObj);
    });

    return trendData.sort((a, b) => a.year - b.year);
}

/**
 * processed data for the Hex Map.
 * Aggregates values by State for a specific Year and Metric.
 */
export function getMapData(
    data: any[],
    year: number,
    metric: string
): Record<string, number> {
    const mapData: Record<string, number> = {};

    // Filter relevant rows
    const filtered = data.filter(d =>
        Number(d.year) === year &&
        d.statisticcat_desc &&
        d.statisticcat_desc.toUpperCase() === metric &&
        d.state_alpha
    );

    // Aggregate by state
    filtered.forEach(d => {
        const state = d.state_alpha;
        const val = cleanValue(d.value_num || d.Value);
        if (mapData[state]) {
            mapData[state] += val;
        } else {
            mapData[state] = val;
        }
    });

    return mapData;
}

/**
 * Get "Boom" crops: Top crops by percentage growth between two years.
 */
export function getBoomCrops(
    data: any[],
    metric: string,
    endYear: number,
    startYear: number
) {
    // 1. Get aggregated values for start and end years
    const getYearValues = (y: number) => {
        const filtered = data.filter(d =>
            d.year === y &&
            d.statisticcat_desc === metric &&
            !d.commodity_desc?.includes('TOTAL')
        );
        return d3.rollups(
            filtered,
            v => d3.sum(v, d => cleanValue(d.value_num || d.Value)),
            d => d.commodity_desc
        );
    };

    const startValues = new Map(getYearValues(startYear));
    const endValues = new Map(getYearValues(endYear));

    const growth: { commodity: string, growth: number, start: number, end: number }[] = [];

    // 2. Calculate growth
    endValues.forEach((endVal, commodity) => {
        const startVal = startValues.get(commodity);
        // Filter out small values to avoid huge % jumps on tiny base
        if (startVal && startVal > 10000 && endVal > 0) {
            const pctChange = ((endVal - startVal) / startVal) * 100;
            growth.push({ commodity, growth: pctChange, start: startVal, end: endVal });
        }
    });

    // 3. Sort by growth desc
    return growth.sort((a, b) => b.growth - a.growth).slice(0, 10);
}

/**
 * Get Land Use trends: Area Planted vs Area Harvested over time.
 */
export function getLandUseTrends(data: any[]) {
    // Filter relevant metrics
    const relevant = data.filter(d =>
        ['AREA PLANTED', 'AREA HARVESTED'].includes(d.statisticcat_desc) &&
        !d.commodity_desc?.includes('TOTAL')
    );

    const yearGroups = d3.group(relevant, d => d.year);
    const trends: any[] = [];

    yearGroups.forEach((rows, year) => {
        const planted = d3.sum(
            rows.filter(r => r.statisticcat_desc === 'AREA PLANTED'),
            r => cleanValue(r.value_num || r.Value)
        );
        const harvested = d3.sum(
            rows.filter(r => r.statisticcat_desc === 'AREA HARVESTED'),
            r => cleanValue(r.value_num || r.Value)
        );

        if (planted > 0 || harvested > 0) {
            trends.push({ year, planted, harvested });
        }
    });

    return trends.sort((a, b) => a.year - b.year);
}

/**
 * Get National Land Use Composition over time (Cropland vs Urban)
 */
export function getLandUseComposition(data: any[]) {
    // Filter for "48 States" which represents the national summary
    const national = data.filter(d => d.state_name === '48 States');

    return national
        .map(d => ({
            year: Number(d.year),
            Cropland: cleanValue(d.total_cropland),
            'Urban Land': cleanValue(d.land_in_urban_areas)
        }))
        .sort((a, b) => a.year - b.year);
}

/**
 * Get Cropland vs Urban Land Change per State (First Year vs Last Year)
 */
export function getLandUseChange(data: any[]) {
    // 1. Group by state
    // Filter out "48 States" and regions (usually they don't have standard postal codes, but here we only have state names)
    // We'll exclude '48 States', 'Northeast', etc. if they exist. Based on inspection, '48 States' is the main aggregate.
    const validStates = data.filter(d =>
        d.state_name &&
        !['48 States', 'Corn Belt', 'Appalachian', 'Delta States', 'Lake States', 'Mountain', 'Northeast', 'Northern Plains', 'Pacific', 'Southeast', 'Southern Plains'].includes(d.state_name)
    );

    const stateGroups = d3.group(validStates, d => d.state_name);
    const changes: any[] = [];

    stateGroups.forEach((rows, state) => {
        // Find min and max year for this state
        const sorted = rows.sort((a, b) => Number(a.year) - Number(b.year));
        if (sorted.length < 2) return;

        const first = sorted[0];
        const last = sorted[sorted.length - 1];

        const urbanFirst = cleanValue(first.land_in_urban_areas);
        const urbanLast = cleanValue(last.land_in_urban_areas);
        const cropFirst = cleanValue(first.total_cropland);
        const cropLast = cleanValue(last.total_cropland);

        if (urbanFirst > 0 && cropFirst > 0) {
            const urbanChange = ((urbanLast - urbanFirst) / urbanFirst) * 100;
            const cropChange = ((cropLast - cropFirst) / cropFirst) * 100;

            changes.push({
                state,
                urbanChange,
                cropChange,
                urbanFirst,
                urbanLast,
                cropFirst,
                cropLast
            });
        }
    });

    return changes;
}

/**
 * Get Labor Wage Trends for Selected State vs National vs Key States
 */
export function getLaborTrends(data: any[], selectedState: string = 'INDIANA') {
    // Key comparison states
    const comparisonStates = ['CALIFORNIA', 'FLORIDA', 'HAWAII'];
    const cleanState = selectedState ? selectedState.toUpperCase() : 'INDIANA';

    // 1. Group by Year
    const yearGroups = d3.group(data, d => d.year);
    const trends: any[] = [];

    yearGroups.forEach((rows, year) => {
        const yearNum = Number(year);
        const yearObj: any = { year: yearNum };

        // 2. Calculate National Average for this year
        const nationalAvg = d3.mean(rows, r => cleanValue(r.wage_rate));
        yearObj['National Avg'] = nationalAvg;

        // 3. Get Selected State
        const stateRow = rows.find(r => r.state_name.toUpperCase() === cleanState);
        yearObj[cleanState] = stateRow ? cleanValue(stateRow.wage_rate) : null;

        // 4. Get Comparison States
        comparisonStates.forEach(s => {
            const sRow = rows.find(r => r.state_name.toUpperCase() === s);
            yearObj[s] = sRow ? cleanValue(sRow.wage_rate) : null;
        });

        trends.push(yearObj);
    });

    return trends.sort((a, b) => a.year - b.year);
}
