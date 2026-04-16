import type { AgSeason } from '@/types/filters';

/**
 * Pure function. Returns the current agricultural season phase.
 * Month is 0-indexed (JS Date convention).
 */
export function getAgSeason(date: Date = new Date()): AgSeason {
  const month = date.getMonth();
  if (month <= 1) return 'pre-plant';      // Jan–Feb
  if (month <= 3) return 'planting';        // Mar–Apr
  if (month <= 5) return 'early-growth';    // May–Jun
  if (month <= 7) return 'mid-season';      // Jul–Aug
  if (month <= 9) return 'harvest';         // Sep–Oct
  return 'post-harvest';                    // Nov–Dec
}

/** Human-readable season label */
export function seasonLabel(season: AgSeason): string {
  const labels: Record<AgSeason, string> = {
    'pre-plant': 'Pre-Plant',
    planting: 'Planting',
    'early-growth': 'Early Growth',
    'mid-season': 'Mid-Season',
    harvest: 'Harvest',
    'post-harvest': 'Post-Harvest',
  };
  return labels[season];
}
