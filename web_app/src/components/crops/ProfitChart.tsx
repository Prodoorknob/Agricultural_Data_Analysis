'use client';

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine, Cell,
} from 'recharts';
import CitationBlock from '@/components/shared/CitationBlock';

interface ProfitPoint {
  year: number;
  profitPerAcre: number;
}

interface ProfitChartProps {
  data: ProfitPoint[];
  commodity: string;
  stateName: string;
}

export default function ProfitChart({ data, commodity, stateName }: ProfitChartProps) {
  if (data.length === 0) return null;

  const min = Math.min(...data.map((d) => d.profitPerAcre));
  const max = Math.max(...data.map((d) => d.profitPerAcre));
  const minYear = data.find((d) => d.profitPerAcre === min)?.year;
  const maxYear = data.find((d) => d.profitPerAcre === max)?.year;

  return (
    <div
      className="p-4 rounded-[var(--radius-lg)] border flex-1"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
    >
      <h4
        className="text-[15px] font-bold mb-1"
        style={{ color: 'var(--text)', fontFamily: 'var(--font-body)' }}
      >
        Profit per Acre
      </h4>
      <p className="text-[13px] mb-3" style={{ color: 'var(--text2)' }}>
        {commodity} profit per acre ranged from ${min.toFixed(0)} ({minYear}) to ${max.toFixed(0)} ({maxYear}).
      </p>

      <div style={{ height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="year"
              axisLine={false}
              tickLine={false}
              tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
              interval={4}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
              tickFormatter={(v) => `$${v}`}
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
              formatter={(v: unknown) => [`$${Number(v).toFixed(0)}/acre`, 'Profit']}
            />
            <ReferenceLine y={0} stroke="var(--text3)" strokeDasharray="3 3" />
            <Bar dataKey="profitPerAcre" radius={[2, 2, 0, 0]} barSize={12}>
              {data.map((entry) => (
                <Cell
                  key={entry.year}
                  fill={entry.profitPerAcre >= 0 ? 'var(--field)' : 'var(--negative)'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <CitationBlock source="NASS yield × CME Oct 1 settle − ERS cost" />
    </div>
  );
}
