import { parquetRead, parquetMetadata } from 'hyparquet';

// S3 bucket configuration - Primary data source
const S3_BUCKET_URL = 'https://usda-analysis-datasets.s3.us-east-2.amazonaws.com/survey_datasets/partitioned_states';

export const US_STATES: Record<string, string> = {
    'AL': 'ALABAMA', 'AK': 'ALASKA', 'AZ': 'ARIZONA', 'AR': 'ARKANSAS', 'CA': 'CALIFORNIA',
    'CO': 'COLORADO', 'CT': 'CONNECTICUT', 'DE': 'DELAWARE', 'FL': 'FLORIDA', 'GA': 'GEORGIA',
    'HI': 'HAWAII', 'ID': 'IDAHO', 'IL': 'ILLINOIS', 'IN': 'INDIANA', 'IA': 'IOWA',
    'KS': 'KANSAS', 'KY': 'KENTUCKY', 'LA': 'LOUISIANA', 'ME': 'MAINE', 'MD': 'MARYLAND',
    'MA': 'MASSACHUSETTS', 'MI': 'MICHIGAN', 'MN': 'MINNESOTA', 'MS': 'MISSISSIPPI', 'MO': 'MISSOURI',
    'MT': 'MONTANA', 'NE': 'NEBRASKA', 'NV': 'NEVADA', 'NH': 'NEW HAMPSHIRE', 'NJ': 'NEW JERSEY',
    'NM': 'NEW MEXICO', 'NY': 'NEW YORK', 'NC': 'NORTH CAROLINA', 'ND': 'NORTH DAKOTA', 'OH': 'OHIO',
    'OK': 'OKLAHOMA', 'OR': 'OREGON', 'PA': 'PENNSYLVANIA', 'RI': 'RHODE ISLAND', 'SC': 'SOUTH CAROLINA',
    'SD': 'SOUTH DAKOTA', 'TN': 'TENNESSEE', 'TX': 'TEXAS', 'UT': 'UTAH', 'VT': 'VERMONT',
    'VA': 'VIRGINIA', 'WA': 'WASHINGTON', 'WV': 'WEST VIRGINIA', 'WI': 'WISCONSIN', 'WY': 'WYOMING'
};

/**
 * Maps state code (e.g., 'IN') to full name (e.g., 'INDIANA')
 * Note: S3 files use UPPERCASE state names.
 */
function getStateName(stateAlpha: string): string | undefined {
    return US_STATES[stateAlpha];
}

export interface CropData {
    state_alpha: string;
    year: number;
    commodity_desc: string;
    value_num: number;
    unit_desc?: string;
    statisticcat_desc?: string;
    Value?: string | number; // Raw value might be string with commas
    [key: string]: any;
}

/**
 * Parse parquet ArrayBuffer and return data objects
 */
async function parseParquetBuffer(arrayBuffer: ArrayBuffer): Promise<any[]> {
    return new Promise((resolve) => {
        let settled = false;
        const done = (result: any[]) => {
            if (settled) return;
            settled = true;
            resolve(result);
        };

        try {
            const metadata = parquetMetadata(arrayBuffer);

            if (!metadata || !metadata.row_groups || metadata.row_groups.length === 0) {
                console.warn('No row groups found in parquet file');
                done([]);
                return;
            }

            const columnHelpers = metadata.row_groups[0].columns;
            const headers = columnHelpers.map((c: any) => c.meta_data.path_in_schema[0]);

            parquetRead({
                file: arrayBuffer,
                onComplete: (data) => {
                    const result = data.map((row: any[]) => {
                        const obj: any = {};
                        headers.forEach((header: string, index: number) => {
                            const val = row[index];
                            obj[header] = typeof val === 'bigint' ? Number(val) : val;
                        });
                        return obj;
                    });
                    done(result);
                },
            });

            // Defensive timeout — malformed files could leave parquetRead hanging
            // without ever calling onComplete. 30s is well past the honest p99.
            setTimeout(() => {
                if (!settled) {
                    console.error('parquetRead timed out after 30s');
                    done([]);
                }
            }, 30_000);
        } catch (e) {
            console.error('Error reading parquet metadata/data', e);
            done([]);
        }
    });
}

/**
 * Fetch and parse a Parquet file with fallback strategy:
 * 1. Try S3 bucket (primary)
 * 2. Try local API proxy (fallback)
 * 3. Return empty array on all failures
 *
 * @param filename Relative path to the parquet file (e.g., 'IN.parquet')
 * @param signal Optional AbortSignal — callers pass one tied to component
 *   lifecycle so rapid state switches don't race older fetches on top of
 *   fresher state updates.
 */
async function fetchParquet(filename: string, signal?: AbortSignal): Promise<any[]> {
    const justFilename = filename.includes('/') ? filename.split('/').pop() || filename : filename;

    console.log(`[S3] Attempting to fetch ${justFilename} from S3...`);
    try {
        const s3Url = `${S3_BUCKET_URL}/${justFilename}`;
        const s3Response = await fetch(s3Url, {
            method: 'GET',
            mode: 'cors',
            credentials: 'omit',
            signal,
        });

        if (s3Response.ok) {
            console.log(`[S3] ✓ Successfully fetched ${justFilename} from S3`);
            const arrayBuffer = await s3Response.arrayBuffer();
            return parseParquetBuffer(arrayBuffer);
        } else {
            console.warn(`[S3] File not found or access denied (${s3Response.status}): ${justFilename}`);
        }
    } catch (s3Error) {
        if ((s3Error as { name?: string })?.name === 'AbortError') throw s3Error;
        console.warn(`[S3] Failed to fetch from S3:`, s3Error instanceof Error ? s3Error.message : s3Error);
    }

    console.log(`[Local API] Attempting to fetch ${filename} from local API...`);
    try {
        const apiUrl = `/api/data?file=${encodeURIComponent(filename)}&t=${Date.now()}`;
        const apiResponse = await fetch(apiUrl, { signal });

        if (apiResponse.ok) {
            console.log(`[Local API] ✓ Successfully fetched ${filename} from local API`);
            const arrayBuffer = await apiResponse.arrayBuffer();
            return parseParquetBuffer(arrayBuffer);
        } else {
            console.warn(`[Local API] File not found or access denied (${apiResponse.status}): ${filename}`);
        }
    } catch (apiError) {
        if ((apiError as { name?: string })?.name === 'AbortError') throw apiError;
        console.warn(`[Local API] Failed to fetch from local API:`, apiError instanceof Error ? apiError.message : apiError);
    }

    console.error(`[Fetch] Failed to retrieve ${filename} from all sources (S3, Local API)`);
    return [];
}

/**
 * Fetch all data for a specific state. Pass an AbortSignal from the caller's
 * useEffect cleanup so rapid state switches don't resolve stale fetches on
 * top of fresh ones.
 */
export async function fetchStateData(stateAlpha: string, signal?: AbortSignal) {
    const stateName = getStateName(stateAlpha);
    if (!stateName) {
        console.error(`Unknown state alpha: ${stateAlpha}`);
        return [];
    }

    const filename = `partitioned_states/${stateAlpha}.parquet`;
    return fetchParquet(filename, signal);
}

/**
 * Fetch national summary data (if needed for comparison)
 */
export async function fetchNationalCrops(signal?: AbortSignal) {
    return fetchParquet('partitioned_states/NATIONAL.parquet', signal);
}

/**
 * Fetch National Land Use Summary
 */
export async function fetchLandUseData(signal?: AbortSignal) {
    return fetchParquet('partitioned_states/NATIONAL.parquet', signal);
}

/**
 * Fetch National Labor Wage Data
 */
export async function fetchLaborData(signal?: AbortSignal) {
    return fetchParquet('partitioned_states/NATIONAL.parquet', signal);
}

// ─── Athena-Backed Fetch Functions ────────────────────────────────
// These provide SQL-powered queries as an alternative to full parquet downloads.
// They fall back gracefully if Athena is not configured.

import type { AthenaQueryParams } from './athenaClient';

/**
 * Fetch aggregated data for a state via Athena SQL.
 * Returns top commodities by the specified metric.
 * Falls back to empty array if Athena is unavailable.
 */
export async function fetchStateAggregated(
    stateAlpha: string,
    year: number,
    metric: string = 'AREA HARVESTED',
    sector?: string,
    limit: number = 25
): Promise<any[]> {
    try {
        const params = new URLSearchParams({
            state: stateAlpha,
            year: year.toString(),
            metric,
            groupBy: 'commodity_desc',
            limit: limit.toString(),
        });
        if (sector) params.set('sector', sector);

        const response = await fetch(`/api/athena?${params.toString()}`);
        if (!response.ok) return [];

        const result = await response.json();
        return result.rows || [];
    } catch {
        console.warn('[Athena] Not available, falling back to parquet');
        return [];
    }
}

/**
 * Fetch trend data for a commodity across years via Athena.
 */
export async function fetchCommodityTrend(
    stateAlpha: string,
    commodity: string,
    metric: string = 'AREA HARVESTED',
    yearStart: number = 2001,
    yearEnd: number = 2025
): Promise<any[]> {
    try {
        const params = new URLSearchParams({
            state: stateAlpha,
            commodity,
            metric,
            yearStart: yearStart.toString(),
            yearEnd: yearEnd.toString(),
            groupBy: 'year',
            orderBy: 'year',
            orderDir: 'ASC',
            limit: '50',
        });

        const response = await fetch(`/api/athena?${params.toString()}`);
        if (!response.ok) return [];

        const result = await response.json();
        return result.rows || [];
    } catch {
        console.warn('[Athena] Not available for trend query');
        return [];
    }
}

/**
 * Fetch state comparison data via Athena.
 */
export async function fetchStateComparison(
    states: string[],
    metric: string,
    commodity?: string,
    yearStart: number = 2010,
    yearEnd: number = 2025
): Promise<any[]> {
    try {
        const params = new URLSearchParams({
            states: states.join(','),
            metric,
            yearStart: yearStart.toString(),
            yearEnd: yearEnd.toString(),
        });
        if (commodity) params.set('commodity', commodity);

        const response = await fetch(`/api/athena/compare?${params.toString()}`);
        if (!response.ok) return [];

        const result = await response.json();
        return result.rows || [];
    } catch {
        console.warn('[Athena] Not available for comparison query');
        return [];
    }
}
