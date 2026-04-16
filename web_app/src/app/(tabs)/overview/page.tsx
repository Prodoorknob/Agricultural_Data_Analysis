'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import { useFilters } from '@/hooks/useFilters';
import { LATEST_NASS_YEAR } from '@/lib/constants';
import { US_STATES, fetchStateData, fetchNationalCrops } from '@/utils/serviceData';
import { filterData, getTopCrops, getMapData } from '@/utils/processData';
import BandShell from '@/components/shared/BandShell';
import HeroStrip from '@/components/overview/HeroStrip';
import USChoropleth from '@/components/maps/USChoropleth';
import StateFingerprint from '@/components/overview/StateFingerprint';
import StoryCards from '@/components/overview/StoryCards';
import peerStatesMap from '@/data/peerStates.json';
import { COMMODITY_COLORS } from '@/lib/constants';

const peers = peerStatesMap as Record<string, string[]>;

export default function OverviewPage() {
  const { filters, setState } = useFilters();
  const stateCode = filters.state;
  const stateName = stateCode ? (US_STATES[stateCode] || stateCode) : 'United States';

  const [nationalData, setNationalData] = useState<any[]>([]);
  const [stateData, setStateData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load initial national data + state data
  useEffect(() => {
    setLoading(true);
    setError(null);
    const fetchData = async () => {
      try {
        const natl = await fetchNationalCrops();
        setNationalData(natl || []);
        if (stateCode) {
          const sd = await fetchStateData(stateCode);
          setStateData(sd || []);
        } else {
          setStateData([]);
        }
      } catch (e) {
        setError('Failed to load data. Check your connection and try again.');
      }
      setLoading(false);
    };
    fetchData();
  }, [stateCode]);

  // Read saved state from localStorage on first visit
  useEffect(() => {
    if (!stateCode && typeof window !== 'undefined') {
      const saved = localStorage.getItem('fieldpulse_state');
      if (saved && US_STATES[saved]) {
        setState(saved);
      }
    }
    // Only on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Derived data
  const activeData = useMemo(() => {
    const raw = stateCode ? stateData : nationalData;
    return filterData(raw);
  }, [stateCode, stateData, nationalData]);

  const year = LATEST_NASS_YEAR;

  // Hero strip data
  const heroData = useMemo(() => {
    const salesRows = activeData.filter(
      (r: any) => r.year === year && r.statisticcat_desc === 'SALES' && r.unit_desc === '$'
    );
    const totalSales = salesRows.reduce((s: number, r: any) => s + (r.value_num || 0), 0);

    const areaRows = activeData.filter(
      (r: any) => r.year === year && r.statisticcat_desc === 'AREA PLANTED' && r.unit_desc === 'ACRES'
    );
    const totalAcres = areaRows.reduce((s: number, r: any) => s + (r.value_num || 0), 0);
    const commodityCount = new Set(areaRows.map((r: any) => r.commodity_desc)).size;

    // Prior year acres for delta
    const priorAreaRows = activeData.filter(
      (r: any) => r.year === year - 1 && r.statisticcat_desc === 'AREA PLANTED' && r.unit_desc === 'ACRES'
    );
    const priorAcres = priorAreaRows.reduce((s: number, r: any) => s + (r.value_num || 0), 0);

    // Top crop by sales
    const topCrops = getTopCrops(activeData, year, 'SALES');
    const top = topCrops[0];

    // 5yr ago sales for growth
    const sales5yr = activeData
      .filter((r: any) => r.year === year - 5 && r.statisticcat_desc === 'SALES' && r.unit_desc === '$')
      .reduce((s: number, r: any) => s + (r.value_num || 0), 0);
    const salesGrowth = sales5yr > 0 ? ((totalSales - sales5yr) / sales5yr) * 100 : 0;

    return {
      stateName,
      stateCode,
      totalSales,
      salesRank: 0, // Would need all-states data to compute
      salesGrowthPct: Math.round(salesGrowth),
      totalAcresPlanted: totalAcres,
      acresDelta: totalAcres - priorAcres,
      acresDeltaDriver: top?.commodity || 'corn',
      topCrop: top?.commodity || 'N/A',
      topCropSales: top?.value || 0,
      topCropStreak: 5, // Placeholder
      commodityCount,
    };
  }, [activeData, stateName, stateCode, year]);

  // Map data — total sales per state (for national view we'd need all states)
  const mapData = useMemo(() => {
    if (nationalData.length > 0) {
      return getMapData(nationalData, year, 'SALES');
    }
    return {};
  }, [nationalData, year]);

  // State fingerprint data
  const fingerprintData = useMemo(() => {
    const topCrops = getTopCrops(activeData, year, 'SALES');
    const top6 = topCrops.slice(0, 6);
    const othersVal = topCrops.slice(6).reduce((s, c) => s + (c.value || 0), 0);

    const revenueMix = [
      ...top6.map((c, i) => ({
        commodity: c.commodity,
        sales: c.value || 0,
        color: COMMODITY_COLORS[c.commodity.toLowerCase()] || `var(--text3)`,
      })),
      ...(othersVal > 0 ? [{ commodity: 'Other', sales: othersVal, color: 'var(--muted)' }] : []),
    ];

    const totalRevenue = revenueMix.reduce((s, r) => s + r.sales, 0);

    // Sparklines — top 5 crops, 25 years of planted area
    const sparklines = top6.slice(0, 5).map((c) => {
      const vals = Array.from({ length: 25 }, (_, i) => {
        const y = year - 24 + i;
        const row = activeData.find(
          (r: any) =>
            r.year === y &&
            r.commodity_desc === c.commodity &&
            r.statisticcat_desc === 'AREA PLANTED'
        );
        return row?.value_num || 0;
      });
      return {
        commodity: c.commodity,
        values: vals,
        latestValue: vals[vals.length - 1] || 0,
      };
    });

    // Peer comparison
    const peerCodes = stateCode ? (peers[stateCode] || []) : [];
    const peerComparison = stateCode
      ? [
          { state: stateCode, value: heroData.totalSales },
          ...peerCodes.slice(0, 4).map((pc) => ({
            state: pc,
            value: 0, // Would need per-state data
          })),
        ]
      : [];

    return {
      revenueMix,
      totalRevenue,
      sparklines,
      peerComparison: peerComparison.filter((p) => p.value > 0),
      peerMetric: 'Total Sales',
      selectedState: stateCode,
    };
  }, [activeData, year, stateCode, heroData.totalSales]);

  const retry = useCallback(() => {
    setLoading(true);
    setError(null);
    const fetchData = async () => {
      try {
        const natl = await fetchNationalCrops();
        setNationalData(natl || []);
        if (stateCode) {
          const sd = await fetchStateData(stateCode);
          setStateData(sd || []);
        }
      } catch {
        setError('Failed to load data.');
      }
      setLoading(false);
    };
    fetchData();
  }, [stateCode]);

  return (
    <div>
      {/* Band A — Hero Strip */}
      <BandShell loading={loading} error={error} onRetry={retry}>
        <HeroStrip {...heroData} />
      </BandShell>

      {/* Pick your state prompt */}
      {!stateCode && !loading && (
        <div
          className="mb-6 px-4 py-2.5 rounded-[var(--radius-full)] inline-flex items-center gap-2"
          style={{ background: 'var(--field-subtle)' }}
        >
          <span
            className="text-[14px] font-semibold"
            style={{ color: 'var(--field)', fontFamily: 'var(--font-stat)' }}
          >
            Pick your state
          </span>
          <span className="text-[13px]" style={{ color: 'var(--text2)' }}>
            Click the map or use the filter above
          </span>
        </div>
      )}

      {/* Band B — Map + State Fingerprint */}
      <BandShell loading={loading} error={error} skeletonHeight={400}>
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-5 mb-8">
          <div className="lg:col-span-3">
            <USChoropleth
              data={mapData}
              selectedState={stateCode}
              onStateSelect={setState}
              metricLabel="Sales $"
            />
          </div>
          <div className="lg:col-span-2">
            <StateFingerprint {...fingerprintData} />
          </div>
        </div>
      </BandShell>

      {/* Band C — Story Cards */}
      <StoryCards />
    </div>
  );
}
