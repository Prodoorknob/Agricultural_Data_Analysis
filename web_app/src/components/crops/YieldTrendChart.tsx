'use client';

import { useState, useMemo } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  ReferenceDot,
} from 'recharts';
import CitationBlock from '@/components/shared/CitationBlock';
import { generateCaption } from '@/lib/captionTemplates';
import anomalyData from '@/data/anomalyContext.json';

const anomalies = anomalyData as Record<string, any>;

interface YieldPoint {
  year: number;
  stateYield: number;
  nationalYield: number;
  isAnomaly: boolean;
}

interface YieldTrendChartProps {
  data: YieldPoint[];
  commodity: string;
  stateName: string;
  unit: string;
}

export default function YieldTrendChart({ data, commodity, stateName, unit }: YieldTrendChartProps) {
  const [hoveredAnomaly, setHoveredAnomaly] = useState<string | null>(null);

  const caption = useMemo(() => {
    if (data.length < 2) return '';
    const first = data[0];
    const last = data[data.length - 1];
    if (!first?.stateYield || !last?.stateYield) return '';
    const pct = ((last.stateYield - first.stateYield) / first.stateYield) * 100;
    return generateCaption('crops-yield-trend', {
      stateName,
      commodity,
      direction: pct >= 0 ? 'grown' : 'declined',
      pct: Math.abs(pct).toFixed(0),
      startYear: first.year,
      percentile: '—',
    });
  }, [data, stateName, commodity]);

  const anomalyPoints = useMemo(
    () => data.filter((d) => d.isAnomaly),
    [data]
  );

  return (
    <div className="mb-8">
      <div className="flex items-baseline justify-between mb-1">
        <h3
          className="text-[18px] font-bold"
          style={{ color: 'var(--text)', fontFamily: 'var(--font-body)' }}
        >
          Yield Trend
        </h3>
      </div>
      {caption && (
        <p className="text-[13px] mb-4" style={{ color: 'var(--text2)' }}>
          {caption}
        </p>
      )}

      <div
        className="p-4 rounded-[var(--radius-lg)] border group"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div style={{ height: 360 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 10, right: 20, bottom: 5, left: 10 }}>
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="var(--border)"
                vertical={false}
              />
              <XAxis
                dataKey="year"
                axisLine={false}
                tickLine={false}
                tick={{ fill: 'var(--text3)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fill: 'var(--text3)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
                domain={['auto', 'auto']}
              />
              <Tooltip
                contentStyle={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  boxShadow: 'var(--shadow-md)',
                  fontSize: 12,
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--text)',
                }}
                formatter={(val, name) => [`${Number(val).toFixed(1)} ${unit}`, String(name ?? '')]}
                labelFormatter={(yr) => `${yr}`}
              />
              <Legend
                verticalAlign="top"
                align="right"
                iconType="plainline"
                wrapperStyle={{ fontSize: 11, fontFamily: 'var(--font-mono)', paddingBottom: 8 }}
              />
              <Line
                type="monotone"
                dataKey="stateYield"
                stroke="var(--field)"
                strokeWidth={2.5}
                dot={false}
                name={stateName}
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="nationalYield"
                stroke="var(--text3)"
                strokeWidth={1.5}
                strokeDasharray="6 3"
                dot={false}
                name="National"
                connectNulls
              />
              {anomalyPoints.map((ap) => (
                <ReferenceDot
                  key={ap.year}
                  x={ap.year}
                  y={ap.stateYield}
                  // Custom shape — invisible 12px hit target over a visible
                  // 6px dot so hover doesn't require pixel-perfect aim.
                  shape={(props: { cx?: number; cy?: number }) => {
                    const cx = props.cx ?? 0;
                    const cy = props.cy ?? 0;
                    return (
                      <g
                        style={{ cursor: 'pointer' }}
                        onMouseEnter={() => setHoveredAnomaly(`${commodity.toLowerCase()}_${ap.year}`)}
                        onMouseLeave={() => setHoveredAnomaly(null)}
                      >
                        <circle cx={cx} cy={cy} r={12} fill="transparent" style={{ pointerEvents: 'all' }} />
                        <circle
                          cx={cx}
                          cy={cy}
                          r={6}
                          fill="var(--negative)"
                          stroke="var(--surface)"
                          strokeWidth={2}
                        />
                      </g>
                    );
                  }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Anomaly popover */}
        {hoveredAnomaly && anomalies[hoveredAnomaly] && (
          <div
            className="mt-3 p-3 rounded-[var(--radius-md)] border-l-[3px]"
            style={{
              background: 'var(--soil-tint)',
              borderLeftColor: 'var(--negative)',
            }}
          >
            <p className="text-[13px] font-semibold" style={{ color: 'var(--text)' }}>
              {anomalies[hoveredAnomaly].year}: {anomalies[hoveredAnomaly].yieldDeltaPct}%
            </p>
            <p className="text-[12px] mt-1" style={{ color: 'var(--text2)' }}>
              {anomalies[hoveredAnomaly].narrative}
            </p>
          </div>
        )}
      </div>

      <CitationBlock source="USDA NASS QuickStats" vintage={`2001–2024`} updated="Apr 2026" />
    </div>
  );
}
