export const LATEST_NASS_YEAR = 2024;
export const CURRENT_YEAR = new Date().getFullYear();

export const CROP_COMMODITIES = [
  { id: 'corn', label: 'Corn', color: 'var(--chart-corn)' },
  { id: 'soybeans', label: 'Soybeans', color: 'var(--chart-soy)' },
  { id: 'wheat', label: 'Wheat', color: 'var(--chart-wheat)' },
  { id: 'cotton', label: 'Cotton', color: 'var(--chart-cotton)' },
  { id: 'hay', label: 'Hay', color: 'var(--chart-hay)' },
  { id: 'rice', label: 'Rice', color: 'var(--sky)' },
  { id: 'sorghum', label: 'Sorghum', color: 'var(--soil)' },
  { id: 'barley', label: 'Barley', color: 'var(--harvest-light)' },
  { id: 'oats', label: 'Oats', color: 'var(--text3)' },
  { id: 'peanuts', label: 'Peanuts', color: 'var(--soil-light)' },
  { id: 'tobacco', label: 'Tobacco', color: 'var(--harvest-dark)' },
] as const;

export type CropId = (typeof CROP_COMMODITIES)[number]['id'];

/** Commodity chart color lookup */
export const COMMODITY_COLORS: Record<string, string> = Object.fromEntries(
  CROP_COMMODITIES.map((c) => [c.id, c.color])
);

/** Tabs in display order */
export const TABS = [
  { id: 'overview' as const, label: 'Overview' },
  { id: 'market' as const, label: 'Market' },
  { id: 'forecasts' as const, label: 'Forecasts' },
  { id: 'crops' as const, label: 'Crops' },
  { id: 'land-economy' as const, label: 'Land & Economy' },
  { id: 'livestock' as const, label: 'Livestock' },
  { id: 'about' as const, label: 'About' },
] as const;
