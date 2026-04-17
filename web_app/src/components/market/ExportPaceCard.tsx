'use client';

import Term from '@/components/shared/Term';
import SectionHeading from '@/components/shared/SectionHeading';

interface ExportPaceCardProps {
  commodity: string;
  asOfDate: string;
  marketingYear: string;
  totalCommittedMt: number;
  fiveYrAvgMt: number;
  pctOfAvg: number;
  weekOfMy: number;
}

export default function ExportPaceCard({
  asOfDate,
  marketingYear,
  totalCommittedMt,
  fiveYrAvgMt,
  pctOfAvg,
  weekOfMy,
}: ExportPaceCardProps) {
  const aheadOfAvg = pctOfAvg >= 100;
  const pctColor = aheadOfAvg ? 'var(--positive)' : 'var(--negative)';
  const pctBackground = aheadOfAvg ? 'var(--field-subtle)' : 'rgba(180,35,24,0.07)';
  const directionLabel = aheadOfAvg ? 'Ahead of pace' : 'Behind pace';

  const formatMt = (mt: number) =>
    mt >= 1_000_000
      ? `${(mt / 1_000_000).toFixed(1)}M mt`
      : `${(mt / 1000).toFixed(0)}K mt`;

  return (
    <div
      className="p-5 rounded-[var(--radius-lg)] border flex-1"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
    >
      <SectionHeading>
        <Term term="export commitments">Export Pace</Term> &middot; {asOfDate}
      </SectionHeading>

      {/* Big percent */}
      <span
        style={{
          fontFamily: 'var(--font-stat)',
          fontSize: '48px',
          fontWeight: 900,
          lineHeight: 0.95,
          color: pctColor,
        }}
      >
        {Math.round(pctOfAvg)}%
      </span>
      <p className="text-[12px] mt-1" style={{ color: 'var(--text2)' }}>
        of 5-yr avg commitments
      </p>

      {/* Supporting metrics */}
      <div className="mt-4 flex flex-col gap-2">
        <StatRow label="Committed" value={formatMt(totalCommittedMt)} />
        <StatRow label="5-yr avg" value={formatMt(fiveYrAvgMt)} />
      </div>

      {/* Direction pill + week */}
      <div className="mt-4 flex items-center justify-between">
        <span
          className="inline-block px-3 py-1 rounded-[var(--radius-full)] text-[12px] font-bold"
          style={{ color: pctColor, background: pctBackground }}
        >
          {directionLabel}
        </span>
        <span
          className="text-[11px]"
          style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
        >
          Week {weekOfMy} of {marketingYear}
        </span>
      </div>
    </div>
  );
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-[12px]" style={{ color: 'var(--text2)' }}>
        {label}
      </span>
      <span
        className="text-[14px] font-bold"
        style={{ color: 'var(--text)', fontFamily: 'var(--font-mono)' }}
      >
        {value}
      </span>
    </div>
  );
}
