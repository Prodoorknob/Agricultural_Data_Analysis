'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { queryAthena, compareStates, AthenaQueryParams, AthenaResult, CompareParams, CompareResult } from '../utils/athenaClient';

/**
 * React hook for Athena SQL queries with loading/error/data states.
 *
 * @example
 * const { data, loading, error, refetch } = useAthenaQuery({
 *   state: 'IN',
 *   year: 2022,
 *   sector: 'CROPS',
 *   metric: 'AREA HARVESTED',
 *   groupBy: 'commodity_desc',
 * });
 */
export function useAthenaQuery(
    params: AthenaQueryParams | null,
    options?: { enabled?: boolean }
) {
    const [data, setData] = useState<AthenaResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const paramsRef = useRef(params);

    // Track param changes by serializing
    const paramsKey = params ? JSON.stringify(params) : null;

    const fetchData = useCallback(async () => {
        if (!params) return;

        setLoading(true);
        setError(null);

        try {
            const result = await queryAthena(params);
            setData(result);
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Query failed';
            setError(message);
            console.error('[useAthenaQuery] Error:', message);
        } finally {
            setLoading(false);
        }
    }, [paramsKey]);

    useEffect(() => {
        const enabled = options?.enabled ?? true;
        if (enabled && params) {
            fetchData();
        }
    }, [fetchData, options?.enabled]);

    return { data, loading, error, refetch: fetchData };
}

/**
 * React hook for Athena state comparison queries.
 *
 * @example
 * const { data, loading, error } = useAthenaCompare({
 *   states: ['IN', 'OH', 'IL'],
 *   metric: 'AREA HARVESTED',
 *   commodity: 'CORN',
 *   yearStart: 2015,
 *   yearEnd: 2023,
 * });
 */
export function useAthenaCompare(
    params: CompareParams | null,
    options?: { enabled?: boolean }
) {
    const [data, setData] = useState<CompareResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const paramsKey = params ? JSON.stringify(params) : null;

    const fetchData = useCallback(async () => {
        if (!params) return;

        setLoading(true);
        setError(null);

        try {
            const result = await compareStates(params);
            setData(result);
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Compare failed';
            setError(message);
            console.error('[useAthenaCompare] Error:', message);
        } finally {
            setLoading(false);
        }
    }, [paramsKey]);

    useEffect(() => {
        const enabled = options?.enabled ?? true;
        if (enabled && params) {
            fetchData();
        }
    }, [fetchData, options?.enabled]);

    return { data, loading, error, refetch: fetchData };
}
