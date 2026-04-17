'use client';

import { useEffect, useState, useMemo } from 'react';
import { useFilters } from '@/hooks/useFilters';
import { LATEST_NASS_YEAR } from '@/lib/constants';
import { US_STATES, fetchStateData, fetchNationalCrops } from '@/utils/serviceData';
import { filterData } from '@/utils/processData';
import BandShell from '@/components/shared/BandShell';
import InventorySnapshot from '@/components/livestock/InventorySnapshot';
import ProductionSalesTable from '@/components/livestock/ProductionSalesTable';

// Inventory species — all drawn from the raw state parquet with:
//   - exact commodity_desc match (kills substring overcounting)
//   - unit_desc === 'HEAD' (keeps head counts, drops $ valuations)
//   - class_desc filter (keeps the species of interest)
// When NASS publishes quarterly (hogs) we pick the MAX across reports in
// the year rather than summing — gives peak inventory instead of 4x.
const isHead = (r: any) => !r.unit_desc || r.unit_desc === 'HEAD';

const INVENTORY_SPECIES = [
  {
    id: 'cattle',
    label: 'Cattle',
    unit: 'head',
    match: (r: any) =>
      r.commodity_desc === 'CATTLE' &&
      r.statisticcat_desc === 'INVENTORY' &&
      isHead(r) &&
      (r.class_desc === 'ALL CLASSES' || !r.class_desc),
  },
  {
    id: 'hogs',
    label: 'Hogs',
    unit: 'head',
    match: (r: any) =>
      r.commodity_desc === 'HOGS' &&
      r.statisticcat_desc === 'INVENTORY' &&
      isHead(r) &&
      (r.class_desc === 'ALL CLASSES' || !r.class_desc),
  },
  {
    id: 'dairy',
    label: 'Dairy Cows',
    unit: 'head',
    match: (r: any) =>
      r.commodity_desc === 'CATTLE' &&
      r.statisticcat_desc === 'INVENTORY' &&
      isHead(r) &&
      typeof r.class_desc === 'string' &&
      r.class_desc.includes('MILK'),
  },
  {
    id: 'broilers',
    label: 'Broilers',
    unit: 'head',
    match: (r: any) =>
      r.commodity_desc === 'CHICKENS' &&
      r.statisticcat_desc === 'PRODUCTION' &&
      isHead(r),
  },
  {
    id: 'layers',
    label: 'Layers',
    unit: 'head',
    match: (r: any) =>
      r.commodity_desc === 'CHICKENS' &&
      r.statisticcat_desc === 'INVENTORY' &&
      isHead(r),
  },
  {
    id: 'turkeys',
    label: 'Turkeys',
    unit: 'head',
    match: (r: any) =>
      r.commodity_desc === 'TURKEYS' &&
      r.statisticcat_desc === 'INVENTORY' &&
      isHead(r) &&
      (r.class_desc === 'ALL CLASSES' || !r.class_desc),
  },
];

export default function LivestockPage() {
  const { filters } = useFilters();
  const stateCode = filters.state;
  const stateName = stateCode ? US_STATES[stateCode] || stateCode : 'United States';
  const year = filters.year ?? LATEST_NASS_YEAR;

  const [rawData, setRawData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    const controller = new AbortController();
    (async () => {
      try {
        const raw = stateCode
          ? await fetchStateData(stateCode, controller.signal)
          : await fetchNationalCrops(controller.signal);
        setRawData(raw || []);
      } catch (err: any) {
        if (err?.name !== 'AbortError') {
          setError('Failed to load livestock data.');
        }
      }
      setLoading(false);
    })();
    return () => controller.abort();
  }, [stateCode]);

  const filteredRaw = useMemo(() => filterData(rawData), [rawData]);

  // Inventory KPIs — peak inventory in the year (max across any quarterly
  // reports), avoiding the 4x overcount that would come from summing.
  const inventoryKpis = useMemo(() => {
    return INVENTORY_SPECIES.map((spec) => {
      const rowsForSpec = filteredRaw.filter(spec.match);
      const peakForYear = (y: number) => {
        const vals = rowsForSpec
          .filter((r: any) => r.year === y)
          .map((r: any) => r.value_num || 0);
        return vals.length ? Math.max(...vals) : 0;
      };

      const headCount = peakForYear(year);
      const priorCount = peakForYear(year - 1);
      const yoyDelta = priorCount > 0 ? ((headCount - priorCount) / priorCount) * 100 : 0;
      const sparklineYears = [year - 4, year - 3, year - 2, year - 1, year];
      const sparkline = sparklineYears.map(peakForYear);

      return {
        species: spec.id,
        label: spec.label,
        headCount,
        unit: spec.unit,
        sparkline5yr: sparkline,
        sparklineYears,
        yoyDeltaPct: yoyDelta,
      };
    }).filter((k) => k.headCount > 0);
  }, [filteredRaw, year]);

  // Production & Sales table — three metrics aligned by year.
  const productionTable = useMemo(() => {
    const sumRaw = (y: number, commodity: string, stat: string) =>
      filteredRaw
        .filter((r: any) => {
          if (r.year !== y) return false;
          if (r.statisticcat_desc !== stat) return false;
          if (stat === 'SALES' && r.unit_desc !== '$') return false;
          // Exact match — no more substring overcounting.
          return r.commodity_desc === commodity;
        })
        .reduce((s: number, r: any) => s + (r.value_num || 0), 0);

    const years = Array.from({ length: 11 }, (_, i) => year - 10 + i);
    const rows = years.map((y) => ({
      year: y,
      cattleSales: sumRaw(y, 'CATTLE', 'SALES'),
      hogSales: sumRaw(y, 'HOGS', 'SALES'),
      milkProduction: sumRaw(y, 'MILK', 'PRODUCTION'),
    }));

    return {
      rows,
      cattleSparkYears: rows.map((r) => r.year),
      cattleSparkValues: rows.map((r) => r.cattleSales),
      hogSparkYears: rows.map((r) => r.year),
      hogSparkValues: rows.map((r) => r.hogSales),
      milkSparkYears: rows.map((r) => r.year),
      milkSparkValues: rows.map((r) => r.milkProduction),
    };
  }, [filteredRaw, year]);

  return (
    <div>
      <h1
        className="text-[28px] font-extrabold tracking-[-0.02em] mb-6"
        style={{ color: 'var(--text)', fontFamily: 'var(--font-body)' }}
      >
        Livestock — {stateName}
      </h1>

      <BandShell
        loading={loading}
        error={error}
        skeletonHeight={300}
        empty={inventoryKpis.length === 0 && !loading}
        emptyMessage={`Livestock data is limited for ${stateName}.`}
      >
        {/* Band A — Inventory */}
        <InventorySnapshot data={inventoryKpis} />

        {/* Band B — Production & Sales table */}
        <ProductionSalesTable data={productionTable} stateName={stateName} />
      </BandShell>
    </div>
  );
}
