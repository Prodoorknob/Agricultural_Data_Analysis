'use client';

import { useRef } from 'react';
import type { CountyProps, Scenario } from './types';
import { thicknessAt } from './aquifer-math';

interface Props {
  year: number;
  onYear: (y: number) => void;
  playing: boolean;
  onPlay: () => void;
  counties: CountyProps[];
  scenario: Scenario;
}

const YEAR_MIN = 1950;
const YEAR_MAX = 2100;
const YEAR_SPAN = YEAR_MAX - YEAR_MIN;
const TICKS = [1950, 1980, 2000, 2024, 2050, 2075, 2100];

export default function VerticalTimeScrubber({
  year,
  onYear,
  playing,
  onPlay,
  counties,
  scenario,
}: Props) {
  const trackRef = useRef<HTMLDivElement>(null);

  const handleDown = (e: React.MouseEvent) => {
    const track = trackRef.current;
    if (!track) return;
    const rect = track.getBoundingClientRect();
    const onMove = (ev: MouseEvent) => {
      const y = ev.clientY - rect.top;
      const pct = Math.max(0, Math.min(1, y / rect.height));
      onYear(Math.round(YEAR_MIN + pct * YEAR_SPAN));
    };
    onMove(e.nativeEvent);
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  };

  // Vertical sparkline — regional mean thickness over 1950→2100, on-HPA only.
  const onHpa = counties.filter((c) => c.onHpa && c.thk != null);
  const sparkData: Array<{ y: number; v: number }> = [];
  for (let y = YEAR_MIN; y <= YEAR_MAX; y += 5) {
    let sum = 0;
    for (const c of onHpa) sum += Math.max(0, thicknessAt(c, y, scenario));
    sparkData.push({ y, v: onHpa.length ? sum / onHpa.length : 0 });
  }
  const maxV = Math.max(...sparkData.map((d) => d.v), 1);

  // SVG: x = thickness (0 → maxV), y = year (0 top → 1 bottom).
  // Track is visually vertical; sparkline draws as the track's background.
  const SW = 44; // spark-width (px) — width of the sparkline area
  const SH = 100; // viewBox height units
  const pct = (year - YEAR_MIN) / YEAR_SPAN;

  const desc =
    year < 1960 ? 'Pre-center-pivot · near pristine baseline' :
    year < 1980 ? 'Center-pivot spreads across High Plains' :
    year < 2000 ? 'Peak pumping · extraction 10× recharge' :
    year <= 2024 ? `Measured · ${onHpa.length} counties ground-truthed` :
    year <= 2050 ? 'Projected · scenario-driven' :
                   'Long-horizon · uncertainty grows';

  return (
    <div
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        padding: '14px 10px 18px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 10,
        height: '100%',
      }}
    >
      <div className="eyebrow" style={{ textAlign: 'center' }}>Year</div>
      <div
        className="stat"
        style={{
          fontSize: 26,
          fontWeight: 800,
          lineHeight: 1,
          color: 'var(--text)',
          letterSpacing: '-0.01em',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {year}
      </div>
      <button
        onClick={onPlay}
        aria-label={playing ? 'pause' : 'play'}
        style={{
          width: 36,
          height: 36,
          borderRadius: '50%',
          background: 'var(--field)',
          color: 'var(--bg)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: 'none',
          cursor: 'pointer',
          flexShrink: 0,
        }}
      >
        {playing ? (
          <svg width="12" height="12" viewBox="0 0 14 14">
            <rect x="3" y="2" width="3" height="10" fill="currentColor" />
            <rect x="8" y="2" width="3" height="10" fill="currentColor" />
          </svg>
        ) : (
          <svg width="12" height="12" viewBox="0 0 14 14">
            <path d="M3 2 L12 7 L3 12 Z" fill="currentColor" />
          </svg>
        )}
      </button>

      {/* Track + sparkline + tick labels */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'auto auto',
          gap: 6,
          flex: 1,
          minHeight: 420,
          alignItems: 'stretch',
        }}
      >
        <div
          ref={trackRef}
          onMouseDown={handleDown}
          style={{
            position: 'relative',
            width: SW,
            cursor: 'pointer',
            background: 'var(--surface2)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border)',
            overflow: 'hidden',
          }}
        >
          {/* Sparkline (thickness area), drawn with x = thickness, y = year */}
          <svg
            viewBox={`0 0 ${SW} ${SH}`}
            preserveAspectRatio="none"
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
          >
            <path
              d={
                `M0,0 ` +
                sparkData
                  .map(
                    (d, i) =>
                      `L${((d.v / maxV) * SW).toFixed(2)},${((i / (sparkData.length - 1)) * SH).toFixed(2)}`,
                  )
                  .join(' ') +
                ` L0,${SH} Z`
              }
              fill="var(--field-tint)"
              stroke="none"
            />
            <path
              d={sparkData
                .map(
                  (d, i) =>
                    `${i === 0 ? 'M' : 'L'}${((d.v / maxV) * SW).toFixed(2)},${((i / (sparkData.length - 1)) * SH).toFixed(2)}`,
                )
                .join(' ')}
              fill="none"
              stroke="var(--field)"
              strokeWidth="1.5"
              vectorEffect="non-scaling-stroke"
            />
          </svg>

          {/* Progress tint from top down to current year */}
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              height: `${pct * 100}%`,
              background: 'linear-gradient(to bottom, var(--dep-9), var(--dep-5))',
              opacity: 0.22,
              pointerEvents: 'none',
            }}
          />

          {/* 2024 "measured" marker — horizontal harvest-colored line */}
          <div
            style={{
              position: 'absolute',
              left: 0,
              right: 0,
              top: `${((2024 - YEAR_MIN) / YEAR_SPAN) * 100}%`,
              height: 2,
              background: 'var(--harvest)',
              pointerEvents: 'none',
            }}
          />

          {/* Thumb */}
          <div
            style={{
              position: 'absolute',
              top: `${pct * 100}%`,
              left: -3,
              right: -3,
              height: 12,
              transform: 'translateY(-50%)',
              background: 'var(--text)',
              borderRadius: 3,
              boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
              pointerEvents: 'none',
            }}
          />
        </div>

        {/* Year tick labels (right column) */}
        <div style={{ position: 'relative', width: 34 }}>
          {TICKS.map((y) => {
            const top = ((y - YEAR_MIN) / YEAR_SPAN) * 100;
            const isMeasured = y === 2024;
            return (
              <div
                key={y}
                style={{
                  position: 'absolute',
                  top: `${top}%`,
                  left: 0,
                  right: 0,
                  transform: 'translateY(-50%)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 3,
                  pointerEvents: 'none',
                }}
              >
                <div style={{ width: 4, height: 1, background: 'var(--text3)' }} />
                <div
                  className="mono"
                  style={{
                    fontSize: 9,
                    color: isMeasured ? 'var(--harvest)' : 'var(--text3)',
                    fontWeight: isMeasured ? 700 : 500,
                    letterSpacing: '0.04em',
                  }}
                >
                  {y}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div
        style={{
          fontSize: 10,
          color: 'var(--text2)',
          fontStyle: 'italic',
          textAlign: 'center',
          lineHeight: 1.4,
          padding: '0 2px',
        }}
      >
        {desc}
      </div>
    </div>
  );
}
