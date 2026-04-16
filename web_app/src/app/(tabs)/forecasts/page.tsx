'use client';

import { useEffect, useState } from 'react';
import { useAcreageForecast, type AcreageAccuracyItem, type StateAcreageItem } from '@/hooks/useAcreageForecast';
import type { YieldAccuracyWeekItem } from '@/hooks/useYieldForecast';
import BandShell from '@/components/shared/BandShell';
import SeasonClock from '@/components/forecasts/SeasonClock';
import AcreageCard from '@/components/forecasts/AcreageCard';
import AccuracyPanel from '@/components/forecasts/AccuracyPanel';
import YieldSeasonReview from '@/components/forecasts/YieldSeasonReview';

type YieldViewMode = 'current' | 'review';

// Backend /acreage endpoints accept only {corn, soybean, wheat} — the
// generic wheat model is served under that key. wheat_winter/wheat_spring
// exist as training artifacts but aren't individually routed yet; the
// footnote below flags the spring-sample limitation.
const WHEAT_CARD_COMMODITY = 'wheat';

// Test MAPE and baseline MAPE for each acreage model, sourced from
// backend/artifacts/acreage/{commodity}/metrics.json. These are the
// walk-forward (2024-2025) figures §5.3.D surfaces. Inlined rather than
// fetched because they only change on retrain.
// Corn and wheat currently fail their baseline gate — flagged experimental
// so readers see an honest signal rather than assume production quality.
const ACREAGE_PERFORMANCE: Record<string, { testMape: number; baselineMape: number; experimental: boolean }> = {
  corn: { testMape: 6.26, baselineMape: 6.24, experimental: true },
  soybean: { testMape: 4.64, baselineMape: 5.42, experimental: false },
  wheat: { testMape: 8.65, baselineMape: 5.73, experimental: true },
};

export default function ForecastsPage() {
  const forecastYear = new Date().getFullYear();

  const corn = useAcreageForecast('corn', forecastYear);
  const soy = useAcreageForecast('soybean', forecastYear);
  const wheat = useAcreageForecast(WHEAT_CARD_COMMODITY, forecastYear);

  const allLoading = corn.loading || soy.loading || wheat.loading;
  const anyError = corn.error || soy.error || wheat.error;

  const acreageAccuracy: AcreageAccuracyItem[] = [
    ...(corn.accuracy || []),
    ...(soy.accuracy || []),
    ...(wheat.accuracy || []),
  ];

  const [yieldAccuracy, setYieldAccuracy] = useState<YieldAccuracyWeekItem[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    const base = process.env.NEXT_PUBLIC_PREDICTION_API_URL || 'http://localhost:8000';
    fetch(`${base}/api/v1/predict/yield/accuracy?crop=corn`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setYieldAccuracy(Array.isArray(data) ? data : []))
      .catch((err: unknown) => {
        if ((err as { name?: string })?.name !== 'AbortError') setYieldAccuracy([]);
      });
    return () => controller.abort();
  }, []);

  function buildCardProps(hook: ReturnType<typeof useAcreageForecast>, commodity: string) {
    const nat = hook.national;
    const states = hook.states;
    // Accuracy rows are keyed on commodity ('wheat_winter' vs 'wheat') — find the
    // most recent published row for the national rollup (state_fips='00').
    const nationalAccuracy = (hook.accuracy || [])
      .filter((a) => a.level === 'national' || !a.level)
      .sort((a, b) => b.forecast_year - a.forecast_year)[0];
    const perf = ACREAGE_PERFORMANCE[commodity] ?? null;
    return {
      commodity,
      forecastAcres: nat?.forecast_acres ?? null,
      p10: nat?.p10_acres ?? null,
      p90: nat?.p90_acres ?? null,
      yoyDeltaPct: nat?.vs_prior_year_pct ?? null,
      keyDriver: nat?.key_driver ?? null,
      usdaProspective: nationalAccuracy?.usda_prospective ?? null,
      usdaDeltaPct: nationalAccuracy?.model_vs_usda_pct ?? null,
      topStates: (states || []).slice(0, 5).map((s: StateAcreageItem) => ({
        state: s.state || s.state_fips,
        forecastAcres: s.forecast_acres || 0,
        deltaPct: s.vs_prior_pct ?? null,
      })),
      testMape: perf?.testMape ?? null,
      baselineMape: perf?.baselineMape ?? null,
      isExperimental: perf?.experimental ?? false,
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

      {/* Band C — County yield forecast + retrospective toggle */}
      <YieldSection />

      {/* Band D — Accuracy panel */}
      <AccuracyPanel
        acreageAccuracy={acreageAccuracy}
        yieldAccuracy={yieldAccuracy}
      />
    </div>
  );
}

/**
 * County yield forecast section with a toggle between live-season mode
 * (empty until May 19) and a 2024-2025 retrospective review. Defaults to
 * Review during off-season so the page has something to show.
 */
function YieldSection() {
  const today = new Date();
  const isOffSeason = today.getMonth() < 4 || today.getMonth() > 9;  // Nov–Apr
  const [mode, setMode] = useState<YieldViewMode>(isOffSeason ? 'review' : 'current');

  return (
    <div className="mb-8">
      <div className="flex items-center justify-between flex-wrap gap-3 mb-3">
        <p
          className="text-[11px] font-bold tracking-[0.1em] uppercase"
          style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
        >
          County Yield Forecasts
        </p>
        <div
          className="inline-flex items-center p-1 rounded-[var(--radius-full)]"
          style={{ background: 'var(--surface2)' }}
          role="tablist"
          aria-label="Yield forecast view mode"
        >
          {([
            { id: 'current', label: 'Current Season' },
            { id: 'review', label: 'Last Season Review' },
          ] as const).map((t) => {
            const active = t.id === mode;
            return (
              <button
                key={t.id}
                onClick={() => setMode(t.id)}
                role="tab"
                aria-selected={active}
                className="px-3 py-1 rounded-[var(--radius-full)] text-[12px] font-semibold transition-colors"
                style={{
                  background: active ? 'var(--surface)' : 'transparent',
                  color: active ? 'var(--text)' : 'var(--text3)',
                  fontFamily: 'var(--font-mono)',
                  border: active ? '1px solid var(--border)' : '1px solid transparent',
                }}
              >
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {mode === 'current' ? (
        <div
          className="p-6 rounded-[var(--radius-lg)] border"
          style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
        >
          <p className="text-[18px] font-bold mb-2" style={{ color: 'var(--text)' }}>
            County Yield Forecast
          </p>
          <p className="text-[13px]" style={{ color: 'var(--text2)' }}>
            County-level yield forecasts for corn and soybean begin May 19 at week 1 of
            the growing season. Switch to <em>Last Season Review</em> to inspect the
            2024–2025 walk-forward test performance.
          </p>
        </div>
      ) : (
        <YieldSeasonReview />
      )}
    </div>
  );
}
