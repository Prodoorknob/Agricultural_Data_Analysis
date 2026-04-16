/**
 * Hook for fetching acreage prediction data from the FastAPI backend.
 * Module 03: Planted Acreage Prediction
 */

import { useState, useEffect, useCallback } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_PREDICTION_API_URL || 'http://localhost:8000';

export interface AcreageForecast {
  commodity: string;
  forecast_year: number;
  level: string;
  state_fips?: string;
  state_name?: string;
  // Raw acres (e.g. 92_800_000). The API used to suffix these `_millions`
  // but the stored values were always raw — renamed in the backend router
  // on 2026-04-16 for honesty.
  forecast_acres: number;
  p10_acres?: number;
  p90_acres?: number;
  corn_soy_ratio?: number;
  corn_soy_ratio_pctile?: number;
  key_driver?: string;
  vs_prior_year_pct?: number;
  published_at?: string;
  model_ver?: string;
}

export interface StateAcreageItem {
  state_fips: string;
  state: string;
  forecast_acres: number;  // raw acres
  vs_prior_pct?: number;
}

export interface StatesAcreageResponse {
  commodity: string;
  forecast_year: number;
  states: StateAcreageItem[];
}

export interface AcreageAccuracyItem {
  forecast_year: number;
  commodity: string;
  level: string;
  model_forecast: number;
  usda_prospective?: number;
  usda_june_actual?: number;
  model_vs_usda_pct?: number;
  model_vs_actual_pct?: number;
}

export interface PriceRatio {
  as_of_date: string;
  corn_dec_futures?: number;
  soy_nov_futures?: number;
  corn_soy_ratio?: number;
  historical_percentile?: number;
  historical_context?: string;
  implication?: string;
}

async function fetchJson<T>(url: string): Promise<T | null> {
  try {
    const resp = await fetch(url);
    if (!resp.ok) return null;
    return await resp.json();
  } catch {
    return null;
  }
}

export function useAcreageForecast(commodity: string, year?: number) {
  const [national, setNational] = useState<AcreageForecast | null>(null);
  const [states, setStates] = useState<StateAcreageItem[]>([]);
  const [accuracy, setAccuracy] = useState<AcreageAccuracyItem[]>([]);
  const [priceRatio, setPriceRatio] = useState<PriceRatio | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);

    const yearParam = year ? `&year=${year}` : '';

    const [nat, st, acc, ratio] = await Promise.all([
      fetchJson<AcreageForecast>(
        `${API_BASE}/api/v1/predict/acreage/?commodity=${commodity}${yearParam}`
      ),
      fetchJson<StatesAcreageResponse>(
        `${API_BASE}/api/v1/predict/acreage/states?commodity=${commodity}${yearParam}`
      ),
      fetchJson<AcreageAccuracyItem[]>(
        `${API_BASE}/api/v1/predict/acreage/accuracy?commodity=${commodity}`
      ),
      fetchJson<PriceRatio>(
        `${API_BASE}/api/v1/predict/acreage/price-ratio`
      ),
    ]);

    setNational(nat);
    setStates(st?.states || []);
    setAccuracy(acc || []);
    setPriceRatio(ratio);

    if (!nat && !st) {
      setError('Acreage forecast data not available. Run inference first.');
    }

    setLoading(false);
  }, [commodity, year]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  return { national, states, accuracy, priceRatio, loading, error, refetch: fetchAll };
}
