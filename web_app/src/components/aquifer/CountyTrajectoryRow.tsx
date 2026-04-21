'use client';

import type { CountyProps } from './types';
import { useIrrigationHistory } from './useIrrigationHistory';

interface Props {
  county: CountyProps;
}

/**
 * Full-width irrigated-acres timeline (Deines 2019 AIM-HPA) for the
 * selected county. The thickness trajectory has moved into the
 * right-rail drill-down; this wide space is now dedicated to the
 * Landsat-derived annual irrigation history.
 */
export default function CountyTrajectoryRow({ county }: Props) {
  const { data: irrHist } = useIrrigationHistory();
  const irrSeries = irrHist?.counties[county.fips] ?? null;

  if (!irrSeries || irrSeries.length < 4) return null;

  const minY = irrSeries[0][0];
  const maxY = irrSeries[irrSeries.length - 1][0];
  const vals = irrSeries.map((p) => p[1]);
  const maxAc = Math.max(...vals, 1);
  const first = vals[0];
  const last = vals[vals.length - 1];
  const changePct = first > 0 ? ((last - first) / first) * 100 : 0;

  const iw = 1200, ih = 160;
  const xOf = (yr: number) => ((yr - minY) / (maxY - minY)) * iw;
  const yOf = (ac: number) => ih - (ac / maxAc) * ih;
  const line = irrSeries
    .map(([yr, ac], i) => `${i === 0 ? 'M' : 'L'}${xOf(yr).toFixed(1)},${yOf(ac).toFixed(1)}`)
    .join(' ');
  const area =
    `M0,${ih} L${irrSeries.map(([yr, ac]) => `${xOf(yr).toFixed(1)},${yOf(ac).toFixed(1)}`).join(' L')} L${iw},${ih} Z`;

  return (
    <div
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        padding: '16px 20px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10, flexWrap: 'wrap', gap: 8 }}>
        <div>
          <div className="eyebrow">Irrigated acres · Deines 2019 AIM-HPA ({minY}–{maxY})</div>
          <div style={{ fontSize: 13, color: 'var(--text2)', marginTop: 2 }}>
            {county.name} <span className="mono" style={{ color: 'var(--text3)' }}>{county.state}</span>
            {' · '}Annual Landsat-derived irrigated area, 30 m binary classification
          </div>
        </div>
        <div
          className="mono"
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: changePct > 5 ? 'var(--field)' : changePct < -5 ? 'var(--negative)' : 'var(--text3)',
          }}
        >
          {changePct >= 0 ? '+' : ''}{changePct.toFixed(0)}% vs. {minY}
        </div>
      </div>
      <div style={{ background: 'var(--surface2)', borderRadius: 'var(--radius-sm)', padding: 8 }}>
        <svg viewBox={`0 0 ${iw} ${ih + 16}`} style={{ width: '100%', height: 'auto' }}>
          <path d={area} fill="var(--harvest-tint)" opacity="0.55" />
          <path d={line} fill="none" stroke="var(--harvest)" strokeWidth="1.8" />
          <text x="4" y="11" fontSize="10" fontFamily="var(--font-mono)" fill="var(--text3)">
            {(maxAc / 1000).toFixed(0)}k ac
          </text>
          <text x="4" y={ih - 3} fontSize="10" fontFamily="var(--font-mono)" fill="var(--text3)">0</text>
          <text x="4" y={ih + 13} fontSize="10" fontFamily="var(--font-mono)" fill="var(--text3)">{minY}</text>
          <text x={iw - 32} y={ih + 13} fontSize="10" fontFamily="var(--font-mono)" fill="var(--text3)">{maxY}</text>
        </svg>
      </div>
    </div>
  );
}
