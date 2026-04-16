'use client';

import { LATEST_NASS_YEAR } from '@/lib/constants';

export default function SourceFooter() {
  return (
    <footer
      className="text-center py-6 mt-12"
      style={{ borderTop: '1px solid var(--border)' }}
    >
      <p
        className="text-[10px] tracking-[0.08em] uppercase"
        style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
      >
        NASS QuickStats: current through {LATEST_NASS_YEAR} &middot; FieldPulse v1.0 &middot; April 2026
      </p>
    </footer>
  );
}
