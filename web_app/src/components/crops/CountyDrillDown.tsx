'use client';

import { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts';
import CitationBlock from '@/components/shared/CitationBlock';

interface CountyItem {
  countyName: string;
  value: number;
}

interface CountyDrillDownProps {
  data: CountyItem[];
  metric: string;
  unit: string;
  stateName: string;
  commodity: string;
}

export default function CountyDrillDown({
  data,
  metric,
  unit,
  stateName,
  commodity,
}: CountyDrillDownProps) {
  const top15 = useMemo(
    () => [...data].sort((a, b) => b.value - a.value).slice(0, 15),
    [data]
  );

  if (top15.length === 0) {
    return (
      <div className="py-8 text-center">
        <p className="text-[14px]" style={{ color: 'var(--text3)' }}>
          No county data available for {commodity} in {stateName}.
        </p>
      </div>
    );
  }

  return (
    <div className="mb-8">
      <h3
        className="text-[18px] font-bold mb-1"
        style={{ color: 'var(--text)', fontFamily: 'var(--font-body)' }}
      >
        County Breakdown
      </h3>
      <p className="text-[13px] mb-4" style={{ color: 'var(--text2)' }}>
        Top 15 counties by {metric.toLowerCase()} for {commodity} in {stateName}.
      </p>

      <div
        className="p-4 rounded-[var(--radius-lg)] border"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div style={{ height: Math.max(320, top15.length * 28) }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={top15}
              layout="vertical"
              margin={{ left: 100, right: 20, top: 5, bottom: 5 }}
            >
              <XAxis
                type="number"
                axisLine={false}
                tickLine={false}
                tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
              />
              <YAxis
                type="category"
                dataKey="countyName"
                axisLine={false}
                tickLine={false}
                tick={{ fill: 'var(--text2)', fontSize: 11, fontFamily: 'var(--font-body)' }}
                width={95}
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
                formatter={(v: number) => [`${v.toLocaleString()} ${unit}`, metric]}
              />
              <Bar dataKey="value" fill="var(--field)" radius={[0, 4, 4, 0]} barSize={16} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <CitationBlock source="USDA NASS QuickStats · County data" />
    </div>
  );
}
