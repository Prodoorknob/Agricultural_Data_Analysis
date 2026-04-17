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
  operationsYearUsed?: number | null;
  operationsBaselineYear?: number | null;
  totalSales: number;
  salesYoyDelta: number;
  salesShareOfState: number;
  stateName: string;
  commodity: string;
}

const CENSUS_YEARS = new Set([2002, 2007, 2012, 2017, 2022]);

export default function CropHeroRow({
  yieldThisYear,
  yieldUnit,
  yield5yrAvg,
  yieldDeltaVs5yr,
  areaPlanted,
  areaYoyDelta,
  operationsCount,
  operationsDeltaSince2010,
  operationsYearUsed,
  operationsBaselineYear,
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

  const opsYearLabel = operationsYearUsed
    ? `(${CENSUS_YEARS.has(operationsYearUsed) ? 'Census ' : ''}${operationsYearUsed})`
    : undefined;
  const baselineClause = operationsBaselineYear
    ? `since ${CENSUS_YEARS.has(operationsBaselineYear) ? 'the ' + operationsBaselineYear + ' Census' : operationsBaselineYear}`
    : 'over time';
  const opsCaption = operationsCount > 0
    ? `${formatCompact(operationsCount)} operations — ${operationsDeltaSince2010 >= 0 ? 'up' : 'down'} ${Math.abs(operationsDeltaSince2010).toFixed(0)}% ${baselineClause}.`
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
      {operationsCount > 0 && (
        <KpiCard
          value={formatCompact(operationsCount)}
          label="Operations"
          unit={opsYearLabel}
          caption={opsCaption}
          delta={operationsDeltaSince2010 !== 0 ? operationsDeltaSince2010 : undefined}
          size="md"
        />
      )}
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
