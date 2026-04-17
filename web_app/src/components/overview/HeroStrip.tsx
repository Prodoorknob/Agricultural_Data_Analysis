'use client';

import KpiCard from '@/components/shared/KpiCard';
import CitationBlock from '@/components/shared/CitationBlock';
import { formatCurrency, formatCompact } from '@/lib/format';
import { generateCaption } from '@/lib/captionTemplates';
import { LATEST_NASS_YEAR } from '@/lib/constants';
import { US_STATES } from '@/utils/serviceData';

interface HeroStripProps {
  stateName: string;
  stateCode: string | null;
  totalSales: number;
  salesRank: number;
  salesGrowthPct: number;
  salesGrowthBaseYear?: number;
  totalAcresPlanted: number;
  acresDelta: number;
  acresDeltaDriver: string;
  topCrop: string;
  topCropSales: number;
  topCropStreak: number;
  commodityCount: number;
}

export default function HeroStrip({
  stateName,
  stateCode,
  totalSales,
  salesRank,
  salesGrowthPct,
  salesGrowthBaseYear,
  totalAcresPlanted,
  acresDelta,
  acresDeltaDriver,
  topCrop,
  topCropSales,
  topCropStreak,
  commodityCount,
}: HeroStripProps) {
  const displayName = stateCode ? (US_STATES[stateCode] || stateCode) : 'United States';
  const compareYear = salesGrowthBaseYear ?? LATEST_NASS_YEAR - 5;

  // Rank 0 means "not applicable" (national view) — hide it from the caption
  // rather than ship "ranks #0" again.
  const rankClause = salesRank > 0 ? `ranks #${salesRank} by total farm sales, ` : '';
  const salesCaption = stateCode
    ? `${displayName} ${rankClause}${salesGrowthPct >= 0 ? 'up' : 'down'} ${Math.abs(salesGrowthPct).toFixed(0)}% since ${compareYear}.`
    : `U.S. total farm sales ${salesGrowthPct >= 0 ? 'up' : 'down'} ${Math.abs(salesGrowthPct).toFixed(0)}% since ${compareYear}.`;

  const acresCaption = generateCaption('overview-hero-acres', {
    acresDeltaDirection: acresDelta >= 0 ? 'Up' : 'Down',
    acresDeltaAbs: formatCompact(Math.abs(acresDelta)),
    priorYear: LATEST_NASS_YEAR - 1,
    acresDeltaDriver,
  });

  const topCropCaption = generateCaption('overview-hero-top-crop', {
    topCrop,
    stateName: displayName,
    topCropStreakText:
      topCropStreak > 1
        ? `every year for ${topCropStreak} years straight`
        : 'in the latest year on record',
  });

  return (
    <section className="mb-8">
      {/* State name display */}
      <div className="flex items-baseline gap-3 mb-5">
        <h1
          className="text-[28px] font-extrabold tracking-[-0.02em]"
          style={{ color: 'var(--text)', fontFamily: 'var(--font-body)' }}
        >
          {displayName}
        </h1>
        {stateCode && (
          <span
            className="text-[12px] font-bold tracking-[0.1em] uppercase"
            style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
          >
            {LATEST_NASS_YEAR}
          </span>
        )}
      </div>

      {/* 3 hero KPI cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KpiCard
          value={formatCurrency(totalSales)}
          label="Total Farm Sales"
          caption={salesCaption}
          delta={salesGrowthPct}
          size="lg"
        />
        <KpiCard
          value={formatCompact(totalAcresPlanted)}
          label="Acres Planted"
          caption={acresCaption}
          unit={`across ${commodityCount} crops`}
          size="lg"
        />
        <KpiCard
          value={topCrop}
          label="Top Crop"
          caption={topCropCaption}
          size="md"
          unit={formatCurrency(topCropSales)}
        />
      </div>

      <CitationBlock
        source="USDA NASS QuickStats"
        vintage={`${LATEST_NASS_YEAR}`}
        updated="Apr 2026"
      />
    </section>
  );
}
