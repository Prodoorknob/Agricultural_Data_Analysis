'use client';

import { AreaChart, Area, Tooltip, ResponsiveContainer } from 'recharts';
import { formatCompact } from '@/lib/format';

interface SparklineProps {
  data: number[];
  /**
   * Optional year labels paired with `data` (same length). When provided, the
   * sparkline shows first/last value labels and a hover tooltip. Omit for the
   * legacy minimal render.
   */
  years?: number[];
  color?: string;
  height?: number;
  width?: number | string;
  /** Unit shown in tooltip (e.g. "head", "$"). Ignored when `years` is missing. */
  unit?: string;
}

export default function Sparkline({
  data,
  years,
  color = 'var(--field)',
  height = 28,
  width = '100%',
  unit,
}: SparklineProps) {
  const points = data.map((v, i) => ({
    i,
    v,
    year: years?.[i],
  }));
  const gradId = `spark-${color.replace(/[^a-zA-Z0-9]/g, '')}`;
  const showEndpoints = !!years && data.length >= 2;
  const firstVal = data[0];
  const lastVal = data[data.length - 1];

  return (
    <div
      style={{ width, height, position: showEndpoints ? 'relative' : undefined }}
    >
      {showEndpoints && (
        <>
          <span
            style={{
              position: 'absolute',
              left: 0,
              top: -10,
              fontSize: 9,
              color: 'var(--text3)',
              fontFamily: 'var(--font-mono)',
              lineHeight: 1,
              pointerEvents: 'none',
            }}
          >
            {formatCompact(firstVal)}
          </span>
          <span
            style={{
              position: 'absolute',
              right: 0,
              top: -10,
              fontSize: 9,
              color: 'var(--text)',
              fontFamily: 'var(--font-mono)',
              lineHeight: 1,
              fontWeight: 700,
              pointerEvents: 'none',
            }}
          >
            {formatCompact(lastVal)}
          </span>
        </>
      )}
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.15} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          {showEndpoints && (
            <Tooltip
              cursor={{ stroke: color, strokeWidth: 1, strokeDasharray: '2 2' }}
              contentStyle={{
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                padding: '4px 6px',
                fontSize: 11,
                lineHeight: 1.2,
                fontFamily: 'var(--font-mono)',
                color: 'var(--text)',
              }}
              formatter={(v) => [
                `${formatCompact(Number(v))}${unit ? ' ' + unit : ''}`,
                '',
              ]}
              labelFormatter={(_label, payload) => {
                const p = Array.isArray(payload) ? payload[0] : null;
                return p?.payload?.year ?? '';
              }}
              wrapperStyle={{ outline: 'none' }}
            />
          )}
          <Area
            type="monotone"
            dataKey="v"
            stroke={color}
            strokeWidth={1.5}
            fill={`url(#${gradId})`}
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
