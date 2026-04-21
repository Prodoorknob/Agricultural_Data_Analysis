'use client';

import type { Aggregate, MapMode, Scenario } from './types';
import { SCENARIOS, fmt } from './aquifer-math';

interface Props {
  agg: Aggregate | null;
  totalCounties: number;
  year: number;
  mode: MapMode;
  onMode: (m: MapMode) => void;
  scenario: Scenario;
  onScenario: (s: Scenario) => void;
  custom: Scenario;
  onCustom: (s: Scenario) => void;
  isBAU: boolean;
}

const MODES: Array<{ k: MapMode; label: string; desc: string }> = [
  { k: 'columns', label: 'Columns', desc: 'Height = thickness' },
  { k: 'choropleth', label: 'Choropleth', desc: 'Color = thickness' },
  { k: 'dots', label: 'Bubbles', desc: 'Size = pumping' },
];

const THK_LEGEND: Array<{ c: string; l: string }> = [
  { c: 'var(--dep-1)', l: '<5' },
  { c: 'var(--dep-3)', l: '10' },
  { c: 'var(--dep-5)', l: '25' },
  { c: 'var(--dep-7)', l: '55' },
  { c: 'var(--dep-9)', l: '100' },
  { c: 'var(--dep-10)', l: '150+' },
];

const DELTA_LEGEND: Array<{ c: string; l: string }> = [
  { c: 'var(--negative)', l: '−10' },
  { c: 'color-mix(in oklab, var(--negative) 55%, var(--surface2))', l: '−5' },
  { c: 'var(--surface2)', l: '±0' },
  { c: 'color-mix(in oklab, var(--positive) 55%, var(--surface2))', l: '+5' },
  { c: 'var(--positive)', l: '+10' },
  { c: 'color-mix(in oklab, var(--positive) 150%, var(--field))', l: '+20 m' },
];

export default function MapTopBar({
  agg,
  totalCounties,
  year,
  mode,
  onMode,
  scenario,
  onScenario,
  custom,
  onCustom,
  isBAU,
}: Props) {
  const isCustom = scenario.id === 'custom';

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

      {/* Row 2 — Scenario strip */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          flexWrap: 'wrap',
          paddingBottom: 10,
          borderBottom: '1px solid var(--border)',
        }}
      >
        <div className="eyebrow" style={{ whiteSpace: 'nowrap' }}>Scenario</div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', flex: 1, minWidth: 0 }}>
          {SCENARIOS.map((s, idx) => {
            const on = scenario.id === s.id;
            const tooltipLines = [
              s.sub,
              s.pumpDelta !== 0 ? `Pumping: ${(s.pumpDelta * 100).toFixed(0)}%` : null,
              s.cropShift !== 0 ? `Crop shift: ${(s.cropShift * 100).toFixed(0)}%` : null,
              s.rechargeMult !== 1 ? `Recharge ×${s.rechargeMult.toFixed(2)}` : null,
              s.threshold != null ? `Threshold: ${s.threshold} m` : null,
            ].filter(Boolean).join(' · ');
            return (
              <button
                key={s.id}
                onClick={() => onScenario(s)}
                title={tooltipLines}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '6px 10px',
                  borderRadius: 'var(--radius-md)',
                  border: `1px solid ${on ? 'var(--field)' : 'var(--border)'}`,
                  background: on ? 'var(--field-tint)' : 'transparent',
                  color: on ? 'var(--text)' : 'var(--text2)',
                  cursor: 'pointer',
                  transition: 'all 150ms var(--ease-out)',
                  boxShadow: on ? '0 0 0 3px color-mix(in oklab, var(--field) 15%, transparent)' : 'none',
                }}
              >
                <span
                  className="mono"
                  style={{
                    fontSize: 9,
                    color: on ? 'var(--field)' : 'var(--text3)',
                    letterSpacing: '0.1em',
                  }}
                >
                  S{String(idx + 1).padStart(2, '0')}
                </span>
                <span style={{ fontSize: 12, fontWeight: on ? 700 : 600 }}>{s.label}</span>
              </button>
            );
          })}
        </div>
        {!isBAU && (
          <span
            className="mono"
            style={{
              fontSize: 9,
              letterSpacing: '0.08em',
              color: 'var(--field)',
              padding: '3px 7px',
              border: '1px solid var(--field)',
              borderRadius: 3,
              background: 'var(--field-tint)',
              whiteSpace: 'nowrap',
            }}
          >
            Δ vs STATUS QUO
          </span>
        )}
      </div>

      {/* Row 2b — Inline Custom sliders (only when Custom is picked) */}
      {isCustom && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 18,
            padding: '12px 14px',
            background: 'var(--surface2)',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--border)',
          }}
        >
          <Slider
            label="Pumping reduction"
            value={((custom.pumpDelta || 0) * -100).toFixed(0) + '%'}
            min={0}
            max={60}
            val={Math.round(-custom.pumpDelta * 100) || 0}
            onChange={(v) => onCustom({ ...custom, pumpDelta: -v / 100 })}
          />
          <Slider
            label="Corn → sorghum/wheat shift"
            value={((custom.cropShift || 0) * 100).toFixed(0) + '%'}
            min={0}
            max={50}
            val={Math.round((custom.cropShift || 0) * 100)}
            onChange={(v) => onCustom({ ...custom, cropShift: v / 100 })}
          />
          <Slider
            label="Recharge multiplier"
            value={'×' + (custom.rechargeMult || 1).toFixed(2)}
            min={100}
            max={200}
            val={Math.round((custom.rechargeMult || 1) * 100)}
            onChange={(v) => onCustom({ ...custom, rechargeMult: v / 100 })}
          />
        </div>
      )}

      {/* Row 3 — Visualization mode + color legend + source dots */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 20,
          flexWrap: 'wrap',
        }}
      >
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

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 260 }}>
          <div className="eyebrow" style={{ whiteSpace: 'nowrap' }}>
            {isBAU ? 'Sat. thickness (m)' : 'Δ thickness vs BAU'}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 2, flex: 1, maxWidth: 360 }}>
            {(isBAU ? THK_LEGEND : DELTA_LEGEND).map((x, i) => (
              <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
                <div style={{ width: '100%', height: 12, borderRadius: 2, background: x.c }} />
                <div className="mono" style={{ fontSize: 9, color: 'var(--text3)' }}>{x.l}</div>
              </div>
            ))}
          </div>
        </div>

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

function Slider({
  label,
  value,
  min,
  max,
  val,
  onChange,
}: {
  label: string;
  value: string;
  min: number;
  max: number;
  val: number;
  onChange: (v: number) => void;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <label className="eyebrow">{label}</label>
        <div className="stat" style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>
          {value}
        </div>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        value={val}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: '100%', accentColor: 'var(--field)' }}
      />
    </div>
  );
}
