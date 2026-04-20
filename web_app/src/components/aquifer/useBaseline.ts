'use client';

import { useEffect, useState } from 'react';
import type { Feature, FeatureCollection, Geometry, Polygon, MultiPolygon, Position } from 'geojson';
import type { CountyCollection, CountyProps } from './types';

/**
 * Public GeoJSON built by aquifer-watch/scripts/build_web_geojson.py.
 * 606 HPA counties, ~0.74 MB, simplified at 0.005 deg Douglas-Peucker.
 * Re-published on every ingest refresh; safe to fetch from the client.
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
  annual_decline_m_pred: number | null;
  recharge_mm_yr: number | null;
  pumping_af_yr: number | null;
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
  data_quality: 'modeled_high' | 'modeled_low';
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
    // degenerate fallback: mean of first ring
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

/**
 * Adapt parquet-backed long-form fields to the design's short-form schema.
 * Falls back to HPA-median thickness (30 m) and a conservative decline
 * (-0.3 m/yr) when a county is modeled_low with nulls — keeps the map
 * renderable while the Tier-2 GBDT imputation is still pending.
 */
function adapt(raw: RawProps, geom: Geometry): CountyProps {
  const [cx, cy] = centroid(geom);
  const dcl = raw.annual_decline_m ?? raw.annual_decline_m_pred ?? -0.3;
  return {
    fips: raw.fips,
    state: raw.state,
    name: raw.county_name,
    thk: num(raw.saturated_thickness_m, 30),
    dcl: num(dcl, -0.3),
    rch: num(raw.recharge_mm_yr, 20),
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
    dq: raw.data_quality,
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
