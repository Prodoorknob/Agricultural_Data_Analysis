import type { Aggregate, CountyProps, Scenario } from './types';

export const BBOX = { minX: -105.5, maxX: -96.5, minY: 31.3, maxY: 44.0 };

export const STATES: Record<string, { name: string; color: string }> = {
  NE: { name: 'Nebraska',   color: '#52B788' },
  KS: { name: 'Kansas',     color: '#D4A017' },
  CO: { name: 'Colorado',   color: '#C17644' },
  TX: { name: 'Texas',      color: '#B8553A' },
  OK: { name: 'Oklahoma',   color: '#A8B878' },
  NM: { name: 'New Mexico', color: '#8B4513' },
  SD: { name: 'S. Dakota',  color: '#7BB3E0' },
  WY: { name: 'Wyoming',    color: '#6B8E5A' },
};

export interface Crop {
  key: 'corn' | 'ctn' | 'soy' | 'wht' | 'srg' | 'alf';
  label: string;
  color: string;
  wa: number;
}

export const CROPS: Crop[] = [
  { key: 'corn', label: 'Corn',    color: '#D4A017', wa: 1.4 },
  { key: 'ctn',  label: 'Cotton',  color: '#C17644', wa: 1.1 },
  { key: 'soy',  label: 'Soy',     color: '#52B788', wa: 0.9 },
  { key: 'wht',  label: 'Wheat',   color: '#A8B878', wa: 0.7 },
  { key: 'srg',  label: 'Sorghum', color: '#8B4513', wa: 0.6 },
  { key: 'alf',  label: 'Alfalfa', color: '#7BB3E0', wa: 1.8 },
];

export const SCENARIOS: Scenario[] = [
  { id: 'bau',     label: 'Status Quo',                    sub: 'Business-as-usual pumping continues',   pumpDelta: 0,     cropShift: 0,    rechargeMult: 1 },
  { id: 'lema',    label: 'Kansas LEMA · Region-Wide',     sub: 'Sheridan-6 style 25% pumping cap',      pumpDelta: -0.25, cropShift: 0.15, rechargeMult: 1 },
  { id: 'drip',    label: 'Drip Irrigation Transition',    sub: '35% water saved over 10 years',         pumpDelta: -0.35, cropShift: 0,    rechargeMult: 1 },
  { id: 'corn25',  label: '25% Corn → Sorghum + Wheat',    sub: 'Corn acres shift to lower-water crops', pumpDelta: -0.18, cropShift: 0.25, rechargeMult: 1 },
  { id: 'stop9m',  label: 'No Pumping Below 9m',           sub: 'Counties under threshold stop extracting', pumpDelta: -0.08, cropShift: 0, rechargeMult: 1, threshold: 9 },
  { id: 'custom',  label: 'Custom Scenario',               sub: 'Set your own levers',                   pumpDelta: 0,     cropShift: 0,    rechargeMult: 1, custom: true },
];

/** Equirectangular projection corrected for High Plains latitude. */
export function project(lon: number, lat: number, W: number, H: number, bbox = BBOX): [number, number] {
  const midLat = (bbox.minY + bbox.maxY) / 2;
  const kx = Math.cos((midLat * Math.PI) / 180);
  const spanX = (bbox.maxX - bbox.minX) * kx;
  const spanY = bbox.maxY - bbox.minY;
  const scale = Math.min(W / spanX, H / spanY);
  const offX = (W - spanX * scale) / 2;
  const offY = (H - spanY * scale) / 2;
  return [offX + (lon - bbox.minX) * kx * scale, offY + (bbox.maxY - lat) * scale];
}

/** 10-step thickness colour ramp, returns a CSS var reference. */
export function depColor(thickness: number): string {
  const stops: Array<[number, string]> = [
    [0,   'var(--dep-1)'],
    [5,   'var(--dep-2)'],
    [10,  'var(--dep-3)'],
    [18,  'var(--dep-4)'],
    [28,  'var(--dep-5)'],
    [40,  'var(--dep-6)'],
    [55,  'var(--dep-7)'],
    [75,  'var(--dep-8)'],
    [100, 'var(--dep-9)'],
    [999, 'var(--dep-10)'],
  ];
  for (const [t, c] of stops) if (thickness <= t) return c;
  return 'var(--dep-10)';
}

/**
 * Deterministic thickness model: linear back-projection from the 2024
 * baseline, optionally modified forward by a scenario's pumping delta
 * and threshold rule.
 */
export function thicknessAt(c: CountyProps, year: number, scenario: Scenario): number {
  const baseline2024 = c.thk;
  const declinePerYr = c.dcl;
  const pumpMult = 1 + scenario.pumpDelta;
  let dec = declinePerYr * pumpMult;
  if (scenario.threshold != null && c.thk < scenario.threshold) dec = 0;

  if (year <= 2024) {
    return baseline2024 - declinePerYr * (year - 2024);
  }
  return baseline2024 + dec * (year - 2024);
}

export function aggregate(counties: CountyProps[], scenario: Scenario, year = 2050): Aggregate {
  let totalThk = 0;
  let totalPmp = 0;
  let totalAg = 0;
  let totalAcres = 0;
  let countDepleted = 0;
  let totalCO2 = 0;
  const pumpMult = 1 + scenario.pumpDelta;

  for (const c of counties) {
    const thkNow = thicknessAt(c, year, scenario);
    if (thkNow < 5) countDepleted++;
    totalThk += Math.max(0, thkNow);

    const pmp = c.pmp * pumpMult;
    totalPmp += pmp;

    const agMult =
      scenario.id === 'lema' ? 0.88 :
      scenario.id === 'corn25' ? 0.94 :
      scenario.id === 'drip' ? 0.99 : 1;
    totalAg += c.agv * agMult;

    totalAcres += c.acres;
    totalCO2 += (pmp * (c.kwh || 220) * (c.co2i || 0.4)) / 1e9;
  }
  return { totalThk, totalPmp, totalAg, totalAcres, countDepleted, totalCO2 };
}

export interface CropRow extends Crop {
  acres: number;
  waterAF: number;
}

export function cropMix(c: CountyProps): CropRow[] {
  return CROPS.map((cr) => ({
    ...cr,
    acres: (c[cr.key] as number) || 0,
    waterAF: ((c[cr.key] as number) || 0) * cr.wa,
  }))
    .filter((r) => r.acres > 0)
    .sort((a, b) => b.waterAF - a.waterAF);
}

/** Formatters. */
export const fmt = {
  num(n: number | null | undefined): string {
    if (n == null || !Number.isFinite(n)) return '—';
    const a = Math.abs(n);
    if (a >= 1e9) return (n / 1e9).toFixed(1) + 'B';
    if (a >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (a >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return Math.round(n).toLocaleString();
  },
  int(n: number | null | undefined): string {
    return n == null ? '—' : Math.round(n).toLocaleString();
  },
  af(n: number | null | undefined): string {
    return fmt.num(n) + ' AF';
  },
  m(n: number | null | undefined): string {
    if (n == null) return '—';
    return n.toFixed(1) + ' m';
  },
  pct(n: number): string {
    return (n * 100).toFixed(0) + '%';
  },
  yr(n: number): string {
    return n >= 999 ? '∞' : Math.round(n) + ' yr';
  },
  usd(n: number | null | undefined): string {
    return '$' + fmt.num(n);
  },
};
