import type { Tab, FilterDefaults } from '@/types/filters';
import { LATEST_NASS_YEAR, CURRENT_YEAR } from './constants';

export const VIEW_FILTER_DEFAULTS: Record<Tab, FilterDefaults> = {
  overview:       { year: LATEST_NASS_YEAR, commodity: null,   section: null },
  market:         { year: null,             commodity: 'corn', section: null },
  forecasts:      { year: CURRENT_YEAR,     commodity: 'corn', section: 'acreage' },
  crops:          { year: LATEST_NASS_YEAR, commodity: 'corn', section: null },
  'land-economy': { year: LATEST_NASS_YEAR, commodity: null,   section: 'revenue' },
  livestock:      { year: LATEST_NASS_YEAR, commodity: null,   section: 'cattle' },
  about:          { year: null,             commodity: null,   section: null },
};
