'use client';

import {
  ComposedChart, Line, Area, LineChart, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import CitationBlock from '@/components/shared/CitationBlock';
import SectionHeading from '@/components/shared/SectionHeading';
import { COMMODITY_COLORS } from '@/lib/constants';

interface AccuracyItem {
  forecast_year: number;
  commodity: string;
  level?: string;
  model_vs_actual_pct?: number | null;
}

interface YieldAccuracyWeek {
  crop: string;
  week: number;
  avg_pct_error: number | null;
  baseline_rrmse: number | null;
}

interface AccuracyPanelProps {
  acreageAccuracy: AccuracyItem[];
  yieldAccuracy: YieldAccuracyWeek[];
}

// Map the training-artifact commodity keys back to the chart-color keys. The
// acreage backend publishes a `wheat_winter`/`wheat_spring` split but the
// accuracy chart compares against the unified frontend `wheat` color.
function normalizeCommodity(c: string): 'corn' | 'soybean' | 'wheat' | null {
  if (c === 'corn') return 'corn';
  if (c === 'soybean' || c === 'soybeans') return 'soybean';
  if (c === 'wheat' || c === 'wheat_winter' || c === 'wheat_spring') return 'wheat';
  return null;
}

// Pivot an array of per-(year,commodity) rows into a chart-friendly shape:
//   [{year: 2021, corn: -3.2, soybean: +1.1, wheat: +4.5}, ...]
// If a single year has multiple rows for the same normalized commodity (e.g.
// wheat_winter + wheat_spring), keep the first seen so the chart doesn't
// flicker on retrain.
function pivotAcreageByYear(
  rows: AccuracyItem[],
): Array<{ year: number; corn?: number; soybean?: number; wheat?: number }> {
  const by = new Map<number, { year: number; corn?: number; soybean?: number; wheat?: number }>();
  for (const r of rows) {
    if (r.model_vs_actual_pct == null) continue;
    const key = normalizeCommodity(r.commodity);
    if (!key) continue;
    const bucket = by.get(r.forecast_year) ?? { year: r.forecast_year };
    if (bucket[key] === undefined) bucket[key] = r.model_vs_actual_pct;
    by.set(r.forecast_year, bucket);
  }
  return Array.from(by.values()).sort((a, b) => a.year - b.year);
}

// Pivot yield rows (one row per crop-week) into per-week rows with each
// crop's RRMSE and one merged baseline line. Baseline comes out of
// whichever crop ships it — they're all computed against the same county
// 5-yr mean, so the numeric value is the same up to rounding.
function pivotYieldByWeek(
  rows: YieldAccuracyWeek[],
): Array<{ week: number; corn?: number; soybean?: number; wheat?: number; baseline?: number }> {
  const by = new Map<number, { week: number; corn?: number; soybean?: number; wheat?: number; baseline?: number }>();
  for (const r of rows) {
    const key = normalizeCommodity(r.crop);
    if (!key) continue;
    const bucket = by.get(r.week) ?? { week: r.week };
    if (r.avg_pct_error != null) bucket[key] = r.avg_pct_error;
    if (r.baseline_rrmse != null && bucket.baseline === undefined) {
      bucket.baseline = r.baseline_rrmse;
    }
    by.set(r.week, bucket);
  }
  return Array.from(by.values()).sort((a, b) => a.week - b.week);
}

export default function AccuracyPanel({ acreageAccuracy, yieldAccuracy }: AccuracyPanelProps) {
  const acreageByYear = pivotAcreageByYear(acreageAccuracy);
  const yieldByWeek = pivotYieldByWeek(yieldAccuracy);
  const hasAcreage = acreageByYear.length > 0;
  const hasYield = yieldByWeek.length > 0;

  if (!hasAcreage && !hasYield) {
    return (
      <div
        className="p-6 rounded-[var(--radius-lg)] border text-center"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <p className="text-[14px]" style={{ color: 'var(--text3)' }}>
          Accuracy data loading from backend...
        </p>
      </div>
    );
  }

  const cornColor = COMMODITY_COLORS['corn'] || '#E8B923';
  const soyColor = COMMODITY_COLORS['soybeans'] || COMMODITY_COLORS['soybean'] || '#6B9E5A';
  const wheatColor = COMMODITY_COLORS['wheat'] || '#C8A968';

  return (
    <div className="mb-8">
      <h3
        className="text-[18px] font-bold mb-1"
        style={{ color: 'var(--text)', fontFamily: 'var(--font-body)' }}
      >
        Season-by-Season Accuracy
      </h3>
      <p className="text-[13px] mb-4" style={{ color: 'var(--text2)' }}>
        Walk-forward test results. No forecast without its track record.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Acreage accuracy — national only, one line per commodity */}
        {hasAcreage && (
          <div
            className="p-4 rounded-[var(--radius-lg)] border"
            style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
          >
            <SectionHeading>Acreage · National Model vs Actual %</SectionHeading>
            <div style={{ height: 240 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={acreageByYear} margin={{ top: 5, right: 10, bottom: 30, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="year" axisLine={false} tickLine={false}
                    tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }} />
                  <YAxis axisLine={false} tickLine={false}
                    tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                    tickFormatter={(v) => `${v}%`} />
                  <Tooltip
                    contentStyle={{
                      background: 'var(--surface)', border: '1px solid var(--border)',
                      borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--text)',
                    }}
                    formatter={(val: number | string, name: string) => [
                      `${Number(val).toFixed(1)}%`,
                      name.charAt(0).toUpperCase() + name.slice(1),
                    ]}
                  />
                  <Legend verticalAlign="bottom" wrapperStyle={{ fontSize: 11, fontFamily: 'var(--font-mono)', paddingTop: 8 }} />
                  <Line type="monotone" dataKey="corn" name="Corn" stroke={cornColor} strokeWidth={2} dot={{ r: 3, fill: cornColor }} connectNulls />
                  <Line type="monotone" dataKey="soybean" name="Soybean" stroke={soyColor} strokeWidth={2} dot={{ r: 3, fill: soyColor }} connectNulls />
                  <Line type="monotone" dataKey="wheat" name="Wheat" stroke={wheatColor} strokeWidth={2} dot={{ r: 3, fill: wheatColor }} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Yield accuracy — shaded area per crop + baseline */}
        {hasYield && (
          <div
            className="p-4 rounded-[var(--radius-lg)] border"
            style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
          >
            <SectionHeading>Corn · Soybean · Wheat — Yield RRMSE by Season Week</SectionHeading>
            <div style={{ height: 240 }}>
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={yieldByWeek} margin={{ top: 5, right: 10, bottom: 30, left: 10 }}>
                  <defs>
                    <linearGradient id="fill-corn" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={cornColor} stopOpacity={0.35} />
                      <stop offset="100%" stopColor={cornColor} stopOpacity={0.05} />
                    </linearGradient>
                    <linearGradient id="fill-soy" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={soyColor} stopOpacity={0.35} />
                      <stop offset="100%" stopColor={soyColor} stopOpacity={0.05} />
                    </linearGradient>
                    <linearGradient id="fill-wheat" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={wheatColor} stopOpacity={0.35} />
                      <stop offset="100%" stopColor={wheatColor} stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis
                    dataKey="week"
                    interval="preserveStartEnd"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                  />
                  <YAxis axisLine={false} tickLine={false}
                    tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                    tickFormatter={(v) => `${v}%`} />
                  <Tooltip
                    contentStyle={{
                      background: 'var(--surface)', border: '1px solid var(--border)',
                      borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--text)',
                    }}
                    formatter={(val: number | string, name: string) => [
                      `${Number(val).toFixed(1)}%`,
                      name,
                    ]}
                    labelFormatter={(w: number | string) => `Week ${w}`}
                  />
                  <Legend verticalAlign="bottom" wrapperStyle={{ fontSize: 11, fontFamily: 'var(--font-mono)', paddingTop: 8 }} />
                  <Area type="monotone" dataKey="corn" name="Corn" stroke={cornColor} strokeWidth={2} fill="url(#fill-corn)" fillOpacity={1} connectNulls />
                  <Area type="monotone" dataKey="soybean" name="Soybean" stroke={soyColor} strokeWidth={2} fill="url(#fill-soy)" fillOpacity={1} connectNulls />
                  <Area type="monotone" dataKey="wheat" name="Wheat" stroke={wheatColor} strokeWidth={2} fill="url(#fill-wheat)" fillOpacity={1} connectNulls />
                  <Line type="monotone" dataKey="baseline" name="Baseline (5-yr mean)" stroke="var(--text3)" strokeWidth={1} strokeDasharray="4 3" dot={false} connectNulls />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
      <CitationBlock source="Walk-forward backtest" vintage="2020–2025" />
    </div>
  );
}
