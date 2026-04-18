'use client';

import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip } from 'recharts';
import Sparkline from '@/components/shared/Sparkline';
import SectionHeading from '@/components/shared/SectionHeading';
import { formatCurrency, formatCompact } from '@/lib/format';
import { COMMODITY_COLORS } from '@/lib/constants';

type RevenueSector = 'CROPS' | 'LIVESTOCK';

interface RevenueMixItem {
  commodity: string;
  sales: number;
  sector: RevenueSector;
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

function RevenueRow({ item, total }: { item: RevenueMixItem; total: number }) {
  const pct = total > 0 ? (item.sales / total) * 100 : 0;
  return (
    <div className="flex items-center gap-2 text-[12px]">
      <span
        className="shrink-0 truncate"
        style={{ color: 'var(--text2)', fontFamily: 'var(--font-body)', width: 96 }}
        title={item.commodity}
      >
        {item.commodity}
      </span>
      <div
        className="flex-1 h-1.5 rounded-full overflow-hidden"
        style={{ background: 'var(--surface2)' }}
      >
        <div
          className="h-full rounded-full"
          style={{ width: `${pct}%`, background: item.color || 'var(--muted)' }}
        />
      </div>
      <span
        className="shrink-0 text-right tabular-nums"
        style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)', fontSize: '10px', width: 32 }}
      >
        {pct.toFixed(0)}%
      </span>
      <span
        className="shrink-0 text-right tabular-nums"
        style={{ color: 'var(--text)', fontFamily: 'var(--font-mono)', fontSize: '11px', width: 52 }}
      >
        {formatCurrency(item.sales)}
      </span>
    </div>
  );
}

function RevenueGroup({
  label,
  items,
  total,
}: {
  label: string;
  items: RevenueMixItem[];
  total: number;
}) {
  const subtotal = items.reduce((s, r) => s + r.sales, 0);
  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <span
          className="text-[10px] font-bold tracking-[0.1em] uppercase"
          style={{ color: 'var(--text2)', fontFamily: 'var(--font-mono)' }}
        >
          {label}
        </span>
        <span
          className="text-[10px] tabular-nums"
          style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
        >
          {formatCurrency(subtotal)}
        </span>
      </div>
      <div className="flex flex-col gap-1.5">
        {items.map((item) => (
          <RevenueRow key={`${item.sector}-${item.commodity}`} item={item} total={total} />
        ))}
      </div>
    </div>
  );
}

export default function StateFingerprint({
  revenueMix,
  totalRevenue,
  sparklines,
  peerComparison,
  peerMetric,
  selectedState,
}: StateFingerprintProps) {
  const crops = revenueMix.filter((r) => r.sector === 'CROPS');
  const livestock = revenueMix.filter((r) => r.sector === 'LIVESTOCK');

  return (
    <div className="flex flex-col gap-5">
      {/* Revenue mix table, split by sector */}
      <div
        className="p-4 rounded-[var(--radius-lg)] border"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-baseline justify-between mb-3">
          <p
            className="text-[11px] font-bold tracking-[0.1em] uppercase"
            style={{ color: 'var(--section-heading)', fontFamily: 'var(--font-mono)' }}
          >
            Revenue Mix
          </p>
          <span
            className="text-[11px] tabular-nums"
            style={{ color: 'var(--text2)', fontFamily: 'var(--font-mono)' }}
          >
            {formatCurrency(totalRevenue)} total
          </span>
        </div>
        {crops.length > 0 && <RevenueGroup label="Crops" items={crops} total={totalRevenue} />}
        {crops.length > 0 && livestock.length > 0 && (
          <div className="my-3 border-t" style={{ borderColor: 'var(--border)' }} />
        )}
        {livestock.length > 0 && (
          <RevenueGroup label="Livestock" items={livestock} total={totalRevenue} />
        )}
        {crops.length === 0 && livestock.length === 0 && (
          <p className="text-[12px]" style={{ color: 'var(--text3)' }}>
            No sales data for this year.
          </p>
        )}
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
                className="text-[11px] w-16 shrink-0 truncate"
                style={{ color: 'var(--text2)', fontFamily: 'var(--font-body)' }}
              >
                {item.commodity}
              </span>
              <div className="flex-1 min-w-0">
                <Sparkline
                  data={item.values}
                  color={COMMODITY_COLORS[item.commodity.toLowerCase()] || 'var(--field)'}
                  width="100%"
                  height={20}
                />
              </div>
              <span
                className="text-[11px] font-medium shrink-0"
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
