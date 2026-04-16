'use client';

interface CitationBlockProps {
  source: string;        // e.g. "USDA NASS QuickStats"
  vintage?: string;      // e.g. "Marketing year 2024"
  updated?: string;      // e.g. "Apr 2026"
}

export default function CitationBlock({ source, vintage, updated }: CitationBlockProps) {
  const parts = [
    `Source: ${source}`,
    vintage,
    updated ? `Updated ${updated}` : null,
  ]
    .filter(Boolean)
    .join(' \u00B7 ');

  return (
    <p
      className="mt-2 text-[11px] tracking-[0.02em]"
      style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
    >
      {parts}
    </p>
  );
}
