'use client';

import { useAgSeason } from '@/hooks/useAgSeason';
import SectionHeading from '@/components/shared/SectionHeading';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export default function SeasonClock() {
  const { month, season } = useAgSeason();

  // Acreage rail: Feb (1) - Apr (3)
  // Yield rail: May (4) - Oct (9)
  const isAcreageLive = month >= 1 && month <= 3;
  const isYieldLive = month >= 4 && month <= 9;

  return (
    <div
      className="p-4 rounded-[var(--radius-lg)] border mb-6"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
    >
      <SectionHeading>Season Clock</SectionHeading>

      {/* Month strip */}
      <div className="flex items-center gap-0 mb-2">
        {MONTHS.map((m, i) => (
          <div
            key={m}
            className="flex-1 text-center py-1.5 text-[10px] font-bold rounded-[var(--radius-sm)] transition-all"
            style={{
              fontFamily: 'var(--font-mono)',
              background: i === month ? 'var(--field)' : 'transparent',
              color: i === month ? '#FFFFFF' : 'var(--text3)',
            }}
          >
            {m}
          </div>
        ))}
      </div>

      {/* Acreage rail */}
      <div className="flex items-center gap-0 mb-1">
        {MONTHS.map((_, i) => (
          <div
            key={`acr-${i}`}
            className="flex-1 h-1.5 first:rounded-l-full last:rounded-r-full"
            style={{
              background:
                i >= 1 && i <= 3
                  ? isAcreageLive ? 'var(--field)' : 'var(--field-subtle)'
                  : 'transparent',
            }}
          />
        ))}
      </div>
      <p className="text-[9px] mb-2" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
        Acreage forecasts {isAcreageLive ? '(live)' : month > 3 ? '(finalized)' : '(upcoming)'}
      </p>

      {/* Yield rail */}
      <div className="flex items-center gap-0 mb-1">
        {MONTHS.map((_, i) => {
          let bg = 'transparent';
          if (i >= 4 && i <= 9) {
            if (!isYieldLive) {
              // Hatched pattern signals "upcoming, not live" with enough
              // contrast to remain legible in both light and dark themes.
              bg =
                'repeating-linear-gradient(45deg, var(--border2) 0 3px, transparent 3px 6px)';
            } else if (i <= 6) bg = 'var(--harvest-subtle)'; // low confidence
            else if (i <= 8) bg = 'var(--harvest)'; // medium
            else bg = 'var(--field)'; // high
          }
          return (
            <div
              key={`yld-${i}`}
              className="flex-1 h-1.5 first:rounded-l-full last:rounded-r-full"
              style={{ background: bg }}
            />
          );
        })}
      </div>
      <p className="text-[9px] mb-3" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
        Yield forecasts {isYieldLive ? '(live)' : month > 9 ? '(complete)' : '(begin May)'}
      </p>

      {/* Caption */}
      <p className="text-[13px]" style={{ color: 'var(--text2)' }}>
        Today is {MONTHS[month]} {new Date().getDate()}.{' '}
        {isAcreageLive ? 'Acreage forecasts are live.' : 'Acreage forecasts are finalized.'}{' '}
        {isYieldLive ? 'Yield forecasts are active.' : 'Yield forecasts begin May 19 for corn and soy.'}
      </p>
    </div>
  );
}
