/**
 * Number formatting utilities for FieldPulse.
 * Extracted from the old design.ts — these are pure functions, no design tokens.
 */

export function formatCompact(val: number): string {
  if (Math.abs(val) >= 1e9) return `${(val / 1e9).toFixed(1)}B`;
  if (Math.abs(val) >= 1e6) return `${(val / 1e6).toFixed(1)}M`;
  if (Math.abs(val) >= 1e3) return `${(val / 1e3).toFixed(0)}K`;
  return val.toLocaleString();
}

export function formatCurrency(val: number): string {
  if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
  if (Math.abs(val) >= 1e6) return `$${(val / 1e6).toFixed(1)}M`;
  if (Math.abs(val) >= 1e3) return `$${(val / 1e3).toFixed(0)}K`;
  return `$${val.toLocaleString()}`;
}

export function formatDelta(
  current: number,
  previous: number
): { text: string; positive: boolean; pct: number } {
  if (!previous || previous === 0) return { text: 'N/A', positive: true, pct: 0 };
  const pct = ((current - previous) / previous) * 100;
  return {
    text: `${pct >= 0 ? '\u25B2' : '\u25BC'} ${Math.abs(pct).toFixed(1)}%`,
    positive: pct >= 0,
    pct,
  };
}

export function formatNumber(val: number, decimals = 0): string {
  return val.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function formatPercent(val: number, decimals = 1): string {
  return `${val >= 0 ? '+' : ''}${val.toFixed(decimals)}%`;
}
