import { NextRequest, NextResponse } from 'next/server';

/**
 * Athena SQL Query API Route
 *
 * Accepts structured query parameters and translates them to parameterized SQL.
 * Never accepts raw SQL from the client to prevent injection.
 *
 * Query params:
 *   state     - State code (e.g., 'IN', 'CA'). Use 'US' for national.
 *   year      - Specific year (e.g., '2022'). Omit for all years.
 *   yearStart - Start of year range (inclusive)
 *   yearEnd   - End of year range (inclusive)
 *   sector    - Sector filter (e.g., 'CROPS', 'ANIMALS & PRODUCTS', 'ECONOMICS')
 *   metric    - statisticcat_desc filter (e.g., 'AREA HARVESTED', 'SALES')
 *   commodity - commodity_desc filter (e.g., 'CORN', 'SOYBEANS')
 *   groupBy   - Column to group by (e.g., 'commodity_desc', 'year')
 *   orderBy   - Column to order by (default: 'total')
 *   orderDir  - 'ASC' or 'DESC' (default: 'DESC')
 *   limit     - Max rows (default: 50, max: 500)
 *   aggregate - Aggregation function: 'SUM', 'AVG', 'COUNT', 'MAX', 'MIN' (default: 'SUM')
 *
 * Example:
 *   GET /api/athena?state=IN&year=2022&sector=CROPS&metric=AREA+HARVESTED&groupBy=commodity_desc&limit=20
 */

// Athena configuration
const ATHENA_DATABASE = 'usda_agricultural';
const ATHENA_TABLE = 'quickstats_data';
const ATHENA_WORKGROUP = 'usda-dashboard';
const ATHENA_OUTPUT = 's3://usda-analysis-datasets/athena-results/';
const AWS_REGION = process.env.AWS_REGION || 'us-east-2';

// Allowed columns for groupBy/orderBy (whitelist to prevent injection)
const ALLOWED_COLUMNS = new Set([
    'source_desc', 'sector_desc', 'group_desc', 'commodity_desc',
    'statisticcat_desc', 'unit_desc', 'domain_desc', 'agg_level_desc',
    'state_alpha', 'year',
    // Temporal columns (added for enriched pipeline)
    'freq_desc', 'reference_period_desc', 'begin_code', 'end_code',
]);

const ALLOWED_AGGREGATES = new Set(['SUM', 'AVG', 'COUNT', 'MAX', 'MIN']);

// Simple in-memory cache (5-minute TTL)
const queryCache = new Map<string, { data: unknown; timestamp: number }>();
const CACHE_TTL_MS = 5 * 60 * 1000;

function getCached(key: string): unknown | null {
    const entry = queryCache.get(key);
    if (!entry) return null;
    if (Date.now() - entry.timestamp > CACHE_TTL_MS) {
        queryCache.delete(key);
        return null;
    }
    return entry.data;
}

function setCache(key: string, data: unknown) {
    // Evict oldest entries if cache grows too large
    if (queryCache.size > 100) {
        const oldest = Array.from(queryCache.entries())
            .sort((a, b) => a[1].timestamp - b[1].timestamp)
            .slice(0, 50);
        for (const [k] of oldest) queryCache.delete(k);
    }
    queryCache.set(key, { data, timestamp: Date.now() });
}

function buildQuery(params: URLSearchParams): { sql: string; error?: string } {
    const state = params.get('state');
    const year = params.get('year');
    const yearStart = params.get('yearStart');
    const yearEnd = params.get('yearEnd');
    const sector = params.get('sector');
    const metric = params.get('metric');
    const commodity = params.get('commodity');
    const groupBy = params.get('groupBy');
    const orderBy = params.get('orderBy') || 'total';
    const orderDir = (params.get('orderDir') || 'DESC').toUpperCase();
    const limitStr = params.get('limit') || '50';
    const aggregate = (params.get('aggregate') || 'SUM').toUpperCase();

    // Validate aggregate function
    if (!ALLOWED_AGGREGATES.has(aggregate)) {
        return { sql: '', error: `Invalid aggregate: ${aggregate}` };
    }

    // Validate orderDir
    if (orderDir !== 'ASC' && orderDir !== 'DESC') {
        return { sql: '', error: `Invalid orderDir: ${orderDir}` };
    }

    // Validate limit
    const limit = Math.min(Math.max(parseInt(limitStr, 10) || 50, 1), 500);

    // Validate groupBy column
    if (groupBy && !ALLOWED_COLUMNS.has(groupBy)) {
        return { sql: '', error: `Invalid groupBy column: ${groupBy}` };
    }

    // Build SELECT clause
    let selectClause: string;
    if (groupBy) {
        selectClause = `SELECT ${groupBy}, ${aggregate}(value_num) AS total`;
    } else {
        selectClause = `SELECT state_alpha, year, commodity_desc, statisticcat_desc, unit_desc, value_num`;
    }

    // Build WHERE clause
    const conditions: string[] = [];
    const values: { [key: string]: string } = {};

    if (state) {
        const stateVal = state === 'US' ? 'US' : state.toUpperCase();
        conditions.push(`state_alpha = '${escapeSql(stateVal)}'`);
    }

    if (year) {
        conditions.push(`year = ${parseInt(year, 10)}`);
    } else if (yearStart && yearEnd) {
        conditions.push(`year >= ${parseInt(yearStart, 10)}`);
        conditions.push(`year <= ${parseInt(yearEnd, 10)}`);
    }

    if (sector) {
        conditions.push(`sector_desc = '${escapeSql(sector.toUpperCase())}'`);
    }

    if (metric) {
        conditions.push(`statisticcat_desc = '${escapeSql(metric.toUpperCase())}'`);
    }

    if (commodity) {
        conditions.push(`commodity_desc = '${escapeSql(commodity.toUpperCase())}'`);
    }

    // Filter out null values
    conditions.push('value_num IS NOT NULL');

    const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

    // Build GROUP BY and ORDER BY
    let groupByClause = '';
    let orderByClause = '';

    if (groupBy) {
        groupByClause = `GROUP BY ${groupBy}`;
        // Validate orderBy for grouped queries
        const validGroupedOrder = orderBy === 'total' || orderBy === groupBy;
        orderByClause = `ORDER BY ${validGroupedOrder ? orderBy : 'total'} ${orderDir}`;
    } else {
        orderByClause = `ORDER BY year DESC, commodity_desc ASC`;
    }

    const sql = [
        selectClause,
        `FROM ${ATHENA_DATABASE}.${ATHENA_TABLE}`,
        whereClause,
        groupByClause,
        orderByClause,
        `LIMIT ${limit}`,
    ]
        .filter(Boolean)
        .join('\n');

    return { sql };
}

function escapeSql(value: string): string {
    // Basic SQL injection prevention: remove single quotes and semicolons
    return value.replace(/[';\\]/g, '').trim();
}

async function executeAthenaQuery(sql: string): Promise<{ rows: unknown[]; metadata: unknown }> {
    // Dynamic import to avoid bundling issues
    const {
        AthenaClient,
        StartQueryExecutionCommand,
        GetQueryExecutionCommand,
        GetQueryResultsCommand,
    } = await import('@aws-sdk/client-athena');

    const client = new AthenaClient({ region: AWS_REGION });

    // Start query
    const startCmd = new StartQueryExecutionCommand({
        QueryString: sql,
        WorkGroup: ATHENA_WORKGROUP,
        ResultConfiguration: {
            OutputLocation: ATHENA_OUTPUT,
        },
    });

    const startResult = await client.send(startCmd);
    const queryId = startResult.QueryExecutionId;

    if (!queryId) {
        throw new Error('Failed to start Athena query');
    }

    // Poll for completion (max 30 seconds)
    const maxWait = 30000;
    const pollInterval = 1000;
    let elapsed = 0;

    while (elapsed < maxWait) {
        const statusCmd = new GetQueryExecutionCommand({
            QueryExecutionId: queryId,
        });
        const statusResult = await client.send(statusCmd);
        const state = statusResult.QueryExecution?.Status?.State;

        if (state === 'SUCCEEDED') {
            break;
        } else if (state === 'FAILED') {
            const reason = statusResult.QueryExecution?.Status?.StateChangeReason;
            throw new Error(`Athena query failed: ${reason}`);
        } else if (state === 'CANCELLED') {
            throw new Error('Athena query was cancelled');
        }

        await new Promise((resolve) => setTimeout(resolve, pollInterval));
        elapsed += pollInterval;
    }

    if (elapsed >= maxWait) {
        throw new Error('Athena query timed out after 30 seconds');
    }

    // Get results
    const resultsCmd = new GetQueryResultsCommand({
        QueryExecutionId: queryId,
    });
    const resultsResponse = await client.send(resultsCmd);

    const resultSet = resultsResponse.ResultSet;
    if (!resultSet?.Rows || resultSet.Rows.length < 2) {
        return { rows: [], metadata: { queryId, scannedBytes: 0 } };
    }

    // First row is the header
    const headers = resultSet.Rows[0].Data?.map((d) => d.VarCharValue || '') || [];
    const dataRows = resultSet.Rows.slice(1).map((row) => {
        const obj: Record<string, string | number | null> = {};
        row.Data?.forEach((d, i) => {
            const colName = headers[i];
            const val = d.VarCharValue;
            // Try to parse as number
            if (val && colName !== 'state_alpha' && colName !== 'commodity_desc' &&
                colName !== 'sector_desc' && colName !== 'group_desc' &&
                colName !== 'statisticcat_desc' && colName !== 'unit_desc' &&
                colName !== 'source_desc' && colName !== 'domain_desc' &&
                colName !== 'freq_desc' && colName !== 'reference_period_desc') {
                const num = Number(val);
                obj[colName] = isNaN(num) ? val : num;
            } else {
                obj[colName] = val || null;
            }
        });
        return obj;
    });

    return {
        rows: dataRows,
        metadata: { queryId },
    };
}

export async function GET(request: NextRequest) {
    try {
        const params = request.nextUrl.searchParams;

        // Build SQL from parameters
        const { sql, error } = buildQuery(params);
        if (error) {
            return NextResponse.json({ error }, { status: 400 });
        }

        // Check cache
        const cacheKey = sql;
        const cached = getCached(cacheKey);
        if (cached) {
            return NextResponse.json({ ...(cached as object), cached: true });
        }

        // Execute query
        const result = await executeAthenaQuery(sql);

        // Cache result
        setCache(cacheKey, result);

        return NextResponse.json({
            rows: result.rows,
            metadata: result.metadata,
            rowCount: (result.rows as unknown[]).length,
            cached: false,
        });
    } catch (err) {
        const message = err instanceof Error ? err.message : 'Unknown error';
        console.error('[Athena API] Error:', message);

        // Check for common errors
        if (message.includes('not found') || message.includes('credentials')) {
            return NextResponse.json(
                {
                    error: 'Athena is not configured. Set up AWS credentials and Glue catalog.',
                    details: message,
                },
                { status: 503 }
            );
        }

        return NextResponse.json({ error: message }, { status: 500 });
    }
}
