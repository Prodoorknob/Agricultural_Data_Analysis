'use client';

import DeltaChip from '@/components/shared/DeltaChip';
import Sparkline from '@/components/shared/Sparkline';

interface MarketHeroProps {
  commodity: string;
  nearbyContract: string;
  settlePrice: number;
  settleDate: string;
  delta1d: number;
  delta1w: number;
  delta1m: number;
  deltaYtd: number;
  sparkline90d: number[];
}

export default function MarketHero({
  commodity,
  nearbyContract,
  settlePrice,
  settleDate,
  delta1d,
  delta1w,
  delta1m,
  deltaYtd,
  sparkline90d,
}: MarketHeroProps) {
  return (
    <div
      className="p-6 rounded-[var(--radius-lg)] border mb-6"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
    >
      <div className="flex items-start justify-between gap-6 flex-wrap">
        <div>
          {/* Price */}
          <div className="flex items-baseline gap-2">
            <span
              style={{
                fontFamily: 'var(--font-stat)',
                fontSize: '64px',
                fontWeight: 900,
                lineHeight: 0.95,
                letterSpacing: '-0.02em',
                color: 'var(--harvest)',
              }}
            >
              ${settlePrice.toFixed(2)}
            </span>
            <span
              className="text-[14px]"
              style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
            >
              /bu {nearbyContract}
            </span>
          </div>

          {/* Delta chips */}
          <div className="flex items-center gap-2 mt-3 flex-wrap">
            <DeltaChip value={delta1d} label="1d" size="md" />
            <DeltaChip value={delta1w} label="1w" size="md" />
            <DeltaChip value={delta1m} label="1m" size="md" />
            <DeltaChip value={deltaYtd} label="YTD" size="md" />
          </div>

          {/* Caption */}
          <p
            className="mt-3 text-[12px]"
            style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
          >
            Nearby contract: {nearbyContract}. Last settle: {settleDate}.
          </p>
        </div>

        {/* 90-day sparkline */}
        {sparkline90d.length > 0 && (
          <div className="shrink-0">
            <Sparkline data={sparkline90d} color="var(--harvest)" width={140} height={50} />
            <p
              className="text-[10px] text-right mt-1"
              style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
            >
              90 days
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
