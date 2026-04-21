'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import { useFilters } from '@/hooks/useFilters';
import { LATEST_NASS_YEAR, CROP_COMMODITIES } from '@/lib/constants';
import {
  US_STATES, fetchStateData, fetchNationalCrops, fetchCountyData, fetchCountyPrecip, fetchIrrigatedCountyAcres,
} from '@/utils/serviceData';
import { filterData, getCommodityStory, detectAnomalies, getTopCrops, getCropConditionTrends } from '@/utils/processData';
import BandShell from '@/components/shared/BandShell';
import CommodityPicker from '@/components/shared/CommodityPicker';
import CropHeroRow from '@/components/crops/CropHeroRow';
import YieldTrendChart from '@/components/crops/YieldTrendChart';
import ProfitChart from '@/components/crops/ProfitChart';
import HarvestEfficiency from '@/components/crops/HarvestEfficiency';
import CropProgressStrip from '@/components/crops/CropProgressStrip';
import CropsStateMap, { rollupByCounty } from '@/components/crops/CropsStateMap';
import CropsPeers from '@/components/crops/CropsPeers';
import CropsCountyDrill from '@/components/crops/CropsCountyDrill';

// Backend /api/v1/crops/profit-history accepts these keys. Frontend stores
// commodity uppercase with plural for 'SOYBEANS' / 'PEANUTS', so normalize
// before hitting the endpoint.
const PROFIT_COMMODITY_MAP: Record<string, string> = {
  corn: 'corn',
  soybeans: 'soybean',
  soybean: 'soybean',
  wheat: 'wheat',
  cotton: 'cotton',
  rice: 'rice',
  peanuts: 'peanut',
  peanut: 'peanut',
  sorghum: 'sorghum',
  oats: 'oats',
  barley: 'barley',
};

interface ProfitPoint {
  year: number;
  price: number | null;
  price_unit: string | null;
  yield_value: number | null;
  yield_unit: string | null;
  revenue_per_acre: number | null;
  variable_cost_per_acre: number | null;
  total_cost_per_acre: number | null;
  profit_per_acre: number | null;
}

interface ProfitHistoryResponse {
  commodity: string;
  state: string;
  cost_source: string | null;
  note: string | null;
  points: ProfitPoint[];
}

export default function CropsPage() {
  const { filters, setCommodity } = useFilters();
  const stateCode = filters.state;
  const stateName = stateCode ? (US_STATES[stateCode] || stateCode) : 'United States';
  const commodity = (filters.commodity || 'corn').toUpperCase();
  const year = filters.year ?? LATEST_NASS_YEAR;

  const [stateData, setStateData] = useState<any[]>([]);
  const [nationalData, setNationalData] = useState<any[]>([]);
  const [countyData, setCountyData] = useState<any[]>([]);
  const [precipByFips, setPrecipByFips] = useState<Map<string, any>>(new Map());
  const [irrigatedByFipsCrop, setIrrigatedByFipsCrop] = useState<Map<string, number>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedFips, setSelectedFips] = useState<string | null>(null);

  // Reset drill-down when state or crop changes
  useEffect(() => {
    setSelectedFips(null);
  }, [stateCode, commodity]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const [sd, nd, cd] = await Promise.all([
          stateCode ? fetchStateData(stateCode) : Promise.resolve([]),
          fetchNationalCrops(),
          stateCode ? fetchCountyData(stateCode) : Promise.resolve([]),
        ]);
        setStateData(sd || []);
        setNationalData(nd || []);
        setCountyData(cd || []);
      } catch {
        setError('Failed to load crop data.');
      }
      setLoading(false);
    })();
  }, [stateCode]);

  // Enrichments (load once per session — small nationwide parquets/JSONs)
  useEffect(() => {
    (async () => {
      try {
        const [precipRows, irrRows] = await Promise.all([
          fetchCountyPrecip(),
          fetchIrrigatedCountyAcres(),
        ]);
        const pm = new Map<string, any>();
        for (const r of precipRows || []) {
          if (r.fips) pm.set(String(r.fips), r);
        }
        setPrecipByFips(pm);
        const im = new Map<string, number>();
        for (const r of irrRows || []) {
          // prefer most-recent census year when both 2017 and 2022 present
          const key = `${r.fips}|${String(r.crop || '').toLowerCase()}`;
          const existing = im.get(key);
          const yr = Number(r.year);
          if (!existing || yr > 0) im.set(key, Number(r.irrigated_acres));
        }
        setIrrigatedByFipsCrop(im);
      } catch (err) {
        console.warn('[enrichments] load failed', err);
      }
    })();
  }, []);

  const activeData = useMemo(() => filterData(stateCode ? stateData : nationalData), [stateCode, stateData, nationalData]);

  // County-level rollup for the map + peers + drill. filterData applies the
  // same reference_period / source / class filters we fixed earlier, so the
  // county numbers stay consistent with the state KPIs.
  const filteredCountyData = useMemo(() => filterData(countyData), [countyData]);
  const countyRollup = useMemo(
    () => rollupByCounty(filteredCountyData, commodity, year),
    [filteredCountyData, commodity, year],
  );

  const handleCountyClick = useCallback((fips: string) => setSelectedFips(fips), []);
  const handleCountyClose = useCallback(() => setSelectedFips(null), []);

  // Esc key dismiss
  useEffect(() => {
    if (!selectedFips) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setSelectedFips(null); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectedFips]);

  // Commodity story — 25 years of merged metrics
  const storyResult = useMemo(() => getCommodityStory(activeData, commodity), [activeData, commodity]);
  const story = storyResult?.story || [];

  // Hero KPI data
  const heroData = useMemo(() => {
    const thisYear = story.find((s: any) => s.year === year);
    const priorYear = story.find((s: any) => s.year === year - 1);
    // 5-year average: exclude years where yield is 0/missing. Census years
    // (2017, 2012) don't always have a SURVEY yield row for every commodity —
    // averaging 0s in drags the baseline down ~20% and makes the delta card
    // lie about how the current year compares.
    const fiveYearYields = story
      .filter((s: any) => s.year >= year - 5 && s.year <= year - 1)
      .map((s: any) => s.yield || 0)
      .filter((v: number) => v > 0);
    const avg5yr = fiveYearYields.length > 0
      ? fiveYearYields.reduce((s: number, v: number) => s + v, 0) / fiveYearYields.length
      : 0;

    const yieldNow = thisYear?.yield || 0;
    const yieldDelta = avg5yr > 0 ? ((yieldNow - avg5yr) / avg5yr) * 100 : 0;

    const areaNow = thisYear?.areaPlanted || 0;
    const areaPrior = priorYear?.areaPlanted || 0;
    const areaDelta = areaPrior > 0 ? ((areaNow - areaPrior) / areaPrior) * 100 : 0;

    // Operations count — NASS OPERATIONS is dense only in Census years
    // (2002, 2007, 2012, 2017, 2022). Walk a fallback chain so the card
    // still shows something reasonable in non-Census years.
    //
    // Use the pre-filter raw dataset: filterData() drops CENSUS rows that
    // aren't SALES+$, so CENSUS-sourced OPERATIONS rows would otherwise
    // vanish.
    const rawForOps = stateCode ? stateData : nationalData;
    const sumOpsForYear = (y: number) =>
      rawForOps
        .filter(
          (r: any) =>
            r.year === y &&
            r.commodity_desc === commodity &&
            r.statisticcat_desc === 'OPERATIONS' &&
            !r.commodity_desc?.includes('TOTAL') &&
            !r.commodity_desc?.includes('ALL CLASSES') &&
            (r.domain_desc === 'TOTAL' || !r.domain_desc),
        )
        .reduce((s: number, r: any) => s + (r.value_num || 0), 0);

    const latestCandidates = [year, year - 1, 2022, 2017, 2012, 2007, 2002];
    let opsCount = 0;
    let opsYearUsed: number | null = null;
    for (const y of latestCandidates) {
      const v = sumOpsForYear(y);
      if (v > 0) {
        opsCount = v;
        opsYearUsed = y;
        break;
      }
    }

    // Baseline: first available Census year to ground the delta.
    const baselineCandidates = [2002, 2007, 2012];
    let opsCountBaseline = 0;
    let opsBaselineYear: number | null = null;
    for (const y of baselineCandidates) {
      if (y >= (opsYearUsed ?? 9999)) break; // baseline must be strictly before latest
      const v = sumOpsForYear(y);
      if (v > 0) {
        opsCountBaseline = v;
        opsBaselineYear = y;
        break;
      }
    }
    const opsDelta = opsCountBaseline > 0 ? ((opsCount - opsCountBaseline) / opsCountBaseline) * 100 : 0;

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
      operationsYearUsed: opsYearUsed,
      operationsBaselineYear: opsBaselineYear,
      totalSales: salesNow,
      salesYoyDelta: salesDelta,
      salesShareOfState: salesShare,
      stateName,
      commodity: commodity.charAt(0) + commodity.slice(1).toLowerCase(),
    };
  }, [story, activeData, stateData, nationalData, stateCode, year, commodity, stateName]);

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

  // Profit data — fetched from /api/v1/crops/profit-history. When the tab
  // is on national view there's no state parquet for ERS to anchor yields
  // against, so default to Iowa (a reasonable corn/soy baseline) and
  // caption that substitution below the chart.
  const [profitHistory, setProfitHistory] = useState<ProfitHistoryResponse | null>(null);

  useEffect(() => {
    const backendKey = PROFIT_COMMODITY_MAP[commodity.toLowerCase()];
    if (!backendKey) {
      setProfitHistory(null);
      return;
    }
    const stateForEndpoint = stateCode || 'IA';
    const base = process.env.NEXT_PUBLIC_PREDICTION_API_URL || 'http://localhost:8000';
    const controller = new AbortController();
    fetch(
      `${base}/api/v1/crops/profit-history?commodity=${backendKey}&state=${stateForEndpoint}`,
      { signal: controller.signal },
    )
      .then((r) => (r.ok ? r.json() : null))
      .then((data: ProfitHistoryResponse | null) => setProfitHistory(data))
      .catch((err: unknown) => {
        if ((err as { name?: string })?.name !== 'AbortError') setProfitHistory(null);
      });
    return () => controller.abort();
  }, [commodity, stateCode]);

  const profitData = useMemo(() => {
    if (!profitHistory) return [];
    return profitHistory.points
      .filter((p) => p.profit_per_acre != null)
      .map((p) => ({ year: p.year, profitPerAcre: p.profit_per_acre as number }))
      .sort((a, b) => a.year - b.year);
  }, [profitHistory]);

  const profitNote = profitHistory?.note ?? null;
  const profitIowaFallback = !stateCode;

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
        const [sd, nd, cd] = await Promise.all([
          stateCode ? fetchStateData(stateCode) : Promise.resolve([]),
          fetchNationalCrops(),
          stateCode ? fetchCountyData(stateCode) : Promise.resolve([]),
        ]);
        setStateData(sd || []);
        setNationalData(nd || []);
        setCountyData(cd || []);
      } catch {
        setError('Failed to load crop data.');
      }
      setLoading(false);
    })();
  }, [stateCode]);

  const commodityLabel = commodity.charAt(0) + commodity.slice(1).toLowerCase();

  // When a state is selected, restrict the picker to commodities actually
  // grown there in the last 3 years (AREA PLANTED > 0). National view keeps
  // the full list. Mapping between NASS `commodity_desc` (uppercase, plural
  // only for a few crops) and the frontend `CROP_COMMODITIES` keys is
  // looser than exact match — we compare uppercased frontend labels.
  const grownInStateCommodities = useMemo(() => {
    if (!stateCode) return CROP_COMMODITIES;
    const latest = LATEST_NASS_YEAR;
    const threeYears = new Set([latest, latest - 1, latest - 2]);
    const grown = new Set<string>();
    for (const r of stateData) {
      if (!threeYears.has(r.year)) continue;
      if (r.statisticcat_desc !== 'AREA PLANTED') continue;
      if (!(r.value_num > 0)) continue;
      if (r.commodity_desc) grown.add(String(r.commodity_desc).toUpperCase());
    }
    if (grown.size === 0) return CROP_COMMODITIES;
    const filtered = CROP_COMMODITIES.filter((c) => {
      const upper = c.label.toUpperCase();
      // NASS uses "SOYBEANS" plural; a few commodities drop 's' vs frontend
      // (peanuts → PEANUT). Check both variants.
      return grown.has(upper) || grown.has(upper.replace(/S$/, '')) || grown.has(upper + 'S');
    });
    return filtered.length > 0 ? filtered : CROP_COMMODITIES;
  }, [stateCode, stateData]);

  return (
    <div>
      {/* Band A — Commodity picker */}
      <div className="mb-6">
        <CommodityPicker
          selected={filters.commodity || 'corn'}
          onSelect={setCommodity}
          commodities={grownInStateCommodities}
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
        {/* Band B — Hero KPI row (state-level KPIs) */}
        <CropHeroRow {...heroData} />

        {/* Band B2 — Inverted-L: map + drill-down panel. Only shown when a
            state is selected and we successfully loaded county data. */}
        {stateCode && countyRollup.size > 0 && (
          <div style={{ marginBottom: 24 }}>
            <div className="crops-invL-wrap">
              <div className="card crops-mapcard">
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.12em', color: 'var(--text3)', textTransform: 'uppercase', marginBottom: 10 }}>
                  County choropleth · Yield anomaly vs state median
                </div>
                <CropsStateMap
                  stateAlpha={stateCode}
                  countyRows={filteredCountyData}
                  commodity={commodity}
                  year={year}
                  onCountyClick={handleCountyClick}
                  selectedFips={selectedFips}
                />
              </div>

              <div className="card crops-panelcard">
                {selectedFips ? (
                  <CropsCountyDrill
                    rollup={countyRollup}
                    selectedFips={selectedFips}
                    stateName={stateName}
                    commodityLabel={commodityLabel}
                    year={year}
                    precipRow={precipByFips.get(selectedFips)}
                    irrigatedAcres={irrigatedByFipsCrop.get(`${selectedFips}|${commodity.toLowerCase()}`)}
                    onClose={handleCountyClose}
                  />
                ) : (
                  <div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.12em', color: 'var(--text3)', textTransform: 'uppercase', marginBottom: 6 }}>
                      {stateName} · {countyRollup.size} reporting counties
                    </div>
                    <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.01em', marginBottom: 12 }}>
                      Click a county to drill in
                    </div>
                    <div style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.6, maxWidth: 640 }}>
                      The map colors counties by yield anomaly vs the state
                      median. Green = above median, rust = below. Clicking any
                      county swaps this panel into an Ogallala-style drill with
                      KPIs, growing-season precipitation vs 30-year normal
                      (NOAA nClimDiv), and irrigated-acres share from the 2022
                      Census of Ag.
                    </div>
                  </div>
                )}
              </div>

              <div className="card crops-peerscard">
                <CropsPeers
                  rollup={countyRollup}
                  mode={selectedFips ? 'county' : 'state'}
                  selectedFips={selectedFips}
                  onCountyClick={handleCountyClick}
                />
              </div>

              <div className="card crops-methcard">
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.4fr', gap: 24 }}>
                  <div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.12em', color: 'var(--text3)', textTransform: 'uppercase', marginBottom: 8 }}>Sources</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      <span className="pchip">USDA NASS QuickStats · 2001–2024</span>
                      <span className="pchip">NOAA nClimDiv 1991–2020 normals</span>
                      <span className="pchip">NASS Census of Ag 2022 · irrigated acres</span>
                      <span className="pchip pchip--faint">Updated Apr 2026</span>
                    </div>
                  </div>
                  <div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.12em', color: 'var(--text3)', textTransform: 'uppercase', marginBottom: 8 }}>Method signature</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text2)', lineHeight: 1.65 }}>
                      State totals are NASS <code>agg_level_desc = &apos;STATE&apos;</code>
                      rows under <code>reference_period_desc = &apos;YEAR&apos;</code>. County
                      rollup uses the same canonical slice with <code>unit_desc</code>
                      checks to avoid biotech-PCT sub-types. Choropleth metric is yield
                      anomaly relative to state median; ranks recompute from the
                      reporting subset. Precipitation from NCEI climdiv-pcpncy
                      (hundredths-of-inches → mm); irrigated-acres from the
                      CENSUS prodn_practice_desc=IRRIGATED split.
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

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
          <ProfitChart
            data={profitData}
            commodity={commodityLabel}
            stateName={stateName}
            note={profitNote}
            iowaFallback={profitIowaFallback}
          />
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
