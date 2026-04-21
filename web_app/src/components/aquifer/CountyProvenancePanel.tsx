'use client';

import type { CountyProps } from './types';
import { useIrrigationHistory } from './useIrrigationHistory';

export default function CountyProvenancePanel({ county }: { county: CountyProps }) {
  const { data: irrHist } = useIrrigationHistory();
  const irrSeries = irrHist?.counties[county.fips] ?? null;

  return (
    <div
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        padding: '16px 20px',
      }}
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(160px, auto) 1fr',
          gap: 24,
          alignItems: 'start',
        }}
      >
        <div>
          <div className="eyebrow">§ 01c Provenance</div>
          <div style={{ fontSize: 12, color: 'var(--text2)', marginTop: 4, lineHeight: 1.5 }}>
            {county.name} <span className="mono" style={{ color: 'var(--text3)' }}>{county.state}</span> · FIPS {county.fips}
          </div>
        </div>
        <div>
          <div className="mono" style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            <Chip on={county.tsrc === 'wells'}>WIZARD / NGWMN / TWDB / NE DNR</Chip>
            <Chip on={county.tsrc === 'raster'}>USGS McGuire SIR 2012-5177</Chip>
            <Chip on={county.dsrc === 'model'}>NB02 CatBoost + conformal</Chip>
            <Chip on>NASS Census 2022</Chip>
            <Chip on>NASS IWMS 2018 · Table 28</Chip>
            <Chip on>ERS budgets 2024</Chip>
            <Chip on>eGRID 2022</Chip>
            <Chip on>NOAA nClimDiv (1895–2024)</Chip>
            <Chip on>EIA State Electricity Profiles</Chip>
            <Chip on={!!irrSeries}>Deines 2019 AIM-HPA (1984–2017)</Chip>
          </div>
          <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 10, lineHeight: 1.55 }}>
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
    </div>
  );
}

function Chip({ children, on }: { children: React.ReactNode; on?: boolean }) {
  return (
    <span
      style={{
        fontSize: 9,
        padding: '3px 7px',
        borderRadius: 3,
        background: on ? 'var(--field-tint)' : 'var(--surface2)',
        color: on ? 'var(--field)' : 'var(--text3)',
        border: `1px solid ${on ? 'var(--field)' : 'var(--border)'}`,
      }}
    >
      {children}
    </span>
  );
}
