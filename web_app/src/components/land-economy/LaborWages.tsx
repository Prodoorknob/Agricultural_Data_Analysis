'use client';

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell,
} from 'recharts';
import CitationBlock from '@/components/shared/CitationBlock';

interface WageTrendPoint {
  year: number;
  stateWage: number;
  nationalWage: number;
}

interface WageRankItem {
  state: string;
  wageGrowthPct10yr: number;
}

interface LaborWagesProps {
  wageTrend: WageTrendPoint[];
  wageRanking: WageRankItem[];
  stateName: string;
}

export default function LaborWages({ wageTrend, wageRanking, stateName }: LaborWagesProps) {
  const hasWage = wageTrend.length > 0;
  const hasRank = wageRanking.length > 0;

  const latest = wageTrend[wageTrend.length - 1];
  const earliest = wageTrend[0];
  const growthPct = earliest?.stateWage > 0
    ? ((latest?.stateWage - earliest.stateWage) / earliest.stateWage) * 100
    : 0;

  return (
    <div className="mb-10" id="labor">
      <h3 className="text-[20px] font-bold mb-1" style={{ color: 'var(--text)' }}>
        Labor & Wages
      </h3>
      {hasWage && (
        <p className="text-[13px] mb-4" style={{ color: 'var(--text2)' }}>
          {stateName} farm wages grew {growthPct.toFixed(0)}% over the period shown.
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Wage trend */}
        {hasWage && (
          <div className="p-4 rounded-[var(--radius-lg)] border" style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
            <p className="text-[11px] font-bold tracking-[0.1em] uppercase mb-2"
              style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>Avg Farm Wage</p>
            <div style={{ height: 220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={wageTrend} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="year" axisLine={false} tickLine={false}
                    tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }} />
                  <YAxis axisLine={false} tickLine={false}
                    tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                    tickFormatter={(v) => `$${v}`} />
                  <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--text)' }} />
                  <Line type="monotone" dataKey="stateWage" stroke="var(--field)" strokeWidth={2} dot={false} name={stateName} />
                  <Line type="monotone" dataKey="nationalWage" stroke="var(--text3)" strokeWidth={1.5} strokeDasharray="4 3" dot={false} name="National" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Wage growth ranking */}
        {hasRank && (
          <div className="p-4 rounded-[var(--radius-lg)] border" style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
            <p className="text-[11px] font-bold tracking-[0.1em] uppercase mb-2"
              style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>Wage Growth Ranking (Top 10)</p>
            <div style={{ height: 220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={wageRanking.slice(0, 10)} layout="vertical" margin={{ left: 30, right: 20 }}>
                  <XAxis type="number" axisLine={false} tickLine={false}
                    tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                    tickFormatter={(v) => `${v}%`} />
                  <YAxis type="category" dataKey="state" axisLine={false} tickLine={false}
                    tick={{ fill: 'var(--text2)', fontSize: 11, fontFamily: 'var(--font-mono)' }} width={28} />
                  <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--text)' }}
                    formatter={(v: unknown) => [`${Number(v).toFixed(1)}%`, 'Growth']} />
                  <Bar dataKey="wageGrowthPct10yr" fill="var(--field)" radius={[0, 4, 4, 0]} barSize={14} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
      <CitationBlock source="USDA NASS QuickStats" vintage="Farm labor wage" />
    </div>
  );
}
