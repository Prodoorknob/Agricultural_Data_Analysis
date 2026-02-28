/**
 * athenaClient.ts - Client-side typed wrapper for Athena API calls
 *
 * Provides clean, typed functions for querying the Athena SQL layer
 * from React components. Falls back gracefully if Athena is not configured.
 */

// ─── Types ───────────────────────────────────────────────────────

export interface AthenaQueryParams {
    state?: string;
    year?: number;
    yearStart?: number;
    yearEnd?: number;
    sector?: string;
    metric?: string;
    commodity?: string;
    groupBy?: string;
    orderBy?: string;
    orderDir?: 'ASC' | 'DESC';
    limit?: number;
    aggregate?: 'SUM' | 'AVG' | 'COUNT' | 'MAX' | 'MIN';
}

export interface AthenaRow {
    [key: string]: string | number | null;
}

export interface AthenaResult {
    rows: AthenaRow[];
    metadata: { queryId?: string };
    rowCount: number;
    cached: boolean;
}

export interface CompareParams {
    states: string[];
    metric: string;
    commodity?: string;
    sector?: string;
    yearStart?: number;
    yearEnd?: number;
    aggregate?: 'SUM' | 'AVG' | 'COUNT' | 'MAX' | 'MIN';
}

export interface CompareResult {
    rows: AthenaRow[];
    states: string[];
    metric: string;
    rowCount: number;
    cached: boolean;
}

// ─── Query Functions ─────────────────────────────────────────────

/**
 * Query the Athena SQL layer with structured parameters.
 *
 * @example
 * const result = await queryAthena({
 *   state: 'IN',
 *   year: 2022,
 *   sector: 'CROPS',
 *   metric: 'AREA HARVESTED',
 *   groupBy: 'commodity_desc',
 *   limit: 20,
 * });
 */
export async function queryAthena(params: AthenaQueryParams): Promise<AthenaResult> {
    const searchParams = new URLSearchParams();

    if (params.state) searchParams.set('state', params.state);
    if (params.year) searchParams.set('year', params.year.toString());
    if (params.yearStart) searchParams.set('yearStart', params.yearStart.toString());
    if (params.yearEnd) searchParams.set('yearEnd', params.yearEnd.toString());
    if (params.sector) searchParams.set('sector', params.sector);
    if (params.metric) searchParams.set('metric', params.metric);
    if (params.commodity) searchParams.set('commodity', params.commodity);
    if (params.groupBy) searchParams.set('groupBy', params.groupBy);
    if (params.orderBy) searchParams.set('orderBy', params.orderBy);
    if (params.orderDir) searchParams.set('orderDir', params.orderDir);
    if (params.limit) searchParams.set('limit', params.limit.toString());
    if (params.aggregate) searchParams.set('aggregate', params.aggregate);

    const response = await fetch(`/api/athena?${searchParams.toString()}`);

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(errorData.error || `Athena query failed: ${response.status}`);
    }

    return response.json();
}

/**
 * Compare data across multiple states over time.
 *
 * @example
 * const result = await compareStates({
 *   states: ['IN', 'OH', 'IL'],
 *   metric: 'AREA HARVESTED',
 *   commodity: 'CORN',
 *   yearStart: 2015,
 *   yearEnd: 2023,
 * });
 */
export async function compareStates(params: CompareParams): Promise<CompareResult> {
    const searchParams = new URLSearchParams();

    searchParams.set('states', params.states.join(','));
    searchParams.set('metric', params.metric);
    if (params.commodity) searchParams.set('commodity', params.commodity);
    if (params.sector) searchParams.set('sector', params.sector);
    if (params.yearStart) searchParams.set('yearStart', params.yearStart.toString());
    if (params.yearEnd) searchParams.set('yearEnd', params.yearEnd.toString());
    if (params.aggregate) searchParams.set('aggregate', params.aggregate);

    const response = await fetch(`/api/athena/compare?${searchParams.toString()}`);

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(errorData.error || `Athena compare failed: ${response.status}`);
    }

    return response.json();
}

/**
 * Check if Athena is available by making a lightweight query.
 */
export async function isAthenaAvailable(): Promise<boolean> {
    try {
        const result = await queryAthena({
            state: 'IN',
            year: 2022,
            metric: 'AREA HARVESTED',
            limit: 1,
        });
        return result.rows.length > 0;
    } catch {
        return false;
    }
}
