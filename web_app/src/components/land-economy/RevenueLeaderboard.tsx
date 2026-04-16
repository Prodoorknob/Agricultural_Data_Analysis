'use client';

import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import CitationBlock from '@/components/shared/CitationBlock';
import { formatCurrency } from '@/lib/format';
import { COMMODITY_COLORS } from '@/lib/constants';

interface RevenueItem {
  commodity: string;
  sales: number;
  growthPct10yr: number;
}

interface RevenueLeaderboardProps {
  data: RevenueItem[];
  stateName: string;
  year: number;
}

export default function RevenueLeaderboard({ data, stateName, year }: RevenueLeaderboardProps) {
  const sorted = [...data].sort((a, b) => b.sales - a.sales).slice(0, 10);
  const boomCrops = [...data].sort((a, b) => b.growthPct10yr - a.growthPct10yr).slice(0, 3);
  const declineCrops = [...data].sort((a, b) => a.growthPct10yr - b.growthPct10yr).slice(0, 3);

  return (
    <div className="mb-10" id="revenue">
      <h3 className="text-[20px] font-bold mb-1" style={{ color: 'var(--text)' }}>
        Revenue Leaderboard
      </h3>
      <p className="text-[13px] mb-4" style={{ color: 'var(--text2)' }}>
        Top commodities by sales in {stateName}, {year}.
      </p>

      <div
        className="p-4 rounded-[var(--radius-lg)] border mb-4"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div style={{ height: Math.max(250, sorted.length * 28) }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={sorted} layout="vertical" margin={{ left: 80, right: 20, top: 5, bottom: 5 }}>
              <XAxis type="number" axisLine={false} tickLine={false}
                tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                tickFormatter={(v) => formatCurrency(v)} />
              <YAxis type="category" dataKey="commodity" axisLine={false} tickLine={false}
                tick={{ fill: 'var(--text2)', fontSize: 11, fontFamily: 'var(--font-body)' }} width={75} />
              <Tooltip contentStyle={{
                background: 'var(--surface)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--text)',
              }} formatter={(v: number) => [formatCurrency(v), 'Sales']} />
              <Bar dataKey="sales" radius={[0, 4, 4, 0]} barSize={16}>
                {sorted.map((entry) => (
                  <Cell key={entry.commodity} fill={COMMODITY_COLORS[entry.commodity.toLowerCase()] || 'var(--field)'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Boom & Decline callouts */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Callout
          title="Boom Crops"
          items={boomCrops.map((c) => `${c.commodity}: +${c.growthPct10yr.toFixed(0)}%`)}
          color="var(--positive)"
        />
        <Callout
          title="Decline Crops"
          items={declineCrops.filter((c) => c.growthPct10yr < 0).map((c) => `${c.commodity}: ${c.growthPct10yr.toFixed(0)}%`)}
          color="var(--negative)"
        />
      </div>
      <CitationBlock source="USDA NASS QuickStats" vintage={`${year}`} />
    </div>
  );
}

function Callout({ title, items, color }: { title: string; items: string[]; color: string }) {
  return (
    <div className="p-3 rounded-[var(--radius-md)] border" style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
      <p className="text-[11px] font-bold tracking-[0.1em] uppercase mb-2"
        style={{ color, fontFamily: 'var(--font-mono)' }}>{title}</p>
      {items.length > 0 ? items.map((item, i) => (
        <p key={i} className="text-[12px]" style={{ color: 'var(--text2)' }}>{item}</p>
      )) : (
        <p className="text-[12px]" style={{ color: 'var(--text3)' }}>None</p>
      )}
    </div>
  );
}
