'use client';

interface DeltaChipProps {
  value: number;          // percent change
  label?: string;         // optional prefix like "1w"
  size?: 'sm' | 'md';
}

export default function DeltaChip({ value, label, size = 'sm' }: DeltaChipProps) {
  const positive = value >= 0;
  const color = positive ? 'var(--positive)' : 'var(--negative)';
  const bg = positive ? 'var(--field-subtle)' : 'rgba(180, 35, 24, 0.07)';
  const arrow = positive ? '\u25B2' : '\u25BC';
  const fontSize = size === 'sm' ? '11px' : '12px';

  return (
    <span
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-[var(--radius-sm)]"
      style={{ color, background: bg, fontSize, fontFamily: 'var(--font-mono)', fontWeight: 600 }}
    >
      {label && <span style={{ color: 'var(--text3)', fontWeight: 500 }}>{label}</span>}
      {arrow} {Math.abs(value).toFixed(1)}%
    </span>
  );
}
