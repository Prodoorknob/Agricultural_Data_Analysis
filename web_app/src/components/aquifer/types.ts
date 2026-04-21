import type { Feature, FeatureCollection, Geometry } from 'geojson';

/**
 * Short-form per-county props consumed by the Ogallala Report UI.
 * Derived from the parquet-backed baseline_counties.geojson produced
 * by aquifer-watch/scripts/build_web_geojson.py.
 *
 * 2026-04-21 update: added USGS McGuire raster provenance + NB02 model
 * predictions + conformal bands + HPA footprint overlap. Counties off
 * the aquifer (`onHpa === false`, `dq === 'no_data'`) are rendered
 * dimmed rather than with a fake 30m fallback.
 */
export interface CountyProps {
  fips: string;
  state: string;
  name: string;
  // Baseline scalar columns (nullable where the source doesn't reach).
  thk: number | null;   // saturated_thickness_m
  dcl: number | null;   // annual_decline_m (heuristic or measured)
  rch: number | null;   // recharge_mm_yr
  pmp: number;          // pumping_af_yr
  acres: number;
  corn: number; soy: number; srg: number; wht: number; ctn: number; alf: number;
  agv: number;
  kwh: number;
  co2i: number;
  // HPA aquifer footprint overlap (0 = off-aquifer, 1 = fully inside).
  hpa: number;
  onHpa: boolean;       // derived: hpa > 0
  // Thickness provenance (matches scripts/enrich_baseline.py output).
  tsrc: 'wells' | 'raster' | 'fallback' | 'none';
  // NB02 CatBoost one-step-ahead prediction + 80% conformal bands on decline.
  dclP: number | null;  // annual_decline_m_pred
  dclLo: number | null; // decline_lo_m
  dclHi: number | null; // decline_hi_m
  thkP: number | null;  // thickness_pred_next_m
  dsrc: 'model' | 'heuristic' | null;  // decline_source
  yrsU: number | null;  // years_until_uneconomic (server-computed, 9m threshold)
  yrsULo: number | null;
  yrsUHi: number | null;
  // Data quality tier (spec §4).
  dq: 'modeled_high' | 'modeled_low' | 'no_data';
  // Climate (NOAA nClimDiv: 1991–2020 normal + 2019–2023 recent).
  pnorm: number | null;   // precip_normal_mm_yr
  prec: number | null;    // precip_recent_mm_yr
  panom: number | null;   // precip_anomaly_pct
  // Pumping economics (EIA industrial electricity × per-county kWh/AF).
  ekwh: number | null;    // electricity_cents_per_kwh
  pcost: number | null;   // pumping_cost_usd_per_af
  // Irrigation method mix (IWMS 2018 Table 28 per-state shares).
  mPivot: number;         // irr_center_pivot
  mFlood: number;         // irr_flood
  mDrip: number;          // irr_drip
  mDry: number;           // irr_dryland
  // Projected centroid in lon/lat for label / spike placement.
  cx: number;
  cy: number;
}

export type CountyFeature = Feature<Geometry, CountyProps>;
export type CountyCollection = FeatureCollection<Geometry, CountyProps>;

export interface Scenario {
  id: string;
  label: string;
  sub: string;
  pumpDelta: number;
  cropShift: number;
  rechargeMult: number;
  threshold?: number;
  custom?: boolean;
}

export type MapMode = 'choropleth' | 'columns' | 'dots';

export interface Aggregate {
  totalThk: number;
  totalPmp: number;
  totalAg: number;
  totalAcres: number;
  countDepleted: number;
  totalCO2: number;
  countOnHpa: number;  // how many counties actually contributed (not off-HPA)
}
