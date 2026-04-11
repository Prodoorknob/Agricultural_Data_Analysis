'use client';

/**
 * Crop Yield Forecasting Section — Module 04
 *
 * Container component with commodity tabs, week slider, county choropleth map,
 * forecast detail card, confidence strip, and season accuracy chart.
 */

import React, { useState, useEffect, useMemo } from 'react';
import {
  AreaChart, Area, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine, Legend,
} from 'recharts';
import { palette, chartDefaults } from '../utils/design';
import { useYieldForecast, YieldForecast, YieldMapItem, YieldHistoryItem } from '../hooks/useYieldForecast';

// ---- Color scale for choropleth (from tech spec) ----
const YIELD_COLORS = {
  deepRed: '#b03030',
  lightRed: '#e08080',
  neutral: '#e8e8e8',
  lightGreen: '#80c080',
  deepGreen: '#2a7a4b',
};

function getYieldColor(vsAvgPct: number | null): string {
  if (vsAvgPct === null) return YIELD_COLORS.neutral;
  if (vsAvgPct < -10) return YIELD_COLORS.deepRed;
  if (vsAvgPct < -5) return YIELD_COLORS.lightRed;
  if (vsAvgPct <= 5) return YIELD_COLORS.neutral;
  if (vsAvgPct <= 10) return YIELD_COLORS.lightGreen;
  return YIELD_COLORS.deepGreen;
}

// ---- Confidence Badge ----
function ConfidenceBadge({ level }: { level: string }) {
  const colors: Record<string, { bg: string; text: string }> = {
    low: { bg: 'rgba(248,113,113,0.15)', text: '#f87171' },
    medium: { bg: 'rgba(251,191,36,0.15)', text: '#fbbf24' },
    high: { bg: 'rgba(52,211,153,0.15)', text: '#34d399' },
  };
  const c = colors[level] || colors.medium;

  return (
    <span
      className="px-2 py-0.5 rounded text-xs font-medium"
      style={{ background: c.bg, color: c.text }}
    >
      {level.toUpperCase()}
    </span>
  );
}

// ---- Yield Forecast Card (county detail) ----
function YieldForecastCard({ forecast }: { forecast: YieldForecast }) {
  const vsColor = (forecast.vs_avg_pct ?? 0) >= 0 ? palette.positive : palette.negative;

  return (
    <div
      className="rounded-lg p-4"
      style={{ background: palette.bgCard, border: `1px solid ${palette.border}` }}
    >
      <div className="flex items-center justify-between mb-3">
        <div>
          <span className="text-xs" style={{ color: palette.textMuted }}>
            FIPS {forecast.fips} — Week {forecast.week}
          </span>
          <h4 className="text-sm font-semibold" style={{ color: palette.textPrimary }}>
            {forecast.crop.charAt(0).toUpperCase() + forecast.crop.slice(1)} Yield Forecast
          </h4>
        </div>
        <ConfidenceBadge level={forecast.confidence} />
      </div>

      {/* P10 / P50 / P90 */}
      <div className="flex items-baseline gap-1 mb-1">
        <span className="text-2xl font-bold" style={{ color: palette.yield }}>
          {forecast.p50.toFixed(1)}
        </span>
        <span className="text-sm" style={{ color: palette.textMuted }}>bu/acre</span>
      </div>
      <div className="text-xs mb-3" style={{ color: palette.textSecondary }}>
        Range: {forecast.p10.toFixed(1)} – {forecast.p90.toFixed(1)} bu/acre
      </div>

      {/* Vs county average */}
      {forecast.vs_avg_pct !== null && (
        <div className="flex items-center gap-2 text-xs">
          <span style={{ color: palette.textMuted }}>vs 5yr avg:</span>
          <span style={{ color: vsColor, fontWeight: 600 }}>
            {forecast.vs_avg_pct > 0 ? '+' : ''}{forecast.vs_avg_pct.toFixed(1)}%
          </span>
          {forecast.county_avg_5yr && (
            <span style={{ color: palette.textMuted }}>
              ({forecast.county_avg_5yr.toFixed(1)} bu/acre)
            </span>
          )}
        </div>
      )}

      {/* Low confidence warning */}
      {forecast.confidence === 'low' && (
        <div
          className="mt-3 p-2 rounded text-xs"
          style={{ background: 'rgba(251,191,36,0.1)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.2)' }}
        >
          Early-season estimate — wide uncertainty. Forecast improves through July.
        </div>
      )}
    </div>
  );
}

// ---- Confidence Strip (uncertainty timeline) ----
function ConfidenceStrip({ mapData, currentWeek }: { mapData: YieldMapItem[]; currentWeek: number }) {
  // Generate mock week-by-week uncertainty data (will be real once multi-week data is available)
  const weekData = useMemo(() => {
    const data = [];
    const baseP50 = mapData.length > 0
      ? mapData.reduce((sum, c) => sum + c.p50, 0) / mapData.length
      : 170;

    for (let w = 1; w <= 20; w++) {
      // Uncertainty narrows as season progresses
      const uncertainty = Math.max(5, 40 - w * 1.8);
      data.push({
        week: w,
        p50: baseP50,
        p10: baseP50 - uncertainty,
        p90: baseP50 + uncertainty,
        isCurrent: w === currentWeek,
      });
    }
    return data;
  }, [mapData, currentWeek]);

  return (
    <div
      className="rounded-lg p-4"
      style={{ background: palette.bgCard, border: `1px solid ${palette.border}` }}
    >
      <h4 className="text-sm font-semibold mb-3" style={{ color: palette.textPrimary }}>
        Forecast Confidence Over Season
      </h4>
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={weekData}>
          <CartesianGrid strokeDasharray="3 3" stroke={palette.border} vertical={false} />
          <XAxis
            dataKey="week"
            tick={{ fill: palette.textMuted, fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            label={{ value: 'Week of Season', position: 'bottom', fill: palette.textMuted, fontSize: 10, offset: -5 }}
          />
          <YAxis
            tick={{ fill: palette.textMuted, fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            domain={['auto', 'auto']}
            width={40}
          />
          <Tooltip
            contentStyle={{
              background: palette.bgCard,
              border: `1px solid ${palette.border}`,
              borderRadius: 6,
              color: palette.textPrimary,
              fontSize: 11,
            }}
            formatter={(val: number) => [`${val.toFixed(1)} bu/acre`]}
          />
          <Area
            type="monotone"
            dataKey="p90"
            stackId="band"
            stroke="none"
            fill="rgba(52,211,153,0.15)"
          />
          <Area
            type="monotone"
            dataKey="p10"
            stackId="band"
            stroke="none"
            fill={palette.bgCard}
          />
          <Line
            type="monotone"
            dataKey="p50"
            stroke={palette.yield}
            strokeWidth={2}
            dot={false}
          />
          {currentWeek > 0 && (
            <ReferenceLine
              x={currentWeek}
              stroke={palette.textAccent}
              strokeDasharray="4 4"
              label={{ value: 'Now', fill: palette.textAccent, fontSize: 10, position: 'top' }}
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ---- Season Accuracy Chart ----
function SeasonAccuracyChart({ history }: { history: YieldHistoryItem[] }) {
  if (history.length === 0) {
    return (
      <div
        className="rounded-lg p-4 flex items-center justify-center"
        style={{ background: palette.bgCard, border: `1px solid ${palette.border}`, minHeight: 180 }}
      >
        <span className="text-xs" style={{ color: palette.textMuted }}>
          Historical accuracy data not yet available
        </span>
      </div>
    );
  }

  return (
    <div
      className="rounded-lg p-4"
      style={{ background: palette.bgCard, border: `1px solid ${palette.border}` }}
    >
      <h4 className="text-sm font-semibold mb-3" style={{ color: palette.textPrimary }}>
        Forecast vs Actual Yield
      </h4>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={history}>
          <CartesianGrid strokeDasharray="3 3" stroke={palette.border} vertical={false} />
          <XAxis
            dataKey="crop_year"
            tick={{ fill: palette.textMuted, fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: palette.textMuted, fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            width={40}
          />
          <Tooltip
            contentStyle={{
              background: palette.bgCard,
              border: `1px solid ${palette.border}`,
              borderRadius: 6,
              color: palette.textPrimary,
              fontSize: 11,
            }}
          />
          <Legend
            wrapperStyle={{ fontSize: 10, color: palette.textMuted }}
          />
          <Line
            type="monotone"
            dataKey="p50_forecast"
            name="Forecast"
            stroke={palette.production}
            strokeWidth={2}
            dot={{ r: 3, fill: palette.production }}
          />
          <Line
            type="monotone"
            dataKey="actual_yield"
            name="Actual"
            stroke={palette.yield}
            strokeWidth={2}
            strokeDasharray="5 5"
            dot={{ r: 3, fill: palette.yield }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ---- County Summary Stats ----
function CountySummaryBar({ mapData }: { mapData: YieldMapItem[] }) {
  if (mapData.length === 0) return null;

  const avgP50 = mapData.reduce((s, c) => s + c.p50, 0) / mapData.length;
  const aboveAvg = mapData.filter(c => (c.vs_avg_pct ?? 0) > 5).length;
  const belowAvg = mapData.filter(c => (c.vs_avg_pct ?? 0) < -5).length;

  return (
    <div className="grid grid-cols-3 gap-3">
      {[
        { label: 'Counties Reporting', value: mapData.length.toLocaleString(), color: palette.textAccent },
        { label: 'Above Average (+5%)', value: aboveAvg.toString(), color: palette.positive },
        { label: 'Below Average (-5%)', value: belowAvg.toString(), color: palette.negative },
      ].map(({ label, value, color }) => (
        <div
          key={label}
          className="rounded-lg p-3 text-center"
          style={{ background: palette.bgCard, border: `1px solid ${palette.border}` }}
        >
          <div className="text-lg font-bold" style={{ color }}>{value}</div>
          <div className="text-xs mt-0.5" style={{ color: palette.textMuted }}>{label}</div>
        </div>
      ))}
    </div>
  );
}

// ---- Main Section ----
export default function YieldForecastSection() {
  const [commodity, setCommodity] = useState<'corn' | 'soybean' | 'wheat'>('corn');
  const [selectedWeek, setSelectedWeek] = useState<number>(15);
  const [selectedFips, setSelectedFips] = useState<string | null>(null);

  const { forecast, mapData, mapWeek, history, loading, error, fetchAll } = useYieldForecast(
    selectedFips,
    commodity,
    undefined,
    selectedWeek,
  );

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const commodities: Array<{ key: 'corn' | 'soybean' | 'wheat'; label: string }> = [
    { key: 'corn', label: 'Corn' },
    { key: 'soybean', label: 'Soybeans' },
    { key: 'wheat', label: 'Wheat' },
  ];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold" style={{ color: palette.textPrimary }}>
            Crop Yield Forecasting
          </h3>
          <p className="text-xs mt-0.5" style={{ color: palette.textMuted }}>
            County-level, in-season yield predictions (p10/p50/p90 bu/acre)
          </p>
        </div>

        {/* Commodity tabs */}
        <div className="flex gap-1">
          {commodities.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => { setCommodity(key); setSelectedFips(null); }}
              className="px-3 py-1.5 rounded text-xs font-medium transition-colors"
              style={{
                background: commodity === key ? 'rgba(52,211,153,0.15)' : 'transparent',
                color: commodity === key ? palette.yield : palette.textMuted,
                border: `1px solid ${commodity === key ? 'rgba(52,211,153,0.3)' : palette.border}`,
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Week slider */}
      <div className="flex items-center gap-3">
        <span className="text-xs" style={{ color: palette.textMuted }}>Week:</span>
        <input
          type="range"
          min={1}
          max={20}
          value={selectedWeek}
          onChange={(e) => setSelectedWeek(parseInt(e.target.value))}
          className="flex-1 h-1 rounded-lg appearance-none cursor-pointer"
          style={{ accentColor: palette.yield }}
        />
        <span className="text-xs font-mono w-12 text-right" style={{ color: palette.textPrimary }}>
          Wk {selectedWeek}
        </span>
        <ConfidenceBadge level={selectedWeek < 8 ? 'low' : selectedWeek < 16 ? 'medium' : 'high'} />
      </div>

      {/* Loading / Error states */}
      {loading && (
        <div className="text-center py-8 text-sm" style={{ color: palette.textMuted }}>
          Loading yield forecast data...
        </div>
      )}
      {error && (
        <div className="text-center py-4 text-xs" style={{ color: palette.negative }}>
          {error}
        </div>
      )}

      {/* County summary stats */}
      {!loading && <CountySummaryBar mapData={mapData} />}

      {/* Map placeholder + County detail card */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Choropleth map placeholder (Deck.gl component will go here) */}
        <div
          className="lg:col-span-2 rounded-lg flex items-center justify-center"
          style={{
            background: palette.bgCard,
            border: `1px solid ${palette.border}`,
            minHeight: 400,
          }}
        >
          {mapData.length > 0 ? (
            <div className="text-center">
              <div className="text-sm font-medium" style={{ color: palette.textPrimary }}>
                County Yield Map
              </div>
              <p className="text-xs mt-1" style={{ color: palette.textMuted }}>
                {mapData.length} counties | Week {mapWeek ?? selectedWeek} | {commodity}
              </p>
              <p className="text-xs mt-2" style={{ color: palette.textSecondary }}>
                Deck.gl choropleth layer will render here
              </p>
              {/* Color legend */}
              <div className="flex items-center gap-1 mt-4 justify-center">
                {[
                  { color: YIELD_COLORS.deepRed, label: '< -10%' },
                  { color: YIELD_COLORS.lightRed, label: '-10 to -5%' },
                  { color: YIELD_COLORS.neutral, label: '-5 to +5%' },
                  { color: YIELD_COLORS.lightGreen, label: '+5 to +10%' },
                  { color: YIELD_COLORS.deepGreen, label: '> +10%' },
                ].map(({ color, label }) => (
                  <div key={label} className="flex items-center gap-1">
                    <div className="w-3 h-3 rounded-sm" style={{ background: color }} />
                    <span className="text-[10px]" style={{ color: palette.textMuted }}>{label}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <span className="text-xs" style={{ color: palette.textMuted }}>
              No yield forecast data available yet
            </span>
          )}
        </div>

        {/* County detail card */}
        <div>
          {forecast ? (
            <YieldForecastCard forecast={forecast} />
          ) : (
            <div
              className="rounded-lg p-4 flex items-center justify-center"
              style={{ background: palette.bgCard, border: `1px solid ${palette.border}`, minHeight: 200 }}
            >
              <span className="text-xs text-center" style={{ color: palette.textMuted }}>
                {selectedFips ? 'Loading county data...' : 'Click a county on the map to see details'}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Bottom row: Confidence Strip + Season Accuracy */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ConfidenceStrip mapData={mapData} currentWeek={selectedWeek} />
        <SeasonAccuracyChart history={history} />
      </div>
    </div>
  );
}
