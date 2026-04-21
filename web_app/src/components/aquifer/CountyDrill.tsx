'use client';

import type { CountyProps, Scenario } from './types';
import { STATES, cropMix, depColor, effectiveDecline, fmt, thicknessAt, SCENARIOS } from './aquifer-math';

interface Props {
  county: CountyProps;
  year: number;
  scenario: Scenario;
  onClose: () => void;
}

export default function CountyDrill({ county, year, scenario, onClose }: Props) {
  const thkNow = thicknessAt(county, year, scenario);
  const dclEff = effectiveDecline(county);
  const hasModelBand = county.dclLo != null && county.dclHi != null && county.dsrc === 'model';

  // Server-computed years-until-uneconomic with conformal band (preferred),
  // else a local estimate from the current decline rate.
  const yrsUi =
    county.yrsU != null
      ? county.yrsU
      : dclEff < 0 && county.thk != null
        ? Math.max(0, (Math.max(0, county.thk) - 9) / -dclEff)
        : 999;
  const yrsULo = county.yrsULo ?? null;
  const yrsUHi = county.yrsUHi ?? null;

  const crops = cropMix(county);
  const totalWater = crops.reduce((s, c) => s + c.waterAF, 0);

  const curve: Array<{ y: number; t: number; tbau: number }> = [];
  for (let y = 1950; y <= 2100; y += 2) {
    curve.push({
      y,
      t: thicknessAt(county, y, scenario),
      tbau: thicknessAt(county, y, SCENARIOS[0]),
    });
  }
  const maxT = Math.max(...curve.map((d) => Math.max(d.t, d.tbau)), (county.thk ?? 0) * 1.1, 10);
  const cw = 380, ch = 110;
  const curvePath = (key: 't' | 'tbau') =>
    curve
      .map((d, i) => {
        const x = (i / (curve.length - 1)) * cw;
        const yv = ch - (Math.max(0, d[key]) / maxT) * ch;
        return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${yv.toFixed(1)}`;
      })
      .join(' ');
  const yearIdx = (year - 1950) / 2;
  const yearX = (yearIdx / (curve.length - 1)) * cw;

  // Source-colored chip style based on thickness provenance.
  const srcTagStyle =
    county.tsrc === 'wells'    ? { background: 'var(--field-tint)',   color: 'var(--field)',   border: '1px solid var(--field)' } :
    county.tsrc === 'raster'   ? { background: 'var(--harvest-tint)', color: 'var(--harvest)', border: '1px solid var(--harvest)' } :
                                 { background: 'var(--surface2)',     color: 'var(--text3)',   border: '1px solid var(--border)' };
  const srcLabel =
    county.tsrc === 'wells'    ? 'Measured' :
    county.tsrc === 'raster'   ? 'USGS raster' :
    county.tsrc === 'fallback' ? 'Fallback' :
                                 'No data';

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
      padding: 20, position: 'relative',
      display: 'flex', flexDirection: 'column', gap: 16,
      maxHeight: '100%', overflowY: 'auto',
    }}>
      <button
        onClick={onClose}
        aria-label="close"
        style={{
          position: 'absolute', top: 10, right: 12, width: 28, height: 28,
          borderRadius: '50%', fontSize: 18, color: 'var(--text3)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'none', border: 'none', cursor: 'pointer',
        }}
      >
        ×
      </button>
      <div style={{ position: 'relative' }}>
        <div className="eyebrow">{STATES[county.state]?.name || county.state} · FIPS {county.fips}</div>
        <div className="stat" style={{ fontSize: 32, fontWeight: 800, lineHeight: 1, margin: '6px 0', letterSpacing: '-0.01em', color: 'var(--text)' }}>
          {county.name}
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 2 }}>
          <div
            className="mono"
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              fontSize: 10, padding: '3px 8px', borderRadius: 3, letterSpacing: '0.1em',
              textTransform: 'uppercase',
              ...srcTagStyle,
            }}
          >
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'currentColor' }} />
            {srcLabel}
          </div>
          {county.dsrc === 'model' && (
            <div
              className="mono"
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                fontSize: 10, padding: '3px 8px', borderRadius: 3, letterSpacing: '0.1em',
                textTransform: 'uppercase',
                background: 'var(--field-tint)', color: 'var(--field)', border: '1px solid var(--field)',
              }}
            >
              NB02 · CatBoost
            </div>
          )}
          <div
            className="mono"
            style={{
              display: 'inline-flex', alignItems: 'center',
              fontSize: 10, padding: '3px 8px', borderRadius: 3, letterSpacing: '0.1em',
              color: 'var(--text3)', border: '1px solid var(--border)',
            }}
          >
            HPA overlap {(county.hpa * 100).toFixed(0)}%
          </div>
        </div>
      </div>

      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8,
        padding: 14, background: 'var(--surface2)', borderRadius: 'var(--radius-md)',
      }}>
        <div>
          <div className="eyebrow">Saturated thickness</div>
          <div className="stat" style={{ fontSize: 26, fontWeight: 800, lineHeight: 1, marginTop: 4, color: depColor(thkNow) }}>
            {thkNow.toFixed(1)}<span style={{ fontSize: 11, color: 'var(--text3)', marginLeft: 3, fontWeight: 500 }}>m</span>
          </div>
        </div>
        <div>
          <div className="eyebrow">Annual decline</div>
          <div className="stat" style={{ fontSize: 26, fontWeight: 800, lineHeight: 1, marginTop: 4, color: dclEff < -0.5 ? 'var(--negative)' : 'var(--text)' }}>
            {dclEff > 0 ? '+' : ''}{dclEff.toFixed(2)}<span style={{ fontSize: 11, color: 'var(--text3)', marginLeft: 3, fontWeight: 500 }}>m/yr</span>
          </div>
          {hasModelBand && (
            <div className="mono" style={{ fontSize: 9, color: 'var(--text3)', marginTop: 2 }}>
              80% CI [{(county.dclLo as number).toFixed(2)}, {(county.dclHi as number).toFixed(2)}]
            </div>
          )}
        </div>
        <div>
          <div className="eyebrow">Years-to-uneconomic</div>
          <div className="stat" style={{ fontSize: 26, fontWeight: 800, lineHeight: 1, marginTop: 4, color: 'var(--text)' }}>
            {yrsUi >= 999 ? '∞' : Math.round(yrsUi)}<span style={{ fontSize: 11, color: 'var(--text3)', marginLeft: 3, fontWeight: 500 }}>yr</span>
          </div>
          {yrsULo != null && yrsUHi != null && yrsULo !== yrsUHi && (
            <div className="mono" style={{ fontSize: 9, color: 'var(--text3)', marginTop: 2 }}>
              [{fmt.yr(yrsULo)}, {fmt.yr(yrsUHi)}]
            </div>
          )}
        </div>
      </div>

      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
          <div className="eyebrow">Thickness trajectory · 1950 → 2100</div>
          <div className="mono" style={{ fontSize: 9, color: 'var(--text3)', display: 'flex', gap: 10, alignItems: 'center' }}>
            <span style={{ display: 'inline-block', width: 8, height: 2, marginRight: 4, verticalAlign: 'middle', background: 'var(--text3)' }} />BAU
            <span style={{ display: 'inline-block', width: 8, height: 2, marginRight: 4, verticalAlign: 'middle', background: 'var(--field)' }} />{scenario.label.split(' ')[0]}
          </div>
        </div>
        <div style={{ background: 'var(--surface2)', borderRadius: 'var(--radius-sm)', padding: 6 }}>
          <svg viewBox={`0 0 ${cw} ${ch + 14}`} style={{ width: '100%' }}>
            <path d={curvePath('tbau')} fill="none" stroke="var(--text3)" strokeWidth="1" strokeDasharray="3 3" />
            <path d={curvePath('t')} fill="none" stroke="var(--field)" strokeWidth="2" />
            <line x1="0" y1={ch - (9 / maxT) * ch} x2={cw} y2={ch - (9 / maxT) * ch} stroke="var(--negative)" strokeDasharray="2 2" strokeWidth="0.8" opacity="0.6" />
            <text x="2" y={ch - (9 / maxT) * ch - 2} fontSize="8" fontFamily="var(--font-mono)" fill="var(--negative)">uneconomic (9 m · Deines 2019)</text>
            <line x1={yearX} y1="0" x2={yearX} y2={ch} stroke="var(--text)" strokeWidth="1" />
            <circle cx={yearX} cy={ch - (Math.max(0, thkNow) / maxT) * ch} r="3" fill="var(--field)" stroke="var(--bg)" strokeWidth="1.5" />
            <text x="2" y="10" fontSize="9" fontFamily="var(--font-mono)" fill="var(--text3)">{maxT.toFixed(0)}m</text>
            <text x="2" y={ch - 2} fontSize="9" fontFamily="var(--font-mono)" fill="var(--text3)">0</text>
          </svg>
        </div>
      </div>

      <div>
        <div className="eyebrow">Who&apos;s drawing the water · {year <= 2024 ? 'measured' : 'baseline crop mix'}</div>
        {crops.length === 0 ? (
          <div className="mono" style={{ fontSize: 11, color: 'var(--text3)', padding: 20, textAlign: 'center', background: 'var(--surface2)', borderRadius: 'var(--radius-sm)', marginTop: 8 }}>
            No irrigated acreage reported
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', height: 22, borderRadius: 4, overflow: 'hidden', background: 'var(--surface2)', marginTop: 8, marginBottom: 10 }}>
              {crops.map((c) => (
                <div
                  key={c.key}
                  title={`${c.label}: ${(100 * c.waterAF / totalWater).toFixed(0)}% of water`}
                  style={{ width: `${(c.waterAF / totalWater) * 100}%`, height: '100%', background: c.color, transition: 'width 250ms var(--ease-out)' }}
                />
              ))}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {crops.map((c) => (
                <div
                  key={c.key}
                  style={{
                    display: 'grid', gridTemplateColumns: '10px 1fr auto auto 30px',
                    gap: 8, alignItems: 'center', fontSize: 11,
                    padding: '4px 0', borderBottom: '1px solid var(--border)',
                  }}
                >
                  <span style={{ width: 10, height: 10, borderRadius: 2, background: c.color }} />
                  <span style={{ color: 'var(--text)', fontWeight: 500 }}>{c.label}</span>
                  <span className="mono" style={{ fontSize: 10, color: 'var(--text3)' }}>{fmt.num(c.acres)} ac</span>
                  <span className="mono" style={{ fontSize: 10, color: 'var(--text3)' }}>{fmt.af(c.waterAF)}</span>
                  <span className="mono" style={{ textAlign: 'right', color: 'var(--text2)', fontWeight: 600, fontSize: 10 }}>
                    {((c.waterAF / totalWater) * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      <div>
        <div className="eyebrow">Baseline economics · 2022</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, padding: 12, background: 'var(--surface2)', borderRadius: 'var(--radius-sm)', marginTop: 8 }}>
          <Econ label="Irrigated acres" value={fmt.int(county.acres)} />
          <Econ label="Pumping" value={fmt.af(county.pmp)} />
          <Econ label="Ag value" value={fmt.usd(county.agv)} />
          <Econ label="$ per acre-foot" value={county.pmp ? '$' + Math.round(county.agv / county.pmp).toLocaleString() : '—'} />
          {county.pcost != null && (
            <>
              <Econ
                label="Pumping cost"
                value={`$${county.pcost.toFixed(2)}/AF`}
              />
              <Econ
                label="Net $ per AF"
                value={
                  county.pmp
                    ? '$' +
                      Math.max(0, Math.round(county.agv / county.pmp - county.pcost)).toLocaleString()
                    : '—'
                }
              />
            </>
          )}
        </div>
        {county.pcost != null && (
          <div className="mono" style={{ fontSize: 9, color: 'var(--text3)', marginTop: 6, lineHeight: 1.5 }}>
            electricity {county.ekwh?.toFixed(1)}¢/kWh (EIA state profile) × {county.kwh.toFixed(0)} kWh/AF pumping intensity
          </div>
        )}
      </div>

      {/* Climate — NOAA nClimDiv 1991-2020 normal vs 2019-2023 recent */}
      {county.pnorm != null && (
        <div>
          <div className="eyebrow">Climate · NOAA nClimDiv</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, padding: 12, background: 'var(--surface2)', borderRadius: 'var(--radius-sm)', marginTop: 8 }}>
            <Econ label="30-yr normal" value={`${county.pnorm.toFixed(0)} mm/yr`} />
            <Econ label="Recent 5-yr" value={county.prec != null ? `${county.prec.toFixed(0)} mm/yr` : '—'} />
            <Econ
              label="Anomaly"
              value={county.panom != null ? `${county.panom > 0 ? '+' : ''}${county.panom.toFixed(1)}%` : '—'}
            />
          </div>
          <div className="mono" style={{ fontSize: 9, color: 'var(--text3)', marginTop: 6, lineHeight: 1.5 }}>
            Normal window 1991–2020; recent window 2019–2023 (NOAA NCEI Climate Division dataset, per-county).
          </div>
        </div>
      )}

      {/* Irrigation method mix — IWMS 2018 per-state shares */}
      <div>
        <div className="eyebrow">Irrigation method mix · IWMS 2018 (state avg)</div>
        <div style={{ display: 'flex', height: 18, borderRadius: 4, overflow: 'hidden', background: 'var(--surface2)', marginTop: 8, marginBottom: 6 }}>
          <div title={`Center pivot ${(county.mPivot * 100).toFixed(0)}%`} style={{ width: `${county.mPivot * 100}%`, background: 'var(--field)' }} />
          <div title={`Flood / gravity ${(county.mFlood * 100).toFixed(0)}%`} style={{ width: `${county.mFlood * 100}%`, background: 'var(--harvest)' }} />
          <div title={`Drip / micro ${(county.mDrip * 100).toFixed(0)}%`} style={{ width: `${county.mDrip * 100}%`, background: 'var(--sky)' }} />
          <div title={`Dryland ${(county.mDry * 100).toFixed(0)}%`} style={{ width: `${county.mDry * 100}%`, background: 'var(--border2)' }} />
        </div>
        <div className="mono" style={{ fontSize: 9, color: 'var(--text3)', display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <span>● pivot {(county.mPivot * 100).toFixed(0)}%</span>
          <span>● flood {(county.mFlood * 100).toFixed(0)}%</span>
          <span>● drip {(county.mDrip * 100).toFixed(0)}%</span>
          <span>● dryland {(county.mDry * 100).toFixed(0)}%</span>
        </div>
      </div>

      <div style={{ paddingTop: 12, borderTop: '1px dashed var(--border2)' }}>
        <div className="eyebrow" style={{ marginBottom: 8 }}>Provenance</div>
        <div className="mono" style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          <Chip on={county.tsrc === 'wells'}>WIZARD / NGWMN / TWDB / NE DNR</Chip>
          <Chip on={county.tsrc === 'raster'}>USGS McGuire SIR 2012-5177</Chip>
          <Chip on={county.dsrc === 'model'}>NB02 CatBoost + conformal</Chip>
          <Chip on>NASS Census 2022</Chip>
          <Chip on>NASS IWMS 2018 · Table 28</Chip>
          <Chip on>ERS budgets 2024</Chip>
          <Chip on>eGRID 2022</Chip>
          <Chip on>NOAA nClimDiv (1895–2024)</Chip>
          <Chip on>EIA State Electricity Profiles</Chip>
        </div>
        <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 8, lineHeight: 1.55 }}>
          {county.tsrc === 'wells' && 'Thickness + decline derived from monitoring wells (WIZARD / NGWMN / TWDB / NE DNR).'}
          {county.tsrc === 'raster' && 'Thickness sampled from the USGS McGuire HPA raster (SIR 2012-5177, 2009); decline from the water-level-change raster (SIR 2012-5291, predev→2011 / 61 yrs).'}
          {county.tsrc === 'fallback' && 'HPA-median fallback applied (thickness 30 m, decline −0.3 m/yr). Rare — occurs only when no well or raster source reaches the county.'}
          {county.dsrc === 'model' && (
            <>
              <br />Next-year thickness forecast from NB02 (CatBoost, spatial-CV R² ≈ 0.93 on the TWDB + KGS WIZARD panel). 80% conformal bands via Romano et al. 2019 (CQR).
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function Econ({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{label}</div>
      <div className="mono" style={{ fontSize: 14, color: 'var(--text)', marginTop: 2, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

function Chip({ children, on }: { children: React.ReactNode; on?: boolean }) {
  return (
    <span
      style={{
        fontSize: 9, padding: '3px 7px', borderRadius: 3,
        background: on ? 'var(--field-tint)' : 'var(--surface2)',
        color: on ? 'var(--field)' : 'var(--text3)',
        border: `1px solid ${on ? 'var(--field)' : 'var(--border)'}`,
      }}
    >
      {children}
    </span>
  );
}
