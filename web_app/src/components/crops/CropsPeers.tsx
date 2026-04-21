'use client';

import { useMemo } from 'react';
import type { CountyRollup } from './CropsStateMap';

interface Props {
  rollup: Map<string, CountyRollup>;
  mode: 'state' | 'county';
  selectedFips: string | null;
  onCountyClick: (fips: string) => void;
}

function titleCase(s: string): string {
  return String(s).toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}

/**
 * Peers card — the narrow content that sits below the map in the inverted-L
 * left column, or full-width underneath in county mode.
 * - State mode: top-5 / bottom-3 counties by yield
 * - County mode: 6 nearest-yield peers to the selected county
 */
export default function CropsPeers({ rollup, mode, selectedFips, onCountyClick }: Props) {
  const rows = useMemo(() => Array.from(rollup.values()).filter((r) => r.yield > 0), [rollup]);

  if (rows.length === 0) return null;

  if (mode === 'county' && selectedFips) {
    const self = rollup.get(selectedFips);
    if (!self) return null;
    const peers = rows
      .filter((r) => r.fips !== selectedFips)
      .sort((a, b) => Math.abs(a.yield - self.yield) - Math.abs(b.yield - self.yield))
      .slice(0, 6);
    return (
      <div>
        <div
          style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.08em',
            color: 'var(--text3)', textTransform: 'uppercase', marginBottom: 8,
          }}
        >
          Nearest peers · closest yield to {titleCase(self.county)}
        </div>
        <div style={{ background: 'var(--surface2)', borderRadius: 'var(--radius-md)', padding: '12px 14px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
            <thead>
              <tr>
                <th style={thStyle}>County</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>Yield</th>
                <th style={{ ...thStyle, textAlign: 'right' }}>Δ</th>
              </tr>
            </thead>
            <tbody>
              {peers.map((p) => {
                const d = p.yield - self.yield;
                const color = d >= 0 ? 'var(--field)' : 'var(--negative)';
                return (
                  <tr key={p.fips}
                      onClick={() => onCountyClick(p.fips)}
                      style={{ cursor: 'pointer' }}>
                    <td style={tdStyle}>{titleCase(p.county)}</td>
                    <td style={{ ...tdStyle, textAlign: 'right', color: 'var(--text2)' }}>{p.yield.toFixed(1)}</td>
                    <td style={{ ...tdStyle, textAlign: 'right', color, fontWeight: 600 }}>
                      {d >= 0 ? '+' : ''}{d.toFixed(1)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div
          style={{
            fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text3)',
            marginTop: 10, lineHeight: 1.5,
          }}
        >
          Ranked by absolute yield distance — spatial neighbors can differ.
        </div>
      </div>
    );
  }

  // State mode: top-5 + bottom-3
  const sorted = [...rows].sort((a, b) => b.yield - a.yield);
  const top5 = sorted.slice(0, 5);
  const bot3 = sorted.slice(-3);

  return (
    <div>
      <div
        style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.08em',
          color: 'var(--text3)', textTransform: 'uppercase', marginBottom: 8,
        }}
      >
        Top-yield counties
      </div>
      <div style={{ background: 'var(--surface2)', borderRadius: 'var(--radius-md)', padding: '12px 14px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
          <thead>
            <tr>
              <th style={thStyle}>Rank</th>
              <th style={thStyle}>County</th>
              <th style={{ ...thStyle, textAlign: 'right' }}>Yield</th>
            </tr>
          </thead>
          <tbody>
            {top5.map((r, i) => (
              <tr key={r.fips}
                  onClick={() => onCountyClick(r.fips)}
                  style={{ cursor: 'pointer' }}>
                <td style={{ ...tdStyle, color: 'var(--field)' }}>#{i + 1}</td>
                <td style={tdStyle}>{titleCase(r.county)}</td>
                <td style={{ ...tdStyle, textAlign: 'right', color: 'var(--text2)' }}>{r.yield.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div
        style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, letterSpacing: '0.08em',
          color: 'var(--text3)', textTransform: 'uppercase', marginBottom: 8, marginTop: 14,
        }}
      >
        Weakest-yield counties
      </div>
      <div style={{ background: 'var(--surface2)', borderRadius: 'var(--radius-md)', padding: '12px 14px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
          <thead>
            <tr>
              <th style={thStyle}>Rank</th>
              <th style={thStyle}>County</th>
              <th style={{ ...thStyle, textAlign: 'right' }}>Yield</th>
            </tr>
          </thead>
          <tbody>
            {bot3.map((r, i) => (
              <tr key={r.fips}
                  onClick={() => onCountyClick(r.fips)}
                  style={{ cursor: 'pointer' }}>
                <td style={{ ...tdStyle, color: 'var(--field)' }}>#{sorted.length - 2 + i}</td>
                <td style={tdStyle}>{titleCase(r.county)}</td>
                <td style={{ ...tdStyle, textAlign: 'right', color: 'var(--text2)' }}>{r.yield.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const thStyle: React.CSSProperties = {
  textAlign: 'left', padding: '4px 0', fontSize: 10, letterSpacing: '0.1em',
  textTransform: 'uppercase', fontWeight: 500, color: 'var(--text3)',
  borderBottom: '1px solid var(--border)',
};

const tdStyle: React.CSSProperties = {
  padding: '5px 0', color: 'var(--text)', borderBottom: '1px solid var(--border)',
};
