'use client';

import { useEffect, useState, useMemo, useCallback } from 'react';
import { useFilters } from '@/hooks/useFilters';
import { LATEST_NASS_YEAR } from '@/lib/constants';
import {
  US_STATES, fetchStateData, fetchNationalCrops, fetchCountyData, fetchCountyPrecip, fetchIrrigatedCountyAcres,
} from '@/utils/serviceData';
import { filterData, getCommodityStory, getCropConditionTrends, deriveCropOptions } from '@/utils/processData';
import { formatCompact, formatCurrency } from '@/lib/format';
import BandShell from '@/components/shared/BandShell';
import CommodityPicker from '@/components/shared/CommodityPicker';
import CropHeroRow, { type HeroCard } from '@/components/crops/CropHeroRow';
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

const CENSUS_YEARS = new Set([2002, 2007, 2012, 2017, 2022]);

// Title-case a NASS commodity_desc for display ("SWEET CORN" -> "Sweet Corn").
function titleCase(desc: string): string {
  return desc.toLowerCase().replace(/\b([a-z])/g, (_, c: string) => c.toUpperCase());
}

// Yield values span bushels/acre (150+) down to tons/acre (~8); format with a
// decimal only when the magnitude is small enough to need it.
function fmtYield(v: number): string {
  return v >= 100 ? v.toFixed(0) : v.toFixed(1);
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

  // Hero KPI data — adaptive per crop. Field crops show Yield (bu/ac) + Area
  // Planted; specialty crops (fruits/nuts/vegetables) fall back to Production
  // in native units, Area Bearing/Harvested, and Value of Production when those
  // are what NASS publishes. The page builds the card list and CropHeroRow just
  // renders it.
  const heroData = useMemo(() => {
    const thisYear = story.find((s: any) => s.year === year);
    const priorYear = story.find((s: any) => s.year === year - 1);

    // --- Primary metric: yield, else production ---
    // 5-year average yield excludes 0/missing years. Census years don't always
    // carry a SURVEY yield row, and averaging 0s drags the baseline down ~20%.
    const fiveYearYields = story
      .filter((s: any) => s.year >= year - 5 && s.year <= year - 1)
      .map((s: any) => s.yield || 0)
      .filter((v: number) => v > 0);
    const avg5yr = fiveYearYields.length > 0
      ? fiveYearYields.reduce((s: number, v: number) => s + v, 0) / fiveYearYields.length
      : 0;
    const yieldNow = thisYear?.yield || 0;
    const yieldUnit = thisYear?.yieldUnit || 'BU / ACRE';
    const yieldDelta = avg5yr > 0 ? ((yieldNow - avg5yr) / avg5yr) * 100 : 0;

    const prodNow = thisYear?.production || 0;
    const prodPrior = priorYear?.production || 0;
    const prodUnit = thisYear?.prodUnit || '';
    const prodDelta = prodPrior > 0 ? ((prodNow - prodPrior) / prodPrior) * 100 : 0;

    // --- Area: planted -> harvested -> bearing (perennials) ---
    const areaChoices: { label: string; now: number; prior: number }[] = [
      { label: 'Area Planted', now: thisYear?.areaPlanted || 0, prior: priorYear?.areaPlanted || 0 },
      { label: 'Area Harvested', now: thisYear?.areaHarvested || 0, prior: priorYear?.areaHarvested || 0 },
      { label: 'Area Bearing', now: thisYear?.areaBearing || 0, prior: priorYear?.areaBearing || 0 },
    ];
    const area = areaChoices.find((a) => a.now > 0);

    // --- Operations count (Census-dense). Raw dataset because filterData drops
    // non-SALES CENSUS rows where OPERATIONS lives. ---
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
      if (v > 0) { opsCount = v; opsYearUsed = y; break; }
    }
    const baselineCandidates = [2002, 2007, 2012];
    let opsCountBaseline = 0;
    let opsBaselineYear: number | null = null;
    for (const y of baselineCandidates) {
      if (y >= (opsYearUsed ?? 9999)) break;
      const v = sumOpsForYear(y);
      if (v > 0) { opsCountBaseline = v; opsBaselineYear = y; break; }
    }
    const opsDelta = opsCountBaseline > 0 ? ((opsCount - opsCountBaseline) / opsCountBaseline) * 100 : 0;

    // --- Dollars: SALES $ total, else Value of Production ($) ---
    const salesNow = thisYear?.revenue || 0;
    const salesPrior = priorYear?.revenue || 0;
    const salesDelta = salesPrior > 0 ? ((salesNow - salesPrior) / salesPrior) * 100 : 0;
    const vopNow = thisYear?.valueOfProduction || 0;
    const vopPrior = priorYear?.valueOfProduction || 0;
    const vopDelta = vopPrior > 0 ? ((vopNow - vopPrior) / vopPrior) * 100 : 0;

    const totalStateSales = activeData
      .filter((r: any) => r.year === year && r.statisticcat_desc === 'SALES' && r.unit_desc === '$')
      .reduce((s: number, r: any) => s + (r.value_num || 0), 0);
    const salesShare = totalStateSales > 0 ? (salesNow / totalStateSales) * 100 : 0;

    // --- Assemble cards (drop empties) ---
    const cards: HeroCard[] = [];

    if (yieldNow > 0) {
      cards.push({
        label: 'Yield',
        value: fmtYield(yieldNow),
        unit: yieldUnit,
        delta: avg5yr > 0 ? yieldDelta : undefined,
        caption: avg5yr > 0
          ? `${fmtYield(yieldNow)} ${yieldUnit}, ${yieldDelta >= 0 ? 'above' : 'below'} the 5-year average of ${fmtYield(avg5yr)}.`
          : `${fmtYield(yieldNow)} ${yieldUnit} in ${year}.`,
      });
    } else if (prodNow > 0) {
      cards.push({
        label: 'Production',
        value: formatCompact(prodNow),
        unit: prodUnit,
        delta: prodPrior > 0 ? prodDelta : undefined,
        caption: prodPrior > 0
          ? `${formatCompact(prodNow)} ${prodUnit}, ${prodDelta >= 0 ? 'up' : 'down'} ${Math.abs(prodDelta).toFixed(1)}% from last year.`
          : `${formatCompact(prodNow)} ${prodUnit} produced in ${year}.`,
      });
    }

    if (area) {
      const ad = area.prior > 0 ? ((area.now - area.prior) / area.prior) * 100 : 0;
      cards.push({
        label: area.label,
        value: formatCompact(area.now),
        unit: 'acres',
        delta: area.prior > 0 ? ad : undefined,
        caption: area.prior > 0
          ? `${formatCompact(area.now)} acres, ${ad >= 0 ? 'up' : 'down'} ${Math.abs(ad).toFixed(1)}% from last year.`
          : `${formatCompact(area.now)} acres in ${year}.`,
      });
    }

    if (opsCount > 0) {
      const opsYearLabel = opsYearUsed
        ? `(${CENSUS_YEARS.has(opsYearUsed) ? 'Census ' : ''}${opsYearUsed})`
        : undefined;
      const baselineClause = opsBaselineYear
        ? `since ${CENSUS_YEARS.has(opsBaselineYear) ? 'the ' + opsBaselineYear + ' Census' : opsBaselineYear}`
        : 'over time';
      cards.push({
        label: 'Operations',
        value: formatCompact(opsCount),
        unit: opsYearLabel,
        delta: opsDelta !== 0 ? opsDelta : undefined,
        caption: `${formatCompact(opsCount)} operations, ${opsDelta >= 0 ? 'up' : 'down'} ${Math.abs(opsDelta).toFixed(0)}% ${baselineClause}.`,
      });
    }

    if (salesNow > 0) {
      cards.push({
        label: 'Total Sales',
        value: formatCurrency(salesNow),
        delta: salesPrior > 0 ? salesDelta : undefined,
        caption: salesShare > 0
          ? `${formatCurrency(salesNow)}, ${salesShare.toFixed(0)}% of ${stateName}'s total farm sales.`
          : `${formatCurrency(salesNow)} in reported sales.`,
      });
    } else if (vopNow > 0) {
      cards.push({
        label: 'Value of Production',
        value: formatCurrency(vopNow),
        delta: vopPrior > 0 ? vopDelta : undefined,
        caption: vopPrior > 0
          ? `${formatCurrency(vopNow)} value of production, ${vopDelta >= 0 ? 'up' : 'down'} ${Math.abs(vopDelta).toFixed(1)}% from last year.`
          : `${formatCurrency(vopNow)} value of production in ${year}.`,
      });
    }

    return { cards, yieldUnit };
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

  const commodityLabel = titleCase(commodity);

  // Grouped commodity options derived from the loaded dataset (state parquet or
  // NATIONAL). Includes field crops, fruits & nuts, and vegetables — every crop
  // with real renderable data in the recent window. Replaces the old
  // AREA-PLANTED-only filter, which silently dropped all specialty crops (most
  // report AREA BEARING / PRODUCTION rather than AREA PLANTED).
  const cropGroups = useMemo(
    () => deriveCropOptions(stateCode ? stateData : nationalData),
    [stateCode, stateData, nationalData],
  );

  return (
    <div>
      {/* Band A — Commodity picker */}
      <div className="mb-6">
        <CommodityPicker
          selected={filters.commodity || 'corn'}
          onSelect={setCommodity}
          groups={cropGroups}
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
        {/* Band B — Hero KPI row (adaptive per crop) */}
        <CropHeroRow cards={heroData.cards} />

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

        {/* Band D — Profit + Harvest efficiency. Both rely on ERS cost data and
            planted/harvested acres, which exist for field crops but not most
            specialty crops, so render only the panels that have data. */}
        {(profitData.length > 0 || efficiencyData.length > 0) && (
          <div className={`grid grid-cols-1 ${profitData.length > 0 && efficiencyData.length > 0 ? 'lg:grid-cols-2' : ''} gap-4 mb-8`}>
            {profitData.length > 0 && (
              <ProfitChart
                data={profitData}
                commodity={commodityLabel}
                stateName={stateName}
                note={profitNote}
                iowaFallback={profitIowaFallback}
              />
            )}
            {efficiencyData.length > 0 && (
              <HarvestEfficiency data={efficiencyData} commodity={commodityLabel} stateName={stateName} />
            )}
          </div>
        )}

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
