'use client';

import React, { useState, useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts';
import { palette, chartDefaults } from '../utils/design';
import {
  useAcreageForecast,
  AcreageForecast,
  StateAcreageItem,
  PriceRatio,
  AcreageAccuracyItem,
} from '../hooks/useAcreageForecast';

const COMMODITIES = [
  { value: 'corn', label: 'Corn' },
  { value: 'soybean', label: 'Soybean' },
  { value: 'wheat', label: 'Wheat' },
];

// ────────────────────────────────────────────────
// Sub-component: National Forecast Summary Card
// ────────────────────────────────────────────────
function AcreageSummaryCard({ forecast }: { forecast: AcreageForecast }) {
  const changeColor = forecast.vs_prior_year_pct && forecast.vs_prior_year_pct > 0
    ? palette.positive
    : forecast.vs_prior_year_pct && forecast.vs_prior_year_pct < 0
      ? palette.negative
      : palette.textSecondary;

  const changePrefix = forecast.vs_prior_year_pct && forecast.vs_prior_year_pct > 0 ? '+' : '';

  return (
    <div className="rounded-xl border p-5" style={{ background: palette.bgCard, borderColor: palette.border }}>
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs font-medium" style={{ color: palette.textMuted }}>
          {forecast.forecast_year} National Planted Acreage
        </div>
        <span className="text-xs px-2 py-0.5 rounded-full"
          style={{ background: 'rgba(96, 165, 250, 0.12)', color: palette.textAccent }}>
          {forecast.published_at ? `Published ${forecast.published_at}` : 'Forecast'}
        </span>
      </div>

      <div className="text-3xl font-bold mb-1" style={{ color: palette.textPrimary }}>
        {forecast.forecast_acres_millions.toFixed(1)}M acres
      </div>

      <div className="flex items-center gap-4 text-sm">
        {forecast.vs_prior_year_pct !== null && forecast.vs_prior_year_pct !== undefined && (
          <span style={{ color: changeColor }}>
            {changePrefix}{forecast.vs_prior_year_pct.toFixed(1)}% vs prior year
          </span>
        )}
        {forecast.p10_acres_millions && forecast.p90_acres_millions && (
          <span style={{ color: palette.textMuted }}>
            Range: {forecast.p10_acres_millions.toFixed(1)} - {forecast.p90_acres_millions.toFixed(1)}M
          </span>
        )}
      </div>

      {forecast.key_driver && (
        <div className="mt-3 text-xs" style={{ color: palette.textSecondary }}>
          Key driver: <span style={{ color: palette.textAccent }}>{forecast.key_driver}</span>
        </div>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────
// Sub-component: State Bar Chart (top 12)
// ────────────────────────────────────────────────
function StateAcreageChart({ states, commodity }: { states: StateAcreageItem[]; commodity: string }) {
  const chartData = useMemo(() =>
    states.slice(0, 12).map(s => ({
      state: s.state,
      acres: s.forecast_acres_millions,
      vs_prior: s.vs_prior_pct,
      fill: (s.vs_prior_pct || 0) >= 0 ? palette.positive : palette.negative,
    })),
    [states]
  );

  if (!chartData.length) return null;

  return (
    <div className="rounded-xl border p-5" style={{ background: palette.bgCard, borderColor: palette.border }}>
      <h3 className="text-sm font-semibold mb-1" style={{ color: palette.textPrimary }}>
        Top States — {commodity.charAt(0).toUpperCase() + commodity.slice(1)} Planted Acreage
      </h3>
      <p className="text-xs mb-4" style={{ color: palette.textMuted }}>
        Forecast acres (millions) with year-over-year change
      </p>
      <ResponsiveContainer width="100%" height={360}>
        <BarChart data={chartData} layout="vertical" margin={{ left: 80, right: 40 }}>
          <CartesianGrid {...chartDefaults.grid} horizontal={false} vertical />
          <XAxis type="number" {...chartDefaults.axisStyle} />
          <YAxis type="category" dataKey="state" {...chartDefaults.axisStyle} width={75} />
          <Tooltip
            contentStyle={{ background: palette.bgCard, border: `1px solid ${palette.border}`, borderRadius: 8 }}
            labelStyle={{ color: palette.textPrimary }}
            formatter={(value: number, _: string, entry: any) => [
              `${value.toFixed(1)}M acres${entry.payload.vs_prior !== null ? ` (${entry.payload.vs_prior > 0 ? '+' : ''}${entry.payload.vs_prior?.toFixed(1)}%)` : ''}`,
              'Forecast',
            ]}
          />
          <Bar dataKey="acres" radius={[0, 4, 4, 0]} animationDuration={chartDefaults.animationDuration}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.fill} fillOpacity={0.8} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ────────────────────────────────────────────────
// Sub-component: Price Ratio Gauge
// ────────────────────────────────────────────────
function PriceRatioDial({ ratio }: { ratio: PriceRatio }) {
  if (!ratio.corn_soy_ratio) return null;

  // Map ratio to gauge position (1.8 to 2.8 range)
  const min = 1.8;
  const max = 2.8;
  const clamped = Math.max(min, Math.min(max, ratio.corn_soy_ratio));
  const pct = ((clamped - min) / (max - min)) * 100;

  const getZoneColor = () => {
    if (ratio.corn_soy_ratio! < 2.2) return palette.negative;
    if (ratio.corn_soy_ratio! > 2.5) return palette.positive;
    return palette.textSecondary;
  };

  const zoneLabel = ratio.implication === 'soy_favored' ? 'Soy Favored'
    : ratio.implication === 'corn_favored' ? 'Corn Favored'
      : 'Neutral Zone';

  return (
    <div className="rounded-xl border p-5" style={{ background: palette.bgCard, borderColor: palette.border }}>
      <h3 className="text-sm font-semibold mb-4" style={{ color: palette.textPrimary }}>
        Corn / Soybean Price Ratio
      </h3>

      {/* Gauge bar */}
      <div className="relative h-3 rounded-full mb-2" style={{ background: palette.bgInput }}>
        {/* Zones */}
        <div className="absolute h-full rounded-l-full" style={{ width: '40%', background: 'rgba(248,113,113,0.25)' }} />
        <div className="absolute h-full" style={{ left: '40%', width: '30%', background: 'rgba(107,114,128,0.2)' }} />
        <div className="absolute h-full rounded-r-full" style={{ left: '70%', width: '30%', background: 'rgba(52,211,153,0.25)' }} />
        {/* Needle */}
        <div className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full border-2"
          style={{ left: `${pct}%`, transform: `translate(-50%, -50%)`, background: getZoneColor(), borderColor: palette.bgCard }}
        />
      </div>

      <div className="flex justify-between text-xs mb-4" style={{ color: palette.textMuted }}>
        <span>1.8 (Soy)</span>
        <span>2.2</span>
        <span>2.5</span>
        <span>2.8 (Corn)</span>
      </div>

      <div className="text-center">
        <div className="text-2xl font-bold" style={{ color: getZoneColor() }}>
          {ratio.corn_soy_ratio.toFixed(2)}
        </div>
        <div className="text-sm font-medium mt-1" style={{ color: getZoneColor() }}>{zoneLabel}</div>
        {ratio.historical_percentile !== null && ratio.historical_percentile !== undefined && (
          <div className="text-xs mt-1" style={{ color: palette.textMuted }}>
            {ratio.historical_percentile}th percentile since 2000
          </div>
        )}
      </div>

      {ratio.historical_context && (
        <div className="mt-3 text-xs p-3 rounded-lg" style={{ background: palette.bgInput, color: palette.textSecondary }}>
          {ratio.historical_context}
        </div>
      )}

      <div className="mt-3 flex justify-between text-xs" style={{ color: palette.textMuted }}>
        <span>Corn Dec: ${ratio.corn_dec_futures?.toFixed(2)}</span>
        <span>Soy Nov: ${ratio.soy_nov_futures?.toFixed(2)}</span>
      </div>
      <div className="text-xs mt-1" style={{ color: palette.textMuted }}>
        As of {ratio.as_of_date}
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────
// Sub-component: USDA Comparison Panel
// ────────────────────────────────────────────────
function UsdaComparisonPanel({ accuracy }: { accuracy: AcreageAccuracyItem[] }) {
  if (!accuracy.length) return null;

  const national = accuracy.filter(a => a.level === 'national');
  if (!national.length) return null;

  return (
    <div className="rounded-xl border p-5" style={{ background: palette.bgCard, borderColor: palette.border }}>
      <h3 className="text-sm font-semibold mb-4" style={{ color: palette.textPrimary }}>
        Forecast Accuracy — Model vs USDA
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr style={{ color: palette.textMuted }}>
              <th className="text-left py-2 font-medium">Year</th>
              <th className="text-left py-2 font-medium">Crop</th>
              <th className="text-right py-2 font-medium">Model</th>
              <th className="text-right py-2 font-medium">USDA Mar</th>
              <th className="text-right py-2 font-medium">USDA Jun</th>
              <th className="text-right py-2 font-medium">vs USDA</th>
              <th className="text-right py-2 font-medium">vs Actual</th>
            </tr>
          </thead>
          <tbody>
            {national.map((a, i) => (
              <tr key={i} style={{ borderTop: `1px solid ${palette.border}` }}>
                <td className="py-2" style={{ color: palette.textPrimary }}>{a.forecast_year}</td>
                <td className="py-2 capitalize" style={{ color: palette.textSecondary }}>{a.commodity}</td>
                <td className="py-2 text-right" style={{ color: palette.textPrimary }}>{a.model_forecast.toFixed(1)}M</td>
                <td className="py-2 text-right" style={{ color: palette.textSecondary }}>
                  {a.usda_prospective ? `${a.usda_prospective.toFixed(1)}M` : '—'}
                </td>
                <td className="py-2 text-right" style={{ color: palette.textSecondary }}>
                  {a.usda_june_actual ? `${a.usda_june_actual.toFixed(1)}M` : '—'}
                </td>
                <td className="py-2 text-right" style={{
                  color: a.model_vs_usda_pct !== null && a.model_vs_usda_pct !== undefined
                    ? Math.abs(a.model_vs_usda_pct) < 2 ? palette.positive : palette.negative
                    : palette.textMuted,
                }}>
                  {a.model_vs_usda_pct !== null && a.model_vs_usda_pct !== undefined
                    ? `${a.model_vs_usda_pct > 0 ? '+' : ''}${a.model_vs_usda_pct.toFixed(1)}%`
                    : '—'}
                </td>
                <td className="py-2 text-right" style={{
                  color: a.model_vs_actual_pct !== null && a.model_vs_actual_pct !== undefined
                    ? Math.abs(a.model_vs_actual_pct) < 3 ? palette.positive : palette.negative
                    : palette.textMuted,
                }}>
                  {a.model_vs_actual_pct !== null && a.model_vs_actual_pct !== undefined
                    ? `${a.model_vs_actual_pct > 0 ? '+' : ''}${a.model_vs_actual_pct.toFixed(1)}%`
                    : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────
// Main: AcreagePredictionSection
// ────────────────────────────────────────────────
export default function AcreagePredictionSection() {
  const [commodity, setCommodity] = useState('corn');
  const currentYear = new Date().getFullYear();
  const { national, states, accuracy, priceRatio, loading, error } = useAcreageForecast(commodity);

  // Seasonal state machine
  const month = new Date().getMonth() + 1;
  const seasonalPhase = month >= 2 && month <= 3 ? 'forecast_live'
    : month >= 4 && month <= 6 ? 'post_usda'
      : month >= 7 ? 'final_accuracy'
        : 'pre_forecast';

  return (
    <div className="space-y-6">
      {/* Section header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold" style={{ color: palette.textPrimary }}>
            Planted Acreage Forecast
          </h2>
          <p className="text-xs mt-0.5" style={{ color: palette.textMuted }}>
            {seasonalPhase === 'pre_forecast'
              ? `Next forecast publishes February 1, ${currentYear + 1}`
              : seasonalPhase === 'forecast_live'
                ? `Pre-season forecast — ahead of USDA March 31 report`
                : seasonalPhase === 'post_usda'
                  ? 'Comparing our forecast to USDA Prospective Plantings'
                  : 'Full-season accuracy review'}
          </p>
        </div>

        {/* Commodity selector */}
        <div className="flex gap-1 rounded-lg p-0.5" style={{ background: palette.bgInput }}>
          {COMMODITIES.map(c => (
            <button
              key={c.value}
              onClick={() => setCommodity(c.value)}
              className="px-3 py-1.5 rounded-md text-xs font-medium transition-colors"
              style={{
                background: commodity === c.value ? palette.bgCard : 'transparent',
                color: commodity === c.value ? palette.textPrimary : palette.textMuted,
                border: commodity === c.value ? `1px solid ${palette.border}` : '1px solid transparent',
              }}
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>

      {/* Loading / error states */}
      {loading && (
        <div className="text-center py-8" style={{ color: palette.textMuted }}>Loading acreage data...</div>
      )}
      {error && !loading && (
        <div className="text-center py-8 text-sm" style={{ color: palette.textMuted }}>{error}</div>
      )}

      {/* Main content */}
      {!loading && !error && (
        <>
          {/* Row 1: Summary + Price Ratio */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {national && <AcreageSummaryCard forecast={national} />}
            {priceRatio && <PriceRatioDial ratio={priceRatio} />}
          </div>

          {/* Row 2: State chart */}
          {states.length > 0 && (
            <StateAcreageChart states={states} commodity={commodity} />
          )}

          {/* Row 3: USDA comparison (shown in post_usda and final_accuracy phases) */}
          {(seasonalPhase === 'post_usda' || seasonalPhase === 'final_accuracy') && accuracy.length > 0 && (
            <UsdaComparisonPanel accuracy={accuracy} />
          )}
        </>
      )}
    </div>
  );
}
