'use client';

import React, { useState, useEffect, useMemo } from 'react';
import {
  AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { palette, chartDefaults, formatCurrency } from '../utils/design';
import {
  usePriceForecast,
  PriceForecast,
  WasdeSignal,
  PriceProbability,
  ForecastHistoryItem,
} from '../hooks/usePriceForecast';

interface PredictionsDashboardProps {
  data: any[];
  year: number;
  stateName: string;
}

const COMMODITIES = [
  { value: 'corn', label: 'Corn' },
  { value: 'soybean', label: 'Soybean' },
  { value: 'wheat', label: 'Wheat' },
];

// ────────────────────────────────────────────────
// Sub-component: Regime Anomaly Alert
// ────────────────────────────────────────────────
function PriceRegimeAlert() {
  return (
    <div className="flex items-center gap-3 rounded-xl border px-5 py-3 mb-6"
      style={{ borderColor: palette.negative, background: 'rgba(248, 113, 113, 0.08)' }}>
      <span className="material-symbols-outlined text-[24px]" style={{ color: palette.negative }}>warning</span>
      <div>
        <span className="font-semibold" style={{ color: palette.negative }}>Regime Anomaly Detected</span>
        <span className="ml-2 text-sm" style={{ color: palette.textSecondary }}>
          Current market conditions are outside the model&apos;s training distribution. Forecast confidence is reduced — defer to futures curve.
        </span>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────
// Sub-component: KPI Card
// ────────────────────────────────────────────────
function KpiCard({ label, value, sub, accent }: {
  label: string; value: string; sub?: string; accent?: string;
}) {
  return (
    <div className="rounded-xl border p-5" style={{ background: palette.bgCard, borderColor: palette.border }}>
      <div className="text-xs font-medium mb-2" style={{ color: palette.textMuted }}>{label}</div>
      <div className="text-2xl font-bold" style={{ color: accent || palette.textPrimary }}>{value}</div>
      {sub && <div className="text-xs mt-1" style={{ color: palette.textSecondary }}>{sub}</div>}
    </div>
  );
}

// ────────────────────────────────────────────────
// Sub-component: Fan Chart (p10/p50/p90 across horizons)
// ────────────────────────────────────────────────
function PriceFanChart({ forecasts }: { forecasts: PriceForecast[] }) {
  const chartData = useMemo(() =>
    forecasts.map(f => ({
      month: f.horizon_month,
      p10: f.p10,
      p50: f.p50,
      p90: f.p90,
    })),
    [forecasts]
  );

  if (!chartData.length) return null;

  return (
    <div className="rounded-xl border p-5" style={{ background: palette.bgCard, borderColor: palette.border }}>
      <h3 className="text-sm font-semibold mb-1" style={{ color: palette.textPrimary }}>
        Price Forecast Fan
      </h3>
      <p className="text-xs mb-4" style={{ color: palette.textMuted }}>
        80% confidence interval (p10 – p90) across forecast horizons
      </p>
      <ResponsiveContainer width="100%" height={320}>
        <AreaChart data={chartData} margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
          <defs>
            <linearGradient id="fanGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={palette.revenue} stopOpacity={0.25} />
              <stop offset="100%" stopColor={palette.revenue} stopOpacity={0.03} />
            </linearGradient>
          </defs>
          <CartesianGrid {...chartDefaults.grid} />
          <XAxis dataKey="month" {...chartDefaults.axisStyle} />
          <YAxis
            {...chartDefaults.axisStyle}
            tickFormatter={(v: number) => `$${v.toFixed(2)}`}
            domain={['auto', 'auto']}
          />
          <Tooltip
            {...chartDefaults.tooltipStyle}
            formatter={(v: any, name: any) => [
              v != null ? `$${Number(v).toFixed(2)}` : '–',
              name === 'p50' ? 'Median' : name === 'p10' ? '10th Pctl' : '90th Pctl',
            ]}
          />
          <Area
            type="monotone" dataKey="p90" stroke="none"
            fill="url(#fanGradient)" fillOpacity={1}
            animationDuration={chartDefaults.animationDuration}
          />
          <Area
            type="monotone" dataKey="p10" stroke="none"
            fill={palette.bgCard} fillOpacity={1}
            animationDuration={chartDefaults.animationDuration}
          />
          <Line
            type="monotone" dataKey="p50"
            stroke={palette.revenue} strokeWidth={2.5}
            dot={{ r: 4, fill: palette.revenue, strokeWidth: 0 }}
            activeDot={{ r: 6, fill: palette.revenue, stroke: '#fff', strokeWidth: 2 }}
            animationDuration={chartDefaults.animationDuration}
          />
          <Line
            type="monotone" dataKey="p90"
            stroke={palette.revenue} strokeWidth={1} strokeDasharray="4 4" dot={false}
            animationDuration={chartDefaults.animationDuration}
          />
          <Line
            type="monotone" dataKey="p10"
            stroke={palette.revenue} strokeWidth={1} strokeDasharray="4 4" dot={false}
            animationDuration={chartDefaults.animationDuration}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ────────────────────────────────────────────────
// Sub-component: Probability Gauge
// ────────────────────────────────────────────────
function ProbabilityGauge({ probability, commodity, onThresholdChange }: {
  probability: PriceProbability | null;
  commodity: string;
  onThresholdChange: (val: number) => void;
}) {
  const [threshold, setThreshold] = useState('5.00');

  const handleSubmit = () => {
    const val = parseFloat(threshold);
    if (!isNaN(val) && val > 0) onThresholdChange(val);
  };

  const pct = probability ? Math.round(probability.probability * 100) : null;
  const barColor = pct !== null
    ? pct >= 60 ? palette.positive : pct <= 40 ? palette.negative : palette.warning
    : palette.textMuted;

  return (
    <div className="rounded-xl border p-5" style={{ background: palette.bgCard, borderColor: palette.border }}>
      <h3 className="text-sm font-semibold mb-3" style={{ color: palette.textPrimary }}>
        Price Probability
      </h3>
      <div className="flex items-end gap-3 mb-4">
        <div>
          <label className="text-xs block mb-1" style={{ color: palette.textMuted }}>
            Threshold ($/bu)
          </label>
          <input
            type="number" step="0.25" min="0.5" value={threshold}
            onChange={e => setThreshold(e.target.value)}
            className="w-28 rounded-lg border-0 py-2 px-3 text-sm text-white"
            style={{ background: palette.bgInput }}
          />
        </div>
        <button
          onClick={handleSubmit}
          className="rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors"
          style={{ background: '#19e63c' }}
        >
          Calculate
        </button>
      </div>
      {pct !== null && (
        <>
          <div className="text-4xl font-bold mb-1" style={{ color: barColor }}>{pct}%</div>
          <div className="text-xs mb-3" style={{ color: palette.textSecondary }}>
            chance price exceeds ${probability!.threshold_price.toFixed(2)} by {probability!.horizon_month}
          </div>
          <div className="w-full h-2 rounded-full overflow-hidden" style={{ background: palette.border }}>
            <div className="h-full rounded-full transition-all duration-700" style={{ width: `${pct}%`, background: barColor }} />
          </div>
          <div className="text-xs mt-2" style={{ color: palette.textMuted }}>
            {probability!.confidence_note}
          </div>
        </>
      )}
      {pct === null && (
        <div className="text-sm" style={{ color: palette.textMuted }}>
          Enter a threshold price and click Calculate
        </div>
      )}
    </div>
  );
}

// ────────────────────────────────────────────────
// Sub-component: WASDE Signal Card
// ────────────────────────────────────────────────
function WasdeSignalCard({ signal }: { signal: WasdeSignal | null }) {
  if (!signal) return null;

  const dirColor = signal.surprise_direction === 'bullish'
    ? palette.positive
    : signal.surprise_direction === 'bearish'
      ? palette.negative
      : palette.textSecondary;

  const dirLabel = signal.surprise_direction
    ? signal.surprise_direction.charAt(0).toUpperCase() + signal.surprise_direction.slice(1)
    : 'N/A';

  return (
    <div className="rounded-xl border p-5" style={{ background: palette.bgCard, borderColor: palette.border }}>
      <h3 className="text-sm font-semibold mb-3" style={{ color: palette.textPrimary }}>
        WASDE Supply Signal
      </h3>
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <div className="text-xs" style={{ color: palette.textMuted }}>Stocks-to-Use</div>
          <div className="text-xl font-bold" style={{ color: palette.textPrimary }}>
            {(signal.stocks_to_use * 100).toFixed(1)}%
          </div>
        </div>
        <div>
          <div className="text-xs" style={{ color: palette.textMuted }}>Percentile</div>
          <div className="text-xl font-bold" style={{ color: palette.textPrimary }}>
            {signal.stocks_to_use_pctile}th
          </div>
        </div>
      </div>
      {/* Percentile bar */}
      <div className="relative w-full h-3 rounded-full mb-4" style={{ background: palette.border }}>
        <div
          className="absolute top-0 left-0 h-full rounded-full"
          style={{
            width: `${signal.stocks_to_use_pctile}%`,
            background: signal.stocks_to_use_pctile <= 25
              ? palette.positive : signal.stocks_to_use_pctile >= 75
                ? palette.negative : palette.warning,
          }}
        />
        <div
          className="absolute -top-1 w-1 h-5 rounded bg-white"
          style={{ left: `${signal.stocks_to_use_pctile}%`, transform: 'translateX(-50%)' }}
        />
      </div>
      {signal.surprise !== null && (
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs" style={{ color: palette.textMuted }}>Monthly Surprise:</span>
          <span className="text-sm font-semibold" style={{ color: dirColor }}>
            {signal.surprise > 0 ? '+' : ''}{(signal.surprise * 100).toFixed(2)}pp — {dirLabel}
          </span>
        </div>
      )}
      {signal.historical_context && (
        <div className="text-xs mt-2" style={{ color: palette.textSecondary }}>
          {signal.historical_context}
        </div>
      )}
      <div className="text-xs mt-2" style={{ color: palette.textMuted }}>
        Release: {signal.release_date}
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────
// Sub-component: Key Driver Callout
// ────────────────────────────────────────────────
function KeyDriverCallout({ driver }: { driver: string | null }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border p-4"
      style={{ background: palette.bgCard, borderColor: palette.border }}>
      <span className="material-symbols-outlined text-[20px]" style={{ color: palette.textAccent }}>
        insights
      </span>
      <div>
        <div className="text-xs" style={{ color: palette.textMuted }}>Top Model Driver</div>
        <div className="text-sm font-semibold" style={{ color: palette.textPrimary }}>
          {driver || 'Loading...'}
        </div>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────
// Sub-component: Forecast History Chart
// ────────────────────────────────────────────────
function ForecastHistoryChart({ history }: { history: ForecastHistoryItem[] }) {
  if (!history.length) return null;

  const chartData = history
    .slice()
    .reverse()
    .map(h => ({
      date: h.run_date,
      forecast: h.p50,
      actual: h.actual,
    }));

  return (
    <div className="rounded-xl border p-5" style={{ background: palette.bgCard, borderColor: palette.border }}>
      <h3 className="text-sm font-semibold mb-1" style={{ color: palette.textPrimary }}>
        Forecast vs. Actual History
      </h3>
      <p className="text-xs mb-4" style={{ color: palette.textMuted }}>
        Past predictions (p50) compared to realized prices
      </p>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData} margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
          <CartesianGrid {...chartDefaults.grid} />
          <XAxis dataKey="date" {...chartDefaults.axisStyle} />
          <YAxis
            {...chartDefaults.axisStyle}
            tickFormatter={(v: number) => `$${v.toFixed(2)}`}
          />
          <Tooltip
            {...chartDefaults.tooltipStyle}
            formatter={(v: any, name: any) => [
              v != null ? `$${Number(v).toFixed(2)}` : '–',
              name === 'forecast' ? 'Forecast (p50)' : 'Actual',
            ]}
          />
          <Line
            type="monotone" dataKey="forecast"
            stroke={palette.production} strokeWidth={2}
            dot={{ r: 3, fill: palette.production, strokeWidth: 0 }}
            animationDuration={chartDefaults.animationDuration}
          />
          <Line
            type="monotone" dataKey="actual"
            stroke={palette.positive} strokeWidth={2}
            dot={{ r: 3, fill: palette.positive, strokeWidth: 0 }}
            strokeDasharray="5 3"
            animationDuration={chartDefaults.animationDuration}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ────────────────────────────────────────────────
// Main Dashboard Component
// ────────────────────────────────────────────────
export default function PredictionsDashboard({ data, year, stateName }: PredictionsDashboardProps) {
  const [commodity, setCommodity] = useState('corn');
  const [horizon, setHorizon] = useState(3);

  const {
    forecast,
    forecasts,
    probability,
    wasdeSignal,
    history,
    loading,
    error,
    fetchAllHorizons,
    fetchProbability,
    fetchWasdeSignal,
    fetchHistory,
  } = usePriceForecast();

  // Fetch data when commodity or horizon changes
  useEffect(() => {
    fetchAllHorizons(commodity);
    fetchWasdeSignal(commodity);
    fetchHistory(commodity, horizon);
  }, [commodity, horizon, fetchAllHorizons, fetchWasdeSignal, fetchHistory]);

  const handleThresholdChange = (threshold: number) => {
    fetchProbability(commodity, threshold, horizon);
  };

  const selectedForecast = forecasts[horizon - 1] || forecast;

  return (
    <div className="space-y-6">
      {/* Header: Commodity + Horizon selectors */}
      <div className="flex flex-wrap items-center gap-4">
        <div>
          <label className="text-xs block mb-1" style={{ color: palette.textMuted }}>Commodity</label>
          <select
            value={commodity}
            onChange={e => setCommodity(e.target.value)}
            className="rounded-lg border-0 py-2 px-3 text-sm text-white"
            style={{ background: palette.bgInput }}
          >
            {COMMODITIES.map(c => (
              <option key={c.value} value={c.value}>{c.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs block mb-1" style={{ color: palette.textMuted }}>Horizon</label>
          <select
            value={horizon}
            onChange={e => setHorizon(Number(e.target.value))}
            className="rounded-lg border-0 py-2 px-3 text-sm text-white"
            style={{ background: palette.bgInput }}
          >
            {[1, 2, 3, 4, 5, 6].map(h => (
              <option key={h} value={h}>{h} month{h > 1 ? 's' : ''}</option>
            ))}
          </select>
        </div>
        {loading && (
          <div className="flex items-center gap-2 ml-auto">
            <div className="w-4 h-4 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: `${palette.textAccent} transparent ${palette.textAccent} ${palette.textAccent}` }} />
            <span className="text-xs" style={{ color: palette.textMuted }}>Loading predictions...</span>
          </div>
        )}
      </div>

      {/* Error state */}
      {error && (
        <div className="rounded-xl border px-5 py-4" style={{ borderColor: palette.negative, background: palette.anomalyBg }}>
          <div className="text-sm" style={{ color: palette.negative }}>
            <span className="font-semibold">API Error:</span> {error}
          </div>
          <div className="text-xs mt-1" style={{ color: palette.textMuted }}>
            Make sure the FastAPI backend is running on port 8000
          </div>
        </div>
      )}

      {/* Regime Anomaly Alert */}
      {selectedForecast?.regime_anomaly && <PriceRegimeAlert />}

      {/* KPI Cards */}
      {selectedForecast && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <KpiCard
            label={`${commodity.charAt(0).toUpperCase() + commodity.slice(1)} — ${horizon}mo Forecast`}
            value={`$${selectedForecast.p50.toFixed(2)}`}
            sub={`Range: $${selectedForecast.p10.toFixed(2)} – $${selectedForecast.p90.toFixed(2)}`}
            accent={palette.revenue}
          />
          <KpiCard
            label="Divergence from Futures"
            value={selectedForecast.divergence_flag ? 'Divergent' : 'Aligned'}
            sub={selectedForecast.divergence_flag
              ? 'Model prediction differs >5% from futures curve'
              : 'Model and futures curve in agreement'}
            accent={selectedForecast.divergence_flag ? palette.warning : palette.positive}
          />
          <KeyDriverCallout driver={selectedForecast.key_driver} />
        </div>
      )}

      {/* Fan Chart */}
      {forecasts.length > 0 && <PriceFanChart forecasts={forecasts} />}

      {/* Two-column: Probability + WASDE */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ProbabilityGauge
          probability={probability}
          commodity={commodity}
          onThresholdChange={handleThresholdChange}
        />
        <WasdeSignalCard signal={wasdeSignal} />
      </div>

      {/* History */}
      <ForecastHistoryChart history={history} />

      {/* Empty state when no data and no error */}
      {!loading && !error && !selectedForecast && (
        <div className="text-center py-16">
          <span className="material-symbols-outlined text-[48px] mb-4 block" style={{ color: palette.textMuted }}>
            analytics
          </span>
          <div className="text-lg font-semibold mb-2" style={{ color: palette.textSecondary }}>
            No forecast data available
          </div>
          <div className="text-sm" style={{ color: palette.textMuted }}>
            Ensure the prediction API is running and models are trained
          </div>
        </div>
      )}
    </div>
  );
}
