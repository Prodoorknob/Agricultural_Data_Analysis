import { useState, useCallback } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_PREDICTION_API_URL || 'http://localhost:8000/api/v1/predict/price';

export interface PriceForecast {
  commodity: string;
  run_date: string;
  horizon_month: string;
  p10: number;
  p50: number;
  p90: number;
  unit: string;
  key_driver: string | null;
  divergence_flag: boolean;
  regime_anomaly: boolean;
  model_ver: string;
}

export interface PriceProbability {
  commodity: string;
  threshold_price: number;
  horizon_month: string;
  probability: number;
  confidence_note: string;
}

export interface WasdeSignal {
  commodity: string;
  release_date: string;
  stocks_to_use: number;
  stocks_to_use_pctile: number;
  prior_month_stu: number | null;
  surprise: number | null;
  surprise_direction: 'bullish' | 'bearish' | 'neutral' | null;
  historical_context: string | null;
}

export interface ForecastHistoryItem {
  run_date: string;
  horizon_month: string;
  p50: number;
  actual: number | null;
  error_pct: number | null;
}

interface UsePriceForecastReturn {
  forecast: PriceForecast | null;
  forecasts: PriceForecast[];
  probability: PriceProbability | null;
  wasdeSignal: WasdeSignal | null;
  history: ForecastHistoryItem[];
  loading: boolean;
  error: string | null;
  fetchForecast: (commodity: string, horizon: number) => Promise<void>;
  fetchAllHorizons: (commodity: string) => Promise<void>;
  fetchProbability: (commodity: string, threshold: number, horizon: number) => Promise<void>;
  fetchWasdeSignal: (commodity: string) => Promise<void>;
  fetchHistory: (commodity: string, horizon: number) => Promise<void>;
}

async function apiFetch<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json();
}

export function usePriceForecast(): UsePriceForecastReturn {
  const [forecast, setForecast] = useState<PriceForecast | null>(null);
  const [forecasts, setForecasts] = useState<PriceForecast[]>([]);
  const [probability, setProbability] = useState<PriceProbability | null>(null);
  const [wasdeSignal, setWasdeSignal] = useState<WasdeSignal | null>(null);
  const [history, setHistory] = useState<ForecastHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchForecast = useCallback(async (commodity: string, horizon: number) => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<PriceForecast>(
        `${API_BASE}/?commodity=${commodity}&horizon_months=${horizon}`
      );
      setForecast(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchAllHorizons = useCallback(async (commodity: string) => {
    setLoading(true);
    setError(null);
    try {
      const promises = [1, 2, 3, 4, 5, 6].map(h =>
        apiFetch<PriceForecast>(`${API_BASE}/?commodity=${commodity}&horizon_months=${h}`)
      );
      const results = await Promise.all(promises);
      setForecasts(results);
      setForecast(results[2]); // Default to 3-month
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchProbability = useCallback(async (commodity: string, threshold: number, horizon: number) => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<PriceProbability>(
        `${API_BASE}/probability?commodity=${commodity}&threshold_price=${threshold}&horizon_months=${horizon}`
      );
      setProbability(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchWasdeSignal = useCallback(async (commodity: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<WasdeSignal>(
        `${API_BASE}/wasde-signal?commodity=${commodity}`
      );
      setWasdeSignal(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchHistory = useCallback(async (commodity: string, horizon: number) => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<ForecastHistoryItem[]>(
        `${API_BASE}/history?commodity=${commodity}&horizon_months=${horizon}`
      );
      setHistory(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    forecast,
    forecasts,
    probability,
    wasdeSignal,
    history,
    loading,
    error,
    fetchForecast,
    fetchAllHorizons,
    fetchProbability,
    fetchWasdeSignal,
    fetchHistory,
  };
}
