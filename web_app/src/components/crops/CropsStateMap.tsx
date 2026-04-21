'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { filterData } from '@/utils/processData';

// ─── Types ─────────────────────────────────────────────────────
export interface CountyRollup {
  fips: string;
  county: string;
  yield: number;
  harvested: number;
  production: number;
}

interface CropsStateMapProps {
  stateAlpha: string;
  countyRows: any[];           // raw COUNTY NASS rows (post-filterData)
  commodity: string;           // commodity_desc, uppercase, e.g. "CORN"
  year: number;
  onCountyClick: (fips: string) => void;
  selectedFips: string | null;
  /**
   * The choropleth metric the map colors by. Default = yield anomaly vs
   * state median. `absolute_yield` colors by raw yield (no median reference).
   */
  metric?: 'yield_anomaly' | 'absolute_yield' | 'harvested' | 'production';
}

// ─── geojson cache — one nationwide file is reused across state switches
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

// ─── helpers ───────────────────────────────────────────────────
const STATE_ALPHA_TO_FIPS: Record<string, string> = {
  AL: '01', AK: '02', AZ: '04', AR: '05', CA: '06', CO: '08', CT: '09', DE: '10',
  FL: '12', GA: '13', HI: '15', ID: '16', IL: '17', IN: '18', IA: '19', KS: '20',
  KY: '21', LA: '22', ME: '23', MD: '24', MA: '25', MI: '26', MN: '27', MS: '28',
  MO: '29', MT: '30', NE: '31', NV: '32', NH: '33', NJ: '34', NM: '35', NY: '36',
  NC: '37', ND: '38', OH: '39', OK: '40', OR: '41', PA: '42', RI: '44', SC: '45',
  SD: '46', TN: '47', TX: '48', UT: '49', VT: '50', VA: '51', WA: '53', WV: '54',
  WI: '55', WY: '56',
};

function cleanValue(val: any): number {
  if (typeof val === 'number') return val;
  if (!val) return NaN;
  const s = String(val).trim();
  if (/^\([A-Z]\)$/i.test(s)) return NaN;
  const n = parseFloat(s.replace(/,/g, ''));
  return isNaN(n) ? NaN : n;
}

/**
 * Build per-county rollup for a given commodity/year from the county parquet.
 * Applies the same canonical slice (filterData already did SURVEY/YEAR/TOTAL
 * dedup). We still enforce ACRES for area + commodity-specific unit for
 * production, and take max() within each (fips, stat) bucket so biotech PCT
 * sub-rows can't contaminate totals.
 */
function rollupByCounty(
  rows: any[],
  commodity: string,
  year: number,
): Map<string, CountyRollup> {
  const BU_UNITS = new Set(['BU', 'CWT', 'LB', 'TONS', 'BOXES', 'BARRELS']);
  const byFips: Record<string, {
    fips: string; county: string;
    yield?: number; harvested?: number; production?: number;
  }> = {};
  for (const r of rows) {
    if (r.commodity_desc !== commodity) continue;
    if (Number(r.year) !== year) continue;
    const fips = r.fips;
    if (!fips) continue;
    const stat = r.statisticcat_desc;
    const unit = String(r.unit_desc || '').toUpperCase();
    const val = cleanValue(r.value_num ?? r.Value);
    if (isNaN(val)) continue;
    const b = (byFips[fips] ||= { fips, county: r.county_name || '' });
    if (!b.county && r.county_name) b.county = r.county_name;

    if (stat === 'YIELD' && !unit.includes('PCT')) {
      b.yield = Math.max(b.yield ?? 0, val);
    } else if (stat === 'AREA HARVESTED' && unit === 'ACRES') {
      b.harvested = Math.max(b.harvested ?? 0, val);
    } else if (stat === 'PRODUCTION' && BU_UNITS.has(unit)) {
      b.production = Math.max(b.production ?? 0, val);
    }
  }
  const map = new Map<string, CountyRollup>();
  for (const r of Object.values(byFips)) {
    if (r.yield == null && r.harvested == null && r.production == null) continue;
    map.set(r.fips, {
      fips: r.fips,
      county: r.county,
      yield: r.yield ?? 0,
      harvested: r.harvested ?? 0,
      production: r.production ?? 0,
    });
  }
  return map;
}

function interpColor(a: string, b: string, t: number): string {
  const ah = parseInt(a.slice(1), 16);
  const bh = parseInt(b.slice(1), 16);
  const r = Math.round(((ah >> 16) & 255) + (((bh >> 16) & 255) - ((ah >> 16) & 255)) * t);
  const g = Math.round(((ah >> 8) & 255) + (((bh >> 8) & 255) - ((ah >> 8) & 255)) * t);
  const bl = Math.round((ah & 255) + ((bh & 255) - (ah & 255)) * t);
  return `rgb(${r},${g},${bl})`;
}

function colorForAnomaly(pct: number): string {
  // Clamp to ±30%, diverging palette: rust → neutral → green
  const x = Math.max(-0.3, Math.min(0.3, pct / 100));
  const t = (x + 0.3) / 0.6; // 0..1
  if (t < 0.5) return interpColor('#7a2a1e', '#3a4a40', t / 0.5);
  return interpColor('#3a4a40', '#52B788', (t - 0.5) / 0.5);
}

function colorForAbsolute(val: number, min: number, max: number): string {
  if (max <= min) return '#3a4a40';
  const t = Math.max(0, Math.min(1, (val - min) / (max - min)));
  return interpColor('#2b3a30', '#52B788', t);
}

// ─── geometry helpers ──────────────────────────────────────────
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
    r.map(([lon, lat], i) => {
      const [x, y] = project(lon, lat);
      return (i === 0 ? 'M' : 'L') + x.toFixed(1) + ',' + y.toFixed(1);
    }).join('') + 'Z';
  if (geom.type === 'Polygon') return geom.coordinates.map(ring).join(' ');
  return geom.coordinates.map((poly: any) => poly.map(ring).join(' ')).join(' ');
}

// ─── component ─────────────────────────────────────────────────
export default function CropsStateMap({
  stateAlpha,
  countyRows,
  commodity,
  year,
  onCountyClick,
  selectedFips,
  metric = 'yield_anomaly',
}: CropsStateMapProps) {
  const [features, setFeatures] = useState<any[]>([]);
  const [tip, setTip] = useState<{
    x: number; y: number; name: string; row?: CountyRollup;
  } | null>(null);
  const mapRef = useRef<HTMLDivElement | null>(null);

  // Load geojson once, filter to selected state
  useEffect(() => {
    const stateFips = STATE_ALPHA_TO_FIPS[stateAlpha];
    if (!stateFips) {
      setFeatures([]);
      return;
    }
    loadCountyGeoJSON()
      .then((gj) => {
        const feats = (gj.features || []).filter((f: any) =>
          String(f.id ?? f.properties?.GEOID ?? '').startsWith(stateFips),
        );
        setFeatures(feats);
      })
      .catch((err) => console.error('county geojson load failed', err));
  }, [stateAlpha]);

  // Roll-up county rows into a per-fips map
  const rollup = useMemo(
    () => rollupByCounty(countyRows, commodity, year),
    [countyRows, commodity, year],
  );

  // State median yield — reference for anomaly colors
  const stateMedian = useMemo(() => {
    const yields = Array.from(rollup.values())
      .map((r) => r.yield)
      .filter((v) => v > 0)
      .sort((a, b) => a - b);
    if (yields.length === 0) return 0;
    return yields[Math.floor(yields.length / 2)];
  }, [rollup]);

  const [absMin, absMax] = useMemo(() => {
    const vals = Array.from(rollup.values())
      .map((r) => {
        if (metric === 'absolute_yield') return r.yield;
        if (metric === 'harvested') return r.harvested;
        if (metric === 'production') return r.production;
        return 0;
      })
      .filter((v) => v > 0);
    if (vals.length === 0) return [0, 1];
    return [Math.min(...vals), Math.max(...vals)];
  }, [rollup, metric]);

  // Compute SVG projection bounds from features
  const { paths, viewBox } = useMemo(() => {
    if (features.length === 0) return { paths: [], viewBox: '0 0 360 420' };
    let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity;
    for (const f of features)
      for (const [lon, lat] of coordEach(f.geometry)) {
        if (lon < minLon) minLon = lon;
        if (lon > maxLon) maxLon = lon;
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
      }
    const W = 360, H = 420, PAD = 10;
    const sx = (W - PAD * 2) / (maxLon - minLon);
    const sy = (H - PAD * 2) / (maxLat - minLat);
    const s = Math.min(sx, sy);
    const cw = (maxLon - minLon) * s;
    const ch = (maxLat - minLat) * s;
    const ox = PAD + ((W - PAD * 2) - cw) / 2;
    const oy = PAD + ((H - PAD * 2) - ch) / 2;
    const project = (lon: number, lat: number): [number, number] =>
      [ox + (lon - minLon) * s, oy + (maxLat - lat) * s];

    return {
      viewBox: `0 0 ${W} ${H}`,
      paths: features.map((f: any) => {
        const fips = String(f.id ?? f.properties?.GEOID ?? '');
        const row = rollup.get(fips);
        let fill = '#2b3a30';
        if (row && row.yield > 0) {
          if (metric === 'yield_anomaly' && stateMedian > 0) {
            fill = colorForAnomaly(((row.yield - stateMedian) / stateMedian) * 100);
          } else {
            const v = metric === 'absolute_yield'
              ? row.yield
              : metric === 'harvested' ? row.harvested : row.production;
            fill = colorForAbsolute(v, absMin, absMax);
          }
        }
        return {
          fips,
          name: (f.properties?.name || fips).toUpperCase(),
          d: pathFor(f.geometry, project),
          fill,
        };
      }),
    };
  }, [features, rollup, metric, stateMedian, absMin, absMax]);

  const handleHover = (e: React.MouseEvent, fips: string, name: string) => {
    const rect = mapRef.current?.getBoundingClientRect();
    setTip({
      x: e.clientX - (rect?.left ?? 0) + 12,
      y: e.clientY - (rect?.top ?? 0) + 10,
      name,
      row: rollup.get(fips),
    });
  };

  const nReported = rollup.size;
  const nTotal = features.length;

  return (
    <div ref={mapRef} style={{ position: 'relative', width: '100%' }}>
      <svg
        viewBox={viewBox}
        preserveAspectRatio="xMidYMid meet"
        style={{ width: '100%', maxHeight: 320, aspectRatio: '360 / 420' }}
      >
        <g>
          {paths.map((p) => (
            <path
              key={p.fips}
              d={p.d}
              fill={p.fill}
              stroke={selectedFips === p.fips ? 'var(--text)' : 'var(--surface)'}
              strokeWidth={selectedFips === p.fips ? 1.6 : 0.6}
              style={{ cursor: 'pointer', transition: 'stroke-width 0.1s' }}
              onMouseMove={(e) => handleHover(e, p.fips, p.name)}
              onMouseLeave={() => setTip(null)}
              onClick={() => onCountyClick(p.fips)}
            />
          ))}
        </g>
      </svg>

      {tip && (
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
          <div style={{ fontWeight: 700, marginBottom: 2 }}>{tip.name}</div>
          {tip.row ? (
            <>
              <div style={{ color: 'var(--field-light)' }}>
                {tip.row.yield.toFixed(1)} bu/ac
                {stateMedian > 0 && (
                  <span style={{ color: 'var(--text3)' }}>
                    {' '}({((tip.row.yield - stateMedian) / stateMedian * 100 >= 0 ? '+' : '')}
                    {(((tip.row.yield - stateMedian) / stateMedian) * 100).toFixed(1)}%)
                  </span>
                )}
              </div>
              <div style={{ color: 'var(--text3)' }}>Harvested {compact(tip.row.harvested)} ac</div>
              <div style={{ color: 'var(--text3)' }}>Production {compact(tip.row.production)} bu</div>
            </>
          ) : (
            <div style={{ color: 'var(--text3)' }}>No reported data</div>
          )}
        </div>
      )}

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
        <span>−30%</span>
        <span
          style={{
            display: 'inline-block',
            height: 8,
            flex: 1,
            borderRadius: 2,
            background: 'linear-gradient(90deg, #7a2a1e, #3a4a40, #52B788)',
          }}
        />
        <span>+20%</span>
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text3)', marginTop: 6 }}>
        {nReported} of {nTotal} counties reported {year} {commodity.toLowerCase()} yield.
        Gray = no data (NASS suppression / not grown).
      </div>
    </div>
  );
}

// Helper for compacting numbers — kept inside the module to avoid a shared util
function compact(n: number): string {
  if (n == null || isNaN(n)) return '—';
  if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return String(Math.round(n));
}

// Re-export the rollup helper so page.tsx can use it for peers + county drill
export { rollupByCounty };
