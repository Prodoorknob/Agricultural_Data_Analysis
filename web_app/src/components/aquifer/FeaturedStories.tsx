'use client';

import type { CountyProps } from './types';
import { fmt } from './aquifer-math';

interface Props {
  counties: CountyProps[];
  onSelect: (fips: string) => void;
}

export default function FeaturedStories({ counties, onSelect }: Props) {
  const findBy = (state: string, ...names: string[]) => {
    for (const n of names) {
      const c = counties.find((c) => c.state === state && c.name.toUpperCase().includes(n.toUpperCase()));
      if (c) return c;
    }
    return null;
  };
  const sheridan = findBy('KS', 'SHERIDAN');
  const dallam = findBy('TX', 'DALLAM');
  const cherry = findBy('NE', 'CHERRY', 'HOLT', 'KEITH');

  const stories: Array<{
    c: CountyProps | null;
    title: string;
    kicker: string;
    chapeau: string;
    body: string;
    tag: string;
    color: string;
  }> = [
    {
      c: sheridan,
      title: 'Sheridan-6 LEMA',
      kicker: '§ 01',
      chapeau: 'The place that worked',
      body: 'In 2012, a few dozen Kansas farmers voted to cap their own pumping by 20 percent for five years. Water tables stabilized. Ag income held. The LEMA was renewed, then adopted by neighboring counties. The scenario engine models this outcome aquifer-wide.',
      tag: 'Policy success',
      color: 'var(--field)',
    },
    {
      c: dallam,
      title: 'Dallam County, TX',
      kicker: '§ 02',
      chapeau: 'The cautionary tale',
      body: 'Top-percentile extractor. Thickness at ~22 m, declining faster than half a meter a year. Texas rule of capture means no metered reporting — our numbers here are modeled, not observed. Economic life under status quo: ~12 years.',
      tag: 'Rule of capture',
      color: 'var(--soil)',
    },
    {
      c: cherry,
      title: 'The Nebraska exception',
      kicker: '§ 03',
      chapeau: 'Best-instrumented, slowest-declining',
      body: 'All 93 HPA counties in Nebraska carry real measurement-backed thickness. Regional decline median is ~−0.10 m/yr, a third of the HPA average. NRD-level governance explains most of it; sandhill recharge explains the rest.',
      tag: 'Governance',
      color: 'var(--sky)',
    },
  ];

  return (
    <section style={{ maxWidth: 1480, margin: '48px auto 0', padding: '0 4px' }}>
      <div style={{ marginBottom: 24 }}>
        <div className="eyebrow">§ 04 Featured stories</div>
        <div className="stat" style={{ fontSize: 48, fontWeight: 800, letterSpacing: '-0.02em', lineHeight: 1, marginTop: 6 }}>
          Three counties. Three futures.
        </div>
        <div style={{ fontSize: 14, color: 'var(--text2)', marginTop: 8, maxWidth: 560 }}>
          Open a story to jump the map, scrubber, and drill-down to that county&apos;s context.
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20 }}>
        {stories.map((s, i) =>
          s.c ? (
            <button
              key={i}
              onClick={() => s.c && onSelect(s.c.fips)}
              style={{
                textAlign: 'left', padding: '28px 28px 22px',
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderTop: `3px solid ${s.color}`,
                borderRadius: 'var(--radius-lg)',
                display: 'flex', flexDirection: 'column', gap: 12,
                transition: 'all 220ms var(--ease-out)',
                cursor: 'pointer',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'translateY(-2px)';
                e.currentTarget.style.boxShadow = 'var(--shadow-lg)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = '';
                e.currentTarget.style.boxShadow = '';
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <div className="eyebrow" style={{ color: s.color }}>{s.kicker}</div>
                <span className="mono" style={{ fontSize: 9, padding: '3px 8px', borderRadius: 3, background: 'var(--surface2)', color: 'var(--text2)', letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                  {s.tag}
                </span>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 600 }}>{s.chapeau}</div>
              <div className="stat" style={{ fontSize: 26, fontWeight: 800, color: 'var(--text)', letterSpacing: '-0.01em', lineHeight: 1.1 }}>
                {s.title}
              </div>
              <div style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.6, flex: 1 }}>{s.body}</div>
              <div style={{
                display: 'flex', gap: 12, alignItems: 'center', marginTop: 8,
                paddingTop: 14, borderTop: '1px solid var(--border)', flexWrap: 'wrap',
              }}>
                <Mini label="thk" value={s.c.thk != null ? `${s.c.thk.toFixed(0)}m` : '—'} />
                <Mini
                  label="decl"
                  value={(s.c.dclP ?? s.c.dcl) != null ? ((s.c.dclP ?? s.c.dcl) as number).toFixed(2) : '—'}
                  valueColor={((s.c.dclP ?? s.c.dcl) ?? 0) < -0.3 ? 'var(--negative)' : 'var(--text)'}
                />
                <Mini label="pmp" value={fmt.af(s.c.pmp)} />
                <span className="mono" style={{ fontSize: 10, color: s.color, marginLeft: 'auto', letterSpacing: '0.12em', fontWeight: 700 }}>OPEN →</span>
              </div>
            </button>
          ) : null,
        )}
      </div>
    </section>
  );
}

function Mini({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <span className="mono" style={{ fontSize: 10, display: 'flex', gap: 4, alignItems: 'baseline' }}>
      <span style={{ color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{label}</span>
      <span style={{ color: valueColor ?? 'var(--text)', fontWeight: 700, fontSize: 11 }}>{value}</span>
    </span>
  );
}
