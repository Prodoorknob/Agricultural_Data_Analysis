'use client';

import { useSearchParams, useRouter, usePathname } from 'next/navigation';
import { useCallback, useMemo } from 'react';
import type { Tab, Filters } from '@/types/filters';
import { VIEW_FILTER_DEFAULTS } from '@/lib/filterDefaults';

export interface UseFiltersReturn {
  filters: Filters;
  setState: (code: string | null) => void;
  setYear: (year: number | null) => void;
  setCommodity: (c: string | null) => void;
  setSection: (s: string | null) => void;
  setRange: (r: string) => void;
  switchTab: (tab: Tab) => void;
  currentTab: Tab;
}

function resolveTab(pathname: string): Tab {
  const segment = pathname.split('/').filter(Boolean)[0] || 'overview';
  const valid: Tab[] = ['overview', 'market', 'forecasts', 'crops', 'land-economy', 'livestock'];
  return valid.includes(segment as Tab) ? (segment as Tab) : 'overview';
}

export function useFilters(): UseFiltersReturn {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const currentTab = resolveTab(pathname);

  const filters: Filters = useMemo(
    () => ({
      state: searchParams.get('state') || null,
      year: searchParams.get('year') ? Number(searchParams.get('year')) : null,
      commodity: searchParams.get('commodity') || null,
      section: searchParams.get('section') || null,
      range: searchParams.get('range') || null,
    }),
    [searchParams]
  );

  const pushParams = useCallback(
    (updates: Partial<Record<string, string | null>>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, val] of Object.entries(updates)) {
        if (val === null || val === undefined) {
          params.delete(key);
        } else {
          params.set(key, val);
        }
      }
      const qs = params.toString();
      router.push(`${pathname}${qs ? '?' + qs : ''}`, { scroll: false });
    },
    [searchParams, pathname, router]
  );

  const setState = useCallback(
    (code: string | null) => {
      pushParams({ state: code });
      // Persist to localStorage for "remember my state" feature
      if (typeof window !== 'undefined') {
        if (code) {
          localStorage.setItem('fieldpulse_state', code);
        } else {
          localStorage.removeItem('fieldpulse_state');
        }
      }
    },
    [pushParams]
  );

  const setYear = useCallback(
    (year: number | null) => pushParams({ year: year?.toString() ?? null }),
    [pushParams]
  );

  const setCommodity = useCallback(
    (c: string | null) => pushParams({ commodity: c }),
    [pushParams]
  );

  const setSection = useCallback(
    (s: string | null) => pushParams({ section: s }),
    [pushParams]
  );

  const setRange = useCallback(
    (r: string) => pushParams({ range: r }),
    [pushParams]
  );

  const switchTab = useCallback(
    (tab: Tab) => {
      const defaults = VIEW_FILTER_DEFAULTS[tab];
      const params = new URLSearchParams();
      // Global state persists across tabs
      const currentState = searchParams.get('state');
      if (currentState) params.set('state', currentState);
      // Per-tab defaults
      if (defaults.year !== null) params.set('year', defaults.year.toString());
      if (defaults.commodity) params.set('commodity', defaults.commodity);
      if (defaults.section) params.set('section', defaults.section);
      const qs = params.toString();
      router.push(`/${tab}${qs ? '?' + qs : ''}`);
    },
    [searchParams, router]
  );

  return { filters, setState, setYear, setCommodity, setSection, setRange, switchTab, currentTab };
}
