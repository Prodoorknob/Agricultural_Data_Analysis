'use client';

import KpiCard from '@/components/shared/KpiCard';
import { formatCompact, formatCurrency } from '@/lib/format';

interface CropHeroRowProps {
  yieldThisYear: number;
  yieldUnit: string;
  yield5yrAvg: number;
  yieldDeltaVs5yr: number;
  areaPlanted: number;
  areaYoyDelta: number;
  operationsCount: number;
  operationsDeltaSince2010: number;
  totalSales: number;
  salesYoyDelta: number;
  salesShareOfState: number;
  stateName: string;
  commodity: string;
}

export default function CropHeroRow({
  yieldThisYear,
  yieldUnit,
  yield5yrAvg,
  yieldDeltaVs5yr,
  areaPlanted,
  areaYoyDelta,
  operationsCount,
  operationsDeltaSince2010,
  totalSales,
  salesYoyDelta,
  salesShareOfState,
  stateName,
  commodity,
}: CropHeroRowProps) {
  const yieldCaption = yieldThisYear > 0
    ? `${yieldThisYear.toFixed(0)} ${yieldUnit} — ${yieldDeltaVs5yr >= 0 ? 'above' : 'below'} the 5-year average of ${yield5yrAvg.toFixed(0)}.`
    : '';

  const areaCaption = areaPlanted > 0
    ? `${formatCompact(areaPlanted)} acres — ${areaYoyDelta >= 0 ? 'up' : 'down'} ${Math.abs(areaYoyDelta).toFixed(1)}% from last year.`
    : '';

  const opsCaption = operationsCount > 0
    ? `${formatCompact(operationsCount)} operations — ${operationsDeltaSince2010 >= 0 ? 'up' : 'down'} ${Math.abs(operationsDeltaSince2010).toFixed(0)}% since 2010.`
    : '';

  const salesCaption = totalSales > 0
    ? `${formatCurrency(totalSales)}, ${salesShareOfState.toFixed(0)}% of ${stateName}'s total farm sales.`
    : '';

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      <KpiCard
        value={yieldThisYear > 0 ? yieldThisYear.toFixed(0) : 'N/A'}
        label="Yield"
        unit={yieldUnit}
        caption={yieldCaption}
        delta={yieldDeltaVs5yr}
        size="md"
      />
      <KpiCard
        value={areaPlanted > 0 ? formatCompact(areaPlanted) : 'N/A'}
        label="Area Planted"
        unit="acres"
        caption={areaCaption}
        delta={areaYoyDelta}
        size="md"
      />
      <KpiCard
        value={operationsCount > 0 ? formatCompact(operationsCount) : 'N/A'}
        label="Operations"
        caption={opsCaption}
        delta={operationsDeltaSince2010}
        size="md"
      />
      <KpiCard
        value={totalSales > 0 ? formatCurrency(totalSales) : 'N/A'}
        label="Total Sales"
        caption={salesCaption}
        delta={salesYoyDelta}
        size="md"
      />
    </div>
  );
}
