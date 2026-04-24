'use client';

import { useEffect, useMemo, useState } from 'react';
import { useYieldForecast } from '@/hooks/useYieldForecast';
import YieldChoroplethMap from './YieldChoroplethMap';
import CountyYieldCard from './CountyYieldCard';
import CitationBlock from '@/components/shared/CitationBlock';

type CropKey = 'corn' | 'soybean' | 'wheat';

const CROP_TABS: { id: CropKey; label: string }[] = [
  { id: 'corn', label: 'Corn' },
  { id: 'soybean', label: 'Soybean' },
  { id: 'wheat', label: 'Wheat' },
];

// The yield_forecasts table is populated by the weekly inference cron. During
// off-season the current year will be empty — fall back to the two prior
// seasons so the panel remains populated year-round.
const YEAR_CANDIDATES = (() => {
  const now = new Date().getFullYear();
  return [now, now - 1, now - 2];
})();

// FIPS -> alpha, needed because the forecast response doesn't include a state
// code. Matches the mapping used in CropsStateMap.
const STATE_FIPS_TO_ALPHA: Record<string, string> = {
  '01': 'AL', '02': 'AK', '04': 'AZ', '05': 'AR', '06': 'CA', '08': 'CO', '09': 'CT',
  '10': 'DE', '12': 'FL', '13': 'GA', '15': 'HI', '16': 'ID', '17': 'IL', '18': 'IN',
  '19': 'IA', '20': 'KS', '21': 'KY', '22': 'LA', '23': 'ME', '24': 'MD', '25': 'MA',
  '26': 'MI', '27': 'MN', '28': 'MS', '29': 'MO', '30': 'MT', '31': 'NE', '32': 'NV',
  '33': 'NH', '34': 'NJ', '35': 'NM', '36': 'NY', '37': 'NC', '38': 'ND', '39': 'OH',
  '40': 'OK', '41': 'OR', '42': 'PA', '44': 'RI', '45': 'SC', '46': 'SD', '47': 'TN',
  '48': 'TX', '49': 'UT', '50': 'VT', '51': 'VA', '53': 'WA', '54': 'WV', '55': 'WI',
  '56': 'WY',
};

// Load the same county GeoJSON the map uses so we can resolve a friendly
// county name from FIPS for the header of the detail card.
let _countyNameIndex: Record<string, string> | null = null;
let _countyNamePromise: Promise<Record<string, string>> | null = null;
function loadCountyNameIndex(): Promise<Record<string, string>> {
  if (_countyNameIndex) return Promise.resolve(_countyNameIndex);
  if (_countyNamePromise) return _countyNamePromise;
  _countyNamePromise = fetch('/us-counties.geojson')
    .then((r) => r.json())
    .then((gj) => {
      const idx: Record<string, string> = {};
      for (const f of gj.features || []) {
        const fips = String(f.id ?? f.properties?.GEOID ?? '').padStart(5, '0');
        if (fips && f.properties?.name) idx[fips] = f.properties.name;
      }
      _countyNameIndex = idx;
      return idx;
    });
  return _countyNamePromise;
}

export default function CountyYieldForecast() {
  const [crop, setCrop] = useState<CropKey>('corn');
  const [year, setYear] = useState<number>(YEAR_CANDIDATES[0]);
  const [autoPicked, setAutoPicked] = useState(false);
  // Once the user clicks a year button, lock out the auto-probe so it doesn't
  // clobber their choice on the next crop change.
  const [userPickedYear, setUserPickedYear] = useState(false);
  const [selectedFips, setSelectedFips] = useState<string | null>(null);
  const [countyNames, setCountyNames] = useState<Record<string, string>>({});

  const { forecast, mapData, mapWeek, loading, error } = useYieldForecast(
    selectedFips,
    crop,
    year,
  );

  useEffect(() => {
    loadCountyNameIndex().then(setCountyNames).catch(() => setCountyNames({}));
  }, []);

  // Reset the user-picked flag so a probe can run again when crop changes.
  // This happens BEFORE the probe effect and in its own effect so state
  // sequencing stays obvious.
  useEffect(() => {
    setUserPickedYear(false);
  }, [crop]);

  // On crop change (and only if the user hasn't manually chosen a year):
  // probe candidate years in order and pick the newest with data. Setting
  // `userPickedYear` when a user clicks a year button prevents this effect
  // from clobbering their choice on the next crop change.
  useEffect(() => {
    if (userPickedYear) return;
    let cancelled = false;
    const base =
      process.env.NEXT_PUBLIC_PREDICTION_API_URL || 'http://localhost:8000';
    (async () => {
      for (const candidate of YEAR_CANDIDATES) {
        try {
          const resp = await fetch(
            `${base}/api/v1/predict/yield/map?crop=${crop}&year=${candidate}`,
          );
          if (!resp.ok) continue;
          const data = await resp.json();
          if (Array.isArray(data?.counties) && data.counties.length > 0) {
            if (!cancelled) {
              setYear(candidate);
              setAutoPicked(candidate !== YEAR_CANDIDATES[0]);
            }
            return;
          }
        } catch {
          // try the next candidate
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [crop, userPickedYear]);

  // Clear selection when the crop or year changes because the prior county
  // might not have data for the new slice.
  useEffect(() => {
    setSelectedFips(null);
  }, [crop, year]);

  const handleYearClick = (y: number) => {
    setUserPickedYear(true);
    setAutoPicked(false);
    setYear(y);
  };

  const selectedCountyName = useMemo(
    () => (selectedFips ? countyNames[selectedFips] || null : null),
    [selectedFips, countyNames],
  );
  const selectedStateAlpha = useMemo(
    () => (selectedFips ? STATE_FIPS_TO_ALPHA[selectedFips.slice(0, 2)] || null : null),
    [selectedFips],
  );

  const empty = !loading && mapData.length === 0;
  // During a year/crop switch we don't want the prior year's counties
  // to linger on the map — better to show a brief loading state than to
  // flash stale data and then swap to an empty message.
  const showLoading = loading && mapData.length === 0;
  const showMap = !loading && mapData.length > 0;

  return (
    <div
      className="p-5 rounded-[var(--radius-lg)] border"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
    >
      {/* Controls row */}
      <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
        <div className="flex items-center gap-4">
          {/* Crop tabs */}
          <div
            className="inline-flex items-center p-1 rounded-[var(--radius-full)]"
            style={{ background: 'var(--surface2)' }}
            role="tablist"
          >
            {CROP_TABS.map((t) => {
              const active = t.id === crop;
              return (
                <button
                  key={t.id}
                  onClick={() => setCrop(t.id)}
                  role="tab"
                  aria-selected={active}
                  className="px-3 py-1 rounded-[var(--radius-full)] text-[12px] font-semibold transition-colors"
                  style={{
                    background: active ? 'var(--surface)' : 'transparent',
                    color: active ? 'var(--text)' : 'var(--text3)',
                    fontFamily: 'var(--font-mono)',
                    border: active ? '1px solid var(--border)' : '1px solid transparent',
                  }}
                >
                  {t.label}
                </button>
              );
            })}
          </div>

          {/* Year picker */}
          <div className="flex items-center gap-1 text-[12px]" style={{ fontFamily: 'var(--font-mono)' }}>
            <span style={{ color: 'var(--text3)' }}>Year</span>
            {YEAR_CANDIDATES.map((y) => {
              const active = y === year;
              return (
                <button
                  key={y}
                  onClick={() => handleYearClick(y)}
                  className="px-2 py-0.5 rounded-[var(--radius-sm)]"
                  style={{
                    background: active ? 'var(--surface2)' : 'transparent',
                    color: active ? 'var(--text)' : 'var(--text3)',
                    border: active ? '1px solid var(--border)' : '1px solid transparent',
                  }}
                >
                  {y}
                </button>
              );
            })}
          </div>
        </div>

        {/* Status chip */}
        <div className="text-[11px]" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
          {loading
            ? 'Loading…'
            : mapWeek
              ? `Week ${mapWeek} · ${mapData.length} counties`
              : empty
                ? 'No forecast'
                : ''}
        </div>
      </div>

      {autoPicked && !empty && (
        <p
          className="mb-3 text-[11px]"
          style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
        >
          Showing {year} — current-year forecasts begin May 19 at week 1.
        </p>
      )}

      {error ? (
        <div className="h-64 flex items-center justify-center text-center text-[13px]"
             style={{ color: 'var(--text3)' }}>
          {error}
        </div>
      ) : showLoading ? (
        <div className="h-64 flex items-center justify-center text-center text-[13px]"
             style={{ color: 'var(--text3)' }}>
          Loading {crop} forecast for {year}…
        </div>
      ) : empty ? (
        <div className="h-64 flex items-center justify-center text-center text-[13px]"
             style={{ color: 'var(--text3)' }}>
          No {crop} forecasts stored for {year}. Try an earlier year or switch to
          &ldquo;Last Season Review&rdquo; for the 2024–2025 walk-forward results.
        </div>
      ) : showMap ? (
        <div
          className="grid gap-4"
          style={{ gridTemplateColumns: 'minmax(0, 2fr) minmax(320px, 1fr)' }}
        >
          <div>
            <YieldChoroplethMap
              counties={mapData}
              selectedFips={selectedFips}
              onCountyClick={setSelectedFips}
              unit={crop === 'wheat' ? 'bu/ac' : 'bu/ac'}
            />
          </div>
          <div>
            <CountyYieldCard
              forecast={forecast}
              countyName={selectedCountyName}
              stateAlpha={selectedStateAlpha}
              loading={!!selectedFips && loading}
            />
          </div>
        </div>
      ) : null}

      <CitationBlock
        source="FieldPulse yield ensemble · LightGBM quantile regression"
        vintage={`${year} inference`}
      />
    </div>
  );
}
