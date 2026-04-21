'use client';

import { useMemo } from 'react';
import type { CountyRollup } from './CropsStateMap';

interface Props {
  rollup: Map<string, CountyRollup>;
  selectedFips: string;
  stateName: string;
  commodityLabel: string;
  year: number;
  precipRow?: {
    precip_normal_mm_yr: number;
    precip_recent_mm_yr: number;
    precip_anomaly_pct: number;
  };
  irrigatedAcres?: number;
  onClose: () => void;
}

function titleCase(s: string): string {
  return String(s).toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}

function compact(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return '—';
  if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return String(Math.round(n));
}

/**
 * County drill-down — the Ogallala-style dense panel shown when the user
 * clicks a county. Populates from county rollup + precip + irrigated ingests.
 */
export default function CropsCountyDrill({
  rollup, selectedFips, stateName, commodityLabel, year, precipRow, irrigatedAcres, onClose,
}: Props) {
  const row = rollup.get(selectedFips);

  const stateStats = useMemo(() => {
    const yields = Array.from(rollup.values()).map((r) => r.yield).filter((v) => v > 0).sort((a, b) => a - b);
    const median = yields.length ? yields[Math.floor(yields.length / 2)] : 0;
    const totalProd = Array.from(rollup.values()).reduce((s, r) => s + (r.production || 0), 0);
    return { median, totalProd, n: yields.length };
  }, [rollup]);

  const rank = useMemo(() => {
    if (!row) return null;
    const sorted = [...rollup.values()].sort((a, b) => b.yield - a.yield);
    return sorted.findIndex((r) => r.fips === selectedFips) + 1;
  }, [rollup, selectedFips, row]);

  if (!row) {
    return (
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <div>
            <div style={sectLabel}>{stateName.toUpperCase()} · FIPS {selectedFips}</div>
            <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.01em' }}>No reported data</div>
          </div>
          <button onClick={onClose} style={closeBtnStyle}>ESC / back to state</button>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text2)' }}>
          This county is in the map but NASS didn&apos;t publish a {commodityLabel.toLowerCase()} yield
          for {year} — likely suppressed under disclosure rules, or the crop isn&apos;t commercially
          grown here. Try a different crop or year.
        </div>
      </div>
    );
  }

  const anomaly = stateStats.median > 0 ? ((row.yield - stateStats.median) / stateStats.median) * 100 : 0;
  const anomalyColor = anomaly >= 0 ? 'var(--field)' : 'var(--negative)';
  const stateShare = stateStats.totalProd > 0 ? (row.production / stateStats.totalProd) * 100 : 0;

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
        <div>
          <div style={sectLabel}>{stateName.toUpperCase()} · FIPS {selectedFips}</div>
          <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.01em' }}>
            {titleCase(row.county)}
          </div>
        </div>
        <button onClick={onClose} style={closeBtnStyle}>ESC / back to state</button>
      </div>

      {/* Status pills */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', margin: '8px 0 16px' }}>
        <span style={{ ...pillStyle, color: 'var(--field-light)', borderColor: 'var(--field-dark)' }}>
          <span style={{ width: 6, height: 6, background: 'var(--field)', borderRadius: 999, marginRight: 6, display: 'inline-block' }} />
          Measured · NASS {year}
        </span>
        <span style={pillStyle}>Rank {rank ?? '—'} of {stateStats.n}</span>
        <span style={{ ...pillStyle, color: anomalyColor, borderColor: anomaly >= 0 ? 'var(--field-dark)' : '#6a2a22' }}>
          Anomaly {anomaly >= 0 ? '+' : ''}{anomaly.toFixed(1)}%
        </span>
      </div>

      {/* KPIs */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10,
        background: 'var(--surface2)', borderRadius: 'var(--radius-md)', padding: 14, marginBottom: 16,
      }}>
        <div>
          <div style={kpiLabel}>Yield</div>
          <div style={kpiValue}>{row.yield.toFixed(1)}<span style={unitStyle}>bu/ac</span></div>
          <div style={kpiSub}>state median {stateStats.median.toFixed(0)}</div>
        </div>
        <div>
          <div style={kpiLabel}>Harvested</div>
          <div style={{ ...kpiValue, color: 'var(--text)' }}>{compact(row.harvested)}<span style={unitStyle}>acres</span></div>
          <div style={kpiSub}>{irrigatedAcres != null && irrigatedAcres > 0
            ? <span>{Math.min(100, (irrigatedAcres / row.harvested) * 100).toFixed(0)}% irrigated (2022 Census)</span>
            : <span>irrigation data not published</span>}
          </div>
        </div>
        <div>
          <div style={kpiLabel}>Production</div>
          <div style={{ ...kpiValue, color: 'var(--text)' }}>{compact(row.production)}<span style={unitStyle}>bu</span></div>
          <div style={{ ...kpiSub, color: 'var(--field)' }}>
            {stateShare.toFixed(1)}% of state total
          </div>
        </div>
      </div>

      {/* Growing-season context (from NOAA nClimDiv) */}
      {precipRow && (
        <div style={{ marginBottom: 18 }}>
          <div style={sectLabel}>Growing-season precipitation · NOAA nClimDiv</div>
          <div style={{
            display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10,
            background: 'var(--surface2)', borderRadius: 'var(--radius-md)', padding: 14, marginTop: 8,
          }}>
            <div>
              <div style={ctxLabel}>30-yr normal</div>
              <div style={ctxVal}>{precipRow.precip_normal_mm_yr.toFixed(0)}<span style={ctxUnit}>mm/yr</span></div>
              <div style={ctxDelta}>1991–2020 baseline</div>
            </div>
            <div>
              <div style={ctxLabel}>Recent avg</div>
              <div style={ctxVal}>{precipRow.precip_recent_mm_yr.toFixed(0)}<span style={ctxUnit}>mm/yr</span></div>
              <div style={ctxDelta}>2019–2023</div>
            </div>
            <div>
              <div style={ctxLabel}>Anomaly</div>
              <div style={{
                ...ctxVal,
                color: precipRow.precip_anomaly_pct >= 0 ? 'var(--field)' : 'var(--negative)',
              }}>
                {precipRow.precip_anomaly_pct >= 0 ? '+' : ''}{precipRow.precip_anomaly_pct.toFixed(1)}%
              </div>
              <div style={ctxDelta}>
                {(precipRow.precip_recent_mm_yr - precipRow.precip_normal_mm_yr).toFixed(0)} mm
              </div>
            </div>
          </div>
        </div>
      )}

      <div style={{ fontSize: 11, color: 'var(--text3)', fontFamily: 'var(--font-mono)', lineHeight: 1.55 }}>
        County yield is the canonical NASS SURVEY row after filtering
        <code style={codeStyle}>reference_period_desc = &apos;YEAR&apos;</code> and
        <code style={codeStyle}>class_desc = &apos;ALL CLASSES&apos;</code>. Anomaly is
        (county − state median) / state median. Precipitation from NOAA
        nClimDiv county series; irrigated-acres overlay from NASS Census of
        Ag 2022.
      </div>
    </div>
  );
}

const sectLabel: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.12em',
  color: 'var(--text3)', textTransform: 'uppercase', marginBottom: 4,
};
const closeBtnStyle: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 10, padding: '4px 10px',
  border: '1px solid var(--border2)', borderRadius: 999,
  background: 'var(--surface2)', color: 'var(--text2)', cursor: 'pointer',
};
const pillStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', padding: '4px 10px',
  border: '1px solid var(--border2)', borderRadius: 999,
  fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text2)',
};
const kpiLabel: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.08em',
  color: 'var(--text3)', textTransform: 'uppercase', marginBottom: 4,
};
const kpiValue: React.CSSProperties = {
  fontSize: 30, fontWeight: 800, letterSpacing: '-0.02em',
  color: 'var(--field-light)', lineHeight: 1.05,
};
const unitStyle: React.CSSProperties = {
  fontSize: 11, color: 'var(--text3)', fontFamily: 'var(--font-mono)',
  fontWeight: 500, marginLeft: 4, textTransform: 'uppercase',
};
const kpiSub: React.CSSProperties = {
  marginTop: 4, fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text3)',
};
const ctxLabel: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.08em',
  color: 'var(--text3)', textTransform: 'uppercase', marginBottom: 6,
};
const ctxVal: React.CSSProperties = {
  fontSize: 18, fontWeight: 700, color: 'var(--text)',
};
const ctxUnit: React.CSSProperties = {
  fontSize: 10, color: 'var(--text3)', fontFamily: 'var(--font-mono)',
  fontWeight: 500, marginLeft: 4,
};
const ctxDelta: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text3)', marginTop: 3,
};
const codeStyle: React.CSSProperties = {
  fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--field-light)',
  background: 'var(--surface2)', padding: '1px 5px', borderRadius: 3, margin: '0 2px',
};
