'use client';

import { useEffect, useMemo, useState } from 'react';
import AquiferHero from './AquiferHero';
import CountyMap from './CountyMap';
import TimeScrubber from './TimeScrubber';
import ScenarioPanel from './ScenarioPanel';
import CountyDrill from './CountyDrill';
import Ranking from './Ranking';
import FeaturedStories from './FeaturedStories';
import MethodologyStrip from './MethodologyStrip';
import { useBaseline } from './useBaseline';
import { SCENARIOS, aggregate, depColor, fmt, thicknessAt } from './aquifer-math';
import type { MapMode, Scenario } from './types';

const MODES: Array<{ k: MapMode; label: string; desc: string }> = [
  { k: 'columns', label: 'Columns', desc: 'Height = thickness' },
  { k: 'choropleth', label: 'Choropleth', desc: 'Color = thickness' },
  { k: 'dots', label: 'Bubbles', desc: 'Size = pumping' },
];

const DEFAULT_CUSTOM: Scenario = {
  id: 'custom',
  label: 'Custom',
  sub: 'your inputs',
  pumpDelta: -0.15,
  cropShift: 0.10,
  rechargeMult: 1.1,
  custom: true,
};

export default function OgallalaReport() {
  const { geo, counties, error } = useBaseline();
  const [year, setYear] = useState(2024);
  const [playing, setPlaying] = useState(false);
  const [scenario, setScenario] = useState<Scenario>(SCENARIOS[0]);
  const [customScenario, setCustomScenario] = useState<Scenario>(DEFAULT_CUSTOM);
  const [mode, setMode] = useState<MapMode>('columns');
  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  const liveScenario = useMemo(
    () => (scenario.custom ? { ...scenario, ...customScenario } : scenario),
    [scenario, customScenario],
  );

  // Autoplay loop
  useEffect(() => {
    if (!playing) return;
    const iv = window.setInterval(() => {
      setYear((y) => {
        if (y >= 2100) {
          setPlaying(false);
          return 2100;
        }
        return Math.min(2100, y + 1);
      });
    }, 60);
    return () => window.clearInterval(iv);
  }, [playing]);

  const selectedC = selected ? counties.find((c) => c.fips === selected) ?? null : null;

  const agg = useMemo(
    () => (counties.length ? aggregate(counties, liveScenario, year) : null),
    [counties, liveScenario, year],
  );

  const onSelectFips = (f: string | null) => {
    setSelected(f);
    if (f) {
      document.querySelector('#map-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  if (error) {
    return (
      <div style={{ padding: 40, background: 'var(--surface)', borderRadius: 12, color: 'var(--text2)' }}>
        Failed to load aquifer data: {error}
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <AquiferHero />

      {/* MAP SECTION */}
      <section
        id="map-section"
        style={{
          margin: '32px 0 0',
          display: 'grid',
          gridTemplateColumns: '260px 1fr 340px',
          gap: 16,
          alignItems: 'stretch',
        }}
      >
        {/* LEFT RAIL */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '16px 18px' }}>
            <div className="eyebrow">§ 01 Live view</div>
            <div
              className="stat"
              style={{ fontSize: 64, fontWeight: 900, lineHeight: 1, color: 'var(--field)', letterSpacing: '-0.02em', margin: '6px 0 8px' }}
            >
              {year}
            </div>
            <div
              className="mono"
              style={{
                fontSize: 10, letterSpacing: '0.12em', color: 'var(--text2)',
                padding: '5px 8px', background: 'var(--surface2)', borderRadius: 4,
                display: 'inline-block', border: '1px solid var(--border)',
              }}
            >
              SCENARIO: {liveScenario.label.toUpperCase()}
            </div>
          </div>

          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '14px 14px 16px' }}>
            <div className="eyebrow" style={{ marginBottom: 10 }}>Visualization</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {MODES.map((m) => {
                const on = mode === m.k;
                return (
                  <button
                    key={m.k}
                    onClick={() => setMode(m.k)}
                    style={{
                      textAlign: 'left', padding: '10px 12px',
                      borderRadius: 'var(--radius-md)',
                      border: `1px solid ${on ? 'var(--field)' : 'transparent'}`,
                      background: on ? 'var(--field-tint)' : 'transparent',
                      color: on ? 'var(--text)' : 'var(--text2)',
                      transition: 'all 150ms var(--ease-out)',
                      cursor: 'pointer',
                    }}
                  >
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{m.label}</div>
                    <div className="mono" style={{ fontSize: 10, color: 'var(--text3)', letterSpacing: '0.06em', marginTop: 2 }}>{m.desc}</div>
                  </button>
                );
              })}
            </div>
          </div>

          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 14 }}>
            <div className="eyebrow">Saturated thickness (m)</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 2, margin: '10px 0 8px' }}>
              {[
                { c: 'var(--dep-1)', l: '<5' },
                { c: 'var(--dep-3)', l: '10' },
                { c: 'var(--dep-5)', l: '25' },
                { c: 'var(--dep-7)', l: '55' },
                { c: 'var(--dep-9)', l: '100' },
                { c: 'var(--dep-10)', l: '150+' },
              ].map((x, i) => (
                <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
                  <div style={{ width: '100%', height: 16, borderRadius: 2, background: x.c }} />
                  <div className="mono" style={{ fontSize: 9, color: 'var(--text3)' }}>{x.l}</div>
                </div>
              ))}
            </div>
            <div className="mono" style={{ fontSize: 9, color: 'var(--text3)', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
              <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', marginRight: 4, background: 'rgba(255,255,255,0.5)', border: '1.5px solid var(--text)' }} />
              measured · <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', marginRight: 4, background: 'transparent', border: '1px dashed var(--text3)' }} />modeled fallback
            </div>
          </div>

          {agg && counties.length > 0 && (
            <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: 14 }}>
              <div className="eyebrow">Region aggregate · {year}</div>
              <KpiRow label="Mean thickness" value={(agg.totalThk / counties.length).toFixed(1)} unit="m" />
              <KpiRow
                label="Depleted counties"
                value={agg.countDepleted.toString()}
                valueColor={agg.countDepleted > 50 ? 'var(--negative)' : 'var(--text)'}
              />
              <KpiRow label="Pumping" value={fmt.af(agg.totalPmp)} unit="" />
              <KpiRow label="CO₂ footprint" value={agg.totalCO2.toFixed(1)} unit="Mt/yr" />
            </div>
          )}
        </div>

        {/* MAP STAGE */}
        <div
          style={{
            position: 'relative',
            background:
              'radial-gradient(ellipse at 50% 50%, oklch(0.98 0.008 150) 0%, oklch(0.92 0.01 150) 90%)',
            border: '1px solid var(--border2)',
            borderRadius: 'var(--radius-lg)',
            overflow: 'hidden',
            minHeight: 640,
          }}
        >
          {!geo && (
            <div style={{ padding: 40, color: 'var(--text3)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
              loading 606 HPA counties…
            </div>
          )}
          {geo && (
            <CountyMap
              geo={geo}
              year={year}
              scenario={liveScenario}
              mode={mode}
              selected={selected}
              hovered={hovered}
              onSelect={onSelectFips}
              onHover={setHovered}
            />
          )}
          {/* Floating hover tooltip */}
          {(() => {
            if (!hovered) return null;
            const c = counties.find((x) => x.fips === hovered);
            if (!c) return null;
            const t = thicknessAt(c, year, liveScenario);
            return (
              <div
                style={{
                  position: 'absolute', top: 16, right: 16,
                  background: 'var(--surface)',
                  border: '1px solid var(--border2)',
                  borderRadius: 'var(--radius-md)',
                  padding: '12px 14px', minWidth: 200,
                  boxShadow: 'var(--shadow-lg)',
                  pointerEvents: 'none',
                }}
              >
                <div style={{ fontWeight: 700, fontSize: 14 }}>
                  {c.name} <span className="mono" style={{ color: 'var(--text3)', marginLeft: 6 }}>{c.state}</span>
                </div>
                <div className="stat" style={{ fontSize: 32, fontWeight: 800, margin: '4px 0 8px', color: depColor(t) }}>
                  {t.toFixed(1)} m
                </div>
                <TTRow label="decline" value={`${c.dcl.toFixed(2)} m/yr`} />
                <TTRow label="pumping" value={fmt.af(c.pmp)} />
                <TTRow label="irr. acres" value={fmt.int(c.acres)} />
                <div
                  className="mono"
                  style={{ marginTop: 6, paddingTop: 6, borderTop: '1px solid var(--border)', fontSize: 9, color: 'var(--text3)', letterSpacing: '0.1em' }}
                >
                  {c.dq === 'modeled_high' ? '● measured' : '○ modeled'}
                </div>
              </div>
            );
          })()}
        </div>

        {/* RIGHT RAIL — drill-down */}
        <div>
          {selectedC ? (
            <CountyDrill county={selectedC} year={year} scenario={liveScenario} onClose={() => setSelected(null)} />
          ) : (
            <div
              style={{
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-lg)',
                padding: 20,
                display: 'flex', flexDirection: 'column', gap: 16,
                justifyContent: 'center', textAlign: 'center', alignItems: 'center',
                height: '100%',
              }}
            >
              <div className="eyebrow">§ 01b County drill-down</div>
              <div className="stat" style={{ fontSize: 28, fontWeight: 800, color: 'var(--text)', marginTop: 8 }}>
                Pick a county
              </div>
              <div style={{ fontSize: 12, color: 'var(--text2)', maxWidth: 260, margin: '6px auto' }}>
                Click any county on the map — or a row in the leaderboard below — to see its thickness trajectory,
                crop-mix attribution, and data provenance.
              </div>
              <div className="mono" style={{ fontSize: 10, color: 'var(--text3)', marginTop: 14, letterSpacing: '0.06em' }}>
                <span style={{ display: 'inline-block', width: 18, height: 18, borderRadius: 4, background: 'var(--surface2)', marginRight: 6, textAlign: 'center', lineHeight: '18px', border: '1px solid var(--border)', color: 'var(--text2)' }}>?</span>
                Try <em style={{ fontStyle: 'normal', color: 'var(--text)', fontWeight: 600 }}>Sheridan KS</em> or <em style={{ fontStyle: 'normal', color: 'var(--text)', fontWeight: 600 }}>Dallam TX</em>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* SCRUBBER */}
      <section style={{ margin: '16px 0 0' }}>
        {counties.length > 0 && (
          <TimeScrubber
            year={year}
            onYear={setYear}
            playing={playing}
            onPlay={() => setPlaying((p) => !p)}
            counties={counties}
            scenario={liveScenario}
          />
        )}
      </section>

      {/* SCENARIO ENGINE + RANKING */}
      <section style={{ margin: '32px 0 0', display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 16 }}>
        {counties.length > 0 && (
          <>
            <ScenarioPanel
              scenario={scenario}
              onScenario={setScenario}
              custom={customScenario}
              onCustom={setCustomScenario}
              counties={counties}
              year={year}
            />
            <Ranking
              counties={counties}
              scenario={liveScenario}
              year={year}
              selected={selected}
              onSelect={onSelectFips}
            />
          </>
        )}
      </section>

      {/* FEATURED STORIES */}
      {counties.length > 0 && <FeaturedStories counties={counties} onSelect={onSelectFips} />}

      {/* METHODOLOGY */}
      <MethodologyStrip countyCount={counties.length} />
    </div>
  );
}

function KpiRow({
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
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
      <div style={{ fontSize: 12, color: 'var(--text2)' }}>{label}</div>
      <div className="stat" style={{ fontSize: 22, fontWeight: 800, color: valueColor ?? 'var(--text)' }}>
        {value}
        {unit && <span style={{ fontSize: 11, color: 'var(--text3)', marginLeft: 3 }}>{unit}</span>}
      </div>
    </div>
  );
}

function TTRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="mono" style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text2)', padding: '2px 0' }}>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  );
}
