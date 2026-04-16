'use client';

import { useTheme } from '@/hooks/useTheme';

export default function ThemeToggle() {
  const { isDark, toggle } = useTheme();
  return (
    <button
      onClick={toggle}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      className="flex items-center justify-center w-[44px] h-[44px] rounded-[var(--radius-md)] hover:bg-[var(--surface2)] transition-colors"
      style={{ transitionDuration: 'var(--duration-fast)' }}
    >
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="var(--text2)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        {isDark ? (
          /* Sun icon */
          <>
            <circle cx="10" cy="10" r="4" />
            <line x1="10" y1="1" x2="10" y2="3" />
            <line x1="10" y1="17" x2="10" y2="19" />
            <line x1="3.05" y1="3.05" x2="4.46" y2="4.46" />
            <line x1="15.54" y1="15.54" x2="16.95" y2="16.95" />
            <line x1="1" y1="10" x2="3" y2="10" />
            <line x1="17" y1="10" x2="19" y2="10" />
            <line x1="3.05" y1="16.95" x2="4.46" y2="15.54" />
            <line x1="15.54" y1="4.46" x2="16.95" y2="3.05" />
          </>
        ) : (
          /* Moon icon */
          <path d="M17.293 13.293A8 8 0 0 1 6.707 2.707a8.003 8.003 0 1 0 10.586 10.586Z" />
        )}
      </svg>
    </button>
  );
}
