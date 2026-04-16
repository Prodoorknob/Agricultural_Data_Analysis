'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import { useFilters } from '@/hooks/useFilters';
import { LATEST_NASS_YEAR, CROP_COMMODITIES } from '@/lib/constants';
import { US_STATES, fetchStateData, fetchNationalCrops } from '@/utils/serviceData';
import { filterData, getCommodityStory, detectAnomalies, getTopCrops, getCropConditionTrends } from '@/utils/processData';
import BandShell from '@/components/shared/BandShell';
import CommodityPicker from '@/components/shared/CommodityPicker';
import CropHeroRow from '@/components/crops/CropHeroRow';
import YieldTrendChart from '@/components/crops/YieldTrendChart';
import ProfitChart from '@/components/crops/ProfitChart';
import HarvestEfficiency from '@/components/crops/HarvestEfficiency';
import CropProgressStrip from '@/components/crops/CropProgressStrip';
import CountyDrillDown from '@/components/crops/CountyDrillDown';

export default function CropsPage() {
  const { filters, setCommodity } = useFilters();
  const stateCode = filters.state;
  const stateName = stateCode ? (US_STATES[stateCode] || stateCode) : 'United States';
  const commodity = (filters.commodity || 'corn').toUpperCase();
  const year = filters.year ?? LATEST_NASS_YEAR;

  const [stateData, setStateData] = useState<any[]>([]);
  const [nationalData, setNationalData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const [sd, nd] = await Promise.all([
          stateCode ? fetchStateData(stateCode) : Promise.resolve([]),
          fetchNationalCrops(),
        ]);
        setStateData(sd || []);
        setNationalData(nd || []);
      } catch {
        setError('Failed to load crop data.');
      }
      setLoading(false);
    })();
  }, [stateCode]);

  const activeData = useMemo(() => filterData(stateCode ? stateData : nationalData), [stateCode, stateData, nationalData]);

  // Commodity story — 25 years of merged metrics
  const storyResult = useMemo(() => getCommodityStory(activeData, commodity), [activeData, commodity]);
  const story = storyResult?.story || [];

  // Hero KPI data
  const heroData = useMemo(() => {
    const thisYear = story.find((s: any) => s.year === year);
    const priorYear = story.find((s: any) => s.year === year - 1);
    const fiveYearsAgo = story.filter((s: any) => s.year >= year - 5 && s.year <= year - 1);
    const avg5yr = fiveYearsAgo.length > 0
      ? fiveYearsAgo.reduce((s: number, r: any) => s + (r.yield || 0), 0) / fiveYearsAgo.length
      : 0;

    const yieldNow = thisYear?.yield || 0;
    const yieldDelta = avg5yr > 0 ? ((yieldNow - avg5yr) / avg5yr) * 100 : 0;

    const areaNow = thisYear?.areaPlanted || 0;
    const areaPrior = priorYear?.areaPlanted || 0;
    const areaDelta = areaPrior > 0 ? ((areaNow - areaPrior) / areaPrior) * 100 : 0;

    // Operations count from raw data
    const opsRows = activeData.filter(
      (r: any) => r.year === year && r.commodity_desc === commodity && r.statisticcat_desc === 'OPERATIONS'
    );
    const opsCount = opsRows.reduce((s: number, r: any) => s + (r.value_num || 0), 0);
    const opsRows2010 = activeData.filter(
      (r: any) => r.year === 2010 && r.commodity_desc === commodity && r.statisticcat_desc === 'OPERATIONS'
    );
    const opsCount2010 = opsRows2010.reduce((s: number, r: any) => s + (r.value_num || 0), 0);
    const opsDelta = opsCount2010 > 0 ? ((opsCount - opsCount2010) / opsCount2010) * 100 : 0;

    const salesNow = thisYear?.revenue || 0;
    const salesPrior = priorYear?.revenue || 0;
    const salesDelta = salesPrior > 0 ? ((salesNow - salesPrior) / salesPrior) * 100 : 0;

    // Total state sales for share calculation
    const totalStateSales = activeData
      .filter((r: any) => r.year === year && r.statisticcat_desc === 'SALES' && r.unit_desc === '$')
      .reduce((s: number, r: any) => s + (r.value_num || 0), 0);
    const salesShare = totalStateSales > 0 ? (salesNow / totalStateSales) * 100 : 0;

    return {
      yieldThisYear: yieldNow,
      yieldUnit: thisYear?.yieldUnit || 'BU / ACRE',
      yield5yrAvg: avg5yr,
      yieldDeltaVs5yr: yieldDelta,
      areaPlanted: areaNow,
      areaYoyDelta: areaDelta,
      operationsCount: opsCount,
      operationsDeltaSince2010: opsDelta,
      totalSales: salesNow,
      salesYoyDelta: salesDelta,
      salesShareOfState: salesShare,
      stateName,
      commodity: commodity.charAt(0) + commodity.slice(1).toLowerCase(),
    };
  }, [story, activeData, year, commodity, stateName]);

  // Yield trend data with anomalies
  const yieldTrendData = useMemo(() => {
    const stateResult = getCommodityStory(filterData(stateCode ? stateData : nationalData), commodity);
    const nationalResult = getCommodityStory(filterData(nationalData), commodity);
    const stateStory = stateResult?.story || [];
    const nationalStory = nationalResult?.story || [];
    const anomalyYearSet = new Set(stateResult?.anomalyYears || []);

    const nationalMap = new Map(nationalStory.map((s: any) => [s.year, s.yield || 0]));

    return stateStory
      .filter((s: any) => s.yield > 0)
      .map((s: any) => ({
        year: s.year,
        stateYield: s.yield,
        nationalYield: nationalMap.get(s.year) || 0,
        isAnomaly: anomalyYearSet.has(s.year),
      }))
      .sort((a: any, b: any) => a.year - b.year);
  }, [stateData, nationalData, stateCode, commodity]);

  // Harvest efficiency
  const efficiencyData = useMemo(() => {
    return story
      .filter((s: any) => s.areaPlanted > 0 && s.areaHarvested > 0)
      .map((s: any) => ({
        year: s.year,
        efficiencyPct: (s.areaHarvested / s.areaPlanted) * 100,
      }))
      .sort((a: any, b: any) => a.year - b.year);
  }, [story]);

  // Profit data — placeholder (needs futures + costs from backend, stubbed for now)
  const profitData = useMemo(() => {
    // Rough profit estimate: yield × $4.50 (placeholder price) − $700 (placeholder cost/acre)
    return story
      .filter((s: any) => s.yield > 0)
      .map((s: any) => ({
        year: s.year,
        profitPerAcre: Math.round(s.yield * 4.5 - 700),
      }))
      .sort((a: any, b: any) => a.year - b.year);
  }, [story]);

  // Crop condition data
  const conditionData = useMemo(() => {
    const raw = getCropConditionTrends(activeData, commodity);
    if (!raw || raw.length === 0) return [];
    // Transform to the component's expected format
    return raw
      .filter((r: any) => r.year === year)
      .map((r: any, i: number) => ({
        week: `W${i + 1}`,
        goodExcellentPct: (r.good || 0) + (r.excellent || 0),
        fiveYearAvgPct: 65, // Placeholder 5yr avg
      }));
  }, [activeData, commodity, year]);

  const retry = useCallback(() => {
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const [sd, nd] = await Promise.all([
          stateCode ? fetchStateData(stateCode) : Promise.resolve([]),
          fetchNationalCrops(),
        ]);
        setStateData(sd || []);
        setNationalData(nd || []);
      } catch {
        setError('Failed to load crop data.');
      }
      setLoading(false);
    })();
  }, [stateCode]);

  const commodityLabel = commodity.charAt(0) + commodity.slice(1).toLowerCase();

  return (
    <div>
      {/* Band A — Commodity picker */}
      <div className="mb-6">
        <CommodityPicker
          selected={filters.commodity || 'corn'}
          onSelect={setCommodity}
        />
      </div>

      {/* Page title */}
      <div className="flex items-baseline gap-3 mb-5">
        <h1
          className="text-[28px] font-extrabold tracking-[-0.02em]"
          style={{ color: 'var(--text)', fontFamily: 'var(--font-body)' }}
        >
          {commodityLabel} in {stateName}
        </h1>
        <span
          className="text-[12px] font-bold tracking-[0.1em] uppercase"
          style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
        >
          {year}
        </span>
      </div>

      <BandShell loading={loading} error={error} onRetry={retry}>
        {/* Band B — Hero KPI row */}
        <CropHeroRow {...heroData} />

        {/* Band C — Yield trend with anomaly flags */}
        {yieldTrendData.length > 0 && (
          <YieldTrendChart
            data={yieldTrendData}
            commodity={commodityLabel}
            stateName={stateName}
            unit={heroData.yieldUnit}
          />
        )}

        {/* Band D — Profit + Harvest efficiency side by side */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-8">
          <ProfitChart data={profitData} commodity={commodityLabel} stateName={stateName} />
          <HarvestEfficiency data={efficiencyData} commodity={commodityLabel} stateName={stateName} />
        </div>

        {/* Band E — Crop progress / condition strip (seasonal) */}
        <CropProgressStrip
          conditionData={conditionData}
          commodity={commodityLabel}
          stateName={stateName}
        />
      </BandShell>
    </div>
  );
}
