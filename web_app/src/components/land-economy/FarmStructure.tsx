'use client';

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import CitationBlock from '@/components/shared/CitationBlock';
import { formatCompact } from '@/lib/format';

interface FarmStructurePoint {
  year: number;
  operationsCount: number;
  avgFarmSize: number;
}

interface FarmStructureProps {
  data: FarmStructurePoint[];
  stateName: string;
}

export default function FarmStructure({ data, stateName }: FarmStructureProps) {
  if (data.length === 0) return null;

  const latest = data[data.length - 1];
  const earlier = data.find((d) => d.year === 2015) || data[0];
  const opsDelta = earlier.operationsCount > 0
    ? latest.operationsCount - earlier.operationsCount
    : 0;
  const sizeDelta = earlier.avgFarmSize > 0
    ? ((latest.avgFarmSize - earlier.avgFarmSize) / earlier.avgFarmSize) * 100
    : 0;

  return (
    <div className="mb-10" id="operations">
      <h3 className="text-[20px] font-bold mb-1" style={{ color: 'var(--text)' }}>
        Operations & Farm Structure
      </h3>
      <p className="text-[13px] mb-4" style={{ color: 'var(--text2)' }}>
        {stateName} {opsDelta >= 0 ? 'gained' : 'lost'} {formatCompact(Math.abs(opsDelta))} farms since {earlier.year} but average farm size {sizeDelta >= 0 ? 'rose' : 'fell'} {Math.abs(sizeDelta).toFixed(0)}% — {opsDelta < 0 && sizeDelta > 0 ? 'consolidation, not decline' : 'structural shift'}.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Operations count */}
        <div className="p-4 rounded-[var(--radius-lg)] border" style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
          <p className="text-[11px] font-bold tracking-[0.1em] uppercase mb-2"
            style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>Operations Count</p>
          <div style={{ height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="year" axisLine={false} tickLine={false}
                  tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }} />
                <YAxis axisLine={false} tickLine={false}
                  tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                  tickFormatter={(v) => formatCompact(v)} />
                <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--text)' }}
                  formatter={(v: number) => [formatCompact(v), 'Operations']} />
                <Line type="monotone" dataKey="operationsCount" stroke="var(--field)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Avg farm size */}
        <div className="p-4 rounded-[var(--radius-lg)] border" style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
          <p className="text-[11px] font-bold tracking-[0.1em] uppercase mb-2"
            style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>Avg Farm Size (acres)</p>
          <div style={{ height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="year" axisLine={false} tickLine={false}
                  tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }} />
                <YAxis axisLine={false} tickLine={false}
                  tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }} />
                <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--text)' }}
                  formatter={(v: number) => [`${v.toFixed(0)} acres`, 'Avg Size']} />
                <Line type="monotone" dataKey="avgFarmSize" stroke="var(--harvest)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
      <CitationBlock source="USDA NASS QuickStats" />
    </div>
  );
}
