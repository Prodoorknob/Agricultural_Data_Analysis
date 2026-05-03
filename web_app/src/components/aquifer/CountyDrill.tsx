'use client';

import type { CountyProps, Scenario } from './types';
import { STATES, cropMix, fmt } from './aquifer-math';
import WaterColumn from './WaterColumn';

interface Props {
  county: CountyProps;
  year: number;
  scenario: Scenario;
  onClose: () => void;
}

export default function CountyDrill({ county, year, scenario, onClose }: Props) {
  const crops = cropMix(county);
  const totalWater = crops.reduce((s, c) => s + c.waterAF, 0);

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
    <div data-drill-root style={{
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
      <div data-drill-section="header" style={{ position: 'relative' }}>
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

      {/* Aquifer water-column gauge — replaces the line trajectory. */}
      <WaterColumn county={county} year={year} scenario={scenario} />

      <div data-drill-section="cropmix">
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

      <div data-drill-section="economics">
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 4 }}>
          <div className="eyebrow">
            Baseline economics · {county.pmpSrc === 'kdwr_orr_metered' && county.pmpKdwrYear
              ? county.pmpKdwrYear
              : '2022'}
          </div>
          <PumpSourceChip src={county.pmpSrc} year={county.pmpKdwrYear} />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, padding: 12, background: 'var(--surface2)', borderRadius: 'var(--radius-sm)', marginTop: 8 }}>
          <Econ label="Irrigated acres" value={fmt.int(county.acres)} />
          <Econ label="Pumping" value={fmt.af(county.pmpDisplay)} />
          <Econ label="Ag value" value={fmt.usd(county.agv)} />
          <Econ label="$ per acre-foot" value={county.pmpDisplay ? '$' + Math.round(county.agv / county.pmpDisplay).toLocaleString() : '—'} />
          {county.pcost != null && (
            <>
              <Econ
                label="Pumping cost"
                value={`$${county.pcost.toFixed(2)}/AF`}
              />
              <Econ
                label="Net $ per AF"
                value={
                  county.pmpDisplay
                    ? '$' +
                      Math.max(0, Math.round(county.agv / county.pmpDisplay - county.pcost)).toLocaleString()
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
        <div data-drill-section="climate">
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
      <div data-drill-section="irrigation">
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
    </div>
  );
}

function PumpSourceChip({ src, year }: { src: CountyProps['pmpSrc']; year: number | null }) {
  const map: Record<CountyProps['pmpSrc'], { label: string; tone: string; tint: string }> = {
    kdwr_orr_metered:    { label: year ? `Metered · KDWR ${year}` : 'Metered · KDWR',  tone: 'var(--field)',   tint: 'var(--field-tint)' },
    usgs2015_water_use:  { label: 'USGS 2015 raster',                                  tone: 'var(--harvest)', tint: 'var(--harvest-tint)' },
    inferred_nass_iwms:  { label: 'Inferred · NASS × IWMS',                            tone: 'var(--text3)',   tint: 'var(--surface2)' },
  };
  const m = map[src];
  return (
    <span
      className="mono"
      style={{
        fontSize: 9, padding: '2px 6px', borderRadius: 3,
        color: m.tone, background: m.tint, border: `1px solid ${m.tone}`,
        textTransform: 'uppercase', letterSpacing: '0.08em', whiteSpace: 'nowrap',
      }}
    >
      {m.label}
    </span>
  );
}

function Econ({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div
        style={{
          fontSize: 10,
          color: 'var(--text3)',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          minHeight: 12,
        }}
      >
        {label}
      </div>
      <div className="mono" style={{ fontSize: 14, color: 'var(--text)', marginTop: 3, fontWeight: 700 }}>{value}</div>
    </div>
  );
}
