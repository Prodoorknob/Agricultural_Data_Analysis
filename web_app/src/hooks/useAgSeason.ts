'use client';

import { useMemo } from 'react';
import type { AgSeason, SeasonOverrides } from '@/types/filters';
import { getAgSeason } from '@/lib/season';

const SEASON_OVERRIDES: Record<number, SeasonOverrides> = {
  0:  { overviewHeroMetric: '5yr revenue growth', marketDefaultCommodity: 'corn', forecastsFeaturedBand: 'Acreage — coming soon', overviewRotatingCard: 'Last year\'s revenue recap' },
  1:  { overviewHeroMetric: 'Total sales',        marketDefaultCommodity: 'corn', forecastsFeaturedBand: 'Acreage — live',        overviewRotatingCard: 'What USDA will say March 31' },
  2:  { overviewHeroMetric: 'Total sales',        marketDefaultCommodity: 'corn', forecastsFeaturedBand: 'Acreage — live',        overviewRotatingCard: 'USDA Prospective Plantings' },
  3:  { overviewHeroMetric: 'Total sales',        marketDefaultCommodity: 'corn', forecastsFeaturedBand: 'Acreage — final',       overviewRotatingCard: 'Planting kicks off' },
  4:  { overviewHeroMetric: 'Area planted',       marketDefaultCommodity: 'corn', forecastsFeaturedBand: 'Yield — low conf.',     overviewRotatingCard: 'Emergence watch' },
  5:  { overviewHeroMetric: 'Area planted',       marketDefaultCommodity: 'corn', forecastsFeaturedBand: 'Yield — medium conf.',  overviewRotatingCard: 'Condition check' },
  6:  { overviewHeroMetric: 'Crop condition %GE', marketDefaultCommodity: 'corn', forecastsFeaturedBand: 'Yield — medium conf.',  overviewRotatingCard: 'Condition check' },
  7:  { overviewHeroMetric: 'Crop condition %GE', marketDefaultCommodity: 'soy',  forecastsFeaturedBand: 'Yield — high conf.',    overviewRotatingCard: 'Pro Farmer tour' },
  8:  { overviewHeroMetric: 'Harvest progress %', marketDefaultCommodity: 'soy',  forecastsFeaturedBand: 'Yield — high conf.',    overviewRotatingCard: 'Harvest progress' },
  9:  { overviewHeroMetric: 'Harvest progress %', marketDefaultCommodity: 'corn', forecastsFeaturedBand: 'Yield — high conf.',    overviewRotatingCard: 'Harvest progress' },
  10: { overviewHeroMetric: 'Total sales',        marketDefaultCommodity: 'corn', forecastsFeaturedBand: 'Dormant',               overviewRotatingCard: 'Revenue recap' },
  11: { overviewHeroMetric: 'Total sales',        marketDefaultCommodity: 'corn', forecastsFeaturedBand: 'Dormant',               overviewRotatingCard: 'Year in review' },
};

export interface UseAgSeasonReturn {
  season: AgSeason;
  month: number;
  overrides: SeasonOverrides;
}

/**
 * Returns current ag season + monthly overrides.
 * Memoized on the current date string (recalculates at most once per day).
 */
export function useAgSeason(): UseAgSeasonReturn {
  return useMemo(() => {
    const now = new Date();
    const month = now.getMonth();
    return {
      season: getAgSeason(now),
      month,
      overrides: SEASON_OVERRIDES[month],
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [new Date().toDateString()]);
}
