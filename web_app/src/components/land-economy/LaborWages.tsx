'use client';

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar,
} from 'recharts';
import CitationBlock from '@/components/shared/CitationBlock';
import SectionHeading from '@/components/shared/SectionHeading';

interface WageTrendPoint {
  year: number;
  /** NASS WAGE RATE for the selected state — hourly $ (undefined nationally). */
  stateWage?: number;
  /** NASS WAGE RATE 'National Avg' — hourly $. */
  nationalWage?: number;
  /** BLS QCEW avg_annual_pay for NAICS 111 (crop production). Denser than
      NASS wage rates, especially post-2014. Displayed on a secondary axis
      because annual pay and hourly wage aren't directly comparable. */
  blsAnnualPay?: number;
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
  const hasBls = wageTrend.some((d) => d.blsAnnualPay != null);

  const latest = wageTrend[wageTrend.length - 1];
  const earliest = wageTrend[0];
  const growthPct =
    (earliest?.stateWage ?? 0) > 0
      ? (((latest?.stateWage ?? 0) - (earliest?.stateWage ?? 0)) / (earliest?.stateWage ?? 1)) * 100
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
            <SectionHeading className="mb-2">Avg Farm Wage</SectionHeading>
            <div style={{ height: 240 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={wageTrend} margin={{ top: 5, right: 20, bottom: 30, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="year" axisLine={false} tickLine={false}
                    tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }} />
                  <YAxis
                    yAxisId="hourly"
                    axisLine={false}
                    tickLine={false}
                    tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                    tickFormatter={(v) => `$${v}/hr`}
                  />
                  {hasBls && (
                    <YAxis
                      yAxisId="annual"
                      orientation="right"
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                      tickFormatter={(v) => `$${Math.round(Number(v) / 1000)}K`}
                    />
                  )}
                  <Tooltip contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--text)' }} />
                  <Legend verticalAlign="bottom" wrapperStyle={{ fontSize: 11, fontFamily: 'var(--font-mono)', paddingTop: 8 }} />
                  <Line yAxisId="hourly" type="monotone" dataKey="stateWage" stroke="var(--field)" strokeWidth={2} dot={false} connectNulls name={`${stateName} (NASS $/hr)`} />
                  <Line yAxisId="hourly" type="monotone" dataKey="nationalWage" stroke="var(--text3)" strokeWidth={1.5} strokeDasharray="4 3" dot={false} connectNulls name="National (NASS $/hr)" />
                  {hasBls && (
                    <Line yAxisId="annual" type="monotone" dataKey="blsAnnualPay" stroke="var(--harvest)" strokeWidth={1.5} dot={false} connectNulls name="BLS QCEW annual pay" />
                  )}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Wage growth ranking */}
        {hasRank && (
          <div className="p-4 rounded-[var(--radius-lg)] border" style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
            <SectionHeading className="mb-2">Wage Growth Ranking (Top 10)</SectionHeading>
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
