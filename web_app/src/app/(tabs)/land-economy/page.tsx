'use client';

import { useEffect, useState, useMemo } from 'react';
import { useFilters } from '@/hooks/useFilters';
import { LATEST_NASS_YEAR } from '@/lib/constants';
import { US_STATES, fetchStateData, fetchNationalCrops } from '@/utils/serviceData';
import { filterData, getTopCrops, getOperationsTrend, getLaborTrends } from '@/utils/processData';
import {
  fetchStateCommodityTotals,
  fetchLandUse,
  fetchBlsEstablishments,
  type StateCommodityRow,
  type LandUseRow,
  type BlsEstablishmentRow,
} from '@/utils/overviewData';
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

// State alpha → FIPS (2-digit zero-padded). Needed because the BLS QCEW
// parquet keys rows by FIPS, while the rest of the app uses 2-letter alpha.
const STATE_ALPHA_TO_FIPS: Record<string, string> = {
  AL: '01', AK: '02', AZ: '04', AR: '05', CA: '06', CO: '08', CT: '09', DE: '10',
  FL: '12', GA: '13', HI: '15', ID: '16', IL: '17', IN: '18', IA: '19', KS: '20',
  KY: '21', LA: '22', ME: '23', MD: '24', MA: '25', MI: '26', MN: '27', MS: '28',
  MO: '29', MT: '30', NE: '31', NV: '32', NH: '33', NJ: '34', NM: '35', NY: '36',
  NC: '37', ND: '38', OH: '39', OK: '40', OR: '41', PA: '42', RI: '44', SC: '45',
  SD: '46', TN: '47', TX: '48', UT: '49', VT: '50', VA: '51', WA: '53', WV: '54',
  WI: '55', WY: '56',
};

export default function LandEconomyPage() {
  const { filters, setSection } = useFilters();
  const stateCode = filters.state;
  const stateName = stateCode ? (US_STATES[stateCode] || stateCode) : 'United States';
  const year = filters.year ?? LATEST_NASS_YEAR;
  const activeSection = filters.section || 'revenue';

  const [data, setData] = useState<any[]>([]);
  const [aggCommodity, setAggCommodity] = useState<StateCommodityRow[]>([]);
  const [landUseRaw, setLandUseRaw] = useState<LandUseRow[]>([]);
  const [blsRaw, setBlsRaw] = useState<BlsEstablishmentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    const controller = new AbortController();
    let cancelled = false;
    (async () => {
      // Use allSettled so one failing overview parquet doesn't blow up the
      // whole page — the raw NASS fetch is the only one the core sections
      // truly require.
      const [rawRes, aggRes, landUseRes, blsRes] = await Promise.allSettled([
        stateCode
          ? fetchStateData(stateCode, controller.signal)
          : fetchNationalCrops(controller.signal),
        fetchStateCommodityTotals(controller.signal),
        fetchLandUse(controller.signal),
        fetchBlsEstablishments(controller.signal),
      ]);
      if (cancelled) return;
      if (rawRes.status === 'fulfilled') {
        setData(rawRes.value || []);
      } else if ((rawRes.reason as any)?.name !== 'AbortError') {
        setError('Failed to load data.');
      }
      setAggCommodity(aggRes.status === 'fulfilled' ? aggRes.value || [] : []);
      setLandUseRaw(landUseRes.status === 'fulfilled' ? landUseRes.value || [] : []);
      setBlsRaw(blsRes.status === 'fulfilled' ? blsRes.value || [] : []);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [stateCode]);

  const filtered = useMemo(() => filterData(data), [data]);

  // Revenue leaderboard — sourced from state_commodity_totals aggregate
  // which carries group_desc / sector_desc for crop-type filtering. Boom /
  // decline are computed against 2012 Census rather than a rolling 10-yr
  // window so the baseline is a stable denominator (SURVEY year sales can
  // be sparse and inflate apparent growth).
  const CENSUS_BASELINE_YEAR = 2012;

  const revenueAllCommodities = useMemo(() => {
    const rowsThisYear = aggCommodity.filter(
      (r) =>
        r.year === year &&
        (!stateCode || r.state_alpha === stateCode) &&
        (r.sales_usd ?? 0) > 0,
    );
    const rowsBaseline = aggCommodity.filter(
      (r) =>
        r.year === CENSUS_BASELINE_YEAR &&
        (!stateCode || r.state_alpha === stateCode) &&
        (r.sales_usd ?? 0) > 0,
    );
    const priorMap = new Map<string, number>();
    rowsBaseline.forEach((r) => {
      priorMap.set(
        r.commodity_desc,
        (priorMap.get(r.commodity_desc) ?? 0) + (r.sales_usd ?? 0),
      );
    });

    // Aggregate sales_usd across matching rows (national rollup sums all
    // states). Keep the first non-null group_desc per commodity.
    const agg = new Map<
      string,
      { sales: number; group_desc: string | null; sector_desc: string | null }
    >();
    rowsThisYear.forEach((r) => {
      const current = agg.get(r.commodity_desc) ?? {
        sales: 0,
        group_desc: null as string | null,
        sector_desc: null as string | null,
      };
      current.sales += r.sales_usd ?? 0;
      current.group_desc = current.group_desc || r.group_desc;
      current.sector_desc = current.sector_desc || r.sector_desc;
      agg.set(r.commodity_desc, current);
    });

    return Array.from(agg.entries()).map(([commodity, v]) => {
      const baseline = priorMap.get(commodity) ?? 0;
      const growthPct = baseline > 0 ? ((v.sales - baseline) / baseline) * 100 : 0;
      return {
        commodity,
        sales: v.sales,
        growthPctVsCensus: growthPct,
        group_desc: v.group_desc,
        sector_desc: v.sector_desc,
      };
    });
  }, [aggCommodity, stateCode, year]);

  // NASS fallback when the aggregate is empty (e.g. parquet fetch failed).
  const revenueNassFallback = useMemo(() => {
    if (revenueAllCommodities.length > 0) return [];
    const topCrops = getTopCrops(filtered, year, 'SALES');
    const topBaseline = getTopCrops(filtered, CENSUS_BASELINE_YEAR, 'SALES');
    const priorMap = new Map(topBaseline.map((c: any) => [c.commodity, c.value || 0]));
    return topCrops.map((c: any) => ({
      commodity: c.commodity,
      sales: c.value || 0,
      growthPctVsCensus: priorMap.get(c.commodity)
        ? ((c.value - (priorMap.get(c.commodity) as number)) /
            (priorMap.get(c.commodity) as number)) *
          100
        : 0,
      group_desc: null as string | null,
      sector_desc: null as string | null,
    }));
  }, [filtered, year, revenueAllCommodities.length]);

  const revenueData = revenueAllCommodities.length > 0 ? revenueAllCommodities : revenueNassFallback;

  // Farm structure — key mismatch fix: `getOperationsTrend` returns
  // {year, operations}, not {year, count}.
  const farmStructure = useMemo(() => {
    const opsTrend = getOperationsTrend(filtered);
    return opsTrend
      .map((d: any) => {
        const areaRows = filtered.filter(
          (r: any) => r.year === d.year && r.statisticcat_desc === 'AREA PLANTED',
        );
        const totalAcres = areaRows.reduce((s: number, r: any) => s + (r.value_num || 0), 0);
        const opsCount = d.operations || 0;
        return {
          year: d.year,
          operationsCount: opsCount,
          avgFarmSize: opsCount > 0 ? Math.round(totalAcres / opsCount) : 0,
        };
      })
      .filter((d: any) => d.operationsCount > 0);
  }, [filtered]);

  // Land use — consume the pre-computed land_use.parquet aggregate and pivot
  // to one row per year with the 6 category columns. When a state is
  // selected, filter by state_alpha; national view sums across states.
  const landUseData = useMemo(() => {
    if (landUseRaw.length === 0) return [];
    const rows = stateCode
      ? landUseRaw.filter((r) => r.state_alpha === stateCode)
      : landUseRaw;
    const byYear = new Map<
      number,
      { year: number; cropland: number; pasture: number; forest: number; urban: number; special: number; other: number }
    >();
    for (const r of rows) {
      if (r.year == null || !r.category) continue;
      const bucket = byYear.get(r.year) ?? {
        year: r.year,
        cropland: 0,
        pasture: 0,
        forest: 0,
        urban: 0,
        special: 0,
        other: 0,
      };
      (bucket as any)[r.category] = ((bucket as any)[r.category] ?? 0) + (r.acres ?? 0);
      byYear.set(r.year, bucket);
    }
    return Array.from(byYear.values()).sort((a, b) => a.year - b.year);
  }, [landUseRaw, stateCode]);

  // Labor wages — fix key mismatch (`getLaborTrends` returns rows shaped
  // like {year, 'National Avg', IN, IL, ...}) and overlay BLS QCEW
  // avg_annual_pay (NAICS 111, crop production) which is denser than NASS
  // WAGE RATE post-2014.
  const laborData = useMemo(() => {
    const labor = getLaborTrends(filtered, stateCode || undefined);
    const nassTrend = Array.isArray(labor)
      ? labor.map((d: any) => ({
          year: d.year,
          stateWage: stateCode ? d[stateCode] : undefined,
          nationalWage: d['National Avg'],
        }))
      : [];

    const blsByYear = new Map<number, number>();
    const stateFips = stateCode ? STATE_ALPHA_TO_FIPS[stateCode] : undefined;
    const blsCropScope = stateCode
      ? blsRaw.filter((r) => r.state_fips === stateFips && String(r.naics) === '111')
      : blsRaw.filter((r) => String(r.naics) === '111');
    // National view: mean avg_annual_pay across states per year. State view:
    // the one row for that (state, year).
    const nationalAcc = new Map<number, { sum: number; n: number }>();
    for (const r of blsCropScope) {
      const pay = r.avg_annual_pay ?? null;
      if (pay == null || r.year == null) continue;
      if (stateFips) {
        blsByYear.set(r.year, pay);
      } else {
        const acc = nationalAcc.get(r.year) ?? { sum: 0, n: 0 };
        acc.sum += pay;
        acc.n += 1;
        nationalAcc.set(r.year, acc);
      }
    }
    if (!stateFips) {
      for (const [y, { sum, n }] of nationalAcc) {
        if (n > 0) blsByYear.set(y, sum / n);
      }
    }

    // Merge by year.
    const years = new Set<number>([
      ...nassTrend.map((d) => d.year),
      ...blsByYear.keys(),
    ]);
    const wageTrend = Array.from(years)
      .sort((a, b) => a - b)
      .map((y) => {
        const nass = nassTrend.find((d) => d.year === y);
        return {
          year: y,
          stateWage: nass?.stateWage,
          nationalWage: nass?.nationalWage,
          blsAnnualPay: blsByYear.get(y),
        };
      })
      .filter((d) => d.stateWage != null || d.nationalWage != null || d.blsAnnualPay != null);

    return { wageTrend, wageRanking: [] as any[] };
  }, [filtered, stateCode, blsRaw]);

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
