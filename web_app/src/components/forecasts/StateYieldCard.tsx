'use client';

import { useMemo } from 'react';
import type { YieldMapItem } from '@/hooks/useYieldForecast';
import { COMMODITY_COLORS } from '@/lib/constants';

interface StateYieldCardProps {
  stateFips: string;
  stateName: string | null;
  stateAlpha: string | null;
  counties: YieldMapItem[];
  crop: string;
  year: number;
  week: number | null;
  unit?: string;
}

function quantile(sorted: number[], q: number): number {
  if (sorted.length === 0) return 0;
  const pos = (sorted.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  if (sorted[base + 1] !== undefined) {
    return sorted[base] + rest * (sorted[base + 1] - sorted[base]);
  }
  return sorted[base];
}

export default function StateYieldCard({
  stateFips,
  stateName,
  stateAlpha,
  counties,
  crop,
  year,
  week,
  unit = 'bu/ac',
}: StateYieldCardProps) {
  const stats = useMemo(() => {
    const inState = counties.filter((c) => c.fips.startsWith(stateFips));
    const vals = inState
      .map((c) => c.p50)
      .filter((v) => Number.isFinite(v) && v > 0)
      .sort((a, b) => a - b);
    if (vals.length === 0) return null;
    const mean = vals.reduce((s, v) => s + v, 0) / vals.length;
    const anomalies = inState
      .map((c) => c.vs_avg_pct)
      .filter((v): v is number => v !== null && v !== undefined && Number.isFinite(v));
    const meanAnomaly =
      anomalies.length > 0 ? anomalies.reduce((s, v) => s + v, 0) / anomalies.length : null;
    return {
      n: inState.length,
      min: vals[0],
      max: vals[vals.length - 1],
      median: quantile(vals, 0.5),
      mean,
      p10: quantile(vals, 0.1),
      p90: quantile(vals, 0.9),
      meanAnomaly,
    };
  }, [counties, stateFips]);

  const color = COMMODITY_COLORS[crop.toLowerCase()] || 'var(--field)';
  const headerLabel = stateName || stateAlpha || `FIPS ${stateFips}`;

  if (!stats) {
    return (
      <div
        className="p-5 rounded-[var(--radius-lg)] border h-full"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)', minHeight: 300 }}
      >
        <p className="text-[14px] font-bold mb-1" style={{ color: 'var(--text)' }}>
          {headerLabel}
        </p>
        <p className="text-[13px]" style={{ color: 'var(--text2)' }}>
          No {crop} county forecasts modeled for this state in {year}
          {week ? `, week ${week}` : ''}. Click a colored county to drill in.
        </p>
      </div>
    );
  }

  return (
    <div
      className="p-5 rounded-[var(--radius-lg)] border h-full"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
        <span
          className="text-[16px] font-extrabold tracking-[-0.01em]"
          style={{ fontFamily: 'var(--font-stat)', color: 'var(--text)' }}
        >
          {headerLabel}
        </span>
        {stateAlpha && stateName && (
          <span
            className="text-[10px] px-1.5 py-0.5 rounded-[var(--radius-sm)]"
            style={{ background: 'var(--surface2)', color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
          >
            {stateAlpha}
          </span>
        )}
      </div>
      <p
        className="text-[12px] mb-4"
        style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
      >
        {crop.toUpperCase()} · {year}
        {week ? ` · week ${week}` : ''} · state aggregate
      </p>

      <div className="flex items-baseline gap-2">
        <span
          style={{
            fontFamily: 'var(--font-stat)',
            fontSize: '40px',
            fontWeight: 900,
            lineHeight: 0.95,
            color: 'var(--text)',
          }}
        >
          {stats.median.toFixed(1)}
        </span>
        <span
          className="text-[13px]"
          style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
        >
          {unit}
        </span>
        <span
          className="ml-2 text-[11px]"
          style={{ color: 'var(--text2)', fontFamily: 'var(--font-mono)' }}
        >
          county median p50
        </span>
      </div>

      {stats.meanAnomaly !== null && (
        <p
          className="mt-2 text-[11px]"
          style={{ color: 'var(--text2)', fontFamily: 'var(--font-mono)' }}
        >
          Avg anomaly{' '}
          <span
            style={{
              color: stats.meanAnomaly >= 0 ? 'var(--field)' : 'var(--negative)',
              fontWeight: 700,
            }}
          >
            {stats.meanAnomaly >= 0 ? '+' : ''}
            {stats.meanAnomaly.toFixed(1)}%
          </span>{' '}
          vs 5-yr county avg
        </p>
      )}

      <div
        className="mt-5 grid grid-cols-3 gap-3 text-[11px]"
        style={{ fontFamily: 'var(--font-mono)' }}
      >
        <div>
          <div style={{ color: 'var(--text3)' }}>Counties</div>
          <div className="text-[18px] font-bold" style={{ color: 'var(--text)', fontFamily: 'var(--font-stat)' }}>
            {stats.n}
          </div>
        </div>
        <div>
          <div style={{ color: 'var(--text3)' }}>Min p50</div>
          <div className="text-[18px] font-bold" style={{ color: 'var(--text)', fontFamily: 'var(--font-stat)' }}>
            {stats.min.toFixed(0)}
          </div>
        </div>
        <div>
          <div style={{ color: 'var(--text3)' }}>Max p50</div>
          <div className="text-[18px] font-bold" style={{ color: 'var(--text)', fontFamily: 'var(--font-stat)' }}>
            {stats.max.toFixed(0)}
          </div>
        </div>
      </div>

      <div className="mt-4 pt-3 border-t" style={{ borderColor: 'var(--border)' }}>
        <p className="text-[11px]" style={{ color: 'var(--text2)' }}>
          Click any colored county to see its p10/p50/p90 forecast. Use the week slider
          below the map to step through the season.
        </p>
      </div>
    </div>
  );
}
