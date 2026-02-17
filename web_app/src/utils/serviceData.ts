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
    return new Promise((resolve, reject) => {
        try {
            const metadata = parquetMetadata(arrayBuffer);

            if (!metadata || !metadata.row_groups || metadata.row_groups.length === 0) {
                console.warn('No row groups found in parquet file');
                resolve([]);
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
                    resolve(result);
                }
            });
        } catch (e) {
            console.error("Error reading parquet metadata/data", e);
            resolve([]);
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
 * @returns Array of data objects
 */
async function fetchParquet(filename: string): Promise<any[]> {
    // Normalize filename: extract just the state code from path like 'partitioned_states/IN.parquet'
    const justFilename = filename.includes('/') ? filename.split('/').pop() || filename : filename;
    
    // Strategy 1: Try S3 bucket first (primary source)
    console.log(`[S3] Attempting to fetch ${justFilename} from S3...`);
    try {
        const s3Url = `${S3_BUCKET_URL}/${justFilename}`;
        const s3Response = await fetch(s3Url, { 
            method: 'GET',
            mode: 'cors',
            credentials: 'omit'
        });
        
        if (s3Response.ok) {
            console.log(`[S3] ✓ Successfully fetched ${justFilename} from S3`);
            const arrayBuffer = await s3Response.arrayBuffer();
            return parseParquetBuffer(arrayBuffer);
        } else {
            console.warn(`[S3] File not found or access denied (${s3Response.status}): ${justFilename}`);
        }
    } catch (s3Error) {
        console.warn(`[S3] Failed to fetch from S3:`, s3Error instanceof Error ? s3Error.message : s3Error);
    }

    // Strategy 2: Fall back to local API proxy
    console.log(`[Local API] Attempting to fetch ${filename} from local API...`);
    try {
        const apiUrl = `/api/data?file=${encodeURIComponent(filename)}&t=${Date.now()}`;
        const apiResponse = await fetch(apiUrl);
        
        if (apiResponse.ok) {
            console.log(`[Local API] ✓ Successfully fetched ${filename} from local API`);
            const arrayBuffer = await apiResponse.arrayBuffer();
            return parseParquetBuffer(arrayBuffer);
        } else {
            console.warn(`[Local API] File not found or access denied (${apiResponse.status}): ${filename}`);
        }
    } catch (apiError) {
        console.warn(`[Local API] Failed to fetch from local API:`, apiError instanceof Error ? apiError.message : apiError);
    }

    // All strategies failed
    console.error(`[Fetch] Failed to retrieve ${filename} from all sources (S3, Local API)`);
    return [];
}

/**
 * Fetch all data for a specific state.
 */
export async function fetchStateData(stateAlpha: string) {
    const stateName = getStateName(stateAlpha);
    if (!stateName) {
        console.error(`Unknown state alpha: ${stateAlpha}`);
        return [];
    }

    // Filename format: partitioned_states/IN.parquet (New Structure)
    // The API route maps this to final_data/IN.parquet
    const filename = `partitioned_states/${stateAlpha}.parquet`;
    return fetchParquet(filename);
}

/**
 * Fetch national summary data (if needed for comparison)
 */
export async function fetchNationalCrops() {
    return fetchParquet('partitioned_states/NATIONAL.parquet');
}

/**
 * Fetch National Land Use Summary
 */
export async function fetchLandUseData() {
    return fetchParquet('partitioned_states/NATIONAL.parquet');
}

/**
 * Fetch National Labor Wage Data
 */
export async function fetchLaborData() {
    return fetchParquet('partitioned_states/NATIONAL.parquet');
}
