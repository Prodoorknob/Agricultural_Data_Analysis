'use client';

import type { Aggregate, MapMode } from './types';
import { fmt } from './aquifer-math';

interface Props {
  agg: Aggregate | null;
  totalCounties: number;
  year: number;
  mode: MapMode;
  onMode: (m: MapMode) => void;
}

const MODES: Array<{ k: MapMode; label: string; desc: string }> = [
  { k: 'columns', label: 'Columns', desc: 'Height = thickness' },
  { k: 'choropleth', label: 'Choropleth', desc: 'Color = thickness' },
  { k: 'dots', label: 'Bubbles', desc: 'Size = pumping' },
];

const LEGEND: Array<{ c: string; l: string }> = [
  { c: 'var(--dep-1)', l: '<5' },
  { c: 'var(--dep-3)', l: '10' },
  { c: 'var(--dep-5)', l: '25' },
  { c: 'var(--dep-7)', l: '55' },
  { c: 'var(--dep-9)', l: '100' },
  { c: 'var(--dep-10)', l: '150+' },
];

export default function MapTopBar({ agg, totalCounties, year, mode, onMode }: Props) {
  return (
    <div
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        padding: '14px 18px',
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}
    >
      {/* Row 1 — Region aggregate as a horizontal KPI strip */}
      {agg && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'auto repeat(4, 1fr) auto',
            gap: 20,
            alignItems: 'center',
            paddingBottom: 10,
            borderBottom: '1px solid var(--border)',
          }}
        >
          <div>
            <div className="eyebrow">Region aggregate</div>
            <div className="mono" style={{ fontSize: 10, color: 'var(--text3)', letterSpacing: '0.08em', marginTop: 2 }}>
              {year}
            </div>
          </div>
          <KpiCol
            label="Mean thickness"
            value={agg.countOnHpa ? (agg.totalThk / agg.countOnHpa).toFixed(1) : '—'}
            unit="m"
          />
          <KpiCol
            label="Depleted counties"
            value={`${agg.countDepleted} / ${agg.countOnHpa}`}
            valueColor={agg.countDepleted > 50 ? 'var(--negative)' : 'var(--text)'}
          />
          <KpiCol label="Pumping" value={fmt.af(agg.totalPmp)} />
          <KpiCol label="CO₂ footprint" value={agg.totalCO2.toFixed(1)} unit="Mt/yr" />
          <div
            className="mono"
            style={{
              fontSize: 9,
              color: 'var(--text3)',
              letterSpacing: '0.06em',
              textAlign: 'right',
              maxWidth: 120,
              lineHeight: 1.4,
            }}
          >
            {agg.countOnHpa} of {totalCounties} counties<br />on HPA footprint
          </div>
        </div>
      )}

      {/* Row 2 — Visualization mode + color legend + source dots */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 20,
          flexWrap: 'wrap',
        }}
      >
        {/* Mode pills */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div className="eyebrow" style={{ whiteSpace: 'nowrap' }}>Visualization</div>
          <div style={{ display: 'flex', gap: 4 }}>
            {MODES.map((m) => {
              const on = mode === m.k;
              return (
                <button
                  key={m.k}
                  onClick={() => onMode(m.k)}
                  title={m.desc}
                  style={{
                    padding: '7px 12px',
                    borderRadius: 'var(--radius-md)',
                    border: `1px solid ${on ? 'var(--field)' : 'var(--border)'}`,
                    background: on ? 'var(--field-tint)' : 'transparent',
                    color: on ? 'var(--text)' : 'var(--text2)',
                    fontSize: 12,
                    fontWeight: 600,
                    transition: 'all 150ms var(--ease-out)',
                    cursor: 'pointer',
                  }}
                >
                  {m.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Color legend ramp */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 260 }}>
          <div className="eyebrow" style={{ whiteSpace: 'nowrap' }}>Saturated thickness (m)</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 2, flex: 1, maxWidth: 360 }}>
            {LEGEND.map((x, i) => (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
                <div style={{ width: '100%', height: 12, borderRadius: 2, background: x.c }} />
                <div className="mono" style={{ fontSize: 9, color: 'var(--text3)' }}>{x.l}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Source dots */}
        <div
          className="mono"
          style={{
            fontSize: 9,
            color: 'var(--text3)',
            display: 'flex',
            gap: 12,
            flexWrap: 'wrap',
            letterSpacing: '0.04em',
          }}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: 'var(--field)' }} />
            measured wells
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: 'var(--harvest)' }} />
            USGS raster
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: 'var(--surface2)', opacity: 0.5, border: '1px solid var(--border)' }} />
            off-aquifer
          </span>
        </div>
      </div>
    </div>
  );
}

function KpiCol({
  label,
  value,
  unit,
  valueColor,
}: {
  label: string;
  value: string;
  unit?: string;
  valueColor?: string;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <div className="eyebrow">{label}</div>
      <div className="stat" style={{ fontSize: 22, fontWeight: 800, lineHeight: 1.05, color: valueColor ?? 'var(--text)' }}>
        {value}
        {unit && <span style={{ fontSize: 11, color: 'var(--text3)', marginLeft: 3, fontWeight: 500 }}>{unit}</span>}
      </div>
    </div>
  );
}
