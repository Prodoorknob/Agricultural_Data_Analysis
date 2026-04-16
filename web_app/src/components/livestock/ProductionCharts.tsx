'use client';

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import CitationBlock from '@/components/shared/CitationBlock';
import { formatCompact } from '@/lib/format';

interface ProductionPoint {
  year: number;
  stateValue: number;
  nationalValue: number;
}

interface ProductionSeries {
  title: string;
  unit: string;
  data: ProductionPoint[];
  color: string;
}

interface ProductionChartsProps {
  series: ProductionSeries[];
  stateName: string;
}

export default function ProductionCharts({ series, stateName }: ProductionChartsProps) {
  if (series.length === 0) return null;

  return (
    <div className="mb-8">
      <p className="text-[11px] font-bold tracking-[0.1em] uppercase mb-3"
        style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
        Production & Sales
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {series.map((s) => (
          <div key={s.title} className="p-4 rounded-[var(--radius-lg)] border"
            style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
            <p className="text-[13px] font-bold mb-2" style={{ color: 'var(--text)' }}>{s.title}</p>
            <div style={{ height: 180 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={s.data} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="year" axisLine={false} tickLine={false}
                    tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }} />
                  <YAxis axisLine={false} tickLine={false}
                    tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                    tickFormatter={(v) => formatCompact(v)} />
                  <Tooltip contentStyle={{
                    background: 'var(--surface)', border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--text)',
                  }} formatter={(v: number) => [formatCompact(v) + ' ' + s.unit]} />
                  <Line type="monotone" dataKey="stateValue" stroke={s.color} strokeWidth={2} dot={false} name={stateName} />
                  <Line type="monotone" dataKey="nationalValue" stroke="var(--text3)" strokeWidth={1} strokeDasharray="4 3" dot={false} name="National" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        ))}
      </div>
      <CitationBlock source="USDA NASS QuickStats" />
    </div>
  );
}
