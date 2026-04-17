'use client';

import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip } from 'recharts';
import Sparkline from '@/components/shared/Sparkline';
import SectionHeading from '@/components/shared/SectionHeading';
import { formatCurrency, formatCompact } from '@/lib/format';
import { COMMODITY_COLORS } from '@/lib/constants';

interface RevenueMixItem {
  commodity: string;
  sales: number;
  color: string;
}

interface SparklineItem {
  commodity: string;
  values: number[];
  latestValue: number;
}

interface PeerItem {
  state: string;
  value: number;
}

interface StateFingerprintProps {
  revenueMix: RevenueMixItem[];
  totalRevenue: number;
  sparklines: SparklineItem[];
  peerComparison: PeerItem[];
  peerMetric: string;
  selectedState: string | null;
}

const DEFAULT_COLORS = [
  'var(--chart-corn)', 'var(--chart-soy)', 'var(--chart-wheat)',
  'var(--chart-cotton)', 'var(--chart-hay)', 'var(--sky)',
  'var(--muted)',
];

export default function StateFingerprint({
  revenueMix,
  totalRevenue,
  sparklines,
  peerComparison,
  peerMetric,
  selectedState,
}: StateFingerprintProps) {
  return (
    <div className="flex flex-col gap-5">
      {/* Revenue mix donut */}
      <div
        className="p-4 rounded-[var(--radius-lg)] border"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <SectionHeading>Revenue Mix</SectionHeading>
        <div className="flex items-center gap-4">
          <div style={{ width: 120, height: 120 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={revenueMix}
                  dataKey="sales"
                  nameKey="commodity"
                  cx="50%"
                  cy="50%"
                  innerRadius={32}
                  outerRadius={52}
                  paddingAngle={2}
                  strokeWidth={0}
                >
                  {revenueMix.map((entry, i) => (
                    <Cell key={entry.commodity} fill={entry.color || DEFAULT_COLORS[i] || DEFAULT_COLORS[6]} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex flex-col gap-1.5 flex-1 min-w-0">
            {revenueMix.slice(0, 5).map((item, i) => (
              <div key={item.commodity} className="flex items-center gap-2 text-[12px]">
                <span
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ background: item.color || DEFAULT_COLORS[i] }}
                />
                <span className="truncate" style={{ color: 'var(--text2)', fontFamily: 'var(--font-body)' }}>
                  {item.commodity}
                </span>
                <span className="ml-auto shrink-0" style={{ color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
                  {formatCurrency(item.sales)}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Sparkline strip */}
      <div
        className="p-4 rounded-[var(--radius-lg)] border"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <SectionHeading>25-Year Planted Area</SectionHeading>
        <div className="flex flex-col gap-2">
          {sparklines.slice(0, 5).map((item) => (
            <div key={item.commodity} className="flex items-center gap-3">
              <span
                className="text-[11px] w-16 truncate"
                style={{ color: 'var(--text2)', fontFamily: 'var(--font-body)' }}
              >
                {item.commodity}
              </span>
              <Sparkline
                data={item.values}
                color={COMMODITY_COLORS[item.commodity.toLowerCase()] || 'var(--field)'}
                width={60}
                height={20}
              />
              <span
                className="text-[11px] font-medium ml-auto"
                style={{ color: 'var(--text)', fontFamily: 'var(--font-stat)' }}
              >
                {formatCompact(item.latestValue)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Peer comparison */}
      {peerComparison.length > 0 && (
        <div
          className="p-4 rounded-[var(--radius-lg)] border"
          style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
        >
          <SectionHeading>Peer Comparison &middot; {peerMetric}</SectionHeading>
          <div style={{ height: 120 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={peerComparison} layout="vertical" margin={{ left: 24, right: 8, top: 4, bottom: 4 }}>
                <XAxis type="number" hide />
                <YAxis
                  type="category"
                  dataKey="state"
                  tick={{ fill: 'var(--text2)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
                  axisLine={false}
                  tickLine={false}
                  width={28}
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
                  formatter={(v: unknown) => [formatCompact(Number(v)), peerMetric]}
                />
                <Bar
                  dataKey="value"
                  fill="var(--field)"
                  radius={[0, 4, 4, 0]}
                  barSize={14}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}
