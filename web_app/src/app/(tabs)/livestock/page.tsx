'use client';

import { useEffect, useState, useMemo } from 'react';
import { useFilters } from '@/hooks/useFilters';
import { LATEST_NASS_YEAR } from '@/lib/constants';
import { US_STATES, fetchStateData, fetchNationalCrops } from '@/utils/serviceData';
import { filterData } from '@/utils/processData';
import BandShell from '@/components/shared/BandShell';
import InventorySnapshot from '@/components/livestock/InventorySnapshot';
import ProductionCharts from '@/components/livestock/ProductionCharts';
import CitationBlock from '@/components/shared/CitationBlock';

const LIVESTOCK_SPECIES = [
  { id: 'cattle', commodity: 'CATTLE', label: 'Cattle', stat: 'INVENTORY', unit: 'head' },
  { id: 'hogs', commodity: 'HOGS', label: 'Hogs', stat: 'INVENTORY', unit: 'head' },
  { id: 'dairy', commodity: 'CATTLE', label: 'Dairy Cows', stat: 'INVENTORY', unit: 'head', filter: 'MILK' },
  { id: 'broilers', commodity: 'CHICKENS', label: 'Broilers', stat: 'PRODUCTION', unit: 'head' },
  { id: 'layers', commodity: 'CHICKENS', label: 'Layers', stat: 'INVENTORY', unit: 'head' },
  { id: 'turkeys', commodity: 'TURKEYS', label: 'Turkeys', stat: 'INVENTORY', unit: 'head' },
];

export default function LivestockPage() {
  const { filters } = useFilters();
  const stateCode = filters.state;
  const stateName = stateCode ? (US_STATES[stateCode] || stateCode) : 'United States';
  const year = filters.year ?? LATEST_NASS_YEAR;

  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    (async () => {
      try {
        const raw = stateCode ? await fetchStateData(stateCode) : await fetchNationalCrops();
        setData(raw || []);
      } catch {
        setError('Failed to load livestock data.');
      }
      setLoading(false);
    })();
  }, [stateCode]);

  const filtered = useMemo(() => filterData(data), [data]);

  // Inventory KPIs
  const inventoryKpis = useMemo(() => {
    return LIVESTOCK_SPECIES.map((spec) => {
      const rows = filtered.filter(
        (r: any) =>
          r.commodity_desc?.includes(spec.commodity) &&
          r.statisticcat_desc === spec.stat &&
          r.year === year
      );
      const headCount = rows.reduce((s: number, r: any) => s + (r.value_num || 0), 0);

      // 5-year sparkline
      const sparkline = Array.from({ length: 5 }, (_, i) => {
        const y = year - 4 + i;
        const yRows = filtered.filter(
          (r: any) => r.commodity_desc?.includes(spec.commodity) && r.statisticcat_desc === spec.stat && r.year === y
        );
        return yRows.reduce((s: number, r: any) => s + (r.value_num || 0), 0);
      });

      // YoY delta
      const priorRows = filtered.filter(
        (r: any) => r.commodity_desc?.includes(spec.commodity) && r.statisticcat_desc === spec.stat && r.year === year - 1
      );
      const priorCount = priorRows.reduce((s: number, r: any) => s + (r.value_num || 0), 0);
      const yoyDelta = priorCount > 0 ? ((headCount - priorCount) / priorCount) * 100 : 0;

      return {
        species: spec.id,
        label: spec.label,
        headCount,
        unit: spec.unit,
        sparkline5yr: sparkline,
        yoyDeltaPct: yoyDelta,
      };
    }).filter((k) => k.headCount > 0);
  }, [filtered, year]);

  // Production series
  const productionSeries = useMemo(() => {
    const series = [
      { commodity: 'CATTLE', stat: 'SALES', title: 'Cattle Sales', unit: '$', color: 'var(--chart-cattle)' },
      { commodity: 'HOGS', stat: 'SALES', title: 'Hog Sales', unit: '$', color: 'var(--chart-hogs)' },
      { commodity: 'MILK', stat: 'PRODUCTION', title: 'Milk Production', unit: 'lbs', color: 'var(--chart-dairy)' },
    ];

    return series.map((s) => {
      const allYears = [...new Set(filtered.filter((r: any) => r.commodity_desc?.includes(s.commodity)).map((r: any) => r.year))].sort();
      const points = allYears.map((y) => {
        const rows = filtered.filter(
          (r: any) => r.commodity_desc?.includes(s.commodity) && r.statisticcat_desc === s.stat && r.year === y
        );
        const val = rows.reduce((sum: number, r: any) => sum + (r.value_num || 0), 0);
        return { year: y as number, stateValue: val, nationalValue: 0 };
      }).filter((p) => p.stateValue > 0);

      return { ...s, data: points };
    }).filter((s) => s.data.length > 0);
  }, [filtered]);

  return (
    <div>
      <h1 className="text-[28px] font-extrabold tracking-[-0.02em] mb-6"
        style={{ color: 'var(--text)', fontFamily: 'var(--font-body)' }}>
        Livestock — {stateName}
      </h1>

      <BandShell loading={loading} error={error} skeletonHeight={300}
        empty={inventoryKpis.length === 0 && !loading}
        emptyMessage={`Livestock data is limited for ${stateName}.`}>
        {/* Band A — Inventory */}
        <InventorySnapshot data={inventoryKpis} />

        {/* Band B — Production */}
        <ProductionCharts series={productionSeries} stateName={stateName} />
      </BandShell>
    </div>
  );
}
