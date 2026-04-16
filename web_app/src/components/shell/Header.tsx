'use client';

import { useFilters } from '@/hooks/useFilters';
import { TABS } from '@/lib/constants';
import ThemeToggle from './ThemeToggle';
import { useEffect, useState } from 'react';

export default function Header() {
  const { currentTab, switchTab } = useFilters();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header
      className="sticky top-0 z-50 flex items-center h-[56px] px-5 gap-6"
      style={{
        background: 'var(--surface)',
        boxShadow: scrolled ? 'var(--shadow-sm)' : 'none',
        transition: `box-shadow var(--duration-fast) var(--ease-out)`,
      }}
    >
      {/* Logo */}
      <div className="flex items-center gap-2 shrink-0 mr-2">
        <div
          className="w-7 h-7 rounded-[var(--radius-sm)] flex items-center justify-center text-white font-bold text-[13px]"
          style={{ background: 'var(--field)' }}
        >
          F
        </div>
        <span
          className="text-[15px] font-bold tracking-[-0.01em] hidden sm:block"
          style={{ color: 'var(--text)', fontFamily: 'var(--font-body)' }}
        >
          FieldPulse
        </span>
      </div>

      {/* Tab nav */}
      <nav className="flex items-center gap-1 overflow-x-auto flex-1 min-w-0">
        {TABS.map((tab) => {
          const active = currentTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => switchTab(tab.id)}
              className="relative px-3 py-1.5 text-[13px] font-medium whitespace-nowrap rounded-[var(--radius-sm)] transition-colors shrink-0"
              style={{
                color: active ? 'var(--field)' : 'var(--text2)',
                fontWeight: active ? 600 : 500,
                background: active ? 'var(--field-subtle)' : 'transparent',
                fontFamily: 'var(--font-body)',
                transitionDuration: 'var(--duration-fast)',
              }}
            >
              {tab.label}
              {active && (
                <span
                  className="absolute bottom-0 left-3 right-3 h-[2px] rounded-full"
                  style={{ background: 'var(--field)' }}
                />
              )}
            </button>
          );
        })}
      </nav>

      {/* Theme toggle */}
      <ThemeToggle />
    </header>
  );
}
