'use client';

import { useEffect, useState, useCallback } from 'react';
import { useFilters } from '@/hooks/useFilters';
import { useAcreageForecast } from '@/hooks/useAcreageForecast';
import BandShell from '@/components/shared/BandShell';
import SeasonClock from '@/components/forecasts/SeasonClock';
import AcreageCard from '@/components/forecasts/AcreageCard';
import AccuracyPanel from '@/components/forecasts/AccuracyPanel';

const ACREAGE_COMMODITIES = ['corn', 'soybean', 'wheat_winter'] as const;

export default function ForecastsPage() {
  const { filters } = useFilters();
  const forecastYear = new Date().getFullYear(); // Forecasts always use current year

  // Fetch acreage for all 3 commodities
  const corn = useAcreageForecast('corn', forecastYear);
  const soy = useAcreageForecast('soybean', forecastYear);
  const wheat = useAcreageForecast('wheat', forecastYear);

  const allLoading = corn.loading || soy.loading || wheat.loading;
  const anyError = corn.error || soy.error || wheat.error;

  // Build accuracy data from all commodities
  const acreageAccuracy = [
    ...(corn.accuracy || []),
    ...(soy.accuracy || []),
    ...(wheat.accuracy || []),
  ];

  // Yield accuracy placeholder (would come from a dedicated endpoint)
  const [yieldAccuracy, setYieldAccuracy] = useState<any[]>([]);

  useEffect(() => {
    // Try fetching yield accuracy
    const base = process.env.NEXT_PUBLIC_PREDICTION_API_URL || 'http://localhost:8000';
    fetch(`${base}/api/v1/predict/yield/accuracy?crop=corn`)
      .then((r) => r.ok ? r.json() : [])
      .then((data) => setYieldAccuracy(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  function buildCardProps(hook: ReturnType<typeof useAcreageForecast>, commodity: string) {
    const nat = hook.national;
    const states = hook.states;
    return {
      commodity,
      forecastAcres: nat?.forecast_acres_millions ?? null,
      p10: nat?.p10_acres_millions ?? null,
      p90: nat?.p90_acres_millions ?? null,
      yoyDeltaPct: nat?.vs_prior_year_pct ?? null,
      keyDriver: nat?.key_driver ?? null,
      usdaProspective: null as number | null,
      usdaDeltaPct: null as number | null,
      topStates: (states || []).slice(0, 5).map((s: any) => ({
        state: s.state || s.state_fips,
        forecastAcres: s.forecast_acres_millions || 0,
        deltaPct: s.vs_prior_pct ?? null,
      })),
      testMape: null as number | null,
      baselineMape: null as number | null,
      isExperimental: commodity === 'corn',
    };
  }

  return (
    <div>
      {/* Band A — Season Clock */}
      <SeasonClock />

      {/* Page title */}
      <div className="flex items-baseline gap-3 mb-5">
        <h1
          className="text-[28px] font-extrabold tracking-[-0.02em]"
          style={{ color: 'var(--text)', fontFamily: 'var(--font-body)' }}
        >
          Forecasts
        </h1>
        <span className="text-[13px]" style={{ color: 'var(--text2)' }}>
          Acreage predictions and county yield forecasts
        </span>
      </div>

      {/* Band B — Acreage forecast cards */}
      <div className="mb-8">
        <p
          className="text-[11px] font-bold tracking-[0.1em] uppercase mb-3"
          style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
        >
          Planted Acreage Forecasts
        </p>
        <BandShell loading={allLoading} error={anyError} skeletonHeight={300}>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <AcreageCard {...buildCardProps(corn, 'corn')} />
            <AcreageCard {...buildCardProps(soy, 'soybean')} />
            <AcreageCard {...buildCardProps(wheat, 'wheat')} />
          </div>
        </BandShell>

        {/* Wheat spring footnote */}
        <p className="mt-3 text-[12px]" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
          Wheat spring forecasts require more training data (5-state sample insufficient).
        </p>
      </div>

      {/* Band C — County yield panel placeholder */}
      <BandShell
        visibleSeasons={['early-growth', 'mid-season', 'harvest']}
        dormantMessage="Yield forecasts begin May 19 for corn and soy."
        dormantSummary={
          <div
            className="p-4 rounded-[var(--radius-lg)] border"
            style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
          >
            <p className="text-[11px] font-bold tracking-[0.1em] uppercase mb-1"
              style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
              County Yield Forecasts
            </p>
            <p className="text-[13px]" style={{ color: 'var(--text2)' }}>
              County-level yield forecasts for corn and soybean. Available during the growing season (May–October).
            </p>
          </div>
        }
      >
        <div
          className="p-6 rounded-[var(--radius-lg)] border mb-8"
          style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
        >
          <p className="text-[18px] font-bold mb-2" style={{ color: 'var(--text)' }}>
            County Yield Forecast
          </p>
          <p className="text-[13px]" style={{ color: 'var(--text2)' }}>
            Interactive county choropleth with week slider and confidence tiers.
            Active during the growing season (May–October).
          </p>
        </div>
      </BandShell>

      {/* Band D — Accuracy panel */}
      <AccuracyPanel
        acreageAccuracy={acreageAccuracy}
        yieldAccuracy={yieldAccuracy}
      />
    </div>
  );
}
