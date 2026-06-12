/**
 * Issue spec contract for the chart-enabled FieldPulse publisher.
 *
 * This is the JSON shape a future agent step emits instead of (or alongside)
 * raw markdown. The renderer (ModelIssue.tsx) maps each block to a styled
 * component, so the agent only decides WHAT to show, never how it looks.
 *
 * Design rules baked into the renderer:
 *   - prose blocks reuse the existing .fp-issue typography classes, so a
 *     spec-rendered issue is visually identical to a markdown-rendered one
 *     where they overlap.
 *   - figures are surface cards with a title/subtitle header and a mono
 *     source line, holding 1 or 2 charts (2 = side-by-side panel pair).
 *   - all colors are CSS custom properties, so dark mode works for free.
 */

export type Tone = 'default' | 'positive' | 'negative' | 'harvest';

export interface KpiItem {
  value: string; // pre-formatted hero number, e.g. "24.3M"
  unit?: string; // small subscript, e.g. "MT"
  label: string; // mono uppercase label
  caption?: string; // one-line plain-English context
  tone?: Tone; // colors the hero value
}

export interface BarDatum {
  label: string;
  value: number;
  color?: string; // CSS color, defaults to var(--field)
}

export interface BarsChart {
  type: 'bars';
  data: BarDatum[];
  /** 'abs' renders the raw value with `unit`; 'signed_pct' renders +/-N% */
  valueFormat?: 'abs' | 'signed_pct';
  unit?: string; // e.g. "M acres"
  decimals?: number;
  height?: number;
  domain?: [number, number];
  caption?: string; // small caption under the panel (used in pairs)
}

export interface TrendForecastChart {
  type: 'trend_forecast';
  actuals: { year: number; value: number }[];
  forecast: { year: number; p50: number; p10: number; p90: number };
  refValue?: number;
  refLabel?: string;
  unit?: string;
  height?: number;
  yDomain?: [number, number];
  caption?: string;
}

export interface RegionMapState {
  fips: string; // 2-digit state FIPS
  abbr: string;
  name: string;
  /** forecast & baseline in the metric's units (e.g. M acres). null = flagged */
  forecast: number | null;
  baseline: number | null;
  note?: string; // tooltip note, e.g. why a state is flagged
}

export interface RegionMapChart {
  type: 'region_map';
  states: RegionMapState[];
  metricLabel: string; // e.g. "2026 forecast vs 2021-24 avg"
  unit?: string; // e.g. "M ac"
  height?: number;
  caption?: string;
}

export type ChartSpec = BarsChart | TrendForecastChart | RegionMapChart;

export type Block =
  | { kind: 'title'; text: string }
  | { kind: 'dek'; text: string }
  | { kind: 'section'; text: string; lead?: boolean }
  | { kind: 'brief'; text: string }
  | { kind: 'p'; text: string; first?: boolean }
  | { kind: 'watch'; text: string }
  | { kind: 'kpis'; title?: string; items: KpiItem[] }
  | { kind: 'stat'; value: string; label: string; detail?: string }
  | {
      kind: 'figure';
      title: string;
      subtitle?: string;
      source?: string;
      charts: ChartSpec[]; // 1 chart = full width, 2 = panel pair
    }
  | { kind: 'hr' };

export interface IssueMetaSpec {
  run_date: string;
  cost_usd?: number;
  duration_sec?: number;
  n_tool_calls?: number;
  n_signals_scanned?: number;
  approved_by?: string;
}

export interface IssueSpec {
  blocks: Block[];
  meta: IssueMetaSpec;
}
