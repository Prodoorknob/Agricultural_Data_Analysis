'use client';

import { useCallback, useMemo } from 'react';
import type { Feature, Geometry, Polygon, MultiPolygon, Position } from 'geojson';
import type { CountyCollection, CountyProps, MapMode, Scenario } from './types';
import { BBOX, depColor, project, thicknessAt } from './aquifer-math';

const W = 1000;
const H = 900;

interface ProjectedCounty {
  fips: string;
  props: CountyProps;
  paths: number[][][]; // paths -> rings -> [x,y]
  cx: number;
  cy: number;
}

function ringsOf(geom: Geometry): Position[][] {
  const rings: Position[][] = [];
  if (geom.type === 'Polygon') {
    for (const r of (geom as Polygon).coordinates) rings.push(r);
  } else if (geom.type === 'MultiPolygon') {
    for (const poly of (geom as MultiPolygon).coordinates) for (const r of poly) rings.push(r);
  }
  return rings;
}

function pathD(polys: number[][][]): string {
  let d = '';
  for (const ring of polys) {
    if (!ring.length) continue;
    d += `M${ring[0][0].toFixed(1)},${ring[0][1].toFixed(1)}`;
    for (let i = 1; i < ring.length; i++) d += `L${ring[i][0].toFixed(1)},${ring[i][1].toFixed(1)}`;
    d += 'Z';
  }
  return d;
}

interface Props {
  geo: CountyCollection;
  year: number;
  scenario: Scenario;
  mode: MapMode;
  selected: string | null;
  hovered: string | null;
  onSelect: (fips: string | null) => void;
  onHover: (fips: string | null) => void;
}

export default function CountyMap({
  geo,
  year,
  scenario,
  mode,
  selected,
  hovered,
  onSelect,
  onHover,
}: Props) {
  /* Project every polygon once per geojson; keep paths + centroid. */
  const projected: ProjectedCounty[] = useMemo(() => {
    return geo.features.map((f: Feature<Geometry, CountyProps>) => {
      const paths = ringsOf(f.geometry).map((r) =>
        r.map(([x, y]) => project(x as number, y as number, W, H))
      );
      const [cxP, cyP] = project(f.properties.cx, f.properties.cy, W, H);
      return { fips: f.properties.fips, props: f.properties, paths, cx: cxP, cy: cyP };
    });
  }, [geo]);

  /* State-boundary edge dedup on RAW lon/lat (float-precise). */
  const stateBoundaryD = useMemo(() => {
    const edges = new Map<string, { count: number; states: Set<string>; pts: [Position, Position] }>();
    const key = (a: Position, b: Position) => {
      const ka = (a[0] as number).toFixed(6) + ',' + (a[1] as number).toFixed(6);
      const kb = (b[0] as number).toFixed(6) + ',' + (b[1] as number).toFixed(6);
      return ka < kb ? `${ka}|${kb}` : `${kb}|${ka}`;
    };
    for (const f of geo.features) {
      const st = f.properties.state;
      for (const ring of ringsOf(f.geometry)) {
        for (let i = 0; i < ring.length - 1; i++) {
          const k = key(ring[i], ring[i + 1]);
          const slot = edges.get(k) ?? { count: 0, states: new Set<string>(), pts: [ring[i], ring[i + 1]] };
          slot.count += 1;
          slot.states.add(st);
          edges.set(k, slot);
        }
      }
    }
    let d = '';
    for (const e of edges.values()) {
      const isBoundary = e.states.size > 1 || e.count === 1;
      if (!isBoundary) continue;
      const [ax, ay] = project(e.pts[0][0] as number, e.pts[0][1] as number, W, H);
      const [bx, by] = project(e.pts[1][0] as number, e.pts[1][1] as number, W, H);
      d += `M${ax.toFixed(1)},${ay.toFixed(1)}L${bx.toFixed(1)},${by.toFixed(1)}`;
    }
    return d;
  }, [geo]);

  /* HPA exterior outline: edges that appear exactly once. */
  const hpaOutlineD = useMemo(() => {
    const edges = new Map<string, { count: number; pts: [Position, Position] }>();
    const key = (a: Position, b: Position) => {
      const ka = (a[0] as number).toFixed(6) + ',' + (a[1] as number).toFixed(6);
      const kb = (b[0] as number).toFixed(6) + ',' + (b[1] as number).toFixed(6);
      return ka < kb ? `${ka}|${kb}` : `${kb}|${ka}`;
    };
    for (const f of geo.features) {
      for (const ring of ringsOf(f.geometry)) {
        for (let i = 0; i < ring.length - 1; i++) {
          const k = key(ring[i], ring[i + 1]);
          const slot = edges.get(k) ?? { count: 0, pts: [ring[i], ring[i + 1]] };
          slot.count += 1;
          edges.set(k, slot);
        }
      }
    }
    let d = '';
    for (const e of edges.values()) {
      if (e.count !== 1) continue;
      const [ax, ay] = project(e.pts[0][0] as number, e.pts[0][1] as number, W, H);
      const [bx, by] = project(e.pts[1][0] as number, e.pts[1][1] as number, W, H);
      d += `M${ax.toFixed(1)},${ay.toFixed(1)}L${bx.toFixed(1)},${by.toFixed(1)}`;
    }
    return d;
  }, [geo]);

  const thkAtYear = useCallback((c: CountyProps) => thicknessAt(c, year, scenario), [year, scenario]);

  const sortedForColumns =
    mode === 'columns' ? [...projected].sort((a, b) => a.cy - b.cy) : projected;

  /* State label positions — lon/lat hand-picked in the design. */
  const stateLabels: Array<[string, [number, number]]> = [
    ['NE', [-99.5, 41.5]],
    ['KS', [-98.5, 38.5]],
    ['CO', [-104.5, 39.0]],
    ['TX', [-101.5, 33.5]],
    ['OK', [-99.0, 35.4]],
    ['NM', [-104.3, 34.5]],
    ['SD', [-100.5, 44.3]],
    ['WY', [-104.5, 43.5]],
  ];

  /* Lat/lon grid lines (subtle) — draw from BBOX. */
  const lonLines = Array.from({ length: 14 }, (_, i) => -105 + i);
  const latLines = Array.from({ length: 14 }, (_, i) => 31 + i);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ width: '100%', height: '100%', display: 'block', userSelect: 'none' }}
    >
      <defs>
        <linearGradient id="spike-grad-red" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="#E63946" stopOpacity="0.3" />
          <stop offset="60%" stopColor="#E63946" stopOpacity="0.95" />
          <stop offset="100%" stopColor="#FFE8EC" stopOpacity="1" />
        </linearGradient>
        <linearGradient id="spike-grad-amber" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="#D4A017" stopOpacity="0.3" />
          <stop offset="60%" stopColor="#D4A017" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#FFF6D3" stopOpacity="1" />
        </linearGradient>
        <linearGradient id="spike-grad-green" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="#52B788" stopOpacity="0.3" />
          <stop offset="60%" stopColor="#52B788" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#E8F5EE" stopOpacity="1" />
        </linearGradient>
      </defs>

      {/* Tilted base map (columns mode) */}
      <g
        transform={
          mode === 'columns'
            ? `translate(${W / 2} ${H * 0.62}) scale(1 0.6) translate(${-W / 2} ${-H * 0.62})`
            : ''
        }
      >
        {/* Subtle lat/lon graticule */}
        <g opacity="0.05">
          {lonLines.map((lon) => {
            const [x1] = project(lon, BBOX.minY, W, H);
            const [x2] = project(lon, BBOX.maxY, W, H);
            return <line key={`lon-${lon}`} x1={x1} y1={0} x2={x2} y2={H} stroke="var(--text3)" strokeWidth="0.5" />;
          })}
          {latLines.map((lat) => {
            const [, y1] = project(BBOX.minX, lat, W, H);
            return <line key={`lat-${lat}`} x1={0} y1={y1} x2={W} y2={y1} stroke="var(--text3)" strokeWidth="0.5" />;
          })}
        </g>

        {/* County fills */}
        <g>
          {projected.map((f) => {
            if (mode === 'choropleth') {
              const thk = thkAtYear(f.props);
              const isSel = selected === f.fips;
              const isHov = hovered === f.fips;
              return (
                <path
                  key={f.fips}
                  d={pathD(f.paths)}
                  fill={depColor(thk)}
                  stroke={isSel ? 'var(--text)' : isHov ? 'var(--text2)' : 'transparent'}
                  strokeWidth={isSel ? 1.8 : isHov ? 1.2 : 0}
                  style={{ cursor: 'pointer', transition: 'fill 400ms var(--ease-out)' }}
                  onMouseEnter={() => onHover(f.fips)}
                  onMouseLeave={() => onHover(null)}
                  onClick={() => onSelect(f.fips)}
                />
              );
            }
            const isHigh = f.props.dq === 'modeled_high';
            const isSel = selected === f.fips;
            const isHov = hovered === f.fips;
            return (
              <path
                key={`${f.fips}-base`}
                d={pathD(f.paths)}
                fill={isSel ? 'var(--field-tint)' : isHigh ? 'var(--surface)' : 'var(--surface2)'}
                stroke={isSel ? 'var(--field)' : 'transparent'}
                strokeWidth={isSel ? 1.2 : 0}
                opacity={isSel ? 1 : isHov ? 0.9 : 0.75}
                style={{ cursor: 'pointer' }}
                onMouseEnter={() => onHover(f.fips)}
                onMouseLeave={() => onHover(null)}
                onClick={() => onSelect(f.fips)}
              />
            );
          })}
        </g>

        {/* Interior county borders */}
        <g style={{ pointerEvents: 'none' }} opacity="0.35">
          {projected.map((f) => (
            <path key={`${f.fips}-cb`} d={pathD(f.paths)} fill="none" stroke="var(--border2)" strokeWidth="0.35" />
          ))}
        </g>

        {/* State boundaries */}
        <path
          d={stateBoundaryD}
          fill="none"
          stroke="var(--text)"
          strokeWidth="1.8"
          strokeLinejoin="round"
          strokeLinecap="round"
          opacity="0.85"
          style={{ pointerEvents: 'none' }}
        />
        {/* HPA outline */}
        <path
          d={hpaOutlineD}
          fill="none"
          stroke="var(--field)"
          strokeWidth="2.2"
          strokeLinejoin="round"
          strokeLinecap="round"
          opacity="0.9"
          style={{ pointerEvents: 'none' }}
        />
      </g>

      {/* Spikes (columns mode) — outside tilt group, stay vertical */}
      {mode === 'columns' && (
        <g>
          {sortedForColumns.map((f) => {
            const thk = Math.max(0, thkAtYear(f.props));
            const severity = Math.max(0, Math.min(1, 1 - thk / 60));
            const decline = f.props.dcl || 0;
            const dSev = Math.max(0, Math.min(1, -decline / 1.0));
            const combined = Math.max(severity, dSev);
            if (combined < 0.05) return null;
            const spikeH = 8 + combined * 180;
            const spikeW = Math.max(2, Math.sqrt(f.props.acres + 1) * 0.05);
            const tiltedY = H * 0.62 + (f.cy - H * 0.62) * 0.6;
            const tiltedX = f.cx;
            const isSel = selected === f.fips;
            const isHov = hovered === f.fips;
            const grad =
              combined > 0.55 ? 'url(#spike-grad-red)' :
              combined > 0.25 ? 'url(#spike-grad-amber)' :
              'url(#spike-grad-green)';
            const tipColor = combined > 0.55 ? '#FF4556' : combined > 0.25 ? '#F5C047' : '#74D4A0';
            return (
              <g
                key={f.fips}
                onMouseEnter={() => onHover(f.fips)}
                onMouseLeave={() => onHover(null)}
                onClick={() => onSelect(f.fips)}
                style={{ cursor: 'pointer' }}
              >
                <ellipse
                  cx={tiltedX}
                  cy={tiltedY + 1}
                  rx={spikeW * 1.4}
                  ry={spikeW * 0.45}
                  fill="rgba(0,0,0,0.5)"
                  opacity="0.35"
                />
                <polygon
                  points={`${tiltedX - spikeW},${tiltedY} ${tiltedX + spikeW},${tiltedY} ${tiltedX},${tiltedY - spikeH}`}
                  fill={grad}
                  opacity={isHov || isSel ? 1 : 0.88}
                  style={{ transition: 'opacity 200ms var(--ease-out)' }}
                />
                <circle
                  cx={tiltedX}
                  cy={tiltedY - spikeH}
                  r={Math.max(1.2, spikeW * 0.45)}
                  fill={tipColor}
                  opacity="0.95"
                />
                {isSel && (
                  <g>
                    <line
                      x1={tiltedX}
                      y1={tiltedY - spikeH - 14}
                      x2={tiltedX}
                      y2={tiltedY - spikeH - 4}
                      stroke="var(--text)"
                      strokeWidth="1.5"
                    />
                    <circle cx={tiltedX} cy={tiltedY - spikeH - 18} r="3" fill="var(--text)" />
                  </g>
                )}
              </g>
            );
          })}
        </g>
      )}

      {/* Dots mode */}
      {mode === 'dots' && (
        <g>
          {projected.map((f) => {
            const thk = thkAtYear(f.props);
            const r = Math.max(1.5, Math.sqrt((f.props.pmp || 0) / 1500));
            const isSel = selected === f.fips;
            const isHov = hovered === f.fips;
            return (
              <circle
                key={f.fips}
                cx={f.cx}
                cy={f.cy}
                r={r}
                fill={depColor(thk)}
                fillOpacity={0.75}
                stroke={isSel ? 'var(--text)' : isHov ? 'var(--text2)' : 'rgba(255,255,255,0.3)'}
                strokeWidth={isSel ? 1.8 : isHov ? 1.2 : 0.4}
                style={{ cursor: 'pointer', transition: 'r 400ms var(--ease-out)' }}
                onMouseEnter={() => onHover(f.fips)}
                onMouseLeave={() => onHover(null)}
                onClick={() => onSelect(f.fips)}
              />
            );
          })}
        </g>
      )}

      {/* State labels */}
      <g pointerEvents="none">
        {stateLabels.map(([st, [lon, lat]]) => {
          const [x, yRaw] = project(lon, lat, W, H);
          const y = mode === 'columns' ? H * 0.62 + (yRaw - H * 0.62) * 0.6 : yRaw;
          return (
            <text
              key={st}
              x={x}
              y={y}
              fontFamily="var(--font-stat)"
              fontWeight="800"
              fontSize="20"
              textAnchor="middle"
              fill="var(--text)"
              opacity="0.18"
              letterSpacing="0.08em"
            >
              {st}
            </text>
          );
        })}
      </g>
    </svg>
  );
}
