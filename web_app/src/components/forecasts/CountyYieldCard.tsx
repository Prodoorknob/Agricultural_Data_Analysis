'use client';

import type { YieldForecast } from '@/hooks/useYieldForecast';
import DeltaChip from '@/components/shared/DeltaChip';
import Term from '@/components/shared/Term';
import { COMMODITY_COLORS } from '@/lib/constants';

interface CountyYieldCardProps {
  forecast: YieldForecast | null;
  countyName: string | null;
  stateAlpha: string | null;
  loading: boolean;
}

const CONFIDENCE_COPY: Record<string, { label: string; fg: string; bg: string }> = {
  high: { label: 'HIGH CONFIDENCE', fg: 'var(--field-dark)', bg: 'var(--field-subtle)' },
  medium: { label: 'MEDIUM CONFIDENCE', fg: 'var(--harvest-dark)', bg: 'var(--harvest-subtle)' },
  low: { label: 'LOW CONFIDENCE', fg: 'var(--negative)', bg: 'var(--surface2)' },
};

export default function CountyYieldCard({
  forecast,
  countyName,
  stateAlpha,
  loading,
}: CountyYieldCardProps) {
  if (loading) {
    return (
      <div
        className="p-5 rounded-[var(--radius-lg)] border h-full flex items-center justify-center"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)', minHeight: 300 }}
      >
        <p className="text-[13px]" style={{ color: 'var(--text3)' }}>Loading forecast…</p>
      </div>
    );
  }

  if (!forecast) {
    return (
      <div
        className="p-5 rounded-[var(--radius-lg)] border h-full"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)', minHeight: 300 }}
      >
        <p className="text-[14px] font-bold mb-1" style={{ color: 'var(--text)' }}>
          Select a county
        </p>
        <p className="text-[13px]" style={{ color: 'var(--text2)' }}>
          Click any green-shaded county on the map to see its p10, p50, and p90 yield forecast
          for the latest modeled week of the season.
        </p>
      </div>
    );
  }

  const color = COMMODITY_COLORS[forecast.crop.toLowerCase()] || 'var(--field)';
  const conf = CONFIDENCE_COPY[forecast.confidence] || CONFIDENCE_COPY.low;

  // Interval band: axis spans p50 +/- 20% so the p10..p90 band sizes itself
  // from real data rather than being pinned to the axis edges.
  const axisMin = forecast.p50 * 0.8;
  const axisMax = forecast.p50 * 1.2;
  const range = axisMax - axisMin || 1;
  const clamp = (pct: number) => Math.max(0, Math.min(100, pct));
  const leftPct = clamp(((forecast.p10 - axisMin) / range) * 100);
  const rightPct = clamp(((axisMax - forecast.p90) / range) * 100);
  const markerPct = clamp(((forecast.p50 - axisMin) / range) * 100);
  const avgPct =
    forecast.county_avg_5yr !== null
      ? clamp(((forecast.county_avg_5yr - axisMin) / range) * 100)
      : null;

  const locationLabel =
    countyName && stateAlpha
      ? `${countyName}, ${stateAlpha}`
      : countyName || `FIPS ${forecast.fips}`;

  return (
    <div
      className="p-5 rounded-[var(--radius-lg)] border h-full"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-1">
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
        <span
          className="text-[16px] font-extrabold tracking-[-0.01em]"
          style={{ fontFamily: 'var(--font-stat)', color: 'var(--text)' }}
        >
          {locationLabel}
        </span>
      </div>
      <p className="text-[12px] mb-4" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
        {forecast.crop.toUpperCase()} · {forecast.crop_year} · week {forecast.week}
      </p>

      {/* Hero p50 */}
      <div className="flex items-baseline gap-2">
        <span
          style={{
            fontFamily: 'var(--font-stat)',
            fontSize: '48px',
            fontWeight: 900,
            lineHeight: 0.95,
            color: 'var(--text)',
          }}
        >
          {forecast.p50.toFixed(1)}
        </span>
        <span className="text-[13px]" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
          {forecast.unit || 'bu/ac'}
        </span>
        <span
          className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded-[var(--radius-full)]"
          style={{
            background: conf.bg,
            color: conf.fg,
            fontFamily: 'var(--font-mono)',
            fontSize: '9px',
            fontWeight: 700,
            letterSpacing: '0.12em',
          }}
        >
          {conf.label}
        </span>
      </div>

      {forecast.vs_avg_pct !== null && (
        <div className="mt-2"><DeltaChip value={forecast.vs_avg_pct} label="vs 5-yr avg" /></div>
      )}

      {/* p10 / p50 / p90 interval band */}
      <div className="mt-5">
        <div
          className="h-3 rounded-full relative"
          style={{ background: 'var(--surface2)' }}
        >
          {/* p10..p90 filled band */}
          <div
            className="absolute h-3 rounded-full"
            style={{
              background: 'var(--field-subtle)',
              left: `${leftPct}%`,
              right: `${rightPct}%`,
              border: '1px solid var(--field)',
            }}
          />
          {/* 5-yr avg reference tick */}
          {avgPct !== null && (
            <div
              className="absolute top-[-3px] h-4 w-0.5 rounded-full"
              style={{
                left: `${avgPct}%`,
                background: 'var(--text3)',
                transform: 'translateX(-50%)',
              }}
              title="5-yr county average"
            />
          )}
          {/* p50 marker */}
          <div
            className="absolute top-[-2px] h-3.5 w-0.5 rounded-full"
            style={{
              left: `${markerPct}%`,
              background: 'var(--text)',
              transform: 'translateX(-50%)',
            }}
          />
        </div>
        <div className="flex justify-between items-center mt-1 text-[10px]"
             style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
          <span>p10 {forecast.p10.toFixed(1)}</span>
          <span style={{ color: 'var(--text2)' }}>
            p50 {forecast.p50.toFixed(1)}
          </span>
          <span>p90 {forecast.p90.toFixed(1)}</span>
        </div>
        <p className="text-[11px] mt-2" style={{ color: 'var(--text2)' }}>
          <Term term="80% interval">80% interval</Term> spans {forecast.p10.toFixed(1)}–{forecast.p90.toFixed(1)} {forecast.unit || 'bu/ac'}.
          {forecast.county_avg_5yr !== null && (
            <> Gray tick marks the county&rsquo;s 5-yr average ({forecast.county_avg_5yr.toFixed(1)}).</>
          )}
        </p>
      </div>

      {/* Footer meta */}
      <div
        className="mt-4 pt-3 border-t flex items-center justify-between text-[10px]"
        style={{ borderColor: 'var(--border)', color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
      >
        <span>Model v{forecast.model_ver}</span>
        {forecast.last_updated && (
          <span>Updated {forecast.last_updated.slice(0, 10)}</span>
        )}
      </div>
    </div>
  );
}
