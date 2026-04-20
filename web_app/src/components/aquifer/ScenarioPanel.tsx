'use client';

import type { CountyProps, Scenario } from './types';
import { SCENARIOS, aggregate, fmt } from './aquifer-math';

interface Props {
  scenario: Scenario;
  onScenario: (s: Scenario) => void;
  custom: Scenario;
  onCustom: (s: Scenario) => void;
  counties: CountyProps[];
  year: number;
}

export default function ScenarioPanel({ scenario, onScenario, custom, onCustom, counties, year }: Props) {
  const compare = aggregate(counties, SCENARIOS[0], year);
  const active = aggregate(counties, scenario, year);

  const delta = {
    ag: active.totalAg - compare.totalAg,
    co2: active.totalCO2 - compare.totalCO2,
  };

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
      padding: 24,
    }}>
      <div style={{ marginBottom: 20 }}>
        <div className="eyebrow">§ 02 Scenario engine</div>
        <div className="stat" style={{ fontSize: 28, fontWeight: 800, color: 'var(--text)', lineHeight: 1.1, marginTop: 6, letterSpacing: '-0.01em' }}>
          Counterfactual levers
        </div>
        <div style={{ fontSize: 13, color: 'var(--text2)', marginTop: 6, maxWidth: 600 }}>
          Every scenario re-runs the physics baseline from 1950 forward. Transparent math, reversible, deterministic.
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        {SCENARIOS.map((s, idx) => {
          const on = scenario.id === s.id;
          return (
            <button
              key={s.id}
              onClick={() => onScenario(s)}
              style={{
                textAlign: 'left',
                padding: '14px 16px',
                background: on ? 'color-mix(in oklab, var(--field) 10%, var(--surface))' : 'var(--surface2)',
                border: `1px solid ${on ? 'var(--field)' : 'var(--border)'}`,
                boxShadow: on ? '0 0 0 3px color-mix(in oklab, var(--field) 15%, transparent)' : 'none',
                borderRadius: 'var(--radius-md)',
                transition: 'all 180ms var(--ease-out)',
                display: 'flex', flexDirection: 'column', gap: 8,
                cursor: 'pointer',
              }}
            >
              <div className="mono" style={{ fontSize: 9, color: on ? 'var(--field)' : 'var(--text3)', letterSpacing: '0.12em' }}>
                S{String(idx + 1).padStart(2, '0')}
              </div>
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', lineHeight: 1.2 }}>{s.label}</div>
                <div style={{ fontSize: 11, color: 'var(--text2)', marginTop: 3 }}>{s.sub}</div>
              </div>
              <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 'auto' }}>
                {s.pumpDelta !== 0 && (
                  <span className="mono" style={{ fontSize: 9, padding: '2px 6px', borderRadius: 3, background: 'var(--sky-tint)', color: 'var(--sky)', letterSpacing: '0.04em' }}>
                    {(s.pumpDelta * 100).toFixed(0)}% pump
                  </span>
                )}
                {s.cropShift !== 0 && (
                  <span className="mono" style={{ fontSize: 9, padding: '2px 6px', borderRadius: 3, background: 'var(--harvest-tint)', color: 'var(--harvest-dark)', letterSpacing: '0.04em' }}>
                    {(s.cropShift * 100).toFixed(0)}% shift
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>

      {scenario.custom && (
        <div style={{
          marginTop: 16, padding: 16,
          background: 'var(--surface2)',
          borderRadius: 'var(--radius-md)',
          display: 'flex', flexDirection: 'column', gap: 12,
        }}>
          <div style={{ display: 'grid', gap: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label className="eyebrow">Pumping reduction</label>
              <div className="stat" style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>
                {((custom.pumpDelta || 0) * -100).toFixed(0)}%
              </div>
            </div>
            <input
              type="range" min={0} max={60}
              value={Math.round(-custom.pumpDelta * 100) || 0}
              onChange={(e) => onCustom({ ...custom, pumpDelta: -Number(e.target.value) / 100 })}
              style={{ width: '100%', accentColor: 'var(--field)' }}
            />
          </div>
          <div style={{ display: 'grid', gap: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label className="eyebrow">Corn → sorghum/wheat shift</label>
              <div className="stat" style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>
                {((custom.cropShift || 0) * 100).toFixed(0)}%
              </div>
            </div>
            <input
              type="range" min={0} max={50}
              value={Math.round((custom.cropShift || 0) * 100)}
              onChange={(e) => onCustom({ ...custom, cropShift: Number(e.target.value) / 100 })}
              style={{ width: '100%', accentColor: 'var(--field)' }}
            />
          </div>
          <div style={{ display: 'grid', gap: 6 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <label className="eyebrow">Recharge multiplier (cover crops)</label>
              <div className="stat" style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>
                ×{(custom.rechargeMult || 1).toFixed(2)}
              </div>
            </div>
            <input
              type="range" min={100} max={200}
              value={Math.round((custom.rechargeMult || 1) * 100)}
              onChange={(e) => onCustom({ ...custom, rechargeMult: Number(e.target.value) / 100 })}
              style={{ width: '100%', accentColor: 'var(--field)' }}
            />
          </div>
        </div>
      )}

      {/* Impact readout */}
      <div style={{
        marginTop: 20, padding: '18px 20px',
        background: 'color-mix(in oklab, var(--field) 4%, var(--surface2))',
        border: '1px solid var(--border)',
        borderLeft: '3px solid var(--field)',
        borderRadius: 'var(--radius-md)',
      }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>Impact vs. Status Quo · year {year}</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
          <Cell
            label="Counties below 5m threshold"
            value={active.countDepleted.toString()}
            delta={active.countDepleted === compare.countDepleted ? '—' : `${active.countDepleted < compare.countDepleted ? '−' : '+'}${Math.abs(active.countDepleted - compare.countDepleted)}`}
            valueColor={active.countDepleted < compare.countDepleted ? 'var(--positive)' : active.countDepleted > compare.countDepleted ? 'var(--negative)' : 'var(--text)'}
          />
          <Cell
            label="Ag value / year"
            value={fmt.usd(active.totalAg)}
            delta={delta.ag === 0 ? '—' : (delta.ag > 0 ? '+' : '−') + fmt.usd(Math.abs(delta.ag))}
            deltaColor={delta.ag < 0 ? 'var(--negative)' : 'var(--positive)'}
          />
          <Cell
            label="Pumping CO₂ · Mt/yr"
            value={active.totalCO2.toFixed(1)}
            delta={delta.co2 === 0 ? '—' : (delta.co2 > 0 ? '+' : '−') + Math.abs(delta.co2).toFixed(1)}
            deltaColor={delta.co2 < 0 ? 'var(--positive)' : 'var(--negative)'}
            noBorder
          />
        </div>
      </div>
    </div>
  );
}

function Cell({ label, value, delta, valueColor, deltaColor, noBorder }: {
  label: string;
  value: string;
  delta: string;
  valueColor?: string;
  deltaColor?: string;
  noBorder?: boolean;
}) {
  return (
    <div style={{ borderRight: noBorder ? 'none' : '1px solid var(--border)', paddingRight: 12 }}>
      <div style={{ fontSize: 11, color: 'var(--text3)', marginBottom: 4 }}>{label}</div>
      <div className="stat" style={{ fontSize: 28, fontWeight: 800, color: valueColor ?? 'var(--text)', lineHeight: 1, display: 'flex', alignItems: 'baseline', gap: 8 }}>
        {value}
        <span className="mono" style={{ fontSize: 11, fontWeight: 700, color: deltaColor }}>{delta}</span>
      </div>
    </div>
  );
}
