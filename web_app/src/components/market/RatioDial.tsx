'use client';

import Term from '@/components/shared/Term';

interface RatioDialProps {
  ratio: number;
  tenYearMin: number;
  tenYearMax: number;
  percentile: number;
  zone: 'soy_favored' | 'balanced' | 'corn_favored';
}

export default function RatioDial({
  ratio,
  tenYearMin,
  tenYearMax,
  percentile,
  zone,
}: RatioDialProps) {
  const zoneLabel = zone === 'soy_favored' ? 'Soy favored' : zone === 'corn_favored' ? 'Corn favored' : 'Balanced';
  const zoneColor = zone === 'soy_favored' ? 'var(--soil)' : zone === 'corn_favored' ? 'var(--harvest)' : 'var(--text3)';

  // Position on the gauge (0-100%)
  const range = tenYearMax - tenYearMin || 1;
  const position = Math.min(Math.max(((ratio - tenYearMin) / range) * 100, 0), 100);

  return (
    <div
      className="p-5 rounded-[var(--radius-lg)] border flex-1"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
    >
      <p className="text-[11px] font-bold tracking-[0.1em] uppercase mb-3"
        style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
        <Term term="corn/soy ratio">Corn/Soy Ratio</Term>
      </p>

      {/* Big number */}
      <span
        style={{
          fontFamily: 'var(--font-stat)',
          fontSize: '48px',
          fontWeight: 900,
          lineHeight: 0.95,
          color: zoneColor,
        }}
      >
        {ratio.toFixed(2)}
      </span>

      {/* Gauge */}
      <div className="mt-4 relative">
        <div className="flex h-3 rounded-full overflow-hidden" style={{ background: 'var(--surface2)' }}>
          <div className="h-full" style={{ width: '33%', background: 'var(--soil-subtle)' }} />
          <div className="h-full" style={{ width: '34%', background: 'var(--surface2)' }} />
          <div className="h-full" style={{ width: '33%', background: 'var(--harvest-subtle)' }} />
        </div>
        {/* Marker */}
        <div
          className="absolute top-0 w-0.5 h-3 rounded-full"
          style={{
            left: `${position}%`,
            background: 'var(--text)',
            transform: 'translateX(-50%)',
          }}
        />
        {/* Labels */}
        <div className="flex justify-between mt-1">
          <span className="text-[9px]" style={{ color: 'var(--soil)', fontFamily: 'var(--font-mono)' }}>&lt;2.2 Soy</span>
          <span className="text-[9px]" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>Balanced</span>
          <span className="text-[9px]" style={{ color: 'var(--harvest)', fontFamily: 'var(--font-mono)' }}>&gt;2.5 Corn</span>
        </div>
      </div>

      <p className="mt-3 text-[13px]" style={{ color: 'var(--text2)' }}>
        At {ratio.toFixed(2)} the ratio is in the {zoneLabel.toLowerCase()} zone.
        Historically ratios below 2.2 have shifted 2–4M acres to soybeans.
      </p>
    </div>
  );
}
