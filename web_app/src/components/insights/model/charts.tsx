'use client';

/**
 * Chart renderers for the issue-spec figure blocks.
 *
 * Styling follows the site-wide Recharts conventions (see YieldTrendChart /
 * ProfitChart): no axis lines or tick marks, dashed horizontal grid, mono
 * tick labels in --text3, surface-card tooltips, CSS-variable colors only.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  ErrorBar,
  LabelList,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
} from 'recharts';
import type { BarsChart, TrendForecastChart } from './types';

const TICK = { fill: 'var(--text3)', fontSize: 11, fontFamily: 'var(--font-mono)' };

function formatBarValue(v: number, chart: BarsChart): string {
  const d = chart.decimals ?? 1;
  if (chart.valueFormat === 'signed_pct') return `${v > 0 ? '+' : ''}${v.toFixed(d)}%`;
  if (chart.unit === '%') return `${v.toFixed(d)}%`;
  // "M acres" style units render as a compact M suffix on the bar label.
  if (chart.unit?.startsWith('M ')) return `${v.toFixed(d)}M`;
  return v.toFixed(d);
}

export function BarsBlock({ chart }: { chart: BarsChart }) {
  const hasNegative = chart.data.some((d) => d.value < 0);
  const height = chart.height ?? 200;
  // Custom label so negative bars label at their zero-side end (open space)
  // instead of colliding with the category axis on the left.
  const renderLabel = (props: unknown) => {
    const { x, y, width, height: h, value } = props as {
      x: number;
      y: number;
      width: number;
      height: number;
      value: number;
    };
    const rx = Math.max(x, x + width) + 6;
    return (
      <text
        x={rx}
        y={y + h / 2}
        dy={4}
        fill="var(--text)"
        fontSize={12}
        fontWeight={600}
        fontFamily="var(--font-mono)"
      >
        {formatBarValue(value, chart)}
      </text>
    );
  };
  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart
          data={chart.data}
          layout="vertical"
          margin={{ top: 4, right: 56, bottom: 0, left: 4 }}
        >
          <XAxis type="number" hide domain={chart.domain ?? [0, 'auto']} />
          <YAxis
            type="category"
            dataKey="label"
            axisLine={false}
            tickLine={false}
            width={132}
            tick={{
              fill: 'var(--text2)',
              fontSize: 12,
              fontFamily: 'var(--font-body)',
            }}
          />
          {hasNegative && <ReferenceLine x={0} stroke="var(--border2)" />}
          <Bar dataKey="value" barSize={22} radius={[0, 3, 3, 0]} isAnimationActive={false}>
            {chart.data.map((d) => (
              <Cell key={d.label} fill={d.color ?? 'var(--field)'} />
            ))}
            <LabelList dataKey="value" content={renderLabel} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {chart.caption && <div className="fpn-panel-caption">{chart.caption}</div>}
    </div>
  );
}

interface TrendRow {
  year: number;
  actual?: number;
  forecast?: number;
  bridge?: number;
  err?: [number, number];
}

function TrendTooltip({
  active,
  payload,
  label,
  chart,
}: {
  active?: boolean;
  payload?: Array<{ dataKey?: string; value?: number; payload?: TrendRow }>;
  label?: number;
  chart: TrendForecastChart;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload;
  if (!row) return null;
  const unit = chart.unit ?? '';
  return (
    <div
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        boxShadow: 'var(--shadow-md)',
        fontSize: 12,
        fontFamily: 'var(--font-mono)',
        color: 'var(--text)',
        padding: '8px 10px',
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 2 }}>{label}</div>
      {row.actual !== undefined && (
        <div style={{ color: 'var(--field)' }}>
          Actual: {row.actual.toFixed(2)} {unit}
        </div>
      )}
      {row.forecast !== undefined && (
        <>
          <div style={{ color: 'var(--harvest-dark)' }}>
            Model P50: {row.forecast.toFixed(2)} {unit}
          </div>
          <div style={{ color: 'var(--text3)' }}>
            P10-P90: {chart.forecast.p10.toFixed(2)} to {chart.forecast.p90.toFixed(2)}
          </div>
        </>
      )}
    </div>
  );
}

export function TrendForecastBlock({ chart }: { chart: TrendForecastChart }) {
  const f = chart.forecast;
  const lastActual = chart.actuals[chart.actuals.length - 1];
  const rows: TrendRow[] = chart.actuals.map((a) => ({
    year: a.year,
    actual: a.value,
    bridge: a.year === lastActual.year ? a.value : undefined,
  }));
  rows.push({
    year: f.year,
    forecast: f.p50,
    bridge: f.p50,
    err: [f.p50 - f.p10, f.p90 - f.p50],
  });

  return (
    <div>
      <ResponsiveContainer width="100%" height={chart.height ?? 280}>
        <ComposedChart data={rows} margin={{ top: 12, right: 24, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis dataKey="year" axisLine={false} tickLine={false} tick={TICK} />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={TICK}
            domain={chart.yDomain ?? ['auto', 'auto']}
            tickFormatter={(v: number) => v.toFixed(1)}
            width={42}
          />
          <Tooltip content={<TrendTooltip chart={chart} />} />
          {chart.refValue !== undefined && (
            <ReferenceLine
              y={chart.refValue}
              stroke="var(--text3)"
              strokeDasharray="4 4"
              label={{
                value: chart.refLabel ?? '',
                position: 'insideTopRight',
                fill: 'var(--text3)',
                fontSize: 10,
                fontFamily: 'var(--font-mono)',
              }}
            />
          )}
          <Line
            dataKey="bridge"
            stroke="var(--harvest)"
            strokeWidth={1.5}
            strokeDasharray="5 4"
            dot={false}
            activeDot={false}
            isAnimationActive={false}
            legendType="none"
          />
          <Line
            dataKey="actual"
            stroke="var(--field)"
            strokeWidth={2.5}
            dot={{ r: 3.5, fill: 'var(--field)', strokeWidth: 0 }}
            isAnimationActive={false}
          />
          <Line
            dataKey="forecast"
            stroke="var(--harvest)"
            strokeWidth={0}
            dot={{ r: 5, fill: 'var(--harvest)', strokeWidth: 0 }}
            isAnimationActive={false}
          >
            <ErrorBar
              dataKey="err"
              width={7}
              strokeWidth={1.5}
              stroke="var(--harvest)"
              direction="y"
            />
          </Line>
        </ComposedChart>
      </ResponsiveContainer>
      {chart.caption && <div className="fpn-panel-caption">{chart.caption}</div>}
      <div className="fpn-trend-legend">
        <span>
          <i style={{ background: 'var(--field)' }} /> Actual (NASS)
        </span>
        <span>
          <i style={{ background: 'var(--harvest)' }} /> Model forecast, P10-P90 whisker
        </span>
      </div>
    </div>
  );
}
