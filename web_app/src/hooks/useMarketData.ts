'use client';

import { useState, useCallback } from 'react';
import type {
  FuturesTimeSeriesResponse,
  ForwardCurveResponse,
  DxyTimeSeriesResponse,
  ProductionCostResponse,
  FertilizerPriceResponse,
} from '@/types/market';

const BASE = process.env.NEXT_PUBLIC_PREDICTION_API_URL || 'http://localhost:8000';

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export function useMarketData() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchFutures = useCallback(
    async (commodity: string, start?: string, end?: string) => {
      setLoading(true);
      setError(null);
      const params = new URLSearchParams({ commodity });
      if (start) params.set('start', start);
      if (end) params.set('end', end);
      const data = await fetchJson<FuturesTimeSeriesResponse>(
        `${BASE}/api/v1/market/futures?${params}`
      );
      setLoading(false);
      if (!data) setError('Failed to load futures data');
      return data;
    },
    []
  );

  const fetchCurve = useCallback(async (commodity: string, asOf?: string) => {
    const params = new URLSearchParams({ commodity });
    if (asOf) params.set('as_of', asOf);
    return fetchJson<ForwardCurveResponse>(`${BASE}/api/v1/market/curve?${params}`);
  }, []);

  const fetchDxy = useCallback(async (start?: string, end?: string) => {
    const params = new URLSearchParams();
    if (start) params.set('start', start);
    if (end) params.set('end', end);
    return fetchJson<DxyTimeSeriesResponse>(`${BASE}/api/v1/market/dxy?${params}`);
  }, []);

  const fetchCosts = useCallback(async (commodity: string) => {
    return fetchJson<ProductionCostResponse>(
      `${BASE}/api/v1/market/costs?commodity=${commodity}`
    );
  }, []);

  const fetchFertilizer = useCallback(async (limit = 4) => {
    return fetchJson<FertilizerPriceResponse[]>(
      `${BASE}/api/v1/market/fertilizer?limit=${limit}`
    );
  }, []);

  const fetchWasdeSignal = useCallback(async (commodity: string) => {
    return fetchJson<any>(`${BASE}/api/v1/predict/price/wasde-signal?commodity=${commodity}`);
  }, []);

  const fetchPriceRatio = useCallback(async () => {
    return fetchJson<any>(`${BASE}/api/v1/predict/acreage/price-ratio`);
  }, []);

  const fetchExportPace = useCallback(async (commodity: string) => {
    return fetchJson<any>(`${BASE}/api/v1/market/exports?commodity=${commodity}`);
  }, []);

  return {
    loading,
    error,
    fetchFutures,
    fetchCurve,
    fetchDxy,
    fetchCosts,
    fetchFertilizer,
    fetchWasdeSignal,
    fetchPriceRatio,
    fetchExportPace,
  };
}
