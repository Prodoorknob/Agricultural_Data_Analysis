'use client';

import DeltaChip from './DeltaChip';
import Sparkline from './Sparkline';

interface KpiCardProps {
  value: string;               // pre-formatted hero number (e.g. "181.3", "$4.8B")
  label: string;               // e.g. "Total Farm Sales"
  caption?: string;            // one-sentence plain-English
  delta?: number;              // percent change for DeltaChip
  sparklineData?: number[];    // optional 5-25 year sparkline
  sparklineColor?: string;
  sparklineYears?: number[];   // optional year labels — enables tooltip + endpoints
  sparklineUnit?: string;      // optional unit shown in the tooltip
  size?: 'lg' | 'md';         // lg = Barlow 48px, md = Barlow 36px
  unit?: string;               // small subscript after value
  className?: string;
}

export default function KpiCard({
  value,
  label,
  caption,
  delta,
  sparklineData,
  sparklineColor,
  sparklineYears,
  sparklineUnit,
  size = 'lg',
  unit,
  className = '',
}: KpiCardProps) {
  const valueFontSize = size === 'lg' ? '48px' : '36px';
  const valueFontWeight = size === 'lg' ? 900 : 800;

  return (
    <div
      className={`p-5 rounded-[var(--radius-lg)] border ${className}`}
      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          {/* Label */}
          <p
            className="text-[11px] font-bold tracking-[0.1em] uppercase mb-1"
            style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
          >
            {label}
          </p>

          {/* Hero value */}
          <div className="flex items-baseline gap-1.5">
            <span
              style={{
                fontFamily: 'var(--font-stat)',
                fontSize: valueFontSize,
                fontWeight: valueFontWeight,
                lineHeight: 0.95,
                letterSpacing: '-0.02em',
                color: 'var(--text)',
              }}
            >
              {value}
            </span>
            {unit && (
              <span
                className="text-[12px] font-medium"
                style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
              >
                {unit}
              </span>
            )}
          </div>

          {/* Delta chip */}
          {delta !== undefined && (
            <div className="mt-2">
              <DeltaChip value={delta} />
            </div>
          )}
        </div>

        {/* Sparkline */}
        {sparklineData && sparklineData.length > 2 && (
          <Sparkline
            data={sparklineData}
            years={sparklineYears}
            color={sparklineColor}
            unit={sparklineUnit}
          />
        )}
      </div>

      {/* Caption */}
      {caption && (
        <p
          className="mt-3 text-[13px] leading-[1.5]"
          style={{ color: 'var(--text2)', fontFamily: 'var(--font-body)' }}
        >
          {caption}
        </p>
      )}
    </div>
  );
}
