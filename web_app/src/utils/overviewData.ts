/**
 * Typed fetchers for the Overview-tab aggregates.
 *
 * These four parquets are pre-computed by the pipeline
 * (pipeline/build_overview_aggregates.py + build_county_aggregates.py) so the
 * client never has to load and re-aggregate raw state-level data:
 *
 *   state_totals.parquet            — (year, state, total_sales_usd, ...)
 *   state_commodity_totals.parquet  — (year, state, commodity, metrics...)
 *   county_metrics/{STATE}.parquet  — (year, fips, commodity, metrics...)
 *   land_use.parquet                — (year, state, category, acres)
 *
 * All fetched via the same hyparquet path as the legacy serviceData.ts
 * partition parquets, but at a fraction of the payload size — the whole
 * overview dataset is ~700KB vs ~15MB of raw NASS state files.
 */

import { parquetRead, parquetMetadata } from 'hyparquet';

const S3_BASE = 'https://usda-analysis-datasets.s3.us-east-2.amazonaws.com/survey_datasets/overview';

export interface StateTotalRow {
  year: number;
  state_alpha: string;
  total_sales_usd: number | null;
  total_area_planted_acres: number | null;
  commodity_count: number | null;
  top_commodity: string | null;
  top_commodity_sales_usd: number | null;
  rank_by_sales: number | null;
}

export interface StateCommodityRow {
  year: number;
  state_alpha: string;
  commodity_desc: string;
  sales_usd: number | null;
  area_planted_acres: number | null;
  area_harvested_acres: number | null;
  inventory_head: number | null;
  production: number | null;
  production_unit: string | null;
  yield_value: number | null;
  yield_unit: string | null;
  group_desc: string | null;
  sector_desc: string | null;
}

export interface CountyMetricRow {
  year: number;
  fips: string;
  commodity_desc: string;
  county_name: string | null;
  area_harvested_acres: number | null;
  area_planted_acres: number | null;
  production: number | null;
  production_unit: string | null;
  yield_value: number | null;
  yield_unit: string | null;
}

export interface LandUseRow {
  year: number;
  state_alpha: string;
  state_fips: string;
  category: 'cropland' | 'pasture' | 'forest' | 'urban' | 'special' | 'other';
  acres: number | null;
}

async function fetchParquet<T>(url: string, signal?: AbortSignal): Promise<T[]> {
  let buf: ArrayBuffer;
  try {
    const resp = await fetch(url, { mode: 'cors', credentials: 'omit', signal });
    if (!resp.ok) {
      console.warn(`[overviewData] ${url} → HTTP ${resp.status}`);
      return [];
    }
    buf = await resp.arrayBuffer();
  } catch (e) {
    if ((e as { name?: string })?.name === 'AbortError') throw e;
    console.warn(`[overviewData] fetch failed for ${url}:`, e);
    return [];
  }

  return new Promise<T[]>((resolve) => {
    let settled = false;
    const done = (rows: T[]) => {
      if (settled) return;
      settled = true;
      resolve(rows);
    };
    try {
      const metadata = parquetMetadata(buf);
      if (!metadata || !metadata.row_groups?.length) {
        done([]);
        return;
      }
      const headers = metadata.row_groups[0].columns.map(
        (c: any) => c.meta_data.path_in_schema[0]
      );
      parquetRead({
        file: buf,
        onComplete: (rows) => {
          const out = rows.map((r: unknown[]) => {
            const obj: Record<string, unknown> = {};
            headers.forEach((h: string, i: number) => {
              const v = r[i];
              obj[h] = typeof v === 'bigint' ? Number(v) : v;
            });
            return obj as T;
          });
          done(out);
        },
      });
      setTimeout(() => done([]), 30_000);
    } catch (e) {
      console.error('[overviewData] parse error', e);
      done([]);
    }
  });
}

export function fetchStateTotals(signal?: AbortSignal): Promise<StateTotalRow[]> {
  return fetchParquet<StateTotalRow>(`${S3_BASE}/state_totals.parquet`, signal);
}

export function fetchStateCommodityTotals(signal?: AbortSignal): Promise<StateCommodityRow[]> {
  return fetchParquet<StateCommodityRow>(`${S3_BASE}/state_commodity_totals.parquet`, signal);
}

export function fetchCountyMetrics(stateAlpha: string, signal?: AbortSignal): Promise<CountyMetricRow[]> {
  return fetchParquet<CountyMetricRow>(
    `${S3_BASE}/county_metrics/${stateAlpha.toUpperCase()}.parquet`,
    signal,
  );
}

export function fetchLandUse(signal?: AbortSignal): Promise<LandUseRow[]> {
  return fetchParquet<LandUseRow>(`${S3_BASE}/land_use.parquet`, signal);
}
