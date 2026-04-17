'use client';

import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts';
import CitationBlock from '@/components/shared/CitationBlock';
import { formatCompact } from '@/lib/format';

interface LandUsePoint {
  year: number;
  cropland: number;
  pasture: number;
  forest: number;
  urban: number;
  /** "Special use" — parks, wildlife refuges, roads, defense. New category
      from the land_use parquet. */
  special?: number;
  other: number;
}

interface LandUseMixProps {
  data: LandUsePoint[];
  stateName: string;
}

export default function LandUseMix({ data, stateName }: LandUseMixProps) {
  if (data.length === 0) return null;

  return (
    <div className="mb-10" id="land-use">
      <h3 className="text-[20px] font-bold mb-1" style={{ color: 'var(--text)' }}>
        Land Use Mix
      </h3>
      <p className="text-[13px] mb-4" style={{ color: 'var(--text2)' }}>
        How {stateName}'s land is allocated across uses over time.
      </p>

      <div className="p-4 rounded-[var(--radius-lg)] border" style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
        <div style={{ height: 300 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 10, right: 20, bottom: 5, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="year" axisLine={false} tickLine={false}
                tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }} />
              <YAxis axisLine={false} tickLine={false}
                tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                tickFormatter={(v) => formatCompact(Number(v))} />
              <Tooltip contentStyle={{
                background: 'var(--surface)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--text)',
              }} formatter={(v: unknown) => [formatCompact(Number(v)) + ' acres']} />
              <Legend verticalAlign="bottom" iconType="square" wrapperStyle={{ fontSize: 11, fontFamily: 'var(--font-mono)', paddingTop: 8 }} />
              <Area type="monotone" dataKey="cropland" stackId="1" fill="var(--field)" stroke="var(--field)" fillOpacity={0.7} name="Cropland" />
              <Area type="monotone" dataKey="pasture" stackId="1" fill="var(--harvest)" stroke="var(--harvest)" fillOpacity={0.5} name="Pasture" />
              <Area type="monotone" dataKey="forest" stackId="1" fill="var(--chart-hay)" stroke="var(--chart-hay)" fillOpacity={0.4} name="Forest" />
              <Area type="monotone" dataKey="urban" stackId="1" fill="var(--soil)" stroke="var(--soil)" fillOpacity={0.4} name="Urban" />
              <Area type="monotone" dataKey="special" stackId="1" fill="var(--sky)" stroke="var(--sky)" fillOpacity={0.3} name="Special Use" />
              <Area type="monotone" dataKey="other" stackId="1" fill="var(--muted)" stroke="var(--muted)" fillOpacity={0.3} name="Other" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
      <CitationBlock source="USDA NASS QuickStats" vintage="Land use categories" />
    </div>
  );
}
