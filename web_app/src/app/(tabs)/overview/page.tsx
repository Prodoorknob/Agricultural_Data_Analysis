'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import { useFilters } from '@/hooks/useFilters';
import { LATEST_NASS_YEAR, COMMODITY_COLORS } from '@/lib/constants';
import { US_STATES } from '@/utils/serviceData';
import {
  fetchStateTotals,
  fetchStateCommodityTotals,
  fetchCountyMetrics,
  type StateTotalRow,
  type StateCommodityRow,
  type CountyMetricRow,
} from '@/utils/overviewData';
import BandShell from '@/components/shared/BandShell';
import HeroStrip from '@/components/overview/HeroStrip';
import USChoropleth from '@/components/maps/USChoropleth';
import StateFingerprint from '@/components/overview/StateFingerprint';
import StoryCards from '@/components/overview/StoryCards';
import peerStatesMap from '@/data/peerStates.json';

const peers = peerStatesMap as Record<string, string[]>;

// Census years since 2012 give a dense, commodity-complete baseline that
// non-Census years lack. Using year-5 against a sparse baseline was the
// cause of the Overview hero's +15487% growth artifact.
const GROWTH_BASE_YEAR = 2022;

export default function OverviewPage() {
  const { filters, setState } = useFilters();
  const stateCode = filters.state;
  const stateName = stateCode ? US_STATES[stateCode] || stateCode : 'United States';

  const [stateTotals, setStateTotals] = useState<StateTotalRow[]>([]);
  const [stateCommodityTotals, setStateCommodityTotals] = useState<StateCommodityRow[]>([]);
  const [countyMetrics, setCountyMetrics] = useState<CountyMetricRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // One-time load of the two small aggregates that serve national + state view.
  useEffect(() => {
    const ac = new AbortController();
    setLoading(true);
    setError(null);
    Promise.all([
      fetchStateTotals(ac.signal),
      fetchStateCommodityTotals(ac.signal),
    ])
      .then(([totals, commodities]) => {
        setStateTotals(totals);
        setStateCommodityTotals(commodities);
      })
      .catch((e) => {
        if ((e as { name?: string })?.name !== 'AbortError') {
          setError('Failed to load overview aggregates.');
        }
      })
      .finally(() => setLoading(false));
    return () => ac.abort();
  }, []);

  // County data only loads when a state is selected (drives the drill-down map).
  useEffect(() => {
    if (!stateCode) {
      setCountyMetrics([]);
      return;
    }
    const ac = new AbortController();
    fetchCountyMetrics(stateCode, ac.signal)
      .then(setCountyMetrics)
      .catch(() => setCountyMetrics([]));
    return () => ac.abort();
  }, [stateCode]);

  // Read saved state from localStorage on first visit.
  useEffect(() => {
    if (!stateCode && typeof window !== 'undefined') {
      const saved = localStorage.getItem('fieldpulse_state');
      if (saved && US_STATES[saved]) setState(saved);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const year = LATEST_NASS_YEAR;

  // All rows for the current year — shared by hero / map / peer panel.
  const currentYearTotals = useMemo(
    () => stateTotals.filter((r) => r.year === year),
    [stateTotals, year],
  );

  // Hero strip data — draws from state_totals when a state is selected,
  // else sums national. Rank is computed from the sorted row.
  const heroData = useMemo(() => {
    if (stateCode) {
      const row = currentYearTotals.find((r) => r.state_alpha === stateCode);
      const priorRow = stateTotals.find(
        (r) => r.year === GROWTH_BASE_YEAR && r.state_alpha === stateCode,
      );
      const priorAcreRow = stateTotals.find(
        (r) => r.year === year - 1 && r.state_alpha === stateCode,
      );
      const sales = row?.total_sales_usd || 0;
      const priorSales = priorRow?.total_sales_usd || 0;
      const growth = priorSales > 0 ? ((sales - priorSales) / priorSales) * 100 : 0;
      const acres = row?.total_area_planted_acres || 0;
      const priorAcres = priorAcreRow?.total_area_planted_acres || 0;
      const acresDelta = acres - priorAcres;

      // Top crop + streak: same top-commodity 5 years running?
      let streak = 0;
      for (let i = 0; i < 6; i += 1) {
        const y = stateTotals.find(
          (r) => r.year === year - i && r.state_alpha === stateCode,
        );
        if (y && y.top_commodity === row?.top_commodity) streak += 1;
        else break;
      }

      return {
        stateName,
        stateCode,
        totalSales: sales,
        salesRank: row?.rank_by_sales || 0,
        salesGrowthPct: Math.round(growth),
        salesGrowthBaseYear: GROWTH_BASE_YEAR,
        totalAcresPlanted: acres,
        acresDelta,
        acresDeltaDriver: row?.top_commodity || 'corn',
        topCrop: row?.top_commodity || 'N/A',
        topCropSales: row?.top_commodity_sales_usd || 0,
        topCropStreak: streak,
        commodityCount: row?.commodity_count || 0,
      };
    }

    // National rollup
    const totalSales = currentYearTotals.reduce((s, r) => s + (r.total_sales_usd || 0), 0);
    const priorSales = stateTotals
      .filter((r) => r.year === GROWTH_BASE_YEAR)
      .reduce((s, r) => s + (r.total_sales_usd || 0), 0);
    const growth = priorSales > 0 ? ((totalSales - priorSales) / priorSales) * 100 : 0;
    const totalAcres = currentYearTotals.reduce(
      (s, r) => s + (r.total_area_planted_acres || 0),
      0,
    );
    const priorAcres = stateTotals
      .filter((r) => r.year === year - 1)
      .reduce((s, r) => s + (r.total_area_planted_acres || 0), 0);

    // National top crop — aggregate commodity sales across states.
    const byCommodity = new Map<string, number>();
    stateCommodityTotals
      .filter((r) => r.year === year)
      .forEach((r) => {
        if (r.sales_usd) {
          byCommodity.set(r.commodity_desc, (byCommodity.get(r.commodity_desc) || 0) + r.sales_usd);
        }
      });
    let topCom = 'N/A', topComVal = 0;
    for (const [c, v] of byCommodity) {
      if (v > topComVal) { topCom = c; topComVal = v; }
    }

    return {
      stateName: 'United States',
      stateCode: null,
      totalSales,
      salesRank: 0,
      salesGrowthPct: Math.round(growth),
      salesGrowthBaseYear: GROWTH_BASE_YEAR,
      totalAcresPlanted: totalAcres,
      acresDelta: totalAcres - priorAcres,
      acresDeltaDriver: topCom,
      topCrop: topCom,
      topCropSales: topComVal,
      topCropStreak: 1,
      commodityCount: byCommodity.size,
    };
  }, [currentYearTotals, stateTotals, stateCommodityTotals, stateCode, stateName, year]);

  // Choropleth map data — state_alpha → total sales for the current year.
  const mapData = useMemo(() => {
    const map: Record<string, number> = {};
    currentYearTotals.forEach((r) => {
      if (r.total_sales_usd) map[r.state_alpha] = r.total_sales_usd;
    });
    return map;
  }, [currentYearTotals]);

  // County-drill-down data for the selected state, year = latest.
  const countyMap = useMemo(() => {
    if (!stateCode) return {};
    const map: Record<string, number> = {};
    countyMetrics
      .filter((r) => r.year === year)
      .forEach((r) => {
        // Use area_harvested as the density metric — available for more
        // (fips, commodity) combos than production or yield. Sum across
        // commodities to get "total harvested acres per county".
        if (r.fips && r.area_harvested_acres) {
          map[r.fips] = (map[r.fips] || 0) + r.area_harvested_acres;
        }
      });
    return map;
  }, [countyMetrics, stateCode, year]);

  // State-fingerprint data.
  const fingerprintData = useMemo(() => {
    const state = stateCode || null;
    const commoditiesThisYear = stateCommodityTotals.filter(
      (r) => r.year === year && r.sales_usd && (!state || r.state_alpha === state),
    );

    // Roll up by commodity (for national view) or just filter (for state view).
    const byCommodity = new Map<string, number>();
    commoditiesThisYear.forEach((r) => {
      byCommodity.set(
        r.commodity_desc,
        (byCommodity.get(r.commodity_desc) || 0) + (r.sales_usd || 0),
      );
    });

    const sorted = [...byCommodity.entries()].sort((a, b) => b[1] - a[1]);
    const top6 = sorted.slice(0, 6);
    const othersVal = sorted.slice(6).reduce((s, [, v]) => s + v, 0);
    const revenueMix = [
      ...top6.map(([commodity, sales]) => ({
        commodity,
        sales,
        color: COMMODITY_COLORS[commodity.toLowerCase()] || 'var(--text3)',
      })),
      ...(othersVal > 0
        ? [{ commodity: 'Other', sales: othersVal, color: 'var(--muted)' }]
        : []),
    ];
    const totalRevenue = revenueMix.reduce((s, r) => s + r.sales, 0);

    // 25-year sparklines — top 5 commodities by current-year sales. Sum
    // across states for national view, filter to single state otherwise.
    // Area_planted preferred; area_harvested fallback for commodities like
    // HAY that publish only harvested acres.
    const topCommodities = top6.slice(0, 5).map(([c]) => c);
    const sparklines = topCommodities.map((commodity) => {
      const values = Array.from({ length: 25 }, (_, i) => {
        const y = year - 24 + i;
        const rows = stateCommodityTotals.filter(
          (r) =>
            r.year === y &&
            r.commodity_desc === commodity &&
            (!state || r.state_alpha === state),
        );
        const planted = rows.reduce((s, r) => s + (r.area_planted_acres || 0), 0);
        const harvested = rows.reduce((s, r) => s + (r.area_harvested_acres || 0), 0);
        return planted > 0 ? planted : harvested;
      });
      return {
        commodity,
        values,
        latestValue: values[values.length - 1] || 0,
      };
    });

    // Peer comparison — look up each peer state's current-year total sales.
    const peerCodes = state ? peers[state] || [] : [];
    const peerComparison = state
      ? [
          {
            state,
            value: currentYearTotals.find((r) => r.state_alpha === state)?.total_sales_usd || 0,
          },
          ...peerCodes.slice(0, 4).map((pc) => ({
            state: pc,
            value: currentYearTotals.find((r) => r.state_alpha === pc)?.total_sales_usd || 0,
          })),
        ].filter((p) => p.value > 0)
      : [];

    return {
      revenueMix,
      totalRevenue,
      sparklines,
      peerComparison,
      peerMetric: 'Total Sales',
      selectedState: state,
    };
  }, [stateCommodityTotals, currentYearTotals, stateCode, year]);

  const retry = useCallback(() => {
    setLoading(true);
    setError(null);
    const ac = new AbortController();
    Promise.all([
      fetchStateTotals(ac.signal),
      fetchStateCommodityTotals(ac.signal),
    ])
      .then(([t, c]) => {
        setStateTotals(t);
        setStateCommodityTotals(c);
      })
      .catch(() => setError('Failed to load.'))
      .finally(() => setLoading(false));
  }, []);

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

      {/* Band B — Map + State Fingerprint. Grid uses `items-stretch` so
          the choropleth container stretches to match the fingerprint column's
          taller content, eliminating the empty space below the old fixed-height map. */}
      <BandShell loading={loading} error={error} skeletonHeight={400}>
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-5 mb-8 items-stretch">
          <div className="lg:col-span-3 min-h-[560px]">
            <USChoropleth
              data={stateCode ? countyMap : mapData}
              selectedState={stateCode}
              onStateSelect={setState}
              metricLabel={stateCode ? 'Harvested acres' : 'Sales $'}
              mode={stateCode ? 'county' : 'state'}
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
