import * as d3 from 'd3-array';
import { CROP_COMMODITIES } from '@/lib/constants';

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
 * Enhanced Filter: Source + Totals + Valid Data + Period Canonicalization
 *
 * NASS publishes the same (state, year, commodity, stat) fact several times —
 * once per `reference_period_desc` (YEAR, YEAR - JUN ACREAGE, YEAR - MAR
 * ACREAGE, YEAR - NOV FORECAST, …) and sometimes once per `source_desc`
 * (SURVEY annual + CENSUS every 5 years). Naive summing inflates acreage/
 * production/sales by 4–6× in non-census years and ~2× in 2022/2017/2012.
 *
 * Canonical rules enforced here:
 *  1. Exclude `YEAR - *` variants (interim acreage reports + monthly forecasts).
 *     Keep YEAR, WEEK #XX (progress/condition), month names (livestock/price),
 *     MARKETING YEAR, and raw quarterly tokens.
 *  2. Dedup SURVEY/CENSUS/DERIVED overlap keyed on
 *     (state, year, commodity, stat, unit, reference_period, class_desc,
 *      prodn_practice, util_practice, short_desc) — reference_period is now
 *     part of the key so Census-year SURVEY and CENSUS rows don't both land
 *     in the output.
 *  3. Priority SURVEY > CENSUS > DERIVED inside each dedup bucket.
 */
const FORECAST_PERIOD_RE = /^YEAR - /;

export function filterData(data: any[]): any[] {
    if (!data || data.length === 0) return [];

    // Step 1: Apply non-source filters (totals, domain, reference period)
    const basicFiltered = data.filter(d =>
        // Source: Survey, Derived (pipeline-computed), Farm Operations, or Census revenue
        (!d.source_desc || d.source_desc === 'SURVEY' || d.source_desc === 'DERIVED' ||
            d.commodity_desc === 'FARM OPERATIONS' ||
            // Allow CENSUS revenue data (SALES with $ unit) for crops where SURVEY lacks dollar revenue
            (d.statisticcat_desc === 'SALES' && d.unit_desc === '$')) &&

        // Remove Totals (User Requirement)
        !d.commodity_desc?.includes('TOTAL') &&
        !d.commodity_desc?.includes('ALL CLASSES') &&

        // Remove Domain Totals — keep only domain=TOTAL for aggregates
        (d.domain_desc === 'TOTAL' || !d.domain_desc) &&

        // Drop interim / forecast reference periods that otherwise 4–6× inflate
        // AREA PLANTED / AREA HARVESTED / PRODUCTION / YIELD aggregates.
        !(typeof d.reference_period_desc === 'string' &&
          FORECAST_PERIOD_RE.test(d.reference_period_desc))
    );

    // Step 2: Deduplicate Census/Survey/Derived overlap.
    // Include reference_period_desc + class_desc + prodn/util practice + short_desc
    // so Census and Survey collapse per fact, and biotech/utility sub-types
    // don't fight for the same bucket.
    const keyMap = new Map<string, any[]>();
    basicFiltered.forEach(d => {
        const key = [
            d.state_alpha || '',
            d.year || '',
            d.commodity_desc || '',
            d.statisticcat_desc || '',
            d.unit_desc || '',
            d.reference_period_desc || '',
            d.class_desc || '',
            d.prodn_practice_desc || '',
            d.util_practice_desc || '',
            d.short_desc || '',
        ].join('|');
        if (!keyMap.has(key)) keyMap.set(key, []);
        keyMap.get(key)!.push(d);
    });

    const result: any[] = [];
    keyMap.forEach((rows) => {
        const hasSurvey = rows.some(r => r.source_desc === 'SURVEY');
        const hasCensus = rows.some(r => r.source_desc === 'CENSUS');
        if (hasSurvey) {
            result.push(...rows.filter(r => r.source_desc === 'SURVEY'));
        } else if (hasCensus) {
            result.push(...rows.filter(r => r.source_desc === 'CENSUS'));
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
            // For SALES metric, convert 0 to undefined to avoid plotting Census gap years as $0
            if (metric === 'SALES' && (yearObj[commodity] === 0 || yearObj[commodity] === undefined)) {
                yearObj[commodity] = undefined;
            }
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

    // Step 3: Aggregate by year
    const yearGroups = d3.group(paired, d => d.year);
    const trends: any[] = [];

    yearGroups.forEach((rows, year) => {
        const planted = d3.sum(rows.filter(r => r.statisticcat_desc === 'AREA PLANTED'), r => cleanValue(r.value_num || r.Value));
        const harvested = d3.sum(rows.filter(r => r.statisticcat_desc === 'AREA HARVESTED'), r => cleanValue(r.value_num || r.Value));
        if (planted > 0 || harvested > 0) trends.push({ year, planted, harvested });
    });

    return trends.sort((a, b) => a.year - b.year);
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
 *
 * State-level NASS rows are canonical-per-metric (one value, not a partition),
 * so we use `max` not `sum` when collapsing within a year. `sum` silently
 * inflates area/production numbers when sub-type rows leak through (biotech
 * PCT BY TYPE under the same statisticcat, grain vs silage splits, etc.).
 * `max` picks the top-line rollup and tolerates near-duplicate rows.
 */
const ACRE_UNITS = new Set(['ACRES']);
const BU_UNITS = new Set(['BU', 'CWT', 'LB', 'TONS', 'BOXES', 'BARRELS']);

export function getCommodityStory(data: any[], commodity: string) {
    const cropsData = filterData(data).filter(d =>
        d.commodity_desc === commodity && d.sector_desc === 'CROPS'
    );

    const yearGroups = d3.group(cropsData, d => d.year);
    const mergedMap = new Map<number, any>();

    yearGroups.forEach((rows, year) => {
        // Production: pick the dominant production unit for this commodity
        // (usually BU for grains, LB for cotton, TONS for hay, TONS/BOXES/CWT
        // for specialty). A commodity can report PRODUCTION in two physical
        // units in the same year (oranges: TONS and BOXES); taking max across
        // both mixes scales, so pick the unit with the most rows, then max
        // within that unit. PCT rows are excluded via the BU_UNITS gate.
        const prodRows = rows.filter(r =>
            r.statisticcat_desc === 'PRODUCTION' &&
            BU_UNITS.has(String(r.unit_desc || '').toUpperCase())
        );
        let production = 0;
        let prodUnit = '';
        if (prodRows.length) {
            const byUnit = d3.group(prodRows, r => String(r.unit_desc || '').toUpperCase());
            let bestUnit = '';
            let bestCount = -1;
            byUnit.forEach((rs, u) => {
                if (rs.length > bestCount) { bestCount = rs.length; bestUnit = u; }
            });
            production = d3.max(byUnit.get(bestUnit) || [], r => cleanValue(r.value_num || r.Value)) || 0;
            prodUnit = bestUnit;
        }

        // Value of production ($) — specialty crops often report
        // "PRODUCTION ... $" instead of a SALES $ row. Captured so the dollar
        // KPI can fall back to it when SALES is absent.
        const valueOfProduction = d3.max(
            rows.filter(r => r.statisticcat_desc === 'PRODUCTION' && r.unit_desc === '$'),
            r => cleanValue(r.value_num || r.Value),
        ) || 0;

        // Yield: average across utility slices is meaningless (bu/ac ≠ tons/ac).
        // Prefer the primary utility (GRAIN for corn, LINT for cotton, etc.) —
        // the row whose short_desc doesn't split into sub-types. In practice,
        // taking the max drops the occasional PCT sub-type because its value
        // is a % (≤100) and the real yield is 150+. Still, gate by unit to be
        // safe — exclude any row whose unit contains "PCT".
        const yieldRows = rows.filter(r =>
            r.statisticcat_desc === 'YIELD' &&
            !String(r.unit_desc || '').toUpperCase().includes('PCT')
        );
        const yieldVal = d3.max(yieldRows, r => cleanValue(r.value_num || r.Value)) || 0;

        const areaHarvestedRows = rows.filter(r =>
            r.statisticcat_desc === 'AREA HARVESTED' &&
            ACRE_UNITS.has(String(r.unit_desc || '').toUpperCase())
        );
        const areaHarvested = d3.max(areaHarvestedRows, r => cleanValue(r.value_num || r.Value)) || 0;

        const areaPlantedRows = rows.filter(r =>
            r.statisticcat_desc === 'AREA PLANTED' &&
            ACRE_UNITS.has(String(r.unit_desc || '').toUpperCase())
        );
        const areaPlanted = d3.max(areaPlantedRows, r => cleanValue(r.value_num || r.Value)) || 0;

        // Area bearing — tree fruits and nuts (oranges, grapes, almonds) report
        // AREA BEARING in acres rather than AREA PLANTED/HARVESTED. Gate to
        // ACRES so the "OPERATIONS" unit variant (a count, not an area) is
        // excluded.
        const areaBearingRows = rows.filter(r =>
            r.statisticcat_desc === 'AREA BEARING' &&
            ACRE_UNITS.has(String(r.unit_desc || '').toUpperCase())
        );
        const areaBearing = d3.max(areaBearingRows, r => cleanValue(r.value_num || r.Value)) || 0;

        // Revenue: use only $ SALES, take max per year to get the aggregate total
        const salesRows = rows.filter(r =>
            r.statisticcat_desc === 'SALES' &&
            r.unit_desc === '$'
        );
        const revenue = d3.max(salesRows, r => cleanValue(r.value_num || r.Value)) || undefined;

        // yieldUnit reflects the non-PCT yield row actually used for yieldVal.
        const yieldUnit = yieldRows[0]?.unit_desc || '';

        mergedMap.set(year, {
            year,
            production,
            yield: yieldVal,
            areaHarvested,
            areaPlanted,
            areaBearing,
            revenue,
            valueOfProduction,
            prodUnit,
            yieldUnit,
        });
    });

    // Merge in revenue from non-CROPS sector (SALES might be under ECONOMICS)
    const revData = getRevenueForCommodity(data, commodity);
    revData.forEach(r => {
        const existing = mergedMap.get(r.year);
        if (existing) {
            if (!existing.revenue) existing.revenue = r.revenue;
        } else {
            mergedMap.set(r.year, {
                year: r.year, production: 0, yield: 0,
                areaHarvested: 0, areaPlanted: 0, areaBearing: 0,
                revenue: r.revenue, valueOfProduction: 0,
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

// ─── Dynamic Commodity Options (per loaded dataset) ──────────────
export interface CropOption { id: string; label: string; color: string; }
export interface CropOptionGroup { id: string; label: string; color: string; options: CropOption[]; }

// Groups surfaced in the Crops tab. HORTICULTURE (cut flowers, bedding plants,
// Christmas trees) is intentionally excluded — it's $-sales-only and doesn't
// fit a yield/acreage view. CROP TOTALS is an aggregate, not a commodity.
const CROP_GROUP_META: { id: string; label: string; color: string }[] = [
    { id: 'FIELD CROPS', label: 'Field Crops', color: 'var(--chart-corn)' },
    { id: 'FRUIT & TREE NUTS', label: 'Fruits & Nuts', color: 'var(--harvest)' },
    { id: 'VEGETABLES', label: 'Vegetables', color: 'var(--field)' },
];

// Stat categories that count as renderable presence. Area stats must be in
// ACRES (the "OPERATIONS" unit variant is a count); the rest must not be a $
// or PCT sub-row for the value/yield gate.
const PRESENCE_AREA_STATS = new Set(['AREA PLANTED', 'AREA HARVESTED', 'AREA BEARING']);
const PRESENCE_VALUE_STATS = new Set(['YIELD', 'PRODUCTION', 'SALES']);

// NASS catch-all / aggregate commodity_desc values that have data but aren't a
// specific crop a user would pick. Excluded from the picker.
const COMMODITY_DENYLIST = new Set([
    'FIELD CROPS, OTHER', 'GRAIN', 'HAY & HAYLAGE', 'GRASSES', 'GRASSES & LEGUMES, OTHER',
    'VEGETABLES, OTHER', 'BERRIES, OTHER', 'FRUIT & TREE NUTS, OTHER',
]);

function titleCaseCommodity(desc: string): string {
    return desc
        .toLowerCase()
        .replace(/\b([a-z])/g, (_, c: string) => c.toUpperCase());
}

/**
 * Build the grouped commodity picker options from whatever dataset is loaded
 * (a state parquet or NATIONAL). A commodity is listed only if it has real,
 * renderable data (yield / production / area in acres / $ sales) in the recent
 * window, so the picker never offers a crop the page can't render. Field crops
 * reuse their canonical CROP_COMMODITIES label + color; fruits/nuts/vegetables
 * are title-cased and colored by group, sorted by economic weight ($ value).
 */
export function deriveCropOptions(data: any[]): CropOptionGroup[] {
    const rows = filterData(data).filter(d => d.sector_desc === 'CROPS');
    if (!rows.length) return [];

    const maxYear = d3.max(rows, (d: any) => Number(d.year)) || 0;
    const windowStart = maxYear - 7; // catches recent surveys + 2017/2022 Census

    // Canonical field-crop metadata by uppercased commodity_desc.
    const canonical = new Map<string, CropOption>();
    CROP_COMMODITIES.forEach((c) => {
        canonical.set(c.label.toUpperCase(), { id: c.id, label: c.label, color: c.color });
        // a couple of NASS plural/singular mismatches
        canonical.set(c.label.toUpperCase().replace(/S$/, ''), { id: c.id, label: c.label, color: c.color });
    });

    // group -> commodity_desc -> economic weight
    const present = new Map<string, Map<string, number>>();
    for (const r of rows) {
        const group = String(r.group_desc || '');
        if (!CROP_GROUP_META.some((g) => g.id === group)) continue;
        const com = String(r.commodity_desc || '');
        if (!com || com.includes('TOTAL') || com.includes('ALL CLASSES')) continue;
        if (COMMODITY_DENYLIST.has(com)) continue;
        if (Number(r.year) < windowStart) continue;
        const stat = String(r.statisticcat_desc || '');
        const unit = String(r.unit_desc || '').toUpperCase();
        const val = cleanValue(r.value_num || r.Value);
        if (!(val > 0)) continue;

        const isArea = PRESENCE_AREA_STATS.has(stat) && unit === 'ACRES';
        const isValue = PRESENCE_VALUE_STATS.has(stat) && unit !== 'OPERATIONS' && !unit.includes('PCT');
        if (!isArea && !isValue) continue;

        if (!present.has(group)) present.set(group, new Map());
        const inner = present.get(group)!;
        // Economic weight for ordering: $ magnitude dominates; crops with no $
        // row fall back to a tiny physical-scale proxy so they still order
        // sensibly among themselves but below any $-reporting crop.
        const weight = unit === '$' ? val : val * 1e-9;
        inner.set(com, Math.max(inner.get(com) || 0, weight));
    }

    const groups: CropOptionGroup[] = [];
    for (const meta of CROP_GROUP_META) {
        const inner = present.get(meta.id);
        if (!inner || inner.size === 0) continue;

        const options: CropOption[] = Array.from(inner.entries())
            .sort((a, b) => b[1] - a[1])
            .map(([com]) => {
                const known = canonical.get(com.toUpperCase());
                if (known) return known;
                return { id: com.toLowerCase(), label: titleCaseCommodity(com), color: meta.color };
            });

        // Field crops read more naturally in their canonical order than by $.
        if (meta.id === 'FIELD CROPS') {
            const order = new Map<string, number>(CROP_COMMODITIES.map((c, i) => [c.id as string, i]));
            options.sort((a, b) => (order.get(a.id) ?? 999) - (order.get(b.id) ?? 999));
        }

        groups.push({ id: meta.id, label: meta.label, color: meta.color, options });
    }
    return groups;
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
