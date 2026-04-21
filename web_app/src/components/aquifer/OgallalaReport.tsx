'use client';

import { useEffect, useMemo, useState } from 'react';
import AquiferHero from './AquiferHero';
import CountyMap from './CountyMap';
import MapTopBar from './MapTopBar';
import VerticalTimeScrubber from './VerticalTimeScrubber';
import CountyTrajectoryRow from './CountyTrajectoryRow';
import CountyProvenancePanel from './CountyProvenancePanel';
import ScenarioPanel from './ScenarioPanel';
import CountyDrill from './CountyDrill';
import Ranking from './Ranking';
import FeaturedStories from './FeaturedStories';
import MethodologyStrip from './MethodologyStrip';
import { useBaseline } from './useBaseline';
import { SCENARIOS, aggregate, depColor, fmt, thicknessAt } from './aquifer-math';
import type { MapMode, Scenario } from './types';

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

  // Only on-HPA counties are drill-targetable — off-aquifer rows have null
  // thickness and aren't part of the Ogallala narrative.
  const selectedC = selected ? counties.find((c) => c.fips === selected && c.onHpa) ?? null : null;

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
          display: 'flex',
          flexDirection: 'column',
          gap: 14,
        }}
      >
        {/* Toolbar above the map */}
        <MapTopBar
          agg={agg}
          totalCounties={counties.length}
          year={year}
          mode={mode}
          onMode={setMode}
        />

        {/* Slider | Map | Drill */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: '110px 1fr 340px',
            gap: 14,
            alignItems: 'stretch',
          }}
        >
          {counties.length > 0 ? (
            <VerticalTimeScrubber
              year={year}
              onYear={setYear}
              playing={playing}
              onPlay={() => setPlaying((p) => !p)}
              counties={counties}
              scenario={liveScenario}
            />
          ) : (
            <div
              style={{
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-lg)',
              }}
            />
          )}

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
            {/* Year badge — floats inside the map */}
            <div
              style={{
                position: 'absolute',
                top: 14,
                left: 14,
                zIndex: 2,
                background: 'rgba(255,255,255,0.88)',
                backdropFilter: 'blur(8px)',
                WebkitBackdropFilter: 'blur(8px)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                padding: '10px 14px',
                pointerEvents: 'none',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              <div className="eyebrow">§ 01 Live view</div>
              <div
                className="stat"
                style={{
                  fontSize: 42,
                  fontWeight: 900,
                  lineHeight: 1,
                  color: 'var(--field)',
                  letterSpacing: '-0.02em',
                  margin: '4px 0 6px',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {year}
              </div>
              <div
                className="mono"
                style={{
                  fontSize: 10,
                  letterSpacing: '0.12em',
                  color: 'var(--text2)',
                  padding: '3px 6px',
                  background: 'var(--surface2)',
                  borderRadius: 4,
                  display: 'inline-block',
                  border: '1px solid var(--border)',
                }}
              >
                SCENARIO: {liveScenario.label.toUpperCase()}
              </div>
            </div>

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
              if (!c || !c.onHpa) return null;
              const t = thicknessAt(c, year, liveScenario);
              const dclShown = c.dclP ?? c.dcl;
              const hasBand = c.dclLo != null && c.dclHi != null;
              const sourceLabel =
                c.tsrc === 'wells'    ? 'Measured · WIZARD/NGWMN/TWDB/NE DNR' :
                c.tsrc === 'raster'   ? 'USGS McGuire raster (SIR 2012-5177)' :
                c.tsrc === 'fallback' ? 'HPA-median fallback' :
                                        '—';
              return (
                <div
                  style={{
                    position: 'absolute', top: 16, right: 16,
                    background: 'var(--surface)',
                    border: '1px solid var(--border2)',
                    borderRadius: 'var(--radius-md)',
                    padding: '12px 14px', minWidth: 220,
                    boxShadow: 'var(--shadow-lg)',
                    pointerEvents: 'none',
                    zIndex: 3,
                  }}
                >
                  <div style={{ fontWeight: 700, fontSize: 14 }}>
                    {c.name} <span className="mono" style={{ color: 'var(--text3)', marginLeft: 6 }}>{c.state}</span>
                  </div>
                  <div className="stat" style={{ fontSize: 32, fontWeight: 800, margin: '4px 0 8px', color: depColor(t) }}>
                    {t.toFixed(1)} m
                  </div>
                  <TTRow label="decline" value={dclShown != null ? `${dclShown.toFixed(2)} m/yr` : '—'} />
                  {hasBand && c.dsrc === 'model' && (
                    <TTRow
                      label="80% band"
                      value={`[${(c.dclLo as number).toFixed(2)}, ${(c.dclHi as number).toFixed(2)}]`}
                    />
                  )}
                  <TTRow label="years→uneconomic" value={fmt.yr(c.yrsU)} />
                  <TTRow label="pumping" value={fmt.af(c.pmp)} />
                  <TTRow label="irr. acres" value={fmt.int(c.acres)} />
                  <div
                    className="mono"
                    style={{ marginTop: 6, paddingTop: 6, borderTop: '1px solid var(--border)', fontSize: 9, color: 'var(--text3)', letterSpacing: '0.08em', lineHeight: 1.5 }}
                  >
                    {sourceLabel}
                    {c.dsrc === 'model' && <span style={{ color: 'var(--field)' }}> · NB02 CatBoost pred</span>}
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
                <div className="stat" style={{ fontSize: 24, fontWeight: 800, color: 'var(--text)', marginTop: 8 }}>
                  Pick a county
                </div>
                <div style={{ fontSize: 12, color: 'var(--text2)', maxWidth: 260, margin: '6px auto' }}>
                  Click any county on the map — or a row in the leaderboard below — to see its thickness trajectory,
                  crop-mix attribution, and data provenance.
                </div>
                <div className="mono" style={{ fontSize: 10, color: 'var(--text3)', marginTop: 10, letterSpacing: '0.06em' }}>
                  Try <em style={{ fontStyle: 'normal', color: 'var(--text)', fontWeight: 600 }}>Sheridan KS</em> or <em style={{ fontStyle: 'normal', color: 'var(--text)', fontWeight: 600 }}>Dallam TX</em>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Below-map: trajectory + irrigated-acres row (full width, county-specific) */}
        {selectedC && (
          <CountyTrajectoryRow county={selectedC} year={year} scenario={liveScenario} />
        )}

        {/* Below-map: provenance (full width, county-specific) */}
        {selectedC && <CountyProvenancePanel county={selectedC} />}
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

function TTRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="mono" style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text2)', padding: '2px 0' }}>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  );
}
