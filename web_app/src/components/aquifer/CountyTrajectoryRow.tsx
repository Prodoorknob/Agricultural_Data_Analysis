'use client';

import type { CountyProps, Scenario } from './types';
import { SCENARIOS, thicknessAt } from './aquifer-math';
import { useIrrigationHistory } from './useIrrigationHistory';

interface Props {
  county: CountyProps;
  year: number;
  scenario: Scenario;
}

export default function CountyTrajectoryRow({ county, year, scenario }: Props) {
  const { data: irrHist } = useIrrigationHistory();
  const irrSeries = irrHist?.counties[county.fips] ?? null;

  // Thickness trajectory curve.
  const curve: Array<{ y: number; t: number; tbau: number }> = [];
  for (let y = 1950; y <= 2100; y += 2) {
    curve.push({
      y,
      t: thicknessAt(county, y, scenario),
      tbau: thicknessAt(county, y, SCENARIOS[0]),
    });
  }
  const thkNow = thicknessAt(county, year, scenario);
  const maxT = Math.max(...curve.map((d) => Math.max(d.t, d.tbau)), (county.thk ?? 0) * 1.1, 10);
  const cw = 760, ch = 180;
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

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: irrSeries && irrSeries.length > 3 ? '1.4fr 1fr' : '1fr',
        gap: 16,
      }}
    >
      {/* Thickness trajectory */}
      <div
        style={{
          background: 'var(--surface)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          padding: '16px 18px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
          <div>
            <div className="eyebrow">Thickness trajectory · 1950 → 2100</div>
            <div style={{ fontSize: 13, color: 'var(--text2)', marginTop: 2 }}>
              {county.name} <span className="mono" style={{ color: 'var(--text3)' }}>{county.state}</span>
            </div>
          </div>
          <div className="mono" style={{ fontSize: 10, color: 'var(--text3)', display: 'flex', gap: 14, alignItems: 'center' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <span style={{ display: 'inline-block', width: 12, height: 2, background: 'var(--text3)' }} />
              BAU
            </span>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <span style={{ display: 'inline-block', width: 12, height: 2, background: 'var(--field)' }} />
              {scenario.label.split(' ')[0]}
            </span>
          </div>
        </div>
        <div style={{ background: 'var(--surface2)', borderRadius: 'var(--radius-sm)', padding: 8 }}>
          <svg viewBox={`0 0 ${cw} ${ch + 16}`} style={{ width: '100%', height: 'auto' }}>
            <path d={curvePath('tbau')} fill="none" stroke="var(--text3)" strokeWidth="1.2" strokeDasharray="3 3" />
            <path d={curvePath('t')} fill="none" stroke="var(--field)" strokeWidth="2.2" />
            <line
              x1="0"
              y1={ch - (9 / maxT) * ch}
              x2={cw}
              y2={ch - (9 / maxT) * ch}
              stroke="var(--negative)"
              strokeDasharray="3 3"
              strokeWidth="1"
              opacity="0.6"
            />
            <text x="4" y={ch - (9 / maxT) * ch - 3} fontSize="9" fontFamily="var(--font-mono)" fill="var(--negative)">
              uneconomic threshold (9 m · Deines 2019)
            </text>
            <line x1={yearX} y1="0" x2={yearX} y2={ch} stroke="var(--text)" strokeWidth="1.2" />
            <circle
              cx={yearX}
              cy={ch - (Math.max(0, thkNow) / maxT) * ch}
              r="4"
              fill="var(--field)"
              stroke="var(--bg)"
              strokeWidth="1.5"
            />
            <text x="4" y="11" fontSize="10" fontFamily="var(--font-mono)" fill="var(--text3)">{maxT.toFixed(0)}m</text>
            <text x="4" y={ch - 3} fontSize="10" fontFamily="var(--font-mono)" fill="var(--text3)">0</text>
            <text x="4" y={ch + 13} fontSize="10" fontFamily="var(--font-mono)" fill="var(--text3)">1950</text>
            <text x={cw - 32} y={ch + 13} fontSize="10" fontFamily="var(--font-mono)" fill="var(--text3)">2100</text>
          </svg>
        </div>
      </div>

      {/* Irrigated acres — Deines 2019 AIM-HPA */}
      {irrSeries && irrSeries.length > 3 && (() => {
        const minY = irrSeries[0][0];
        const maxY = irrSeries[irrSeries.length - 1][0];
        const vals = irrSeries.map((p) => p[1]);
        const maxAc = Math.max(...vals, 1);
        const first = vals[0];
        const last = vals[vals.length - 1];
        const changePct = first > 0 ? ((last - first) / first) * 100 : 0;
        const iw = 500, ih = 150;
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
              padding: '16px 18px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
              <div>
                <div className="eyebrow">Irrigated acres · Deines 2019 ({minY}–{maxY})</div>
                <div style={{ fontSize: 12, color: 'var(--text2)', marginTop: 2 }}>
                  Annual Landsat-derived irrigated area, 30 m binary classification
                </div>
              </div>
              <div
                className="mono"
                style={{
                  fontSize: 11,
                  color: changePct > 5 ? 'var(--field)' : changePct < -5 ? 'var(--negative)' : 'var(--text3)',
                  fontWeight: 700,
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
      })()}
    </div>
  );
}
