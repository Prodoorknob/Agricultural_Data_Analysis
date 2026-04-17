'use client';

import KpiCard from '@/components/shared/KpiCard';
import SectionHeading from '@/components/shared/SectionHeading';
import { formatCompact } from '@/lib/format';

interface LivestockKPI {
  species: string;
  label: string;
  headCount: number;
  unit: string;
  sparkline5yr: number[];
  sparklineYears?: number[];
  yoyDeltaPct: number;
}

interface InventorySnapshotProps {
  data: LivestockKPI[];
}

const SPECIES_COLORS: Record<string, string> = {
  cattle: 'var(--chart-cattle)',
  hogs: 'var(--chart-hogs)',
  dairy: 'var(--chart-dairy)',
  broilers: 'var(--soil)',
  layers: 'var(--harvest)',
  turkeys: 'var(--sky)',
};

export default function InventorySnapshot({ data }: InventorySnapshotProps) {
  const primary = data.slice(0, 4);
  const secondary = data.slice(4);

  return (
    <div className="mb-8">
      <SectionHeading>Inventory Snapshot</SectionHeading>

      {/* Primary row — 4 cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
        {primary.map((item) => (
          <KpiCard
            key={item.species}
            value={formatCompact(item.headCount)}
            label={item.label}
            unit={item.unit}
            delta={item.yoyDeltaPct}
            sparklineData={item.sparkline5yr}
            sparklineYears={item.sparklineYears}
            sparklineUnit={item.unit}
            sparklineColor={SPECIES_COLORS[item.species] || 'var(--field)'}
            size="md"
          />
        ))}
      </div>

      {/* Secondary row — smaller */}
      {secondary.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {secondary.map((item) => (
            <KpiCard
              key={item.species}
              value={formatCompact(item.headCount)}
              label={item.label}
              unit={item.unit}
              delta={item.yoyDeltaPct}
              sparklineData={item.sparkline5yr}
              sparklineColor={SPECIES_COLORS[item.species] || 'var(--field)'}
              size="md"
            />
          ))}
        </div>
      )}
    </div>
  );
}
