'use client';

import { useState } from 'react';
import type { CountyProps, Scenario } from './types';
import { depColor, effectiveDecline, fmt, thicknessAt } from './aquifer-math';

type Tab = 'dry' | 'fast' | 'pump';

interface Props {
  counties: CountyProps[];
  scenario: Scenario;
  year: number;
  selected: string | null;
  onSelect: (fips: string) => void;
}

const TABS: Array<{ k: Tab; num: string; label: string; sub: string }> = [
  { k: 'dry', num: '01', label: 'Thinnest remaining', sub: 'sat. thickness · ascending' },
  { k: 'fast', num: '02', label: 'Fastest-declining', sub: 'annual decline · most negative' },
  { k: 'pump', num: '03', label: 'Largest extractors', sub: 'pumping · descending' },
];

export default function Ranking({ counties, scenario, year, selected, onSelect }: Props) {
  const [expanded, setExpanded] = useState<Record<Tab, boolean>>({ dry: false, fast: false, pump: false });

  const onHpa = counties.filter((c) => c.onHpa && c.thk != null);

  const sortedFor = (tab: Tab): Array<{ c: CountyProps; v: number }> => {
    if (tab === 'dry')  return onHpa.map((c) => ({ c, v: thicknessAt(c, year, scenario) })).sort((a, b) => a.v - b.v).slice(0, 10);
    if (tab === 'fast') return onHpa.map((c) => ({ c, v: effectiveDecline(c) })).sort((a, b) => a.v - b.v).slice(0, 10);
    return onHpa.map((c) => ({ c, v: c.pmp || 0 })).sort((a, b) => b.v - a.v).slice(0, 10);
  };

  const formatV = (tab: Tab, v: number) =>
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
        <div className="stat" style={{ fontSize: 26, fontWeight: 800, color: 'var(--text)', lineHeight: 1.1, marginTop: 6, letterSpacing: '-0.01em' }}>
          Who&apos;s closest to zero
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 16,
        }}
      >
        {TABS.map(({ k: tab, num, label, sub }) => {
          const fullList = sortedFor(tab);
          const isExpanded = expanded[tab];
          const visible = isExpanded ? fullList : fullList.slice(0, 5);
          const maxV = Math.max(...fullList.map((s) => Math.abs(s.v)), 1);

          return (
            <div
              key={tab}
              style={{
                display: 'flex',
                flexDirection: 'column',
                background: 'var(--surface2)',
                borderRadius: 'var(--radius-md)',
                padding: 14,
              }}
            >
              <div style={{ marginBottom: 10, paddingBottom: 8, borderBottom: '1px solid var(--border)' }}>
                <div
                  className="mono"
                  style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: '0.12em', marginBottom: 2 }}
                >
                  S{num}
                </div>
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', lineHeight: 1.2 }}>
                  {label}
                </div>
                <div className="mono" style={{ fontSize: 9, color: 'var(--text3)', marginTop: 2, letterSpacing: '0.06em' }}>
                  {sub}
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column' }}>
                {visible.map((r, i) => {
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
                        display: 'grid',
                        gridTemplateColumns: '22px 1fr auto',
                        gap: 8,
                        alignItems: 'center',
                        padding: '8px 6px',
                        borderBottom: '1px solid var(--border)',
                        textAlign: 'left',
                        transition: 'background 150ms var(--ease-out)',
                        background: isSel ? 'var(--field-tint)' : 'transparent',
                        border: 'none',
                        cursor: 'pointer',
                      }}
                    >
                      <div className="mono" style={{ fontSize: 10, color: 'var(--text3)' }}>
                        {String(i + 1).padStart(2, '0')}
                      </div>
                      <div>
                        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {c.name}
                        </div>
                        <div
                          className="mono"
                          style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: '0.06em', marginTop: 1 }}
                        >
                          {c.state} · {c.tsrc === 'wells' ? 'measured' : c.tsrc === 'raster' ? 'raster' : 'modeled'}
                        </div>
                        <div style={{ height: 4, marginTop: 4, background: 'var(--surface)', borderRadius: 2, overflow: 'hidden' }}>
                          <div
                            style={{
                              height: '100%',
                              width,
                              background: depColor(thkNow),
                              transition: 'width 300ms var(--ease-out)',
                            }}
                          />
                        </div>
                      </div>
                      <div
                        className="stat"
                        style={{ fontSize: 12, fontWeight: 700, color: 'var(--text)', textAlign: 'right', whiteSpace: 'nowrap' }}
                      >
                        {formatV(tab, r.v)}
                      </div>
                    </button>
                  );
                })}
              </div>

              {fullList.length > 5 && (
                <button
                  onClick={() => setExpanded((prev) => ({ ...prev, [tab]: !prev[tab] }))}
                  className="mono"
                  style={{
                    marginTop: 10,
                    padding: '6px 10px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border)',
                    background: 'transparent',
                    color: 'var(--text2)',
                    fontSize: 10,
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    cursor: 'pointer',
                    alignSelf: 'flex-start',
                  }}
                >
                  {isExpanded ? 'show top 5 ▴' : `show top 10 ▾`}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
