import { parquetRead, parquetMetadata } from 'hyparquet';

// const S3_BUCKET_URL = 'https://usda-analysis-datasets.s3.us-east-2.amazonaws.com/survey_datasets';

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
 * Fetch and parse a Parquet file via local API proxy.
 * 
 * @param filename Relative path to the parquet file (e.g., 'partitioned_states/INDIANA.parquet')
 * @returns Array of data objects
 */
async function fetchParquet(filename: string): Promise<any[]> {
    // Use local API proxy to avoid CORS issues with S3
    // Append timestamp to bust cache
    const url = `/api/data?file=${encodeURIComponent(filename)}&t=${Date.now()}`;
    console.log(`Fetching ${url}...`);

    try {
        const response = await fetch(url);
        if (!response.ok) {
            if (response.status === 403 || response.status === 404) {
                console.warn(`File not found or access denied: ${filename}`);
                return [];
            }
            throw new Error(`Failed to fetch ${url}: ${response.statusText}`);
        }

        const arrayBuffer = await response.arrayBuffer();

        // 1. Read Metadata to get Column Names
        return new Promise((resolve, reject) => {
            try {
                // parquetMetadata is synchronous
                const metadata = parquetMetadata(arrayBuffer);

                if (!metadata || !metadata.row_groups || metadata.row_groups.length === 0) {
                    console.warn('No row groups found in parquet file');
                    resolve([]);
                    return;
                }

                const columnHelpers = metadata.row_groups[0].columns;
                const headers = columnHelpers.map((c: any) => c.meta_data.path_in_schema[0]);
                console.log('Parquet Headers:', headers);

                // 2. Read Data
                parquetRead({
                    file: arrayBuffer,
                    onComplete: (data) => {
                        // hyparquet returns an array of arrays (rows)
                        // data is [ [val0, val1...], [val0, val1...] ... ]

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

    } catch (error) {
        console.error(`Error fetching parquet file ${filename}:`, error);
        return [];
    }
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
