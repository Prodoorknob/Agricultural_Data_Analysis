'use client';

import { useCallback } from 'react';

interface ChartToolbarProps {
  chartRef?: React.RefObject<HTMLDivElement | null>;
}

export default function ChartToolbar({ chartRef }: ChartToolbarProps) {
  const copyPermalink = useCallback(() => {
    navigator.clipboard.writeText(window.location.href);
  }, []);

  return (
    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
      {/* Permalink */}
      <button
        onClick={copyPermalink}
        className="p-1.5 rounded-[var(--radius-sm)] hover:bg-[var(--surface2)] transition-colors"
        title="Copy permalink"
      >
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="var(--text3)" strokeWidth="1.5">
          <path d="M6.5 9.5L9.5 6.5M7 5L8.5 3.5a2.12 2.12 0 1 1 3 3L10 8M9 11l-1.5 1.5a2.12 2.12 0 1 1-3-3L6 8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
    </div>
  );
}
