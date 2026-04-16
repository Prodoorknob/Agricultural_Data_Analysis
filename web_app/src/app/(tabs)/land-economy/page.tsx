'use client';

import { useEffect, useState, useMemo } from 'react';
import { useFilters } from '@/hooks/useFilters';
import { LATEST_NASS_YEAR } from '@/lib/constants';
import { US_STATES, fetchStateData, fetchNationalCrops } from '@/utils/serviceData';
import { filterData, getTopCrops, getOperationsTrend, getLaborTrends, getLandUseTrends } from '@/utils/processData';
import BandShell from '@/components/shared/BandShell';
import RevenueLeaderboard from '@/components/land-economy/RevenueLeaderboard';
import FarmStructure from '@/components/land-economy/FarmStructure';
import LandUseMix from '@/components/land-economy/LandUseMix';
import LaborWages from '@/components/land-economy/LaborWages';

const SECTIONS = [
  { id: 'revenue', label: 'Revenue' },
  { id: 'operations', label: 'Operations' },
  { id: 'land-use', label: 'Land Use' },
  { id: 'labor', label: 'Labor' },
];

export default function LandEconomyPage() {
  const { filters, setSection } = useFilters();
  const stateCode = filters.state;
  const stateName = stateCode ? (US_STATES[stateCode] || stateCode) : 'United States';
  const year = filters.year ?? LATEST_NASS_YEAR;
  const activeSection = filters.section || 'revenue';

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
        setError('Failed to load data.');
      }
      setLoading(false);
    })();
  }, [stateCode]);

  const filtered = useMemo(() => filterData(data), [data]);

  // Revenue leaderboard
  const revenueData = useMemo(() => {
    const topCrops = getTopCrops(filtered, year, 'SALES');
    const topCrops10yr = getTopCrops(filtered, year - 10, 'SALES');
    const priorMap = new Map(topCrops10yr.map((c: any) => [c.commodity, c.value || 0]));

    return topCrops.map((c: any) => {
      const prior = priorMap.get(c.commodity) || 0;
      const growth = prior > 0 ? ((c.value - prior) / prior) * 100 : 0;
      return { commodity: c.commodity, sales: c.value || 0, growthPct10yr: growth };
    });
  }, [filtered, year]);

  // Farm structure
  const farmStructure = useMemo(() => {
    const opsTrend = getOperationsTrend(filtered);
    return opsTrend.map((d: any) => {
      const areaRows = filtered.filter(
        (r: any) => r.year === d.year && r.statisticcat_desc === 'AREA PLANTED'
      );
      const totalAcres = areaRows.reduce((s: number, r: any) => s + (r.value_num || 0), 0);
      return {
        year: d.year,
        operationsCount: d.count || 0,
        avgFarmSize: d.count > 0 ? Math.round(totalAcres / d.count) : 0,
      };
    }).filter((d: any) => d.operationsCount > 0);
  }, [filtered]);

  // Land use
  const landUseData = useMemo(() => {
    const trends = getLandUseTrends(filtered);
    if (!trends || !Array.isArray(trends)) return [];
    return trends.map((d: any) => ({
      year: d.year,
      cropland: d.planted || 0,
      pasture: 0,
      forest: 0,
      urban: 0,
      other: d.harvested || 0,
    }));
  }, [filtered]);

  // Labor wages
  const laborData = useMemo(() => {
    const labor = getLaborTrends(filtered, stateCode || undefined);
    if (!labor || !Array.isArray(labor)) return { wageTrend: [], wageRanking: [] };
    const wageTrend = labor.map((d: any) => ({
      year: d.year,
      stateWage: d.stateWage || d.value || 0,
      nationalWage: d.nationalWage || 0,
    })).filter((d: any) => d.stateWage > 0);
    return { wageTrend, wageRanking: [] as any[] };
  }, [filtered, stateCode]);

  return (
    <div>
      {/* Section rail */}
      <div className="flex items-center gap-1.5 mb-6 overflow-x-auto">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            onClick={() => {
              setSection(s.id);
              document.getElementById(s.id)?.scrollIntoView({ behavior: 'smooth' });
            }}
            className="px-3 py-1.5 text-[13px] font-medium rounded-[var(--radius-full)] border transition-all shrink-0"
            style={{
              background: activeSection === s.id ? 'var(--field)' : 'transparent',
              color: activeSection === s.id ? '#FFFFFF' : 'var(--text2)',
              borderColor: activeSection === s.id ? 'var(--field)' : 'var(--border2)',
              fontFamily: 'var(--font-body)',
            }}
          >
            {s.label}
          </button>
        ))}
      </div>

      <h1 className="text-[28px] font-extrabold tracking-[-0.02em] mb-6"
        style={{ color: 'var(--text)', fontFamily: 'var(--font-body)' }}>
        Land & Economy — {stateName}
      </h1>

      <BandShell loading={loading} error={error} skeletonHeight={400}>
        <RevenueLeaderboard data={revenueData} stateName={stateName} year={year} />
        <FarmStructure data={farmStructure} stateName={stateName} />
        <LandUseMix data={landUseData} stateName={stateName} />
        <LaborWages wageTrend={laborData.wageTrend} wageRanking={laborData.wageRanking} stateName={stateName} />
      </BandShell>
    </div>
  );
}
