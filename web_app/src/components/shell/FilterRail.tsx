'use client';

import { useFilters } from '@/hooks/useFilters';
import { US_STATES } from '@/utils/serviceData';
import { LATEST_NASS_YEAR } from '@/lib/constants';

const YEARS = Array.from({ length: 25 }, (_, i) => LATEST_NASS_YEAR - i);
const COMMODITIES = ['corn', 'soybean', 'wheat', 'soybeans', 'cotton', 'hay'];
const COMMODITY_TABS = new Set(['market', 'forecasts', 'crops']);
const STATE_CODES = Object.keys(US_STATES).sort();

export default function FilterRail() {
  const { filters, setState, setYear, setCommodity, currentTab } = useFilters();
  const showCommodity = COMMODITY_TABS.has(currentTab);
  const showYear = currentTab !== 'market'; // Market uses range chips instead

  return (
    <div
      className="flex items-center h-[44px] px-5 gap-3 overflow-x-auto"
      style={{ background: 'var(--surface2)', borderBottom: '1px solid var(--border)' }}
    >
      {/* State pill — always visible */}
      <Pill label="State">
        <select
          value={filters.state || ''}
          onChange={(e) => setState(e.target.value || null)}
          className="appearance-none bg-transparent outline-none cursor-pointer text-[12px] font-medium pr-4"
          style={{ color: 'var(--text)', fontFamily: 'var(--font-mono)' }}
        >
          <option value="">National</option>
          {STATE_CODES.map((code) => (
            <option key={code} value={code}>
              {code}
            </option>
          ))}
        </select>
      </Pill>

      {/* Year pill — hidden on Market tab */}
      {showYear && (
        <Pill label="Year">
          <select
            value={filters.year ?? LATEST_NASS_YEAR}
            onChange={(e) => setYear(Number(e.target.value))}
            className="appearance-none bg-transparent outline-none cursor-pointer text-[12px] font-medium pr-4"
            style={{ color: 'var(--text)', fontFamily: 'var(--font-mono)' }}
          >
            {YEARS.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </Pill>
      )}

      {/* Commodity pill — Market, Forecasts, Crops */}
      {showCommodity && (
        <Pill label="Commodity">
          <select
            value={filters.commodity || 'corn'}
            onChange={(e) => setCommodity(e.target.value)}
            className="appearance-none bg-transparent outline-none cursor-pointer text-[12px] font-medium capitalize pr-4"
            style={{ color: 'var(--text)', fontFamily: 'var(--font-mono)' }}
          >
            {COMMODITIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </Pill>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* Data freshness strip */}
      <div
        className="flex items-center gap-3 text-[10px] tracking-wider uppercase shrink-0"
        style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
      >
        <span className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--positive)]" />
          NASS {LATEST_NASS_YEAR}
        </span>
      </div>
    </div>
  );
}

/** Small pill wrapper for filter selects */
function Pill({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div
      className="flex items-center gap-1.5 h-[30px] px-2.5 rounded-[var(--radius-full)] border shrink-0"
      style={{ borderColor: 'var(--border2)', background: 'var(--surface)' }}
    >
      <span
        className="text-[9px] font-bold tracking-[0.1em] uppercase"
        style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
      >
        {label}
      </span>
      {children}
    </div>
  );
}
