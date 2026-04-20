export type Tab = 'overview' | 'market' | 'forecasts' | 'crops' | 'land-economy' | 'livestock' | 'aquifer' | 'about';

export interface Filters {
  state: string | null;       // 2-letter code or null (national)
  year: number | null;        // null on Market (uses range instead)
  commodity: string | null;   // 'corn' | 'soybean' | 'wheat' | ... | null
  section: string | null;     // sub-section within a tab
  range: string | null;       // '1M' | '6M' | '1Y' | '5Y' | 'MAX' (Market only)
}

export interface FilterDefaults {
  year: number | null;
  commodity: string | null;
  section: string | null;
}

export type AgSeason =
  | 'pre-plant'
  | 'planting'
  | 'early-growth'
  | 'mid-season'
  | 'harvest'
  | 'post-harvest';

export interface SeasonOverrides {
  overviewHeroMetric: string;
  marketDefaultCommodity: string;
  forecastsFeaturedBand: string;
  overviewRotatingCard: string;
}
