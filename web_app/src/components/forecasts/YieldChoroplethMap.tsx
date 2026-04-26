'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type { YieldMapItem } from '@/hooks/useYieldForecast';

interface YieldChoroplethMapProps {
  counties: YieldMapItem[];
  selectedFips: string | null;
  selectedState?: string | null;
  onCountyClick: (fips: string) => void;
  onStateClick?: (stateFips: string) => void;
  unit?: string;
  height?: number;
}

let _countyGeoJSON: any | null = null;
let _countyPromise: Promise<any> | null = null;

function loadCountyGeoJSON(): Promise<any> {
  if (_countyGeoJSON) return Promise.resolve(_countyGeoJSON);
  if (_countyPromise) return _countyPromise;
  _countyPromise = fetch('/us-counties.geojson')
    .then((r) => r.json())
    .then((gj) => {
      _countyGeoJSON = gj;
      return gj;
    });
  return _countyPromise;
}

function interp(a: string, b: string, t: number): string {
  const ah = parseInt(a.slice(1), 16);
  const bh = parseInt(b.slice(1), 16);
  const r = Math.round(((ah >> 16) & 255) + (((bh >> 16) & 255) - ((ah >> 16) & 255)) * t);
  const g = Math.round(((ah >> 8) & 255) + (((bh >> 8) & 255) - ((ah >> 8) & 255)) * t);
  const bl = Math.round((ah & 255) + ((bh & 255) - (ah & 255)) * t);
  return `rgb(${r},${g},${bl})`;
}

// Diverging palette used when counties have a vs_avg_pct anomaly vs 5-yr mean.
// Clamps to ±20% so extreme outliers don't flatten the middle.
function colorForAnomaly(pct: number): string {
  const x = Math.max(-0.2, Math.min(0.2, pct / 100));
  const t = (x + 0.2) / 0.4;
  if (t < 0.5) return interp('#7a2a1e', '#3a4a40', t / 0.5);
  return interp('#3a4a40', '#52B788', (t - 0.5) / 0.5);
}

// Sequential palette used when anomaly isn't available — color by raw p50.
function colorForAbsolute(val: number, min: number, max: number): string {
  if (max <= min) return '#3a4a40';
  const t = Math.max(0, Math.min(1, (val - min) / (max - min)));
  return interp('#2b3a30', '#52B788', t);
}

function* coordEach(geom: any): Generator<[number, number]> {
  if (!geom) return;
  if (geom.type === 'Polygon') {
    for (const r of geom.coordinates) for (const c of r) yield c as [number, number];
  } else if (geom.type === 'MultiPolygon') {
    for (const p of geom.coordinates) for (const r of p) for (const c of r) yield c as [number, number];
  }
}

function pathFor(
  geom: any,
  project: (lon: number, lat: number) => [number, number],
): string {
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

export default function YieldChoroplethMap({
  counties,
  selectedFips,
  selectedState = null,
  onCountyClick,
  onStateClick,
  unit = 'bu/ac',
  height = 420,
}: YieldChoroplethMapProps) {
  const [features, setFeatures] = useState<any[]>([]);
  const [tip, setTip] = useState<{ x: number; y: number; fips: string } | null>(null);
  const mapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    loadCountyGeoJSON()
      .then((gj) => {
        // Skip Alaska (02), Hawaii (15), and territories (>=60) so the
        // conterminous US fills the viewport.
        const feats = (gj.features || []).filter((f: any) => {
          const id = String(f.id ?? f.properties?.GEOID ?? '');
          if (id.startsWith('02') || id.startsWith('15')) return false;
          if (id.length >= 2 && Number(id.slice(0, 2)) >= 60) return false;
          return true;
        });
        setFeatures(feats);
      })
      .catch((err) => console.error('county geojson load failed', err));
  }, []);

  const byFips = useMemo(() => {
    const m = new Map<string, YieldMapItem>();
    for (const c of counties) m.set(c.fips, c);
    return m;
  }, [counties]);

  const hasAnomaly = useMemo(
    () => counties.some((c) => c.vs_avg_pct !== null && c.vs_avg_pct !== undefined),
    [counties],
  );

  const [absMin, absMax] = useMemo(() => {
    const vals = counties.map((c) => c.p50).filter((v) => Number.isFinite(v) && v > 0);
    if (vals.length === 0) return [0, 1];
    // Clamp to 5th/95th so a single extreme doesn't wash out the ramp.
    const sorted = [...vals].sort((a, b) => a - b);
    const lo = sorted[Math.floor(sorted.length * 0.05)];
    const hi = sorted[Math.floor(sorted.length * 0.95)];
    return [lo, hi];
  }, [counties]);

  const { paths, viewBox } = useMemo(() => {
    if (features.length === 0) return { paths: [], viewBox: '0 0 960 600' };
    let minLon = Infinity,
      maxLon = -Infinity,
      minLat = Infinity,
      maxLat = -Infinity;
    for (const f of features)
      for (const [lon, lat] of coordEach(f.geometry)) {
        if (lon < minLon) minLon = lon;
        if (lon > maxLon) maxLon = lon;
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
      }
    const W = 960,
      H = 600,
      PAD = 8;
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

    return {
      viewBox: `0 0 ${W} ${H}`,
      paths: features.map((f: any) => {
        const fips = String(f.id ?? f.properties?.GEOID ?? '').padStart(5, '0');
        const stateFips = fips.slice(0, 2);
        const row = byFips.get(fips);
        let fill = '#2b3a30';
        if (row) {
          if (hasAnomaly && row.vs_avg_pct !== null && row.vs_avg_pct !== undefined) {
            fill = colorForAnomaly(row.vs_avg_pct);
          } else if (Number.isFinite(row.p50)) {
            fill = colorForAbsolute(row.p50, absMin, absMax);
          }
        }
        return {
          fips,
          stateFips,
          name: (f.properties?.name || fips).toUpperCase(),
          d: pathFor(f.geometry, project),
          fill,
          hasData: !!row,
        };
      }),
    };
  }, [features, byFips, hasAnomaly, absMin, absMax]);

  const handleHover = (e: React.MouseEvent, fips: string) => {
    const rect = mapRef.current?.getBoundingClientRect();
    setTip({
      x: e.clientX - (rect?.left ?? 0) + 12,
      y: e.clientY - (rect?.top ?? 0) + 10,
      fips,
    });
  };

  const hoverRow = tip ? byFips.get(tip.fips) : null;
  const hoverPath = tip ? paths.find((p) => p.fips === tip.fips) : null;
  const nReported = counties.length;
  const nTotal = features.length;

  return (
    <div ref={mapRef} style={{ position: 'relative', width: '100%' }}>
      <svg
        viewBox={viewBox}
        preserveAspectRatio="xMidYMid meet"
        style={{ width: '100%', maxHeight: height, aspectRatio: '960 / 600' }}
      >
        <g>
          {paths.map((p) => {
            const dimmed = !!selectedState && p.stateFips !== selectedState;
            const isSelectedCounty = selectedFips === p.fips;
            const isInSelectedState = !!selectedState && p.stateFips === selectedState;
            const stroke = isSelectedCounty
              ? 'var(--text)'
              : isInSelectedState
                ? 'var(--text2)'
                : 'var(--surface)';
            const strokeWidth = isSelectedCounty ? 1.2 : isInSelectedState ? 0.5 : 0.3;
            return (
              <path
                key={p.fips}
                d={p.d}
                fill={p.fill}
                fillOpacity={dimmed ? 0.35 : 1}
                stroke={stroke}
                strokeWidth={strokeWidth}
                style={{ cursor: 'pointer', transition: 'stroke-width 0.1s, fill-opacity 0.15s' }}
                onMouseMove={(e) => handleHover(e, p.fips)}
                onMouseLeave={() => setTip(null)}
                onClick={() => {
                  if (p.hasData) {
                    onCountyClick(p.fips);
                  } else if (onStateClick) {
                    onStateClick(p.stateFips);
                  }
                }}
              />
            );
          })}
        </g>
      </svg>

      {tip && hoverPath && (
        <div
          style={{
            position: 'absolute',
            left: tip.x,
            top: tip.y,
            background: 'var(--surface2)',
            border: '1px solid var(--border2)',
            borderRadius: 6,
            padding: '8px 10px',
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--text)',
            boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
            pointerEvents: 'none',
            zIndex: 10,
            minWidth: 160,
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 2 }}>{hoverPath.name}</div>
          {hoverRow ? (
            <>
              <div style={{ color: 'var(--field-light)' }}>
                {hoverRow.p50.toFixed(1)} {unit}
              </div>
              {hoverRow.vs_avg_pct !== null && hoverRow.vs_avg_pct !== undefined && (
                <div style={{ color: 'var(--text3)' }}>
                  {hoverRow.vs_avg_pct >= 0 ? '+' : ''}
                  {hoverRow.vs_avg_pct.toFixed(1)}% vs 5-yr avg
                </div>
              )}
              <div style={{ color: 'var(--text3)' }}>
                Confidence: {hoverRow.confidence}
              </div>
              <div style={{ color: 'var(--text3)', marginTop: 2 }}>Click to drill in</div>
            </>
          ) : (
            <>
              <div style={{ color: 'var(--text3)' }}>No model output</div>
              {onStateClick && (
                <div style={{ color: 'var(--text3)', marginTop: 2 }}>Click to filter state</div>
              )}
            </>
          )}
        </div>
      )}

      {/* Legend */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          marginTop: 10,
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: 'var(--text3)',
        }}
      >
        {hasAnomaly ? (
          <>
            <span>−20%</span>
            <span
              style={{
                display: 'inline-block',
                height: 8,
                flex: 1,
                borderRadius: 2,
                background: 'linear-gradient(90deg, #7a2a1e, #3a4a40, #52B788)',
              }}
            />
            <span>+20% vs 5-yr avg</span>
          </>
        ) : (
          <>
            <span>{absMin.toFixed(0)}</span>
            <span
              style={{
                display: 'inline-block',
                height: 8,
                flex: 1,
                borderRadius: 2,
                background: 'linear-gradient(90deg, #2b3a30, #52B788)',
              }}
            />
            <span>{absMax.toFixed(0)} {unit}</span>
          </>
        )}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          color: 'var(--text3)',
          marginTop: 6,
        }}
      >
        {nReported} of {nTotal} counties forecast. Gray = no model output.
      </div>
    </div>
  );
}
