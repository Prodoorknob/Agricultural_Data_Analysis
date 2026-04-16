'use client';

import { useMemo } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Area, AreaChart,
} from 'recharts';
import CitationBlock from '@/components/shared/CitationBlock';
import type { FuturesPoint } from '@/types/market';

interface PriceHistoryChartProps {
  data: FuturesPoint[];
  commodity: string;
  range: string;
  onRangeChange: (r: string) => void;
}

const RANGES = ['1M', '6M', '1Y', '5Y', 'MAX'];

export default function PriceHistoryChart({
  data,
  commodity,
  range,
  onRangeChange,
}: PriceHistoryChartProps) {
  const chartData = useMemo(() => {
    return data.map((p) => ({
      date: p.date,
      price: p.settle,
    }));
  }, [data]);

  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-3">
        <h3
          className="text-[18px] font-bold"
          style={{ color: 'var(--text)', fontFamily: 'var(--font-body)' }}
        >
          Price History
        </h3>
        {/* Range chips */}
        <div className="flex items-center gap-1">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => onRangeChange(r)}
              className="px-2.5 py-1 text-[11px] font-bold rounded-[var(--radius-full)] border transition-all"
              style={{
                background: range === r ? 'var(--field)' : 'transparent',
                color: range === r ? '#FFFFFF' : 'var(--text3)',
                borderColor: range === r ? 'var(--field)' : 'var(--border2)',
                fontFamily: 'var(--font-mono)',
                transitionDuration: 'var(--duration-fast)',
              }}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      <div
        className="p-4 rounded-[var(--radius-lg)] border"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div style={{ height: 360 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 10, right: 20, bottom: 5, left: 10 }}>
              <defs>
                <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--harvest)" stopOpacity={0.1} />
                  <stop offset="100%" stopColor="var(--harvest)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis
                dataKey="date"
                axisLine={false}
                tickLine={false}
                tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                tickFormatter={(d) => {
                  const dt = new Date(d);
                  return `${dt.getMonth() + 1}/${dt.getFullYear().toString().slice(2)}`;
                }}
                minTickGap={40}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                tick={{ fill: 'var(--text3)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
                tickFormatter={(v) => `$${Number(v).toFixed(2)}`}
                domain={['auto', 'auto']}
              />
              <Tooltip
                contentStyle={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  boxShadow: 'var(--shadow-md)',
                  fontSize: 12,
                  color: 'var(--text)',
                }}
                formatter={(v: unknown) => [`$${Number(v).toFixed(2)}/bu`, 'Settle']}
                labelFormatter={(d) => new Date(d).toLocaleDateString()}
              />
              <Area
                type="monotone"
                dataKey="price"
                stroke="var(--harvest)"
                strokeWidth={2}
                fill="url(#priceGrad)"
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
      <CitationBlock source="CME Group via Yahoo Finance" vintage="Daily settle" />
    </div>
  );
}
