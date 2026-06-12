'use client';

import KpiCard from '@/components/shared/KpiCard';

export interface HeroCard {
  /** Pre-formatted hero value (e.g. "198", "$4.3B", "5.2M"). */
  value: string;
  label: string;
  unit?: string;
  caption?: string;
  delta?: number;
}

interface CropHeroRowProps {
  cards: HeroCard[];
}

/**
 * Adaptive KPI row. The page builds the card list so it can vary per crop:
 * field crops show Yield (bu/ac) + Area Planted, while specialty crops fall
 * back to Production (native unit), Area Bearing/Harvested, and Value of
 * Production when those are what NASS actually publishes. Empty metrics are
 * dropped upstream, so this just renders whatever it's given.
 */
export default function CropHeroRow({ cards }: CropHeroRowProps) {
  if (!cards.length) return null;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      {cards.map((c) => (
        <KpiCard
          key={c.label}
          value={c.value}
          label={c.label}
          unit={c.unit}
          caption={c.caption}
          delta={c.delta}
          size="md"
        />
      ))}
    </div>
  );
}
