'use client';

import type { ReactNode } from 'react';

/**
 * Uppercase section label used throughout the dashboards.
 *
 * Previously every section used `text-[11px] font-bold tracking-[0.1em]
 * uppercase` with `color: var(--text3)`. The low-contrast text3 made the
 * labels disappear against the cream background. This component centralizes
 * the class string and uses the new `--section-heading` token so contrast
 * can be adjusted in one place.
 */
export default function SectionHeading({
  children,
  className = '',
  as: Tag = 'p',
}: {
  children: ReactNode;
  className?: string;
  as?: 'p' | 'h2' | 'h3' | 'h4';
}) {
  return (
    <Tag
      className={`text-[11px] font-bold tracking-[0.1em] uppercase mb-3 ${className}`}
      style={{ color: 'var(--section-heading)', fontFamily: 'var(--font-mono)' }}
    >
      {children}
    </Tag>
  );
}
