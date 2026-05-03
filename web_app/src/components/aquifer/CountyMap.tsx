'use client';

import { useCallback, useMemo } from 'react';
import type { Feature, Geometry, Polygon, MultiPolygon, Position } from 'geojson';
import type { CountyCollection, CountyProps, MapMode, Scenario } from './types';
import { BBOX, depColor, physicalThicknessAt, project, thicknessAt } from './aquifer-math';

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
  /** When true and `bauScenario` is provided, county fills use a
   *  red-neutral-green delta-vs-BAU ramp instead of absolute thickness. */
  deltaMode?: boolean;
  bauScenario?: Scenario;
}

/** Red → neutral → green ramp for scenario-vs-BAU thickness delta (m). */
function deltaColor(d: number): string {
  const clamped = Math.max(-1, Math.min(1, d / 15));
  if (clamped < -0.02) {
    const t = Math.min(1, Math.abs(clamped));
    return `color-mix(in oklab, var(--negative) ${Math.round(t * 75)}%, var(--surface2))`;
  }
  if (clamped > 0.02) {
    const t = Math.min(1, clamped);
    return `color-mix(in oklab, var(--positive) ${Math.round(t * 75)}%, var(--surface2))`;
  }
  return 'var(--surface2)';
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
  deltaMode = false,
  bauScenario,
}: Props) {
  const useDelta = deltaMode && bauScenario != null;
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

  /* HPA exterior outline: dissolve the on-aquifer counties into a single
     polygon and extract its boundary. "Boundary" = edges that appear an
     odd number of times across aquifer-county polygons (the even ones are
     internal). Uses hpa_overlap_pct > 0 counties only — without this the
     "outline" is really just the HPA-state outline. */
  const hpaOutlineD = useMemo(() => {
    const edges = new Map<string, { count: number; pts: [Position, Position] }>();
    const key = (a: Position, b: Position) => {
      const ka = (a[0] as number).toFixed(6) + ',' + (a[1] as number).toFixed(6);
      const kb = (b[0] as number).toFixed(6) + ',' + (b[1] as number).toFixed(6);
      return ka < kb ? `${ka}|${kb}` : `${kb}|${ka}`;
    };
    for (const f of geo.features) {
      if (!f.properties.onHpa) continue;
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
      if (e.count % 2 === 0) continue;
      const [ax, ay] = project(e.pts[0][0] as number, e.pts[0][1] as number, W, H);
      const [bx, by] = project(e.pts[1][0] as number, e.pts[1][1] as number, W, H);
      d += `M${ax.toFixed(1)},${ay.toFixed(1)}L${bx.toFixed(1)},${by.toFixed(1)}`;
    }
    return d;
  }, [geo]);

  const thkAtYear = useCallback((c: CountyProps) => thicknessAt(c, year, scenario), [year, scenario]);
  const deltaAtYear = useCallback(
    (c: CountyProps) => {
      if (!useDelta || !bauScenario) return 0;
      return thicknessAt(c, year, scenario) - thicknessAt(c, year, bauScenario);
    },
    [useDelta, bauScenario, year, scenario],
  );

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
        {/* Water-fill gradients — bottom darker, top brighter so the surface
            catches a highlight, like the cone gradients did at their tips. */}
        <linearGradient id="water-blue" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%"   stopColor="#0F2F52" stopOpacity="0.85" />
          <stop offset="60%"  stopColor="#1F4E80" stopOpacity="0.92" />
          <stop offset="100%" stopColor="#5B9BD5" stopOpacity="1" />
        </linearGradient>
        <linearGradient id="water-red" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%"   stopColor="#4A130C" stopOpacity="0.85" />
          <stop offset="60%"  stopColor="#7A1F12" stopOpacity="0.92" />
          <stop offset="100%" stopColor="#E05A4A" stopOpacity="1" />
        </linearGradient>
        <filter id="lift-shadow" x="-30%" y="-30%" width="160%" height="160%">
          <feDropShadow dx="0" dy="3" stdDeviation="3.5" floodColor="#000" floodOpacity="0.42" />
        </filter>
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

        {/* County fills — off-HPA counties render as flat gray tiles with
            no interaction, so the choropleth story stays on the aquifer. */}
        <g>
          {projected.map((f) => {
            const off = !f.props.onHpa;
            if (off) {
              return (
                <path
                  key={`${f.fips}-off`}
                  d={pathD(f.paths)}
                  fill="var(--surface2)"
                  opacity={0.35}
                  stroke="transparent"
                  strokeWidth={0}
                  style={{ pointerEvents: 'none' }}
                />
              );
            }
            if (mode === 'choropleth') {
              const thk = thkAtYear(f.props);
              const fillColor = useDelta ? deltaColor(deltaAtYear(f.props)) : depColor(thk);
              const isSel = selected === f.fips;
              const isHov = hovered === f.fips;
              return (
                <path
                  key={f.fips}
                  data-fips={f.fips}
                  d={pathD(f.paths)}
                  fill={fillColor}
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
            // In columns/bubbles mode, when delta overlay is active, tint
            // the county fill by delta so the scenario story reads even
            // through the spikes/dots on top.
            const baseFill = useDelta
              ? deltaColor(deltaAtYear(f.props))
              : isSel
                ? 'var(--field-tint)'
                : isHigh
                  ? 'var(--surface)'
                  : 'var(--surface2)';
            return (
              <path
                key={`${f.fips}-base`}
                data-fips={f.fips}
                d={pathD(f.paths)}
                fill={baseFill}
                stroke={isSel ? 'var(--field)' : 'transparent'}
                strokeWidth={isSel ? 1.2 : 0}
                opacity={isSel ? 1 : isHov ? 0.9 : useDelta ? 0.9 : 0.75}
                style={{ cursor: 'pointer', transition: 'fill 400ms var(--ease-out)' }}
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

      {/* 3-D water columns (columns mode) — outside tilt group, stay vertical.
          Each county renders as a transparent glass tank with water filled
          inside. Container height scales mildly by acres (so big-ag counties
          stand out) but stays in a tight range so tanks read as comparable.
          Water fill = current thickness / baseline (matches WaterColumn
          panel); color is blue gradient when above the optimum line, red
          gradient below. Optimum = max(9 m, 50% of baseline). */}
      {mode === 'columns' && (
        <g>
          {sortedForColumns.map((f) => {
            if (!f.props.onHpa) return null;
            const baseline = Math.max(1, f.props.thk ?? 0);
            const thk = Math.max(0, Math.min(baseline, physicalThicknessAt(f.props, year, scenario)));
            const optimum = Math.max(9, baseline * 0.5);
            const aboveOpt = thk >= optimum;
            const fillPct = thk / baseline;
            const optPct = Math.min(1, optimum / baseline);

            // Mildly acres-scaled tank size, kept in a comfortable range so
            // tanks compare apples-to-apples across the map.
            const acresScale = Math.sqrt(f.props.acres + 1);
            const colW = Math.max(2.6, Math.min(8, 2.6 + acresScale * 0.025));
            const colH = Math.max(28, Math.min(64, 28 + acresScale * 0.18));
            const dx = colW * 0.55;
            const dy = colW * 0.32;

            const tiltedY = H * 0.62 + (f.cy - H * 0.62) * 0.6;
            const tiltedX = f.cx;
            const isSel = selected === f.fips;
            const isHov = hovered === f.fips;

            // Container corners (front face + back face, axonometric).
            const fl = tiltedX - colW, fr = tiltedX + colW;
            const yb = tiltedY,        yt = tiltedY - colH;
            const bl = fl + dx, br = fr + dx;
            const yBb = yb - dy, yBt = yt - dy;

            // Water surface y-coordinates (front + back).
            const waterH = colH * fillPct;
            const ywF = yb - waterH;
            const ywB = ywF - dy;
            const yOptF = yb - colH * optPct;

            // Container = transparent cyan wireframe. Water = saturated
            // gradient that reads cleanly against the muted base map.
            const tankStroke = isSel ? '#9BE2FF' : isHov ? '#7DD3FC' : '#7DD3FC';
            const tankOpacity = isSel ? 1 : isHov ? 1 : 0.78;
            const waterFill = aboveOpt ? 'url(#water-blue)' : 'url(#water-red)';
            const waterSide = aboveOpt ? '#0F2F52' : '#4A130C';
            const waterTop  = aboveOpt ? '#7DB6E0' : '#F08070';

            // Per-county clip — keeps the water box's right & top faces
            // from poking through neighbouring tanks at extreme zooms.
            const clipId = `tank-clip-${f.fips}`;

            return (
              <g
                key={f.fips}
                data-fips={f.fips}
                onMouseEnter={() => onHover(f.fips)}
                onMouseLeave={() => onHover(null)}
                onClick={() => onSelect(f.fips)}
                style={{ cursor: 'pointer' }}
              >
                <defs>
                  <clipPath id={clipId}>
                    {/* Composite of the three visible tank faces */}
                    <polygon points={`${fl},${yb} ${fr},${yb} ${br},${yBb} ${br},${yBt} ${bl},${yBt} ${fl},${yt}`} />
                  </clipPath>
                </defs>

                {/* Ground shadow */}
                <ellipse
                  cx={tiltedX + dx * 0.5}
                  cy={tiltedY + 1}
                  rx={colW * 1.7}
                  ry={colW * 0.55}
                  fill="rgba(0,0,0,0.5)"
                  opacity="0.28"
                />

                {/* Subtle "empty glass" fill so the tank reads as a vessel
                    even when nearly drained */}
                <polygon
                  points={`${fl},${yb} ${fr},${yb} ${br},${yBb} ${br},${yBt} ${bl},${yBt} ${fl},${yt}`}
                  fill="rgba(125, 211, 252, 0.08)"
                  pointerEvents="none"
                />

                {/* Water (clipped to tank silhouette so faces stay tidy) */}
                {waterH > 0.4 && (
                  <g clipPath={`url(#${clipId})`}>
                    {/* Right face of water */}
                    <polygon
                      points={`${fr},${yb} ${br},${yBb} ${br},${ywB} ${fr},${ywF}`}
                      fill={waterSide}
                      opacity="0.7"
                    />
                    {/* Water surface (top face of water box) */}
                    <polygon
                      points={`${fl},${ywF} ${fr},${ywF} ${br},${ywB} ${bl},${ywB}`}
                      fill={waterTop}
                      opacity="0.92"
                    />
                    {/* Front face of water */}
                    <rect
                      x={fl}
                      y={ywF}
                      width={colW * 2}
                      height={waterH}
                      fill={waterFill}
                    />
                    {/* Subtle surface highlight band */}
                    <rect
                      x={fl}
                      y={ywF}
                      width={colW * 2}
                      height={Math.min(1.4, waterH * 0.2)}
                      fill="rgba(255,255,255,0.35)"
                    />
                  </g>
                )}

                {/* Optimum dashed line on the front face */}
                <line
                  x1={fl - 0.6}
                  x2={fr + 0.6}
                  y1={yOptF}
                  y2={yOptF}
                  stroke="rgba(255,255,255,0.65)"
                  strokeWidth="0.55"
                  strokeDasharray="1.6 1.4"
                  opacity={isHov || isSel ? 1 : 0.75}
                  pointerEvents="none"
                />

                {/* Container wireframe — drawn last so the glass edges sit on top */}
                <g
                  fill="none"
                  stroke={tankStroke}
                  strokeWidth={isSel ? 1.4 : isHov ? 1.2 : 1.0}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  opacity={tankOpacity}
                  pointerEvents="none"
                >
                  {/* Front face */}
                  <rect x={fl} y={yt} width={colW * 2} height={colH} />
                  {/* Top face (parallelogram) */}
                  <polygon points={`${fl},${yt} ${fr},${yt} ${br},${yBt} ${bl},${yBt}`} />
                  {/* Right (side) face */}
                  <polygon points={`${fr},${yb} ${br},${yBb} ${br},${yBt} ${fr},${yt}`} />
                </g>

                {/* Invisible hit-target so thin tanks are still easy to click */}
                <rect
                  x={fl - 1.5}
                  y={yt - 2}
                  width={colW * 2 + dx + 3}
                  height={colH + dy + 4}
                  fill="transparent"
                />

                {/* Selection callout — vertical pin above the column */}
                {isSel && (
                  <g pointerEvents="none">
                    <line
                      x1={tiltedX}
                      y1={yt - 14}
                      x2={tiltedX}
                      y2={yt - 4}
                      stroke="var(--text)"
                      strokeWidth="1.5"
                    />
                    <circle cx={tiltedX} cy={yt - 18} r="3" fill="var(--text)" />
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
            if (!f.props.onHpa) return null;
            const thk = thkAtYear(f.props);
            const r = Math.max(1.5, Math.sqrt((f.props.pmp || 0) / 1500));
            const isSel = selected === f.fips;
            const isHov = hovered === f.fips;
            return (
              <circle
                key={f.fips}
                data-fips={f.fips}
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

      {/* Lifted selected county — render on top with drop shadow + slight
          scale around its centroid, so the chosen county "pops out" of the
          base layer without losing its geographic context. */}
      {selected && (() => {
        const sel = projected.find((f) => f.fips === selected);
        if (!sel || !sel.props.onHpa) return null;
        const tilted = mode === 'columns';
        const baseTx = tilted
          ? `translate(${W / 2} ${H * 0.62}) scale(1 0.6) translate(${-W / 2} ${-H * 0.62})`
          : '';
        const liftScale = 1.08;
        const fillColor = useDelta
          ? deltaColor(deltaAtYear(sel.props))
          : mode === 'choropleth'
            ? depColor(thkAtYear(sel.props))
            : 'var(--field-tint)';
        return (
          <g transform={baseTx} pointerEvents="none">
            <g
              transform={`translate(${sel.cx} ${sel.cy}) scale(${liftScale}) translate(${-sel.cx} ${-sel.cy})`}
              style={{ transition: 'transform 250ms var(--ease-out)' }}
            >
              <path
                d={pathD(sel.paths)}
                fill={fillColor}
                stroke="var(--text)"
                strokeWidth="1.8"
                filter="url(#lift-shadow)"
              />
            </g>
          </g>
        );
      })()}

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
