'use client';

/**
 * Region map for issue figures: a state-level choropleth built from the same
 * county geojson the Forecasts and Crops tabs use. Counties are filled with
 * their state's value, which gives the state choropleth a subtle county
 * texture. States with a null value render with a hatch pattern (flagged).
 *
 * The viewport crops to the bounding box of the states in the spec, so a
 * "High Plains wheat belt" figure shows just the belt, not the whole CONUS.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import type { RegionMapChart, RegionMapState } from './types';

let _geo: any | null = null;
let _geoPromise: Promise<any> | null = null;

function loadGeo(): Promise<any> {
  if (_geo) return Promise.resolve(_geo);
  if (_geoPromise) return _geoPromise;
  _geoPromise = fetch('/us-counties.geojson')
    .then((r) => r.json())
    .then((gj) => {
      _geo = gj;
      return gj;
    });
  return _geoPromise;
}

function interp(a: string, b: string, t: number): string {
  const ah = parseInt(a.slice(1), 16);
  const bh = parseInt(b.slice(1), 16);
  const r = Math.round(((ah >> 16) & 255) + (((bh >> 16) & 255) - ((ah >> 16) & 255)) * t);
  const g = Math.round(((ah >> 8) & 255) + (((bh >> 8) & 255) - ((ah >> 8) & 255)) * t);
  const bl = Math.round((ah & 255) + ((bh & 255) - (ah & 255)) * t);
  return `rgb(${r},${g},${bl})`;
}

// Diverging rust -> neutral -> green, clamped to +/-25%. The midpoint has to
// track the theme: parchment on the light theme, the muted green-gray the
// yield choropleth uses on dark.
const RAMP = {
  light: { neg: '#9C3B22', mid: '#E8E2D6', pos: '#2D6A4F' },
  dark: { neg: '#7a2a1e', mid: '#3a4a40', pos: '#52B788' },
};

function colorForDelta(pct: number, theme: 'light' | 'dark'): string {
  const r = RAMP[theme];
  const x = Math.max(-25, Math.min(25, pct)) / 25;
  if (x < 0) return interp(r.mid, r.neg, -x);
  return interp(r.mid, r.pos, x);
}

function useTheme(): 'light' | 'dark' {
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  useEffect(() => {
    const read = () =>
      setTheme(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');
    read();
    const mo = new MutationObserver(read);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => mo.disconnect();
  }, []);
  return theme;
}

function* coordEach(geom: any): Generator<[number, number]> {
  if (!geom) return;
  if (geom.type === 'Polygon') {
    for (const r of geom.coordinates) for (const c of r) yield c as [number, number];
  } else if (geom.type === 'MultiPolygon') {
    for (const p of geom.coordinates) for (const r of p) for (const c of r) yield c as [number, number];
  }
}

function pathFor(geom: any, project: (lon: number, lat: number) => [number, number]): string {
  const ring = (r: [number, number][]) =>
    r
      .map(([lon, lat], i) => {
        const [x, y] = project(lon, lat);
        return (i === 0 ? 'M' : 'L') + x.toFixed(1) + ',' + y.toFixed(1);
      })
      .join('') + 'Z';
  if (geom.type === 'Polygon') return geom.coordinates.map(ring).join(' ');
  return geom.coordinates.map((poly: any) => poly.map(ring).join(' ')).join(' ');
}

export default function RegionMap({ chart }: { chart: RegionMapChart }) {
  const [features, setFeatures] = useState<any[]>([]);
  const [hover, setHover] = useState<{ x: number; y: number; fips: string } | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const theme = useTheme();

  const byState = useMemo(() => {
    const m = new Map<string, RegionMapState>();
    for (const s of chart.states) m.set(s.fips, s);
    return m;
  }, [chart.states]);

  useEffect(() => {
    loadGeo()
      .then((gj) => {
        const wanted = new Set(chart.states.map((s) => s.fips));
        const feats = (gj.features || []).filter((f: any) => {
          const id = String(f.id ?? f.properties?.GEOID ?? '').padStart(5, '0');
          return wanted.has(id.slice(0, 2));
        });
        setFeatures(feats);
      })
      .catch((err) => console.error('region map geojson load failed', err));
  }, [chart.states]);

  const { paths, labels, viewBox } = useMemo(() => {
    if (features.length === 0)
      return { paths: [] as any[], labels: [] as any[], viewBox: '0 0 760 560' };
    let minLon = Infinity,
      maxLon = -Infinity,
      minLat = Infinity,
      maxLat = -Infinity;
    const stateBounds = new Map<
      string,
      { minLon: number; maxLon: number; minLat: number; maxLat: number }
    >();
    for (const f of features) {
      const fips = String(f.id ?? f.properties?.GEOID ?? '').padStart(5, '0');
      const st = fips.slice(0, 2);
      let b = stateBounds.get(st);
      if (!b) {
        b = { minLon: Infinity, maxLon: -Infinity, minLat: Infinity, maxLat: -Infinity };
        stateBounds.set(st, b);
      }
      for (const [lon, lat] of coordEach(f.geometry)) {
        if (lon < minLon) minLon = lon;
        if (lon > maxLon) maxLon = lon;
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
        if (lon < b.minLon) b.minLon = lon;
        if (lon > b.maxLon) b.maxLon = lon;
        if (lat < b.minLat) b.minLat = lat;
        if (lat > b.maxLat) b.maxLat = lat;
      }
    }
    const W = 760,
      H = 560,
      PAD = 10;
    const sx = (W - PAD * 2) / (maxLon - minLon);
    const sy = (H - PAD * 2) / (maxLat - minLat);
    const s = Math.min(sx, sy);
    const cw = (maxLon - minLon) * s;
    const ch = (maxLat - minLat) * s;
    const ox = PAD + (W - PAD * 2 - cw) / 2;
    const oy = PAD + (H - PAD * 2 - ch) / 2;
    const project = (lon: number, lat: number): [number, number] => [
      ox + (lon - minLon) * s,
      oy + (maxLat - lat) * s,
    ];

    const paths = features.map((f: any) => {
      const fips = String(f.id ?? f.properties?.GEOID ?? '').padStart(5, '0');
      const st = fips.slice(0, 2);
      const row = byState.get(st);
      let fill = 'var(--surface2)';
      if (row) {
        if (row.forecast === null || row.baseline === null || !row.baseline) {
          fill = 'url(#fpnHatch)';
        } else {
          fill = colorForDelta(((row.forecast - row.baseline) / row.baseline) * 100, theme);
        }
      }
      return { fips, stateFips: st, d: pathFor(f.geometry, project), fill };
    });

    const labels = chart.states
      .map((st) => {
        const b = stateBounds.get(st.fips);
        if (!b) return null;
        const [x, y] = project((b.minLon + b.maxLon) / 2, (b.minLat + b.maxLat) / 2);
        const delta =
          st.forecast !== null && st.baseline
            ? ((st.forecast - st.baseline) / st.baseline) * 100
            : null;
        return { ...st, x, y, delta };
      })
      .filter(Boolean) as Array<RegionMapState & { x: number; y: number; delta: number | null }>;

    return { paths, labels, viewBox: `0 0 ${W} ${H}` };
  }, [features, byState, chart.states, theme]);

  const handleHover = (e: React.MouseEvent, fips: string) => {
    const rect = wrapRef.current?.getBoundingClientRect();
    setHover({
      x: e.clientX - (rect?.left ?? 0) + 12,
      y: e.clientY - (rect?.top ?? 0) + 10,
      fips,
    });
  };

  const hoverState = hover ? byState.get(hover.fips) : null;
  const hoverDelta =
    hoverState && hoverState.forecast !== null && hoverState.baseline
      ? ((hoverState.forecast - hoverState.baseline) / hoverState.baseline) * 100
      : null;

  return (
    <div ref={wrapRef} style={{ position: 'relative', width: '100%' }}>
      <svg
        viewBox={viewBox}
        preserveAspectRatio="xMidYMid meet"
        style={{ width: '100%', maxHeight: chart.height ?? 460, aspectRatio: '760 / 560' }}
      >
        <defs>
          <pattern
            id="fpnHatch"
            patternUnits="userSpaceOnUse"
            width="7"
            height="7"
            patternTransform="rotate(45)"
          >
            <rect width="7" height="7" fill="var(--harvest-subtle)" />
            <line x1="0" y1="0" x2="0" y2="7" stroke="var(--harvest)" strokeWidth="1.4" />
          </pattern>
        </defs>
        <g>
          {paths.map((p) => {
            const dimOthers = hover && p.stateFips !== hover.fips;
            return (
              <path
                key={p.fips}
                d={p.d}
                fill={p.fill}
                fillOpacity={dimOthers ? 0.55 : 1}
                stroke="var(--bg)"
                strokeWidth={0.5}
                style={{ transition: 'fill-opacity 0.12s' }}
                onMouseMove={(e) => handleHover(e, p.stateFips)}
                onMouseLeave={() => setHover(null)}
              />
            );
          })}
        </g>
        <g style={{ pointerEvents: 'none' }}>
          {labels.map((l) => (
            <g key={l.fips}>
              <text
                x={l.x}
                y={l.y - 4}
                textAnchor="middle"
                style={{
                  fontFamily: 'var(--font-barlow), system-ui, sans-serif',
                  fontWeight: 800,
                  fontSize: 18,
                  fill: 'var(--text)',
                  paintOrder: 'stroke',
                  stroke: 'var(--bg)',
                  strokeWidth: 3,
                  strokeLinejoin: 'round',
                }}
              >
                {l.abbr}
              </text>
              <text
                x={l.x}
                y={l.y + 14}
                textAnchor="middle"
                style={{
                  fontFamily: 'var(--font-jetbrains), monospace',
                  fontWeight: 700,
                  fontSize: 12,
                  fill: l.delta === null ? 'var(--harvest-dark)' : 'var(--text2)',
                  paintOrder: 'stroke',
                  stroke: 'var(--bg)',
                  strokeWidth: 3,
                  strokeLinejoin: 'round',
                }}
              >
                {l.delta === null
                  ? 'flagged'
                  : `${l.delta > 0 ? '+' : ''}${l.delta.toFixed(1)}%`}
              </text>
            </g>
          ))}
        </g>
      </svg>

      {hover && hoverState && (
        <div
          style={{
            position: 'absolute',
            left: hover.x,
            top: hover.y,
            background: 'var(--surface)',
            border: '1px solid var(--border2)',
            borderRadius: 6,
            padding: '8px 10px',
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--text)',
            boxShadow: 'var(--shadow-md)',
            pointerEvents: 'none',
            zIndex: 10,
            minWidth: 170,
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 2 }}>{hoverState.name}</div>
          {hoverState.forecast !== null ? (
            <>
              <div style={{ color: 'var(--text2)' }}>
                2026 forecast: {hoverState.forecast.toFixed(2)} {chart.unit ?? ''}
              </div>
              <div style={{ color: 'var(--text2)' }}>
                2021-24 avg: {hoverState.baseline?.toFixed(2)} {chart.unit ?? ''}
              </div>
              {hoverDelta !== null && (
                <div style={{ color: hoverDelta < 0 ? 'var(--negative)' : 'var(--positive)' }}>
                  {hoverDelta > 0 ? '+' : ''}
                  {hoverDelta.toFixed(1)}% vs baseline
                </div>
              )}
            </>
          ) : (
            <div style={{ color: 'var(--harvest-dark)' }}>
              {hoverState.note ?? 'Flagged: no published value.'}
            </div>
          )}
        </div>
      )}

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginTop: 10,
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: 'var(--text3)',
        }}
      >
        <span>-25%</span>
        <span
          style={{
            display: 'inline-block',
            height: 8,
            flex: 1,
            borderRadius: 2,
            background: `linear-gradient(90deg, ${RAMP[theme].neg}, ${RAMP[theme].mid}, ${RAMP[theme].pos})`,
          }}
        />
        <span>+25%</span>
        <span style={{ marginLeft: 12, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
          <svg width="14" height="10" style={{ display: 'block' }}>
            <rect width="14" height="10" fill="url(#fpnHatch)" stroke="var(--border2)" strokeWidth="0.5" />
          </svg>
          flagged
        </span>
        <span style={{ marginLeft: 'auto' }}>{chart.metricLabel}</span>
      </div>
      {chart.caption && <div className="fpn-panel-caption">{chart.caption}</div>}
    </div>
  );
}
