import { Suspense } from 'react';
import Header from '@/components/shell/Header';
import SourceFooter from '@/components/shell/SourceFooter';

/**
 * /insights uses the global Header (so the tab nav is visible) but skips the
 * FilterRail entirely — the newsletter has no state/year/commodity filters.
 */
export default function InsightsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg)' }}>
      <Suspense>
        <Header />
      </Suspense>
      {children}
      <SourceFooter />
    </div>
  );
}
