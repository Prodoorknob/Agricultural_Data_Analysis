'use client';

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import CitationBlock from '@/components/shared/CitationBlock';
import type { DxyPoint } from '@/types/market';

interface DxyStripProps {
  data: DxyPoint[];
}

export default function DxyStrip({ data }: DxyStripProps) {
  if (data.length < 2) return null;

  const latest = data[data.length - 1]?.value || 0;
  const threeMonthsAgo = data[Math.max(0, data.length - 63)]?.value || latest;
  const changePct = threeMonthsAgo > 0 ? ((latest - threeMonthsAgo) / threeMonthsAgo) * 100 : 0;
  const direction = changePct >= 0 ? 'strengthened' : 'weakened';
  const impact = changePct >= 0 ? 'headwind' : 'tailwind';

  return (
    <div className="mb-6">
      <h3 className="text-[15px] font-bold mb-1" style={{ color: 'var(--text)' }}>
        Dollar Index (DXY)
      </h3>
      <p className="text-[13px] mb-3" style={{ color: 'var(--text2)' }}>
        The dollar has {direction} {Math.abs(changePct).toFixed(1)}% in 3 months — historically a {impact} for U.S. grain exports.
      </p>

      <div
        className="p-3 rounded-[var(--radius-lg)] border"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div style={{ height: 100 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 5, right: 10, bottom: 0, left: 10 }}>
              <XAxis dataKey="date" hide />
              <YAxis hide domain={['auto', 'auto']} />
              <Tooltip
                contentStyle={{
                  background: 'var(--surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-md)',
                  fontSize: 11,
                  color: 'var(--text)',
                }}
                formatter={(v: number) => [v.toFixed(2), 'DXY']}
                labelFormatter={(d) => new Date(d).toLocaleDateString()}
              />
              <Line type="monotone" dataKey="value" stroke="var(--sky)" strokeWidth={1.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
      <CitationBlock source="FRED" vintage="Daily" />
    </div>
  );
}
