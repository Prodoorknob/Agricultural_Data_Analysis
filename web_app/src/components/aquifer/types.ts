import type { Feature, FeatureCollection, Geometry } from 'geojson';

/**
 * Short-form per-county props consumed by the Ogallala Report UI.
 * Derived from the parquet-backed baseline_counties.geojson produced
 * by aquifer-watch/scripts/build_web_geojson.py.
 */
export interface CountyProps {
  fips: string;
  state: string;
  name: string;
  thk: number;
  dcl: number;
  rch: number;
  pmp: number;
  acres: number;
  corn: number;
  soy: number;
  srg: number;
  wht: number;
  ctn: number;
  alf: number;
  agv: number;
  kwh: number;
  co2i: number;
  dq: 'modeled_high' | 'modeled_low';
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
}
