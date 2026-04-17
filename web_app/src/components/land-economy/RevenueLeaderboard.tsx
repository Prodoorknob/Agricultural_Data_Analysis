'use client';

import { useState, useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import CitationBlock from '@/components/shared/CitationBlock';
import { formatCurrency } from '@/lib/format';
import { COMMODITY_COLORS } from '@/lib/constants';

interface RevenueItem {
  commodity: string;
  sales: number;
  /** Growth vs. the fixed 2012 Census baseline. */
  growthPctVsCensus: number;
  /** NASS group_desc ('FIELD CROPS', 'VEGETABLES', ...). May be null on fallback. */
  group_desc: string | null;
  /** NASS sector_desc ('CROPS', 'ANIMALS & PRODUCTS'). Used to bucket livestock. */
  sector_desc: string | null;
}

interface RevenueLeaderboardProps {
  data: RevenueItem[];
  stateName: string;
  year: number;
}

// Crop-type pills → NASS group_desc values that each pill filters to. 'ALL'
// is a sentinel that bypasses the filter entirely. 'LIVESTOCK' is a special
// case that covers the animal-products sector (NASS publishes livestock
// species under sector_desc='ANIMALS & PRODUCTS' rather than a single
// group_desc).
type GroupId =
  | 'ALL'
  | 'FIELD CROPS'
  | 'FRUIT & TREE NUTS'
  | 'VEGETABLES'
  | 'LIVESTOCK'
  | 'DAIRY'
  | 'POULTRY';

const PILLS: { id: GroupId; label: string }[] = [
  { id: 'ALL', label: 'All' },
  { id: 'FIELD CROPS', label: 'Field Crops' },
  { id: 'FRUIT & TREE NUTS', label: 'Fruits' },
  { id: 'VEGETABLES', label: 'Vegetables' },
  { id: 'LIVESTOCK', label: 'Livestock' },
  { id: 'DAIRY', label: 'Dairy' },
  { id: 'POULTRY', label: 'Poultry' },
];

function matchesPill(item: RevenueItem, pill: GroupId): boolean {
  if (pill === 'ALL') return true;
  if (pill === 'LIVESTOCK') {
    return item.sector_desc === 'ANIMALS & PRODUCTS' || item.group_desc === 'LIVESTOCK';
  }
  return item.group_desc === pill;
}

export default function RevenueLeaderboard({ data, stateName, year }: RevenueLeaderboardProps) {
  const [pill, setPill] = useState<GroupId>('ALL');

  const filtered = useMemo(() => data.filter((d) => matchesPill(d, pill)), [data, pill]);
  const sorted = [...filtered].sort((a, b) => b.sales - a.sales).slice(0, 10);
  const boomCrops = [...filtered].sort((a, b) => b.growthPctVsCensus - a.growthPctVsCensus).slice(0, 3);
  const declineCrops = [...filtered].sort((a, b) => a.growthPctVsCensus - b.growthPctVsCensus).slice(0, 3);

  return (
    <div className="mb-10" id="revenue">
      <h3 className="text-[20px] font-bold mb-1" style={{ color: 'var(--text)' }}>
        Revenue Leaderboard
      </h3>
      <p className="text-[13px] mb-3" style={{ color: 'var(--text2)' }}>
        Top commodities by sales in {stateName}, {year}.
      </p>

      {/* Crop-type pills */}
      <div className="flex items-center gap-1.5 flex-wrap mb-3">
        {PILLS.map((p) => {
          const active = p.id === pill;
          return (
            <button
              key={p.id}
              onClick={() => setPill(p.id)}
              className="px-2.5 py-1 text-[12px] font-medium rounded-[var(--radius-full)] border transition-colors"
              style={{
                background: active ? 'var(--field)' : 'transparent',
                color: active ? '#FFFFFF' : 'var(--text2)',
                borderColor: active ? 'var(--field)' : 'var(--border2)',
                fontFamily: 'var(--font-body)',
              }}
            >
              {p.label}
            </button>
          );
        })}
      </div>

      <div
        className="p-4 rounded-[var(--radius-lg)] border mb-4"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        {sorted.length === 0 ? (
          <p className="text-[13px] py-8 text-center" style={{ color: 'var(--text3)' }}>
            No commodities in this category for {stateName}.
          </p>
        ) : (
          <div style={{ height: Math.max(250, sorted.length * 28) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={sorted} layout="vertical" margin={{ left: 80, right: 20, top: 5, bottom: 5 }}>
                <XAxis type="number" axisLine={false} tickLine={false}
                  tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                  tickFormatter={(v) => formatCurrency(Number(v))} />
                <YAxis type="category" dataKey="commodity" axisLine={false} tickLine={false}
                  tick={{ fill: 'var(--text2)', fontSize: 11, fontFamily: 'var(--font-body)' }} width={75} />
                <Tooltip contentStyle={{
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--text)',
                }} formatter={(v: unknown) => [formatCurrency(Number(v)), 'Sales']} />
                <Bar dataKey="sales" radius={[0, 4, 4, 0]} barSize={16}>
                  {sorted.map((entry) => (
                    <Cell key={entry.commodity} fill={COMMODITY_COLORS[entry.commodity.toLowerCase()] || 'var(--field)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Boom & Decline callouts — baseline is 2012 Census. */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Callout
          title="Boom Crops vs 2012 Census"
          items={boomCrops
            .filter((c) => c.growthPctVsCensus > 0)
            .map((c) => `${c.commodity}: +${c.growthPctVsCensus.toFixed(0)}%`)}
          color="var(--positive)"
        />
        <Callout
          title="Decline Crops vs 2012 Census"
          items={declineCrops
            .filter((c) => c.growthPctVsCensus < 0)
            .map((c) => `${c.commodity}: ${c.growthPctVsCensus.toFixed(0)}%`)}
          color="var(--negative)"
        />
      </div>
      <CitationBlock source="state_commodity_totals aggregate" vintage={`${year} vs 2012 Census`} />
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
