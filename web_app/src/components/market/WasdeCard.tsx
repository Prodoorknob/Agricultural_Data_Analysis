'use client';

import Term from '@/components/shared/Term';
import SectionHeading from '@/components/shared/SectionHeading';

interface WasdeCardProps {
  releaseDate: string;
  endingStocks: number | null;
  stocksToUse: number | null;
  stocksToUsePctile: number | null;
  priorMonthStu: number | null;
  surpriseDirection: 'supportive' | 'pressuring' | 'neutral';
  commodity: string;
}

export default function WasdeCard({
  releaseDate,
  endingStocks,
  stocksToUse,
  stocksToUsePctile,
  priorMonthStu,
  surpriseDirection,
  commodity,
}: WasdeCardProps) {
  const directionColor =
    surpriseDirection === 'supportive' ? 'var(--positive)' :
    surpriseDirection === 'pressuring' ? 'var(--negative)' :
    'var(--text2)';
  const directionLabel =
    surpriseDirection === 'supportive' ? 'Supportive' :
    surpriseDirection === 'pressuring' ? 'Pressuring' :
    'Neutral';

  const stuDelta = priorMonthStu && stocksToUse
    ? (stocksToUse - priorMonthStu).toFixed(1)
    : null;

  return (
    <div
      className="p-5 rounded-[var(--radius-lg)] border flex-1"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
    >
      <SectionHeading>
        Latest <Term>WASDE</Term> &middot; {releaseDate}
      </SectionHeading>

      <div className="flex flex-col gap-3">
        {/* Ending stocks */}
        {endingStocks !== null && (
          <StatRow label="Ending Stocks" value={`${endingStocks.toLocaleString()} M bu`} />
        )}

        {/* Stocks-to-use */}
        {stocksToUse !== null && (
          <div>
            <StatRow
              label="Stocks-to-Use"
              value={`${stocksToUse.toFixed(1)}%`}
              delta={stuDelta ? `${Number(stuDelta) >= 0 ? '+' : ''}${stuDelta}pp` : undefined}
            />
            {/* Percentile bar */}
            {stocksToUsePctile !== null && (
              <div className="mt-1.5">
                <div
                  className="h-1.5 rounded-full relative"
                  style={{ background: 'var(--surface2)' }}
                >
                  <div
                    className="absolute top-0 h-1.5 rounded-full"
                    style={{
                      background: 'var(--field)',
                      width: `${stocksToUsePctile}%`,
                    }}
                  />
                </div>
                <p className="text-[9px] mt-0.5" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
                  {stocksToUsePctile}th percentile (10yr)
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Direction pill */}
      <div className="mt-4">
        <span
          className="inline-block px-3 py-1 rounded-[var(--radius-full)] text-[12px] font-bold"
          style={{
            color: directionColor,
            background: surpriseDirection === 'supportive' ? 'var(--field-subtle)' :
                        surpriseDirection === 'pressuring' ? 'rgba(180,35,24,0.07)' :
                        'var(--surface2)',
          }}
          title={surpriseDirection === 'supportive' ? 'Bullish' : surpriseDirection === 'pressuring' ? 'Bearish' : 'Neutral'}
        >
          {directionLabel}
        </span>
      </div>
    </div>
  );
}

function StatRow({ label, value, delta }: { label: string; value: string; delta?: string }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-[12px]" style={{ color: 'var(--text2)' }}>{label}</span>
      <div className="flex items-baseline gap-2">
        <span className="text-[16px] font-bold" style={{ color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>
          {value}
        </span>
        {delta && (
          <span className="text-[11px]" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
            {delta}
          </span>
        )}
      </div>
    </div>
  );
}
