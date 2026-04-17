'use client';

import Sparkline from '@/components/shared/Sparkline';
import CitationBlock from '@/components/shared/CitationBlock';
import SectionHeading from '@/components/shared/SectionHeading';
import { formatCompact } from '@/lib/format';

interface TableData {
  rows: { year: number; cattleSales: number; hogSales: number; milkProduction: number }[];
  cattleSparkYears: number[];
  cattleSparkValues: number[];
  hogSparkYears: number[];
  hogSparkValues: number[];
  milkSparkYears: number[];
  milkSparkValues: number[];
}

interface Props {
  data: TableData;
  stateName: string;
}

const METRICS = [
  {
    key: 'cattleSales' as const,
    title: 'Cattle Sales',
    unit: '$',
    color: 'var(--chart-cattle)',
    format: (v: number) => (v > 0 ? `$${formatCompact(v)}` : '—'),
  },
  {
    key: 'hogSales' as const,
    title: 'Hog Sales',
    unit: '$',
    color: 'var(--chart-hogs)',
    format: (v: number) => (v > 0 ? `$${formatCompact(v)}` : '—'),
  },
  {
    key: 'milkProduction' as const,
    title: 'Milk Production',
    unit: 'lbs',
    color: 'var(--chart-dairy)',
    format: (v: number) => (v > 0 ? `${formatCompact(v)} lbs` : '—'),
  },
];

export default function ProductionSalesTable({ data, stateName }: Props) {
  // If every metric column is zero across all years, render nothing to avoid
  // a wall of em-dashes.
  const anyData = data.rows.some(
    (r) => r.cattleSales > 0 || r.hogSales > 0 || r.milkProduction > 0,
  );
  if (!anyData) return null;

  // Reverse so the most recent year reads top-down.
  const sortedRows = [...data.rows].sort((a, b) => b.year - a.year);

  return (
    <div className="mb-8">
      <div className="flex items-baseline justify-between mb-3">
        <SectionHeading className="mb-0">Production &amp; Sales</SectionHeading>
        <span className="text-[12px]" style={{ color: 'var(--text3)' }}>
          {stateName} · last 11 years
        </span>
      </div>

      <div
        className="rounded-[var(--radius-lg)] border overflow-hidden"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        {/* Header row with sparklines */}
        <div
          className="grid grid-cols-[80px_repeat(3,minmax(0,1fr))] gap-x-4 px-4 py-3 border-b"
          style={{ borderColor: 'var(--border)', background: 'var(--surface2)' }}
        >
          <div
            className="text-[10px] font-bold tracking-[0.1em] uppercase"
            style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
          >
            Year
          </div>
          {METRICS.map((m, i) => {
            const values =
              i === 0 ? data.cattleSparkValues : i === 1 ? data.hogSparkValues : data.milkSparkValues;
            const years =
              i === 0 ? data.cattleSparkYears : i === 1 ? data.hogSparkYears : data.milkSparkYears;
            return (
              <div key={m.key} className="flex flex-col gap-2">
                <span
                  className="text-[11px] font-bold tracking-[0.05em] uppercase"
                  style={{ color: 'var(--text2)', fontFamily: 'var(--font-mono)' }}
                >
                  {m.title} <span style={{ color: 'var(--text3)' }}>({m.unit})</span>
                </span>
                <div style={{ paddingTop: 10 }}>
                  <Sparkline
                    data={values}
                    years={years}
                    color={m.color}
                    width={140}
                    height={24}
                    unit={m.unit}
                  />
                </div>
              </div>
            );
          })}
        </div>

        {/* Data rows */}
        <div>
          {sortedRows.map((row, idx) => {
            const prior = sortedRows[idx + 1]; // prior = older year, since sorted desc
            return (
              <div
                key={row.year}
                className="grid grid-cols-[80px_repeat(3,minmax(0,1fr))] gap-x-4 px-4 py-2 border-b last:border-b-0"
                style={{ borderColor: 'var(--border)' }}
              >
                <div
                  className="text-[13px] font-bold"
                  style={{ color: 'var(--text)', fontFamily: 'var(--font-mono)' }}
                >
                  {row.year}
                </div>
                {METRICS.map((m) => {
                  const val = row[m.key];
                  const priorVal = prior ? prior[m.key] : 0;
                  const yoy = priorVal > 0 ? ((val - priorVal) / priorVal) * 100 : null;
                  return (
                    <div key={m.key} className="flex items-baseline gap-2">
                      <span
                        className="text-[13px]"
                        style={{ color: 'var(--text)', fontFamily: 'var(--font-mono)' }}
                      >
                        {m.format(val)}
                      </span>
                      {yoy !== null && val > 0 && (
                        <span
                          className="text-[10px]"
                          style={{
                            color:
                              yoy >= 0 ? 'var(--positive)' : 'var(--negative)',
                            fontFamily: 'var(--font-mono)',
                          }}
                        >
                          {yoy >= 0 ? '▲' : '▼'} {Math.abs(yoy).toFixed(1)}%
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>

      <CitationBlock source="USDA NASS QuickStats" vintage="SURVEY · annual" />
    </div>
  );
}
