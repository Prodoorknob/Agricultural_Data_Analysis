'use client';

import { useState } from 'react';
import type { CountyProps, Scenario } from './types';
import { depColor, fmt, thicknessAt } from './aquifer-math';

type Tab = 'dry' | 'fast' | 'pump';

interface Props {
  counties: CountyProps[];
  scenario: Scenario;
  year: number;
  selected: string | null;
  onSelect: (fips: string) => void;
}

export default function Ranking({ counties, scenario, year, selected, onSelect }: Props) {
  const [tab, setTab] = useState<Tab>('dry');

  let sorted: Array<{ c: CountyProps; v: number }>;
  if (tab === 'dry') {
    sorted = counties.map((c) => ({ c, v: thicknessAt(c, year, scenario) })).sort((a, b) => a.v - b.v).slice(0, 10);
  } else if (tab === 'fast') {
    sorted = counties.map((c) => ({ c, v: c.dcl })).sort((a, b) => a.v - b.v).slice(0, 10);
  } else {
    sorted = counties.map((c) => ({ c, v: c.pmp || 0 })).sort((a, b) => b.v - a.v).slice(0, 10);
  }
  const maxV = Math.max(...sorted.map((s) => Math.abs(s.v)), 1);

  const formatV = (v: number) =>
    tab === 'dry' ? v.toFixed(1) + ' m' :
    tab === 'fast' ? v.toFixed(2) + ' m/yr' :
    fmt.af(v);

  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
      padding: 24,
    }}>
      <div style={{ marginBottom: 20 }}>
        <div className="eyebrow">§ 03 Accountability leaderboard</div>
        <div className="stat" style={{ fontSize: 28, fontWeight: 800, color: 'var(--text)', lineHeight: 1.1, marginTop: 6, letterSpacing: '-0.01em' }}>
          Who&apos;s closest to zero
        </div>
      </div>
      <div style={{
        display: 'flex', gap: 2, background: 'var(--surface2)',
        padding: 3, borderRadius: 'var(--radius-md)', marginBottom: 12,
      }}>
        {([['dry', '01', 'Thinnest remaining'], ['fast', '02', 'Fastest-declining'], ['pump', '03', 'Largest extractors']] as Array<[Tab, string, string]>).map(([k, n, label]) => {
          const on = tab === k;
          return (
            <button
              key={k}
              onClick={() => setTab(k)}
              style={{
                flex: 1, padding: 8, fontSize: 11,
                color: on ? 'var(--text)' : 'var(--text2)',
                background: on ? 'var(--surface)' : 'transparent',
                boxShadow: on ? 'var(--shadow-sm)' : 'none',
                borderRadius: 'var(--radius-sm)',
                display: 'flex', gap: 6, alignItems: 'center', justifyContent: 'center',
                border: 'none', cursor: 'pointer',
              }}
            >
              <span className="mono eyebrow" style={{ color: 'inherit' }}>{n}</span> {label}
            </button>
          );
        })}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {sorted.map((r, i) => {
          const c = r.c;
          const isSel = selected === c.fips;
          const thkNow = thicknessAt(c, year, scenario);
          const width =
            tab === 'dry' ? `${Math.min(100, (thkNow / 60) * 100)}%` :
            tab === 'fast' ? `${Math.min(100, (Math.abs(r.v) / 1) * 100)}%` :
            `${Math.min(100, (r.v / maxV) * 100)}%`;
          return (
            <button
              key={c.fips}
              onClick={() => onSelect(c.fips)}
              style={{
                display: 'grid', gridTemplateColumns: '28px 1.3fr 1fr auto',
                gap: 10, alignItems: 'center', padding: '10px 8px',
                borderBottom: '1px solid var(--border)', textAlign: 'left',
                transition: 'background 150ms var(--ease-out)',
                background: isSel ? 'var(--field-tint)' : 'transparent',
                border: 'none', cursor: 'pointer',
              }}
            >
              <div className="mono" style={{ fontSize: 11, color: 'var(--text3)' }}>{String(i + 1).padStart(2, '0')}</div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{c.name}</div>
                <div className="mono" style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: '0.08em' }}>
                  {c.state} · {c.dq === 'modeled_high' ? 'measured' : 'modeled'}
                </div>
              </div>
              <div>
                <div style={{ height: 6, background: 'var(--surface2)', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width, background: depColor(thkNow), transition: 'width 300ms var(--ease-out)' }} />
                </div>
              </div>
              <div className="stat" style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', textAlign: 'right' }}>
                {formatV(r.v)}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
