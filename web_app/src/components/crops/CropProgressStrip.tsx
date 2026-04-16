'use client';

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Area, AreaChart,
} from 'recharts';
import BandShell from '@/components/shared/BandShell';
import CitationBlock from '@/components/shared/CitationBlock';

interface ConditionPoint {
  week: string;
  goodExcellentPct: number;
  fiveYearAvgPct: number;
}

interface CropProgressStripProps {
  conditionData: ConditionPoint[];
  commodity: string;
  stateName: string;
}

export default function CropProgressStrip({
  conditionData,
  commodity,
  stateName,
}: CropProgressStripProps) {
  const hasData = conditionData.length > 0;
  const latest = conditionData[conditionData.length - 1];
  const delta = latest ? latest.goodExcellentPct - latest.fiveYearAvgPct : 0;

  return (
    <BandShell
      visibleSeasons={['early-growth', 'mid-season', 'harvest']}
      dormantMessage={`Crop conditions return May. ${commodity} G/E was ${latest?.goodExcellentPct?.toFixed(0) || '—'}% at season end.`}
      empty={!hasData}
      emptyMessage={`No crop condition data available for ${commodity} in ${stateName}.`}
    >
      <div className="mb-8">
        <h3
          className="text-[18px] font-bold mb-1"
          style={{ color: 'var(--text)', fontFamily: 'var(--font-body)' }}
        >
          Crop Condition
        </h3>
        <p className="text-[13px] mb-4" style={{ color: 'var(--text2)' }}>
          {latest
            ? `Condition is tracking ${Math.abs(delta).toFixed(0)} points ${delta >= 0 ? 'above' : 'below'} the 5-year average.`
            : ''}
        </p>

        <div
          className="p-4 rounded-[var(--radius-lg)] border"
          style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
        >
          <div style={{ height: 220 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={conditionData} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis
                  dataKey="week"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                  domain={[0, 100]}
                  tickFormatter={(v) => `${v}%`}
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
                  formatter={(v: number) => [`${v.toFixed(1)}%`]}
                />
                <Area
                  type="monotone"
                  dataKey="fiveYearAvgPct"
                  fill="var(--field-subtle)"
                  stroke="var(--text3)"
                  strokeWidth={1}
                  strokeDasharray="4 3"
                  name="5yr Avg"
                />
                <Area
                  type="monotone"
                  dataKey="goodExcellentPct"
                  fill="var(--field-tint)"
                  stroke="var(--field)"
                  strokeWidth={2}
                  name="Good/Excellent %"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
        <CitationBlock source="USDA NASS Crop Progress" vintage="Weekly" />
      </div>
    </BandShell>
  );
}
