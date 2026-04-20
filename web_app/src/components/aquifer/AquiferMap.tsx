'use client';

import { useEffect, useMemo, useState } from 'react';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer } from '@deck.gl/layers';
import type { Feature, FeatureCollection, Geometry } from 'geojson';

/**
 * Public GeoJSON built by aquifer-watch/scripts/build_web_geojson.py.
 * Re-published on every ingest refresh; safe to fetch from the client.
 * 606 HPA counties, 0.74 MB, simplified at 0.005 deg Douglas-Peucker.
 */
const BASELINE_URL =
  'https://usda-analysis-datasets.s3.amazonaws.com/aquiferwatch/web/baseline_counties.geojson';

/**
 * Property schema mirrored from baseline.parquet. Only the fields we actually
 * read on the map are typed; the rest remain on the feature for drill-down.
 */
export interface CountyProps {
  fips: string;
  state: string;
  state_name: string;
  county_name: string;
  saturated_thickness_m: number | null;
  annual_decline_m: number | null;
  pumping_af_yr: number | null;
  irrigated_acres_total: number | null;
  data_quality: 'modeled_high' | 'modeled_low';
}

type CountyFeature = Feature<Geometry, CountyProps>;

/**
 * Warm-paper → forest ramp mirroring the Cobbles & Currents palette.
 * Lighter bands map to thinner remaining aquifer; darker → healthier.
 * Quantile bucketing, not linear — thickness distribution is long-tailed.
 */
const THICKNESS_STOPS_M = [5, 10, 20, 35, 60, 100];
const THICKNESS_COLORS: [number, number, number][] = [
  [200, 70, 60],   // rust-red — critically depleted
  [220, 130, 70],  // warm clay
  [210, 175, 90],  // amber
  [150, 170, 120], // sage
  [90, 140, 110],  // mid forest
  [42, 74, 62],    // deep forest
];

function thicknessColor(m: number | null): [number, number, number, number] {
  if (m === null || !Number.isFinite(m)) {
    return [180, 180, 180, 150];
  }
  let bucket = 0;
  for (let i = 0; i < THICKNESS_STOPS_M.length; i++) {
    if (m >= THICKNESS_STOPS_M[i]) bucket = i;
  }
  const [r, g, b] = THICKNESS_COLORS[bucket];
  return [r, g, b, 210];
}

const INITIAL_VIEW_STATE = {
  longitude: -100.5,
  latitude: 38.5,
  zoom: 4.6,
  pitch: 0,
  bearing: 0,
} as const;

export default function AquiferMap() {
  const [geojson, setGeojson] = useState<FeatureCollection<Geometry, CountyProps> | null>(null);
  const [hovered, setHovered] = useState<CountyFeature | null>(null);
  const [selected, setSelected] = useState<CountyFeature | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(BASELINE_URL)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j: FeatureCollection<Geometry, CountyProps>) => setGeojson(j))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const layers = useMemo(() => {
    if (!geojson) return [];
    return [
      new GeoJsonLayer<CountyProps>({
        id: 'hpa-counties',
        data: geojson,
        pickable: true,
        stroked: true,
        filled: true,
        lineWidthMinPixels: 0.5,
        getFillColor: (f) => thicknessColor(f.properties.saturated_thickness_m),
        getLineColor: (f) =>
          selected?.properties.fips === f.properties.fips
            ? [15, 14, 12, 255]
            : f.properties.data_quality === 'modeled_low'
              ? [120, 100, 80, 160]
              : [60, 50, 40, 120],
        getLineWidth: (f): number =>
          selected?.properties.fips === f.properties.fips ? 2 : 0.5,
        onHover: (info) => setHovered((info.object as CountyFeature) ?? null),
        onClick: (info) => setSelected((info.object as CountyFeature) ?? null),
        updateTriggers: {
          getLineColor: [selected?.properties.fips],
          getLineWidth: [selected?.properties.fips],
        },
      }),
    ];
  }, [geojson, selected]);

  if (error) {
    return (
      <div
        className="p-6 rounded-lg text-sm"
        style={{ background: 'var(--surface)', color: 'var(--text2)' }}
      >
        Failed to load aquifer data: {error}
      </div>
    );
  }

  return (
    <div
      className="relative w-full"
      style={{ height: '640px', background: 'var(--surface)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}
    >
      <div className="absolute inset-0">
        <DeckGL
          initialViewState={INITIAL_VIEW_STATE}
          controller
          layers={layers}
        />
      </div>

      {!geojson && (
        <div
          className="absolute inset-0 flex items-center justify-center text-xs"
          style={{ color: 'var(--text2)' }}
        >
          loading 606 HPA counties…
        </div>
      )}

      <ThicknessLegend />

      {hovered && <HoverCard feature={hovered} />}
      {selected && <CountyPanel feature={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Legend — thickness color ramp + data-quality badges
// ---------------------------------------------------------------------------
function ThicknessLegend() {
  return (
    <div
      className="absolute bottom-4 left-4 px-4 py-3 rounded-md text-[11px] font-medium"
      style={{
        background: 'var(--surface)',
        color: 'var(--text)',
        boxShadow: 'var(--shadow-md)',
        fontFamily: 'var(--font-body)',
      }}
    >
      <div
        className="mb-2 text-[10px] uppercase tracking-wider"
        style={{ color: 'var(--text2)' }}
      >
        Saturated thickness (m)
      </div>
      <div className="flex items-center gap-1">
        {THICKNESS_COLORS.map((rgb, i) => (
          <div key={i} className="flex flex-col items-center gap-1">
            <div
              className="w-9 h-3 rounded-sm"
              style={{ background: `rgb(${rgb.join(',')})` }}
            />
            <span style={{ color: 'var(--text2)', fontSize: 10 }}>
              {i === 0 ? `<${THICKNESS_STOPS_M[1]}` : `${THICKNESS_STOPS_M[i]}`}
            </span>
          </div>
        ))}
      </div>
      <div
        className="mt-2 pt-2 border-t text-[10px]"
        style={{ borderColor: 'var(--line)', color: 'var(--text2)' }}
      >
        Tan outline = <span style={{ color: 'var(--text)' }}>modeled_low</span> (estimated).
        Darker outline = <span style={{ color: 'var(--text)' }}>modeled_high</span> (measured).
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Floating hover card — shows a one-line summary, follows the cursor
// ---------------------------------------------------------------------------
function HoverCard({ feature }: { feature: CountyFeature }) {
  const p = feature.properties;
  return (
    <div
      className="absolute top-4 left-4 px-3 py-2 rounded-md text-[12px] pointer-events-none"
      style={{
        background: 'var(--surface)',
        color: 'var(--text)',
        boxShadow: 'var(--shadow-md)',
        fontFamily: 'var(--font-body)',
      }}
    >
      <div className="font-semibold">
        {p.county_name}, {p.state}
      </div>
      <div style={{ color: 'var(--text2)', fontSize: 11 }}>
        {fmt(p.saturated_thickness_m, 1)} m remaining
        {p.annual_decline_m != null && (
          <span> · {fmt(p.annual_decline_m, 2)} m/yr</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Right-side drill-down panel — county stats + data quality
// ---------------------------------------------------------------------------
function CountyPanel({
  feature,
  onClose,
}: {
  feature: CountyFeature;
  onClose: () => void;
}) {
  const p = feature.properties;
  const yearsLeft =
    p.saturated_thickness_m != null &&
    p.annual_decline_m != null &&
    p.annual_decline_m > 0
      ? p.saturated_thickness_m / p.annual_decline_m
      : null;

  return (
    <div
      className="absolute top-4 right-4 bottom-4 w-[320px] px-5 py-4 rounded-md flex flex-col gap-3"
      style={{
        background: 'var(--surface)',
        color: 'var(--text)',
        boxShadow: 'var(--shadow-md)',
        fontFamily: 'var(--font-body)',
      }}
    >
      <div className="flex items-start justify-between">
        <div>
          <div
            className="text-[10px] uppercase tracking-wider"
            style={{ color: 'var(--text2)' }}
          >
            {p.state_name} · FIPS {p.fips}
          </div>
          <div className="text-[18px] font-semibold mt-0.5">{p.county_name}</div>
        </div>
        <button
          onClick={onClose}
          className="text-[14px] px-2"
          style={{ color: 'var(--text2)' }}
          aria-label="close"
        >
          ×
        </button>
      </div>

      <Stat
        label="Saturated thickness"
        value={fmt(p.saturated_thickness_m, 1)}
        unit="m"
      />
      <Stat
        label="Annual decline"
        value={fmt(p.annual_decline_m, 2)}
        unit="m/yr"
      />
      <Stat
        label="Years to depletion (linear)"
        value={yearsLeft != null ? Math.round(yearsLeft).toString() : '—'}
        unit={yearsLeft != null ? 'yr' : ''}
      />
      <Stat
        label="Pumping (inferred)"
        value={fmt(p.pumping_af_yr, 0)}
        unit="AF/yr"
      />
      <Stat
        label="Irrigated acres"
        value={fmt(p.irrigated_acres_total, 0)}
        unit=""
      />

      <div
        className="mt-auto pt-3 border-t flex items-center gap-2"
        style={{ borderColor: 'var(--line)' }}
      >
        <span
          className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider"
          style={{
            background: p.data_quality === 'modeled_high' ? 'var(--field-subtle)' : 'var(--amber-subtle, #f0e6d0)',
            color: p.data_quality === 'modeled_high' ? 'var(--field)' : 'var(--text)',
          }}
        >
          {p.data_quality}
        </span>
        <span style={{ color: 'var(--text2)', fontSize: 11 }}>
          {p.data_quality === 'modeled_high'
            ? 'measured thickness + decline'
            : 'bedrock estimate — awaiting imputation'}
        </span>
      </div>
    </div>
  );
}

function Stat({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div className="flex items-baseline justify-between">
      <span
        className="text-[12px]"
        style={{ color: 'var(--text2)', fontFamily: 'var(--font-body)' }}
      >
        {label}
      </span>
      <span
        className="text-[14px] font-semibold tabular-nums"
        style={{ color: 'var(--text)' }}
      >
        {value} <span style={{ color: 'var(--text2)', fontWeight: 400 }}>{unit}</span>
      </span>
    </div>
  );
}

function fmt(v: number | null | undefined, digits: number): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return v.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}
