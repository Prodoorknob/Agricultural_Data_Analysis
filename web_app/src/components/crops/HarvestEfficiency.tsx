'use client';

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import CitationBlock from '@/components/shared/CitationBlock';

interface EfficiencyPoint {
  year: number;
  efficiencyPct: number;
}

interface HarvestEfficiencyProps {
  data: EfficiencyPoint[];
  commodity: string;
  stateName: string;
}

export default function HarvestEfficiency({ data, commodity, stateName }: HarvestEfficiencyProps) {
  if (data.length === 0) return null;

  const avg = data.reduce((s, d) => s + d.efficiencyPct, 0) / data.length;
  const isMultiHarvest = data.some((d) => d.efficiencyPct > 105);

  return (
    <div
      className="p-4 rounded-[var(--radius-lg)] border flex-1"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
    >
      <h4
        className="text-[15px] font-bold mb-1"
        style={{ color: 'var(--text)', fontFamily: 'var(--font-body)' }}
      >
        Harvest Efficiency
      </h4>
      <p className="text-[13px] mb-3" style={{ color: 'var(--text2)' }}>
        {commodity} harvest efficiency averaged {avg.toFixed(0)}% over {data.length} years in {stateName}.
        {isMultiHarvest && ' Values above 100% indicate multiple harvests per year (e.g. hay cuttings).'}
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
              tickFormatter={(v) => `${v}%`}
              domain={[0, 'auto']}
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
              formatter={(v: number) => [`${v.toFixed(1)}%`, 'Efficiency']}
            />
            <ReferenceLine y={100} stroke="var(--harvest)" strokeDasharray="4 4" label="" />
            <Bar dataKey="efficiencyPct" fill="var(--sky)" radius={[2, 2, 0, 0]} barSize={12} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <CitationBlock source="USDA NASS QuickStats" vintage="Harvested / Planted × 100" />
    </div>
  );
}
