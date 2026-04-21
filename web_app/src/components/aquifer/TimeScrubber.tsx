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

const years = [1950, 1980, 2000, 2024, 2050, 2075, 2100];

export default function TimeScrubber({ year, onYear, playing, onPlay, counties, scenario }: Props) {
  const trackRef = useRef<HTMLDivElement>(null);

  const handleDown = (e: React.MouseEvent) => {
    const track = trackRef.current;
    if (!track) return;
    const rect = track.getBoundingClientRect();
    const onMove = (ev: MouseEvent) => {
      const x = ev.clientX - rect.left;
      const pct = Math.max(0, Math.min(1, x / rect.width));
      onYear(Math.round(1950 + pct * 150));
    };
    onMove(e.nativeEvent);
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  };

  // Sparkline of regional mean thickness over time — on-HPA counties only.
  const onHpa = counties.filter((c) => c.onHpa && c.thk != null);
  const sparkData: Array<{ y: number; v: number }> = [];
  for (let y = 1950; y <= 2100; y += 5) {
    let sum = 0;
    for (const c of onHpa) sum += Math.max(0, thicknessAt(c, y, scenario));
    sparkData.push({ y, v: onHpa.length ? sum / onHpa.length : 0 });
  }
  const maxV = Math.max(...sparkData.map((d) => d.v), 1);
  const sparkW = 720, sparkH = 34;
  const pct = (year - 1950) / 150;

  const desc =
    year < 1960 ? 'Pre-center-pivot era — aquifer near pristine baseline' :
    year < 1980 ? 'Center-pivot irrigation spreads across the High Plains' :
    year < 2000 ? 'Peak pumping decades — extraction outpaces recharge 10×' :
    year <= 2024 ? `Measured present — ${onHpa.length} HPA counties ground-truthed` :
    year <= 2050 ? 'Projected · scenario-driven' :
                   'Long-horizon projection · uncertainty grows';

  return (
    <div className="scrubber" style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
      padding: '18px 24px 28px',
    }}>
      <div className="scrubber-head" style={{ display: 'flex', alignItems: 'center', gap: 20, marginBottom: 16 }}>
        <button
          onClick={onPlay}
          aria-label={playing ? 'pause' : 'play'}
          style={{
            width: 42, height: 42, borderRadius: '50%',
            background: 'var(--field)', color: 'var(--bg)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            border: 'none', cursor: 'pointer',
          }}
        >
          {playing ? (
            <svg width="14" height="14" viewBox="0 0 14 14">
              <rect x="3" y="2" width="3" height="10" fill="currentColor" />
              <rect x="8" y="2" width="3" height="10" fill="currentColor" />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 14 14">
              <path d="M3 2 L12 7 L3 12 Z" fill="currentColor" />
            </svg>
          )}
        </button>
        <div>
          <div className="eyebrow">Year</div>
          <div className="stat" style={{ fontSize: 34, fontWeight: 800, lineHeight: 1, color: 'var(--text)', letterSpacing: '-0.01em' }}>{year}</div>
        </div>
        <div style={{ flex: 1, fontSize: 13, color: 'var(--text2)', fontStyle: 'italic', textAlign: 'right', maxWidth: 480, marginLeft: 'auto' }}>
          {desc}
        </div>
      </div>
      <div style={{ position: 'relative' }}>
        <svg viewBox={`0 0 ${sparkW} ${sparkH}`} preserveAspectRatio="none" style={{ display: 'block', width: '100%', height: 34, marginBottom: 4 }}>
          <path
            d={
              'M0,' + sparkH + ' ' +
              sparkData.map((d, i) => `L${(i / (sparkData.length - 1)) * sparkW},${sparkH - (d.v / maxV) * sparkH}`).join(' ') +
              ` L${sparkW},${sparkH} Z`
            }
            fill="var(--field-tint)"
            stroke="none"
          />
          <path
            d={sparkData.map((d, i) => `${i === 0 ? 'M' : 'L'}${(i / (sparkData.length - 1)) * sparkW},${sparkH - (d.v / maxV) * sparkH}`).join(' ')}
            fill="none"
            stroke="var(--field)"
            strokeWidth="1.5"
          />
          <line x1={pct * sparkW} y1="0" x2={pct * sparkW} y2={sparkH} stroke="var(--text)" strokeWidth="1.2" />
        </svg>
        <div
          ref={trackRef}
          onMouseDown={handleDown}
          style={{
            position: 'relative', height: 32, cursor: 'pointer',
            background: 'var(--surface2)',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border)',
            marginTop: 8,
          }}
        >
          <div
            style={{
              position: 'absolute', top: 0, left: 0, height: '100%',
              width: `${pct * 100}%`,
              background: 'linear-gradient(to right, var(--dep-9), var(--dep-5))',
              borderRadius: 'var(--radius-sm) 0 0 var(--radius-sm)',
              pointerEvents: 'none',
              opacity: 0.35,
            }}
          />
          <div
            style={{
              position: 'absolute', top: '50%', left: `${pct * 100}%`,
              width: 14, height: 38,
              background: 'var(--text)', borderRadius: 3,
              transform: 'translate(-50%, -50%)',
              boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
              pointerEvents: 'none',
            }}
          />
          {years.map((y) => (
            <div
              key={y}
              style={{ position: 'absolute', top: 0, transform: 'translateX(-50%)', pointerEvents: 'none', left: `${((y - 1950) / 150) * 100}%` }}
            >
              <div style={{ width: 1, height: 8, background: 'var(--text3)' }} />
              <div className="mono" style={{ fontSize: 10, color: 'var(--text3)', marginTop: 12 }}>{y}</div>
            </div>
          ))}
          <div
            style={{ position: 'absolute', top: -4, transform: 'translateX(-50%)', pointerEvents: 'none', left: `${((2024 - 1950) / 150) * 100}%` }}
          >
            <div style={{ width: 2, height: 40, background: 'var(--harvest)', margin: '0 auto' }} />
            <div className="mono" style={{ fontSize: 9, color: 'var(--harvest)', textTransform: 'uppercase', letterSpacing: '0.1em', marginTop: 4, whiteSpace: 'nowrap' }}>
              measured · 2024
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
