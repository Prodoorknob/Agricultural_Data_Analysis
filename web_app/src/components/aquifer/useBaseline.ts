'use client';

import { useEffect, useState } from 'react';
import type { Feature, FeatureCollection, Geometry, Polygon, MultiPolygon, Position } from 'geojson';
import type { CountyCollection, CountyProps } from './types';

/**
 * Public GeoJSON built by aquifer-watch/scripts/build_web_geojson.py.
 * 606 counties, ~1.0 MB, simplified at 0.005° Douglas-Peucker.
 *
 * As of 2026-04-21 the payload carries USGS McGuire raster thickness fills,
 * HPA footprint overlap per county, NB02 model predictions + 80% conformal
 * bands on decline, and a server-computed `years_until_uneconomic`. Off-HPA
 * counties carry `data_quality === "no_data"` and have null thickness — the
 * client must NOT render them as regular aquifer counties (dim/gray instead).
 */
export const BASELINE_URL =
  'https://usda-analysis-datasets.s3.amazonaws.com/aquiferwatch/web/baseline_counties.geojson';

interface RawProps {
  fips: string;
  state: string;
  state_name: string;
  county_name: string;
  saturated_thickness_m: number | null;
  annual_decline_m: number | null;
  recharge_mm_yr: number | null;
  hpa_overlap_pct: number | null;
  overlap_area_km2: number | null;
  county_area_km2: number | null;
  thickness_source: 'wells' | 'raster' | 'fallback' | 'none' | null;
  annual_decline_m_pred: number | null;
  decline_lo_m: number | null;
  decline_hi_m: number | null;
  thickness_pred_next_m: number | null;
  decline_source: 'model' | 'heuristic' | null;
  years_until_uneconomic: number | null;
  years_until_uneconomic_lo: number | null;
  years_until_uneconomic_hi: number | null;
  model_id: string | null;
  coverage_target: number | null;
  precip_normal_mm_yr: number | null;
  precip_recent_mm_yr: number | null;
  precip_anomaly_pct: number | null;
  electricity_cents_per_kwh: number | null;
  pumping_cost_usd_per_af: number | null;
  irr_center_pivot: number | null;
  irr_flood: number | null;
  irr_drip: number | null;
  irr_dryland: number | null;
  pumping_af_yr: number | null;
  pumping_af_yr_usgs2015: number | null;
  irrigated_acres_total: number | null;
  acres_corn: number | null;
  acres_soybeans: number | null;
  acres_sorghum: number | null;
  acres_wheat: number | null;
  acres_cotton: number | null;
  acres_alfalfa: number | null;
  ag_value_usd: number | null;
  kwh_per_af_pumped: number | null;
  grid_intensity_kg_per_kwh: number | null;
  n_wells: number | null;
  data_quality: 'modeled_high' | 'modeled_low' | 'no_data';
}

/** Polygon / MultiPolygon area-weighted centroid (lon/lat). */
function centroid(geom: Geometry): [number, number] {
  const rings: Position[][] = [];
  if (geom.type === 'Polygon') {
    rings.push(...(geom as Polygon).coordinates);
  } else if (geom.type === 'MultiPolygon') {
    for (const poly of (geom as MultiPolygon).coordinates) rings.push(...poly);
  } else {
    return [0, 0];
  }

  let cx = 0, cy = 0, area = 0;
  for (const ring of rings) {
    for (let i = 0, n = ring.length - 1; i < n; i++) {
      const [x0, y0] = ring[i];
      const [x1, y1] = ring[i + 1];
      const f = x0 * y1 - x1 * y0;
      cx += (x0 + x1) * f;
      cy += (y0 + y1) * f;
      area += f;
    }
  }
  if (area === 0) {
    const r = rings[0];
    const mx = r.reduce((s, p) => s + p[0], 0) / r.length;
    const my = r.reduce((s, p) => s + p[1], 0) / r.length;
    return [mx, my];
  }
  area *= 0.5;
  return [cx / (6 * area), cy / (6 * area)];
}

function num(v: number | null | undefined, fallback: number): number {
  return v != null && Number.isFinite(v) ? v : fallback;
}

function nullable(v: number | null | undefined): number | null {
  return v != null && Number.isFinite(v) ? v : null;
}

/**
 * Adapt parquet-backed long-form fields to the design's short-form schema.
 *
 * Key invariant: off-HPA counties (thickness_source === 'none' or
 * hpa_overlap_pct === 0) keep `thk/dcl/yrsU` as null. The map dims them;
 * aggregations skip them. No 30m halo.
 */
function adapt(raw: RawProps, geom: Geometry): CountyProps {
  const [cx, cy] = centroid(geom);
  const hpa = num(raw.hpa_overlap_pct, 0);
  const onHpa = hpa > 0;
  return {
    fips: raw.fips,
    state: raw.state,
    name: raw.county_name,
    thk: nullable(raw.saturated_thickness_m),
    dcl: nullable(raw.annual_decline_m),
    rch: nullable(raw.recharge_mm_yr),
    pmp: num(raw.pumping_af_yr, 0),
    acres: num(raw.irrigated_acres_total, 0),
    corn: num(raw.acres_corn, 0),
    soy: num(raw.acres_soybeans, 0),
    srg: num(raw.acres_sorghum, 0),
    wht: num(raw.acres_wheat, 0),
    ctn: num(raw.acres_cotton, 0),
    alf: num(raw.acres_alfalfa, 0),
    agv: num(raw.ag_value_usd, 0),
    kwh: num(raw.kwh_per_af_pumped, 220),
    co2i: num(raw.grid_intensity_kg_per_kwh, 0.4),
    hpa,
    onHpa,
    tsrc: raw.thickness_source ?? 'none',
    dclP: nullable(raw.annual_decline_m_pred),
    dclLo: nullable(raw.decline_lo_m),
    dclHi: nullable(raw.decline_hi_m),
    thkP: nullable(raw.thickness_pred_next_m),
    dsrc: raw.decline_source,
    yrsU: nullable(raw.years_until_uneconomic),
    yrsULo: nullable(raw.years_until_uneconomic_lo),
    yrsUHi: nullable(raw.years_until_uneconomic_hi),
    dq: raw.data_quality,
    pnorm: nullable(raw.precip_normal_mm_yr),
    prec: nullable(raw.precip_recent_mm_yr),
    panom: nullable(raw.precip_anomaly_pct),
    ekwh: nullable(raw.electricity_cents_per_kwh),
    pcost: nullable(raw.pumping_cost_usd_per_af),
    mPivot: num(raw.irr_center_pivot, 0.85),
    mFlood: num(raw.irr_flood, 0.05),
    mDrip: num(raw.irr_drip, 0.05),
    mDry: num(raw.irr_dryland, 0.05),
    cx,
    cy,
  };
}

export function useBaseline(): {
  geo: CountyCollection | null;
  counties: CountyProps[];
  error: string | null;
} {
  const [geo, setGeo] = useState<CountyCollection | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(BASELINE_URL)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((raw: FeatureCollection<Geometry, RawProps>) => {
        if (cancelled) return;
        const features: Feature<Geometry, CountyProps>[] = raw.features.map((f) => ({
          ...f,
          properties: adapt(f.properties, f.geometry),
        }));
        setGeo({ type: 'FeatureCollection', features });
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const counties = geo ? geo.features.map((f) => f.properties) : [];
  return { geo, counties, error };
}
