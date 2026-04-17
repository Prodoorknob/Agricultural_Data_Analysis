'use client';

import { useEffect, useState, useCallback, useMemo } from 'react';
import { useFilters } from '@/hooks/useFilters';
import { useMarketData } from '@/hooks/useMarketData';
import BandShell from '@/components/shared/BandShell';
import CommodityPicker from '@/components/shared/CommodityPicker';
import MarketHero from '@/components/market/MarketHero';
import PriceHistoryChart from '@/components/market/PriceHistoryChart';
import WasdeCard from '@/components/market/WasdeCard';
import RatioDial from '@/components/market/RatioDial';
import ExportPaceCard from '@/components/market/ExportPaceCard';
import InputCostCard from '@/components/market/InputCostCard';
import DxyStrip from '@/components/market/DxyStrip';
import { CROP_COMMODITIES } from '@/lib/constants';
import type { FuturesPoint, DxyPoint } from '@/types/market';

const MARKET_COMMODITIES = CROP_COMMODITIES.filter((c) =>
  ['corn', 'soybeans', 'wheat'].includes(c.id)
);

function rangeToStart(range: string): string {
  const now = new Date();
  const d = new Date(now);
  switch (range) {
    case '1M': d.setMonth(d.getMonth() - 1); break;
    case '6M': d.setMonth(d.getMonth() - 6); break;
    case '1Y': d.setFullYear(d.getFullYear() - 1); break;
    case '5Y': d.setFullYear(d.getFullYear() - 5); break;
    case 'MAX': return '2000-01-01';
    default: d.setFullYear(d.getFullYear() - 1);
  }
  return d.toISOString().split('T')[0];
}

export default function MarketPage() {
  const { filters, setCommodity, setRange } = useFilters();
  const commodity = filters.commodity || 'corn';
  const range = filters.range || '1Y';
  const market = useMarketData();

  const [futuresData, setFuturesData] = useState<FuturesPoint[]>([]);
  const [dxyData, setDxyData] = useState<DxyPoint[]>([]);
  const [wasde, setWasde] = useState<any>(null);
  const [costs, setCosts] = useState<any>(null);
  const [fertilizer, setFertilizer] = useState<any>(null);
  const [priceRatio, setPriceRatio] = useState<any>(null);
  const [exportPace, setExportPace] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const start = rangeToStart(range);
      const dxyStart = rangeToStart('1Y');

      const [fut, dxy, wasdeRes, costsRes, fertRes, ratioRes, exportRes] = await Promise.all([
        market.fetchFutures(commodity, start),
        market.fetchDxy(dxyStart),
        market.fetchWasdeSignal(commodity),
        market.fetchCosts(commodity),
        market.fetchFertilizer(4),
        commodity === 'corn' || commodity === 'soybeans' ? market.fetchPriceRatio() : Promise.resolve(null),
        commodity === 'wheat' ? market.fetchExportPace(commodity) : Promise.resolve(null),
      ]);

      setFuturesData(fut?.points || []);
      setDxyData(dxy?.points || []);
      setWasde(wasdeRes);
      setCosts(costsRes);
      setFertilizer(fertRes);
      setPriceRatio(ratioRes);
      setExportPace(exportRes);
    } catch {
      setError('Failed to load market data. Is the backend running?');
    }
    setLoading(false);
  }, [commodity, range, market]);

  useEffect(() => { fetchAll(); }, [commodity, range]); // eslint-disable-line react-hooks/exhaustive-deps

  // Hero data derived from futures
  const heroData = useMemo(() => {
    if (futuresData.length === 0) return null;
    const pts = futuresData;
    const latest = pts[pts.length - 1];
    const prices = pts.map((p) => p.settle);
    const spark90 = prices.slice(-90);

    const findDaysBack = (n: number) => {
      const idx = Math.max(0, pts.length - 1 - n);
      return pts[idx]?.settle || latest.settle;
    };

    const pct = (a: number, b: number) => b > 0 ? ((a - b) / b) * 100 : 0;
    const jan1 = pts.find((p) => p.date.startsWith(`${new Date().getFullYear()}-01`));

    // Guess nearby contract
    const latestDate = new Date(latest.date);
    const contractMonth = new Date(latestDate.getFullYear(), latestDate.getMonth() + 1, 1);
    const nearbyContract = contractMonth.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });

    return {
      commodity,
      nearbyContract,
      settlePrice: latest.settle,
      settleDate: new Date(latest.date).toLocaleDateString(),
      delta1d: pct(latest.settle, findDaysBack(1)),
      delta1w: pct(latest.settle, findDaysBack(5)),
      delta1m: pct(latest.settle, findDaysBack(21)),
      deltaYtd: pct(latest.settle, jan1?.settle || findDaysBack(pts.length - 1)),
      sparkline90d: spark90,
    };
  }, [futuresData, commodity]);

  // Ratio data for dial
  const ratioDialData = useMemo(() => {
    if (!priceRatio) return null;
    const r = priceRatio.corn_soy_ratio || priceRatio.ratio || 0;
    const zone: 'soy_favored' | 'balanced' | 'corn_favored' =
      r < 2.2 ? 'soy_favored' : r > 2.5 ? 'corn_favored' : 'balanced';
    return {
      ratio: r,
      tenYearMin: 2.0,
      tenYearMax: 2.8,
      percentile: priceRatio.historical_percentile || 50,
      zone,
    };
  }, [priceRatio]);

  // Input cost data
  const inputCostData = useMemo(() => {
    if (!costs) return null;
    const latestFert = fertilizer?.[0] || null;
    return {
      commodity,
      productionCostPerBu: costs.total_cost_per_bu,
      currentFuturesPrice: costs.current_futures_price,
      marginPerBu: costs.margin_per_bu,
      fertilizer: latestFert ? {
        anhydrousAmmonia: latestFert.anhydrous_ammonia_ton,
        dap: latestFert.dap_ton,
        potash: latestFert.potash_ton,
      } : null,
    };
  }, [costs, fertilizer, commodity]);

  const showRatio = commodity === 'corn' || commodity === 'soybeans';
  const showExportPace = commodity === 'wheat' && exportPace;

  return (
    <div>
      {/* Commodity selector */}
      <div className="mb-6">
        <CommodityPicker
          selected={commodity}
          onSelect={setCommodity}
          commodities={MARKET_COMMODITIES}
        />
      </div>

      <BandShell loading={loading} error={error} onRetry={fetchAll} skeletonHeight={180}>
        {/* Band A — Hero quote */}
        {heroData && <MarketHero {...heroData} />}

        {/* Band B — Price history */}
        <PriceHistoryChart
          data={futuresData}
          commodity={commodity}
          range={range}
          onRangeChange={setRange}
        />

        {/* Band C — Context row (3 cards) */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
          {/* C.1 — WASDE */}
          {wasde && (
            <WasdeCard
              releaseDate={wasde.release_date || 'N/A'}
              endingStocks={wasde.ending_stocks ?? null}
              stocksToUse={wasde.stocks_to_use ?? null}
              stocksToUsePctile={wasde.stocks_to_use_pctile ?? null}
              priorMonthStu={wasde.prior_month_stu ?? null}
              surpriseDirection={
                wasde.surprise_direction === 'bullish' ? 'supportive' :
                wasde.surprise_direction === 'bearish' ? 'pressuring' : 'neutral'
              }
              commodity={commodity}
            />
          )}

          {/* C.2 — Ratio dial (corn/soy) or Export Pace (wheat) */}
          {showRatio && ratioDialData && <RatioDial {...ratioDialData} />}
          {showExportPace && (
            <ExportPaceCard
              commodity={commodity}
              asOfDate={exportPace.as_of_date}
              marketingYear={exportPace.marketing_year}
              totalCommittedMt={exportPace.total_committed_mt}
              fiveYrAvgMt={exportPace.five_yr_avg_committed_mt}
              pctOfAvg={exportPace.pct_of_5yr_avg}
              weekOfMy={exportPace.week_of_marketing_year}
            />
          )}

          {/* C.3 — Input costs */}
          {inputCostData && <InputCostCard {...inputCostData} />}
        </div>

        {/* Band D — Basis stub */}
        <div
          className="p-4 rounded-[var(--radius-lg)] border mb-6 text-center"
          style={{ background: 'var(--surface2)', borderColor: 'var(--border)' }}
        >
          <p className="text-[14px]" style={{ color: 'var(--text3)' }}>
            Basis data coming — we're ingesting USDA AMS local cash reports. Expected: summer 2026.
          </p>
        </div>

        {/* Band E — DXY macro strip */}
        <DxyStrip data={dxyData} />
      </BandShell>
    </div>
  );
}
