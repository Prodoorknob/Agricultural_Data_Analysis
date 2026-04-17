'use client';

import DeltaChip from '@/components/shared/DeltaChip';
import ExperimentalPill from '@/components/shared/ExperimentalPill';
import CitationBlock from '@/components/shared/CitationBlock';
import Term from '@/components/shared/Term';
import { formatCompact } from '@/lib/format';
import { COMMODITY_COLORS } from '@/lib/constants';

interface AcreageCardProps {
  commodity: string;
  forecastAcres: number | null;
  p10: number | null;
  p90: number | null;
  yoyDeltaPct: number | null;
  keyDriver: string | null;
  usdaProspective: number | null;
  usdaDeltaPct: number | null;
  topStates: { state: string; forecastAcres: number; deltaPct: number | null }[];
  testMape: number | null;
  baselineMape: number | null;
  isExperimental: boolean;
}

export default function AcreageCard({
  commodity,
  forecastAcres,
  p10,
  p90,
  yoyDeltaPct,
  keyDriver,
  usdaProspective,
  usdaDeltaPct,
  topStates,
  testMape,
  baselineMape,
  isExperimental,
}: AcreageCardProps) {
  const color = COMMODITY_COLORS[commodity.toLowerCase()] || 'var(--field)';
  const displayName = commodity.charAt(0).toUpperCase() + commodity.slice(1);

  return (
    <div
      className="p-5 rounded-[var(--radius-lg)] border"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
        <span
          className="text-[20px] font-extrabold tracking-[-0.01em]"
          style={{ fontFamily: 'var(--font-stat)', color: 'var(--text)' }}
        >
          {displayName.toUpperCase()}
        </span>
        {isExperimental && <ExperimentalPill />}
      </div>

      {/* Hero forecast */}
      {forecastAcres !== null ? (
        <>
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
              {formatCompact(forecastAcres)}
            </span>
            <span className="text-[14px]" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
              acres
            </span>
          </div>
          {yoyDeltaPct !== null && (
            <div className="mt-2"><DeltaChip value={yoyDeltaPct} label="YoY" /></div>
          )}

          {/* P10-P90 bar — axis spans p50 ± 15%, positions are computed
              relative to that window so the bar width honors the actual
              interval instead of a hardcoded placeholder. */}
          {p10 !== null && p90 !== null && forecastAcres !== null && (() => {
            const axisMin = forecastAcres * 0.85;
            const axisMax = forecastAcres * 1.15;
            const range = axisMax - axisMin || 1;
            const clamp = (pct: number) => Math.max(0, Math.min(100, pct));
            const leftPct = clamp(((p10 - axisMin) / range) * 100);
            const rightPct = clamp(((axisMax - p90) / range) * 100);
            const markerPct = clamp(((forecastAcres - axisMin) / range) * 100);
            return (
              <div className="mt-3">
                <div className="h-2 rounded-full relative" style={{ background: 'var(--surface2)' }}>
                  <div
                    className="absolute h-2 rounded-full"
                    style={{
                      background: 'var(--field-subtle)',
                      left: `${leftPct}%`,
                      right: `${rightPct}%`,
                      border: `1px solid var(--field)`,
                    }}
                  />
                  <div
                    className="absolute top-[-1px] h-2.5 w-0.5 rounded-full"
                    style={{
                      left: `${markerPct}%`,
                      background: 'var(--text)',
                      transform: 'translateX(-50%)',
                    }}
                  />
                </div>
                <p className="text-[10px] mt-1" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
                  <Term term="80% interval">80% interval</Term>: {formatCompact(p10)}–{formatCompact(p90)}
                </p>
              </div>
            );
          })()}

          {/* Key driver */}
          {keyDriver && (
            <p className="mt-3 text-[13px]" style={{ color: 'var(--text2)' }}>
              Key driver: {keyDriver}
            </p>
          )}

          {/* USDA comparison */}
          {usdaProspective !== null && (
            <div
              className="mt-3 px-3 py-2 rounded-[var(--radius-md)]"
              style={{ background: 'var(--surface2)' }}
            >
              <p className="text-[12px]" style={{ color: 'var(--text2)' }}>
                USDA Prospective Plantings (Mar 31): <strong>{formatCompact(usdaProspective)}</strong>.
                {usdaDeltaPct !== null && (
                  <> Our forecast is <strong style={{ color: usdaDeltaPct >= 0 ? 'var(--positive)' : 'var(--negative)' }}>
                    {usdaDeltaPct >= 0 ? '+' : ''}{usdaDeltaPct.toFixed(1)}%
                  </strong> {usdaDeltaPct >= 0 ? 'above' : 'below'}.</>
                )}
              </p>
            </div>
          )}

          {/* Top 5 states */}
          {topStates.length > 0 && (
            <div className="mt-3 flex flex-col gap-1">
              {topStates.slice(0, 5).map((s, i) => (
                <div key={`${s.state}-${i}`} className="flex items-center justify-between text-[12px]">
                  <span style={{ color: 'var(--text2)' }}>{s.state}</span>
                  <span style={{ color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>
                    {formatCompact(s.forecastAcres)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Track record */}
          {testMape !== null && (
            <p className="mt-3 text-[10px]" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
              Test MAPE: {testMape.toFixed(2)}% · Baseline: {baselineMape?.toFixed(2)}%
            </p>
          )}
        </>
      ) : (
        <p className="text-[14px] py-8 text-center" style={{ color: 'var(--text3)' }}>
          No forecast available. Backend may be offline.
        </p>
      )}

      <CitationBlock source="FieldPulse ensemble" vintage="Walk-forward" />
    </div>
  );
}
