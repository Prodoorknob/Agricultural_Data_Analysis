'use client';

import { useEffect, useState } from 'react';

/**
 * Lazy-load Deines et al. 2019 AIM-HPA annual irrigation time series.
 *
 * Source: aquifer-watch/scripts/build_irrigation_history.py reads
 * data/processed/deines_annual_irrigated_acres.parquet (34-year zonal sum of
 * 30 m binary-irrigation rasters per HPA-footprint county) and ships JSON to
 * s3://usda-analysis-datasets/aquiferwatch/web/county_irrigation_history.json.
 *
 * Payload shape:
 *   { version, min_year, max_year, n_counties, citation,
 *     counties: { "<fips>": [[year, acres], ...] },
 *     aggregate: [[year, acres_total_hpa], ...] }
 *
 * Fetched once per session, cached in state. Counties not over the HPA
 * footprint are absent from `counties` — consumer should handle `undefined`.
 */

const URL_IRRIGATION =
  'https://usda-analysis-datasets.s3.amazonaws.com/aquiferwatch/web/county_irrigation_history.json';

export interface IrrigationHistory {
  version: string;
  min_year: number;
  max_year: number;
  n_counties: number;
  citation: string;
  counties: Record<string, [number, number][]>;
  aggregate: [number, number][];
}

export function useIrrigationHistory(): {
  data: IrrigationHistory | null;
  error: string | null;
} {
  const [data, setData] = useState<IrrigationHistory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(URL_IRRIGATION)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((payload: IrrigationHistory) => {
        if (!cancelled) setData(payload);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { data, error };
}
