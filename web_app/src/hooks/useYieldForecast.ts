/**
 * Hook for fetching crop yield forecast data from the backend API.
 * Follows the parallel Promise.all pattern from useAcreageForecast.ts.
 */

import { useState, useCallback } from 'react';

const API_BASE =
  process.env.NEXT_PUBLIC_PREDICTION_API_URL?.replace(/\/price$/, '/yield') ||
  'http://localhost:8000/api/v1/predict/yield';

// ---- Response Types ----

export interface YieldForecast {
  fips: string;
  crop: string;
  crop_year: number;
  week: number;
  p10: number;
  p50: number;
  p90: number;
  unit: string;
  confidence: 'low' | 'medium' | 'high';
  county_avg_5yr: number | null;
  vs_avg_pct: number | null;
  model_ver: string;
  last_updated: string | null;
}

export interface YieldMapItem {
  fips: string;
  p50: number;
  confidence: string;
  vs_avg_pct: number | null;
}

export interface YieldMapResponse {
  crop: string;
  crop_year: number;
  week: number;
  counties: YieldMapItem[];
}

export interface YieldHistoryItem {
  crop_year: number;
  week: number;
  p50_forecast: number;
  actual_yield: number | null;
  error_pct: number | null;
}

// ---- Fetch Helper ----

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const resp = await fetch(url);
    if (!resp.ok) return null;
    return (await resp.json()) as T;
  } catch {
    return null;
  }
}

// ---- Hook ----

export function useYieldForecast(
  fips: string | null,
  crop: string,
  year?: number,
  week?: number,
) {
  const [forecast, setForecast] = useState<YieldForecast | null>(null);
  const [mapData, setMapData] = useState<YieldMapItem[]>([]);
  const [mapWeek, setMapWeek] = useState<number | null>(null);
  const [history, setHistory] = useState<YieldHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const cropYear = year || new Date().getFullYear();
      const weekParam = week ? `&week=${week}` : '';

      // Fetch in parallel
      const [forecastData, mapResponse, historyData] = await Promise.all([
        fips
          ? fetchJson<YieldForecast>(
              `${API_BASE}/?fips=${fips}&crop=${crop}&year=${cropYear}`,
            )
          : Promise.resolve(null),
        fetchJson<YieldMapResponse>(
          `${API_BASE}/map?crop=${crop}&year=${cropYear}${weekParam}`,
        ),
        fips
          ? fetchJson<YieldHistoryItem[]>(
              `${API_BASE}/history?fips=${fips}&crop=${crop}&start_year=2015`,
            )
          : Promise.resolve(null),
      ]);

      setForecast(forecastData);
      setMapData(mapResponse?.counties || []);
      setMapWeek(mapResponse?.week || null);
      setHistory(historyData || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch yield data');
    } finally {
      setLoading(false);
    }
  }, [fips, crop, year, week]);

  return {
    forecast,
    mapData,
    mapWeek,
    history,
    loading,
    error,
    fetchAll,
  };
}
