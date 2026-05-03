'use client';

import type { CountyProps, Scenario } from './types';
import { physicalThicknessAt, fmt } from './aquifer-math';

interface Props {
  county: CountyProps;
  year: number;
  scenario: Scenario;
}

/**
 * Vertical water-tank gauge for the selected county.
 *
 * Container height represents the county's predevelopment (1950) saturated
 * thickness — the "full" aquifer. Fill level = current-year thickness under
 * the active scenario. The dotted line marks the optimum threshold (half
 * the predev thickness, a HPA sustainability heuristic). Below optimum the
 * water turns red; at or above it stays in the blue family with a deeper
 * shade the further above optimum the level sits.
 */
export default function WaterColumn({ county, year, scenario }: Props) {
  // Container = the 2024 measured saturated thickness (`c.thk`). Water level
  // is the scenario-projected thickness for the selected year, clamped to the
  // container so historical scrubbing doesn't visually overflow. Optimum is a
  // sustainability heuristic — 50% of baseline, floored at the 9 m uneconomic
  // line so it never sits below the "county can't pump" threshold.
  const baseline = Math.max(1, county.thk ?? 1);
  const thkNow = Math.min(baseline, Math.max(0, physicalThicknessAt(county, year, scenario)));
  const optimum = Math.max(9, baseline * 0.5);

  const fillPct = thkNow / baseline;
  const optPct = Math.min(1, optimum / baseline);

  // Distance above (or below) optimum, normalized for a smooth color ramp.
  const aboveOpt = thkNow >= optimum;
  // 0 → just at optimum; 1 → at baseline (saturated)
  const headroom = Math.max(0, Math.min(1, (thkNow - optimum) / Math.max(1, baseline - optimum)));
  // 0 → just at optimum; 1 → fully drained
  const deficit  = Math.max(0, Math.min(1, (optimum - thkNow) / Math.max(1, optimum)));

  const fillTop    = aboveOpt
    ? mix('#5B9BD5', '#1B4F84', headroom)  // sky → deep blue
    : mix('#E05A4A', '#7A1F12', deficit);  // soft red → dark red
  const fillBottom = aboveOpt
    ? mix('#1B4F84', '#0B2A4A', headroom)
    : mix('#7A1F12', '#3F0E07', deficit);

  // Layout — a square card holding a centered column.
  const W = 200, H = 200;
  const colW = 84, colH = 156;
  const colX = (W - colW) / 2;
  const colY = 22;

  const waterH = colH * fillPct;
  const waterY = colY + (colH - waterH);
  const optY   = colY + colH * (1 - optPct);

  const status: { label: string; color: string } =
    aboveOpt
      ? headroom > 0.5
        ? { label: 'Healthy',     color: 'var(--sky)' }
        : { label: 'Stressed',    color: 'var(--sky)' }
      : deficit > 0.6
        ? { label: 'Critical',    color: 'var(--negative)' }
        : { label: 'Below optimum', color: 'var(--negative)' };

  return (
    <div data-drill-section="water-column">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
        <div className="eyebrow">Aquifer column · {year}</div>
        <span
          className="mono"
          style={{
            fontSize: 9, padding: '2px 6px', borderRadius: 3,
            color: status.color, border: `1px solid ${status.color}`,
            textTransform: 'uppercase', letterSpacing: '0.08em',
          }}
        >
          {status.label}
        </span>
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: `${W}px 1fr`,
          gap: 12,
          background: 'var(--surface2)',
          borderRadius: 'var(--radius-sm)',
          padding: 10,
        }}
      >
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: W, height: H }}>
          <defs>
            <linearGradient id="aw-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={fillTop} />
              <stop offset="100%" stopColor={fillBottom} />
            </linearGradient>
            <clipPath id="aw-clip">
              <rect x={colX} y={colY} width={colW} height={colH} rx="3" />
            </clipPath>
          </defs>

          {/* Container chrome */}
          <rect
            x={colX} y={colY} width={colW} height={colH} rx="3"
            fill="var(--surface)" stroke="var(--border2)" strokeWidth="1.2"
          />

          {/* Water (clipped to container so corners stay rounded) */}
          <g clipPath="url(#aw-clip)">
            <rect
              x={colX} y={waterY} width={colW} height={waterH}
              fill="url(#aw-fill)"
            />
            {/* Subtle surface highlight so it reads as liquid, not a solid bar */}
            <rect
              x={colX} y={waterY} width={colW} height={Math.min(3, waterH)}
              fill="rgba(255,255,255,0.25)"
            />
          </g>

          {/* Optimum line — dotted, drawn over both empty + filled regions */}
          <line
            x1={colX - 6} x2={colX + colW + 6}
            y1={optY} y2={optY}
            stroke="var(--text2)"
            strokeWidth="1"
            strokeDasharray="3 3"
            opacity="0.85"
          />
          <text
            x={colX + colW + 8} y={optY + 3}
            fontSize="9" fontFamily="var(--font-mono)" fill="var(--text2)"
          >
            optimum
          </text>
          <text
            x={colX + colW + 8} y={optY + 14}
            fontSize="9" fontFamily="var(--font-mono)" fill="var(--text3)"
          >
            {optimum.toFixed(0)} m
          </text>

          {/* Top tick = predev thickness */}
          <line
            x1={colX - 4} x2={colX} y1={colY} y2={colY}
            stroke="var(--text3)" strokeWidth="1"
          />
          <text
            x={colX - 6} y={colY + 3}
            fontSize="9" fontFamily="var(--font-mono)" fill="var(--text3)"
            textAnchor="end"
          >
            {baseline.toFixed(0)}m
          </text>

          {/* Bottom tick = 0 m */}
          <line
            x1={colX - 4} x2={colX} y1={colY + colH} y2={colY + colH}
            stroke="var(--text3)" strokeWidth="1"
          />
          <text
            x={colX - 6} y={colY + colH + 3}
            fontSize="9" fontFamily="var(--font-mono)" fill="var(--text3)"
            textAnchor="end"
          >
            0
          </text>

          {/* Now-level callout */}
          <text
            x={colX + colW / 2}
            y={waterY - 5}
            fontSize="11" fontFamily="var(--font-mono)" fontWeight="700"
            fill="var(--text)" textAnchor="middle"
            opacity={waterY - colY > 12 ? 1 : 0}
          >
            {thkNow.toFixed(1)} m
          </text>
        </svg>

        <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'space-between', padding: '4px 0', minWidth: 0 }}>
          <Stat label="Now" value={fmt.m(thkNow)} accent={status.color} />
          <Stat label="Optimum" value={fmt.m(optimum)} mono />
          <Stat label="Baseline (2024)" value={fmt.m(baseline)} mono />
          <Stat
            label="vs. optimum"
            value={`${(((thkNow - optimum) / optimum) * 100).toFixed(0)}%`}
            accent={status.color}
          />
        </div>
      </div>
      <div className="mono" style={{ fontSize: 9, color: 'var(--text3)', marginTop: 6, lineHeight: 1.5 }}>
        Container = 2024 measured saturated thickness. Optimum = 50% of baseline,
        floored at the 9 m uneconomic line. Fill = scenario-projected thickness for {year}.
      </div>
    </div>
  );
}

function Stat({ label, value, accent, mono }: { label: string; value: string; accent?: string; mono?: boolean }) {
  return (
    <div>
      <div
        style={{
          fontSize: 9, color: 'var(--text3)',
          textTransform: 'uppercase', letterSpacing: '0.08em',
        }}
      >
        {label}
      </div>
      <div
        className={mono ? 'mono' : undefined}
        style={{
          fontSize: 14, fontWeight: 700, marginTop: 2,
          color: accent || 'var(--text)',
        }}
      >
        {value}
      </div>
    </div>
  );
}

/** Linear-interpolate two hex colors. t ∈ [0,1]. */
function mix(a: string, b: string, t: number): string {
  const ha = hex(a), hb = hex(b);
  const r = Math.round(ha[0] + (hb[0] - ha[0]) * t);
  const g = Math.round(ha[1] + (hb[1] - ha[1]) * t);
  const bl = Math.round(ha[2] + (hb[2] - ha[2]) * t);
  return `rgb(${r},${g},${bl})`;
}
function hex(s: string): [number, number, number] {
  const v = s.replace('#', '');
  return [parseInt(v.slice(0, 2), 16), parseInt(v.slice(2, 4), 16), parseInt(v.slice(4, 6), 16)];
}
