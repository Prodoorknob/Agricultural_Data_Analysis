import { NextRequest, NextResponse } from 'next/server';

/**
 * Athena Compare API Route
 *
 * Specialized endpoint for state-vs-state and year-vs-year comparisons.
 *
 * Query params:
 *   states     - Comma-separated state codes (e.g., 'IN,OH,IL')
 *   metric     - statisticcat_desc (e.g., 'AREA HARVESTED', 'YIELD')
 *   commodity  - commodity_desc filter (e.g., 'CORN')
 *   sector     - sector_desc filter (e.g., 'CROPS')
 *   yearStart  - Start year (default: 2010)
 *   yearEnd    - End year (default: current year)
 *   aggregate  - SUM, AVG, MAX, MIN (default: SUM)
 *
 * Example:
 *   GET /api/athena/compare?states=IN,OH,IL&metric=AREA+HARVESTED&commodity=CORN&yearStart=2015&yearEnd=2023
 *
 * Returns:
 *   { rows: [{ year: 2023, IN: 5000000, OH: 3200000, IL: 10000000 }, ...], metadata: {...} }
 */

const ATHENA_DATABASE = 'usda_agricultural';
const ATHENA_TABLE = 'quickstats_data';
const ATHENA_WORKGROUP = 'usda-dashboard';
const ATHENA_OUTPUT = 's3://usda-analysis-datasets/athena-results/';
const AWS_REGION = process.env.AWS_REGION || 'us-east-2';

const ALLOWED_AGGREGATES = new Set(['SUM', 'AVG', 'COUNT', 'MAX', 'MIN']);

// Simple cache (5-minute TTL)
const compareCache = new Map<string, { data: unknown; timestamp: number }>();
const CACHE_TTL_MS = 5 * 60 * 1000;

function getCached(key: string): unknown | null {
    const entry = compareCache.get(key);
    if (!entry) return null;
    if (Date.now() - entry.timestamp > CACHE_TTL_MS) {
        compareCache.delete(key);
        return null;
    }
    return entry.data;
}

function setCache(key: string, data: unknown) {
    if (compareCache.size > 50) {
        const oldest = Array.from(compareCache.entries())
            .sort((a, b) => a[1].timestamp - b[1].timestamp)
            .slice(0, 25);
        for (const [k] of oldest) compareCache.delete(k);
    }
    compareCache.set(key, { data, timestamp: Date.now() });
}

function escapeSql(value: string): string {
    return value.replace(/[';\\]/g, '').trim();
}

export async function GET(request: NextRequest) {
    try {
        const params = request.nextUrl.searchParams;
        const statesParam = params.get('states');
        const metric = params.get('metric');
        const commodity = params.get('commodity');
        const sector = params.get('sector');
        const yearStart = parseInt(params.get('yearStart') || '2010', 10);
        const yearEnd = parseInt(params.get('yearEnd') || new Date().getFullYear().toString(), 10);
        const aggregate = (params.get('aggregate') || 'SUM').toUpperCase();

        if (!statesParam) {
            return NextResponse.json({ error: 'states parameter is required' }, { status: 400 });
        }
        if (!metric) {
            return NextResponse.json({ error: 'metric parameter is required' }, { status: 400 });
        }
        if (!ALLOWED_AGGREGATES.has(aggregate)) {
            return NextResponse.json({ error: `Invalid aggregate: ${aggregate}` }, { status: 400 });
        }

        const states = statesParam
            .split(',')
            .map((s) => s.trim().toUpperCase())
            .filter((s) => s.length === 2)
            .slice(0, 10); // Max 10 states

        if (states.length === 0) {
            return NextResponse.json({ error: 'At least one valid state code required' }, { status: 400 });
        }

        // Build comparison SQL using CASE WHEN for pivoting
        const stateConditions = states.map((s) => `'${escapeSql(s)}'`).join(', ');
        const pivotColumns = states
            .map(
                (s) =>
                    `${aggregate}(CASE WHEN state_alpha = '${escapeSql(s)}' THEN value_num END) AS "${s}"`
            )
            .join(',\n    ');

        const conditions = [
            `state_alpha IN (${stateConditions})`,
            `year >= ${yearStart}`,
            `year <= ${yearEnd}`,
            `statisticcat_desc = '${escapeSql(metric.toUpperCase())}'`,
            'value_num IS NOT NULL',
        ];

        if (commodity) {
            conditions.push(`commodity_desc = '${escapeSql(commodity.toUpperCase())}'`);
        }
        if (sector) {
            conditions.push(`sector_desc = '${escapeSql(sector.toUpperCase())}'`);
        }

        const sql = `
SELECT year,
    ${pivotColumns}
FROM ${ATHENA_DATABASE}.${ATHENA_TABLE}
WHERE ${conditions.join('\n  AND ')}
GROUP BY year
ORDER BY year ASC
`.trim();

        // Check cache
        const cacheKey = sql;
        const cached = getCached(cacheKey);
        if (cached) {
            return NextResponse.json({ ...(cached as object), cached: true });
        }

        // Execute query
        const {
            AthenaClient,
            StartQueryExecutionCommand,
            GetQueryExecutionCommand,
            GetQueryResultsCommand,
        } = await import('@aws-sdk/client-athena');

        const client = new AthenaClient({ region: AWS_REGION });

        const startResult = await client.send(
            new StartQueryExecutionCommand({
                QueryString: sql,
                WorkGroup: ATHENA_WORKGROUP,
                ResultConfiguration: { OutputLocation: ATHENA_OUTPUT },
            })
        );

        const queryId = startResult.QueryExecutionId;
        if (!queryId) throw new Error('Failed to start Athena query');

        // Poll for completion
        const maxWait = 30000;
        let elapsed = 0;
        while (elapsed < maxWait) {
            const status = await client.send(
                new GetQueryExecutionCommand({ QueryExecutionId: queryId })
            );
            const state = status.QueryExecution?.Status?.State;
            if (state === 'SUCCEEDED') break;
            if (state === 'FAILED')
                throw new Error(
                    `Query failed: ${status.QueryExecution?.Status?.StateChangeReason}`
                );
            if (state === 'CANCELLED') throw new Error('Query cancelled');
            await new Promise((r) => setTimeout(r, 1000));
            elapsed += 1000;
        }
        if (elapsed >= maxWait) throw new Error('Query timed out');

        // Get results
        const results = await client.send(
            new GetQueryResultsCommand({ QueryExecutionId: queryId })
        );

        const resultRows = results.ResultSet?.Rows || [];
        if (resultRows.length < 2) {
            return NextResponse.json({ rows: [], states, metric, cached: false });
        }

        const headers = resultRows[0].Data?.map((d) => d.VarCharValue || '') || [];
        const rows = resultRows.slice(1).map((row) => {
            const obj: Record<string, number | null> = {};
            row.Data?.forEach((d, i) => {
                const val = d.VarCharValue;
                obj[headers[i]] = val ? Number(val) : null;
            });
            return obj;
        });

        const response = { rows, states, metric, rowCount: rows.length, cached: false };
        setCache(cacheKey, response);

        return NextResponse.json(response);
    } catch (err) {
        const message = err instanceof Error ? err.message : 'Unknown error';
        console.error('[Athena Compare] Error:', message);
        return NextResponse.json({ error: message }, { status: 500 });
    }
}
