'use client';

import { useEffect, useState, useCallback, useMemo } from 'react';
import Map, { Source, Layer, type MapMouseEvent } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';

const STATE_GEOJSON_URL =
  'https://d2ad6b4ur7yvpq.cloudfront.net/naturalearth-3.3.0/ne_110m_admin_1_states_provinces.geojson';
// Pre-converted from us-atlas counties-10m.json at build time — served from
// our own /public to dodge the topojson-client ESM import issues in Next.
const COUNTY_GEOJSON_URL = '/us-counties.geojson';

const MAP_COLORS = [
  '#F3EFE8', '#E8E0D0', '#D0C4A8', '#B8A878',
  '#8CAA6C', '#6B9E5A', '#4A8B48', '#3A7A3E',
  '#2D6A4F', '#1B4332',
];

// State FIPS → bounding box [lonMin, latMin, lonMax, latMax] for zoom-on-select.
// Sourced from a condensed version of the GeoNames US state boundaries.
const STATE_BBOX: Record<string, [number, number, number, number]> = {
  AL:[-88.5,30.2,-84.9,35.0], AK:[-179.1,51.2,-130.0,71.4], AZ:[-114.8,31.3,-109.0,37.0],
  AR:[-94.6,33.0,-89.6,36.5], CA:[-124.5,32.5,-114.1,42.0], CO:[-109.1,36.9,-102.0,41.0],
  CT:[-73.7,40.9,-71.8,42.1], DE:[-75.8,38.4,-75.0,39.9], FL:[-87.6,24.5,-80.0,31.0],
  GA:[-85.6,30.3,-80.8,35.0], HI:[-161.0,18.8,-154.7,22.3], ID:[-117.3,42.0,-111.0,49.0],
  IL:[-91.5,36.9,-87.4,42.5], IN:[-88.1,37.8,-84.8,41.8], IA:[-96.6,40.4,-90.1,43.5],
  KS:[-102.1,36.9,-94.6,40.0], KY:[-89.6,36.5,-81.9,39.2], LA:[-94.0,28.9,-88.8,33.1],
  ME:[-71.1,43.1,-66.9,47.5], MD:[-79.5,37.9,-75.0,39.7], MA:[-73.5,41.2,-69.9,42.9],
  MI:[-90.4,41.7,-82.4,48.3], MN:[-97.3,43.4,-89.5,49.4], MS:[-91.7,30.2,-88.1,35.0],
  MO:[-95.8,36.0,-89.1,40.6], MT:[-116.0,44.4,-104.0,49.0], NE:[-104.1,40.0,-95.3,43.0],
  NV:[-120.0,35.0,-114.0,42.0], NH:[-72.6,42.7,-70.6,45.3], NJ:[-75.6,38.9,-73.9,41.4],
  NM:[-109.1,31.3,-103.0,37.0], NY:[-79.8,40.5,-71.9,45.0], NC:[-84.3,33.8,-75.5,36.6],
  ND:[-104.1,45.9,-96.6,49.0], OH:[-84.8,38.4,-80.5,42.3], OK:[-103.0,33.6,-94.4,37.0],
  OR:[-124.6,42.0,-116.5,46.3], PA:[-80.5,39.7,-74.7,42.3], RI:[-71.9,41.1,-71.1,42.0],
  SC:[-83.4,32.0,-78.5,35.2], SD:[-104.1,42.5,-96.4,45.9], TN:[-90.3,34.9,-81.6,36.7],
  TX:[-106.7,25.8,-93.5,36.5], UT:[-114.1,37.0,-109.0,42.0], VT:[-73.4,42.7,-71.5,45.0],
  VA:[-83.7,36.5,-75.2,39.5], WA:[-124.8,45.5,-116.9,49.0], WV:[-82.7,37.2,-77.7,40.6],
  WI:[-92.9,42.5,-86.8,47.1], WY:[-111.1,41.0,-104.1,45.0],
};

function makeQuantileScale(values: number[], colors: string[]) {
  const sorted = [...values].sort((a, b) => a - b);
  const n = colors.length;
  return (v: number): string => {
    if (sorted.length === 0) return colors[0];
    const idx = sorted.findIndex((s) => s >= v);
    const pos = idx === -1 ? sorted.length - 1 : idx;
    const bucket = Math.min(Math.floor((pos / sorted.length) * n), n - 1);
    return colors[bucket];
  };
}

interface USChoroplethProps {
  data: Record<string, number>;
  selectedState: string | null;
  onStateSelect: (stateAlpha: string) => void;
  metricLabel?: string;
  mode?: 'state' | 'county';
}

export default function USChoropleth({
  data,
  selectedState,
  onStateSelect,
  metricLabel = '',
  mode = 'state',
}: USChoroplethProps) {
  const [stateGeojson, setStateGeojson] = useState<GeoJSON.FeatureCollection | null>(null);
  const [countyGeojson, setCountyGeojson] = useState<GeoJSON.FeatureCollection | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  // Load state GeoJSON (always needed — outline even in county mode).
  useEffect(() => {
    fetch(STATE_GEOJSON_URL)
      .then((r) => r.json())
      .then((raw) => {
        const features = (raw as GeoJSON.FeatureCollection).features.filter(
          (f) => f.properties?.iso_a2 === 'US',
        );
        setStateGeojson({ type: 'FeatureCollection', features });
      })
      .catch(() => {});
  }, []);

  // Load county GeoJSON only when we enter county mode — saves ~3MB on the
  // initial national page load.
  useEffect(() => {
    if (mode !== 'county' || countyGeojson) return;
    fetch(COUNTY_GEOJSON_URL)
      .then((r) => r.json())
      .then((geo) => setCountyGeojson(geo as GeoJSON.FeatureCollection))
      .catch((e) => console.warn('county geojson load failed', e));
  }, [mode, countyGeojson]);

  const colorScale = useMemo(() => {
    const values = Object.values(data).filter((v) => v > 0);
    if (!values.length) return () => MAP_COLORS[0];
    return makeQuantileScale(values, MAP_COLORS);
  }, [data]);

  // Build the fill-color match expression keyed on the right property.
  const fillColor = useMemo((): string | unknown[] => {
    if (mode === 'county') {
      if (!countyGeojson) return MAP_COLORS[0];
      // County GeoJSON from us-atlas uses an `id` field with the 5-digit FIPS
      // code. Note: the id lives on the feature, not under properties.
      const entries: unknown[] = [];
      for (const f of countyGeojson.features) {
        const fips = (f.id as string) || f.properties?.id;
        if (fips && data[fips] !== undefined) {
          entries.push(fips, colorScale(data[fips]) ?? MAP_COLORS[0]);
        }
      }
      if (!entries.length) return MAP_COLORS[0];
      return ['match', ['to-string', ['id']], ...entries, MAP_COLORS[0]];
    }
    if (!stateGeojson) return MAP_COLORS[0];
    const entries: unknown[] = [];
    for (const f of stateGeojson.features) {
      const code = f.properties?.postal;
      if (code && data[code] !== undefined) {
        entries.push(code, colorScale(data[code]) ?? MAP_COLORS[0]);
      }
    }
    if (!entries.length) return MAP_COLORS[0];
    return ['match', ['get', 'postal'], ...entries, MAP_COLORS[0]];
  }, [mode, stateGeojson, countyGeojson, data, colorScale]);

  const onClick = useCallback(
    (e: MapMouseEvent) => {
      const feature = e.features?.[0];
      // In state mode, clicking a state selects it. In county mode, clicking
      // the faded surrounding-state outline layer should deselect back to
      // national. County features don't have a postal code so we check both.
      if (feature?.properties?.postal) {
        onStateSelect(feature.properties.postal);
      }
    },
    [onStateSelect],
  );

  const onHover = useCallback(
    (e: MapMouseEvent) => {
      const feature = e.features?.[0];
      if (mode === 'county') {
        const fips = (feature?.id as string) || null;
        setHovered(fips);
      } else {
        setHovered(feature?.properties?.postal || null);
      }
    },
    [mode],
  );

  // Compute view settings — state BBox → centered zoom when a state is
  // selected. Kept above any early return so hook call order stays stable.
  const viewState = useMemo(() => {
    if (!selectedState || !STATE_BBOX[selectedState]) {
      return { longitude: -98, latitude: 39, zoom: 3.5 };
    }
    const [lonMin, latMin, lonMax, latMax] = STATE_BBOX[selectedState];
    return {
      longitude: (lonMin + lonMax) / 2,
      latitude: (latMin + latMax) / 2,
      zoom: 5.3,
    };
  }, [selectedState]);

  const ready = mode === 'county' ? !!countyGeojson : !!stateGeojson;
  if (!ready) {
    return <div className="skeleton w-full h-full" style={{ minHeight: 380 }} />;
  }

  const values = Object.values(data).filter((v) => v > 0);
  const minVal = values.length ? Math.min(...values) : 0;
  const maxVal = values.length ? Math.max(...values) : 0;

  const interactiveLayers =
    mode === 'county' ? ['counties-fill', 'states-fill'] : ['states-fill'];

  return (
    <div className="relative w-full h-full" style={{ minHeight: 560 }}>
      <Map
        key={`${mode}-${selectedState ?? 'nat'}`}
        initialViewState={viewState}
        style={{ width: '100%', height: '100%' }}
        mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
        interactiveLayerIds={interactiveLayers}
        onClick={onClick}
        onMouseMove={onHover}
        onMouseLeave={() => setHovered(null)}
        cursor={hovered ? 'pointer' : 'default'}
      >
        {mode === 'county' && countyGeojson && (
          <Source id="counties" type="geojson" data={countyGeojson}>
            <Layer
              id="counties-fill"
              type="fill"
              // Only color counties inside the selected state — id[0:2] === state FIPS.
              filter={
                selectedState
                  ? ['==', ['slice', ['to-string', ['id']], 0, 2], stateFipsCode(selectedState)]
                  : true
              }
              paint={{
                'fill-color': fillColor as any,
                'fill-opacity': 0.85,
              }}
            />
            <Layer
              id="counties-border"
              type="line"
              filter={
                selectedState
                  ? ['==', ['slice', ['to-string', ['id']], 0, 2], stateFipsCode(selectedState)]
                  : true
              }
              paint={{ 'line-color': 'rgba(0,0,0,0.1)', 'line-width': 0.5 }}
            />
          </Source>
        )}

        {stateGeojson && (
          <Source id="states" type="geojson" data={stateGeojson}>
            {/* In state mode, state fill carries the data. In county mode, it's a
                faint backdrop that lets clicks re-select a different state. */}
            <Layer
              id="states-fill"
              type="fill"
              paint={{
                'fill-color': mode === 'state' ? (fillColor as any) : '#FFFFFF',
                'fill-opacity': mode === 'state' ? 0.85 : 0,
              }}
            />
            <Layer
              id="states-border"
              type="line"
              paint={{
                'line-color': 'rgba(0, 0, 0, 0.14)',
                'line-width': mode === 'county' ? 1.4 : 0.8,
              }}
            />
            {selectedState && (
              <Layer
                id="states-highlight"
                type="line"
                filter={['==', ['get', 'postal'], selectedState]}
                paint={{ 'line-color': '#2D6A4F', 'line-width': 2.5 }}
              />
            )}
          </Source>
        )}
      </Map>

      {/* Legend */}
      <div
        className="absolute bottom-3 left-3 flex items-center gap-1 px-2 py-1 rounded-[var(--radius-sm)]"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', boxShadow: 'var(--shadow-sm)' }}
      >
        <span className="text-[9px]" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
          {metricLabel || ''} {values.length ? `${(minVal / 1e6).toFixed(0)}M` : ''}
        </span>
        <div className="flex h-3 rounded-[2px] overflow-hidden">
          {MAP_COLORS.map((c, i) => (
            <div key={i} style={{ width: 16, height: 12, background: c }} />
          ))}
        </div>
        <span className="text-[9px]" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
          {values.length ? `${(maxVal / 1e6).toFixed(0)}M` : ''}
        </span>
      </div>

      {/* Back-to-national button in county mode */}
      {mode === 'county' && selectedState && (
        <button
          onClick={() => onStateSelect('')}
          className="absolute top-3 left-3 px-3 py-1.5 rounded-[var(--radius-full)] text-[12px] font-semibold cursor-pointer"
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            color: 'var(--text2)',
            boxShadow: 'var(--shadow-sm)',
            fontFamily: 'var(--font-mono)',
          }}
          aria-label="Back to U.S. map"
        >
          ← U.S. map
        </button>
      )}

      {/* Hover tooltip */}
      {hovered && data[hovered] !== undefined && (
        <div
          className="absolute top-3 right-3 px-3 py-2 rounded-[var(--radius-md)]"
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            boxShadow: 'var(--shadow-md)',
          }}
        >
          <p className="text-[16px] font-bold" style={{ fontFamily: 'var(--font-stat)', color: 'var(--text)' }}>
            {hovered}
          </p>
          <p className="text-[13px] font-medium" style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}>
            {data[hovered].toLocaleString()}
          </p>
        </div>
      )}
    </div>
  );
}

/** 2-letter state code → 2-digit FIPS, for the county-filter expression. */
function stateFipsCode(alpha: string): string {
  const map: Record<string, string> = {
    AL:'01',AK:'02',AZ:'04',AR:'05',CA:'06',CO:'08',CT:'09',DE:'10',FL:'12',GA:'13',
    HI:'15',ID:'16',IL:'17',IN:'18',IA:'19',KS:'20',KY:'21',LA:'22',ME:'23',MD:'24',
    MA:'25',MI:'26',MN:'27',MS:'28',MO:'29',MT:'30',NE:'31',NV:'32',NH:'33',NJ:'34',
    NM:'35',NY:'36',NC:'37',ND:'38',OH:'39',OK:'40',OR:'41',PA:'42',RI:'44',SC:'45',
    SD:'46',TN:'47',TX:'48',UT:'49',VT:'50',VA:'51',WA:'53',WV:'54',WI:'55',WY:'56',
  };
  return map[alpha] || '00';
}
