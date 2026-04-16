import { Suspense } from 'react';
import Header from '@/components/shell/Header';
import FilterRail from '@/components/shell/FilterRail';
import SourceFooter from '@/components/shell/SourceFooter';

export default function TabsLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg)' }}>
      <Suspense>
        <Header />
        <FilterRail />
      </Suspense>
      <main className="flex-1 w-full max-w-[1400px] mx-auto px-5 py-6">
        <Suspense
          fallback={
            <div className="flex flex-col gap-4">
              <div className="skeleton h-[200px]" />
              <div className="skeleton h-[400px]" />
            </div>
          }
        >
          {children}
        </Suspense>
      </main>
      <SourceFooter />
    </div>
  );
}
