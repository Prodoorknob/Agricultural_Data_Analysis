'use client';

import { useEffect, useState, useCallback, useMemo } from 'react';
import Map, { Source, Layer, type MapMouseEvent } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
const GEOJSON_URL =
  'https://d2ad6b4ur7yvpq.cloudfront.net/naturalearth-3.3.0/ne_110m_admin_1_states_provinces.geojson';

const MAP_COLORS = [
  '#F3EFE8', '#E8E0D0', '#D0C4A8', '#B8A878',
  '#8CAA6C', '#6B9E5A', '#4A8B48', '#3A7A3E',
  '#2D6A4F', '#1B4332',
];

/** Simple quantile color mapper — no d3-scale dependency needed */
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
  data: Record<string, number>;             // state_alpha -> metric value
  selectedState: string | null;
  onStateSelect: (stateAlpha: string) => void;
  metricLabel?: string;
}

export default function USChoropleth({
  data,
  selectedState,
  onStateSelect,
  metricLabel = '',
}: USChoroplethProps) {
  const [geojson, setGeojson] = useState<GeoJSON.FeatureCollection | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  // Load GeoJSON
  useEffect(() => {
    fetch(GEOJSON_URL)
      .then((r) => r.json())
      .then((raw) => {
        const features = (raw as GeoJSON.FeatureCollection).features.filter(
          (f) => f.properties?.iso_a2 === 'US'
        );
        setGeojson({ type: 'FeatureCollection', features });
      })
      .catch(() => {});
  }, []);

  // Color scale
  const colorScale = useMemo(() => {
    const values = Object.values(data).filter((v) => v > 0);
    if (values.length === 0) return () => MAP_COLORS[0];
    return makeQuantileScale(values, MAP_COLORS);
  }, [data]);

  // Build match expression for MapLibre
  const fillColor = useMemo((): string | unknown[] => {
    if (!geojson) return MAP_COLORS[0];
    const entries: unknown[] = [];
    for (const f of geojson.features) {
      const code = f.properties?.postal;
      if (code && data[code] !== undefined) {
        entries.push(code, colorScale(data[code]) ?? MAP_COLORS[0]);
      }
    }
    // MapLibre match needs at least one pair; fallback to solid color if no data
    if (entries.length === 0) return MAP_COLORS[0];
    return ['match', ['get', 'postal'], ...entries, MAP_COLORS[0]];
  }, [geojson, data, colorScale]);

  const onClick = useCallback(
    (e: MapMouseEvent) => {
      const feature = e.features?.[0];
      if (feature?.properties?.postal) {
        onStateSelect(feature.properties.postal);
      }
    },
    [onStateSelect]
  );

  const onHover = useCallback((e: MapMouseEvent) => {
    const feature = e.features?.[0];
    setHovered(feature?.properties?.postal || null);
  }, []);

  if (!geojson) {
    return <div className="skeleton w-full" style={{ height: 380 }} />;
  }

  const minVal = Math.min(...Object.values(data).filter(Boolean));
  const maxVal = Math.max(...Object.values(data).filter(Boolean));

  return (
    <div className="relative w-full" style={{ height: 380 }}>
      <Map
        initialViewState={{ longitude: -98, latitude: 39, zoom: 3.5 }}
        style={{ width: '100%', height: '100%' }}
        mapStyle="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json"
        interactiveLayerIds={['states-fill']}
        onClick={onClick}
        onMouseMove={onHover}
        onMouseLeave={() => setHovered(null)}
        cursor={hovered ? 'pointer' : 'default'}
      >
        <Source id="states" type="geojson" data={geojson}>
          <Layer
            id="states-fill"
            type="fill"
            paint={{
              'fill-color': fillColor as any,
              'fill-opacity': 0.85,
            }}
          />
          <Layer
            id="states-border"
            type="line"
            paint={{
              'line-color': 'rgba(0, 0, 0, 0.14)',
              'line-width': 0.8,
            }}
          />
          {selectedState && (
            <Layer
              id="states-highlight"
              type="line"
              filter={['==', ['get', 'postal'], selectedState]}
              paint={{
                'line-color': '#2D6A4F',
                'line-width': 2.5,
              }}
            />
          )}
        </Source>
      </Map>

      {/* Legend */}
      <div
        className="absolute bottom-3 left-3 flex items-center gap-1 px-2 py-1 rounded-[var(--radius-sm)]"
        style={{ background: 'var(--surface)', border: '1px solid var(--border)', boxShadow: 'var(--shadow-sm)' }}
      >
        <span className="text-[9px]" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
          {metricLabel || ''} {minVal > 0 ? `${(minVal / 1e6).toFixed(0)}M` : ''}
        </span>
        <div className="flex h-3 rounded-[2px] overflow-hidden">
          {MAP_COLORS.map((c, i) => (
            <div key={i} style={{ width: 16, height: 12, background: c }} />
          ))}
        </div>
        <span className="text-[9px]" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
          {maxVal > 0 ? `${(maxVal / 1e6).toFixed(0)}M` : ''}
        </span>
      </div>

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
          <p
            className="text-[16px] font-bold"
            style={{ fontFamily: 'var(--font-stat)', color: 'var(--text)' }}
          >
            {hovered}
          </p>
          <p
            className="text-[13px] font-medium"
            style={{ fontFamily: 'var(--font-mono)', color: 'var(--text2)' }}
          >
            {data[hovered].toLocaleString()}
          </p>
        </div>
      )}
    </div>
  );
}
