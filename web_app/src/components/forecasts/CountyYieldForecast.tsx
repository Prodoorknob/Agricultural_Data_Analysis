'use client';

import { useEffect, useMemo, useState } from 'react';
import { useYieldForecast } from '@/hooks/useYieldForecast';
import YieldChoroplethMap from './YieldChoroplethMap';
import CountyYieldCard from './CountyYieldCard';
import StateYieldCard from './StateYieldCard';
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

const STATE_FIPS_TO_NAME: Record<string, string> = {
  '01': 'Alabama', '04': 'Arizona', '05': 'Arkansas', '06': 'California',
  '08': 'Colorado', '09': 'Connecticut', '10': 'Delaware', '12': 'Florida',
  '13': 'Georgia', '16': 'Idaho', '17': 'Illinois', '18': 'Indiana',
  '19': 'Iowa', '20': 'Kansas', '21': 'Kentucky', '22': 'Louisiana',
  '23': 'Maine', '24': 'Maryland', '25': 'Massachusetts', '26': 'Michigan',
  '27': 'Minnesota', '28': 'Mississippi', '29': 'Missouri', '30': 'Montana',
  '31': 'Nebraska', '32': 'Nevada', '33': 'New Hampshire', '34': 'New Jersey',
  '35': 'New Mexico', '36': 'New York', '37': 'North Carolina', '38': 'North Dakota',
  '39': 'Ohio', '40': 'Oklahoma', '41': 'Oregon', '42': 'Pennsylvania',
  '44': 'Rhode Island', '45': 'South Carolina', '46': 'South Dakota', '47': 'Tennessee',
  '48': 'Texas', '49': 'Utah', '50': 'Vermont', '51': 'Virginia',
  '53': 'Washington', '54': 'West Virginia', '55': 'Wisconsin', '56': 'Wyoming',
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

const MIN_WEEK = 1;
const MAX_WEEK = 20;

export default function CountyYieldForecast() {
  const [crop, setCrop] = useState<CropKey>('corn');
  const [year, setYear] = useState<number>(YEAR_CANDIDATES[0]);
  const [autoPicked, setAutoPicked] = useState(false);
  const [userPickedYear, setUserPickedYear] = useState(false);
  const [selectedFips, setSelectedFips] = useState<string | null>(null);
  const [selectedState, setSelectedState] = useState<string | null>(null);
  const [countyNames, setCountyNames] = useState<Record<string, string>>({});

  // Week control: `userWeek` is null until the user touches the slider, so
  // the API picks the latest available week and we display whatever it
  // returns. Once the user moves the slider, the chosen week is sent.
  const [userWeek, setUserWeek] = useState<number | null>(null);

  const { forecast, mapData, mapWeek, loading, error } = useYieldForecast(
    selectedFips,
    crop,
    year,
    userWeek ?? undefined,
  );

  useEffect(() => {
    loadCountyNameIndex().then(setCountyNames).catch(() => setCountyNames({}));
  }, []);

  // Reset the user-picked flag so the auto-probe can run again on crop change.
  useEffect(() => {
    setUserPickedYear(false);
  }, [crop]);

  // On crop change: probe candidate years in order and pick the newest with
  // data. Setting `userPickedYear` when a user clicks a year button prevents
  // this from clobbering their choice on the next crop change.
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

  // Clear county+state selection and week override when the crop or year
  // changes — prior selections may not be valid for the new slice.
  useEffect(() => {
    setSelectedFips(null);
    setSelectedState(null);
    setUserWeek(null);
  }, [crop, year]);

  // Keep selectedState in sync with whichever county is currently selected
  // so the map's dimming behavior follows the panel.
  useEffect(() => {
    if (selectedFips) setSelectedState(selectedFips.slice(0, 2));
  }, [selectedFips]);

  const handleYearClick = (y: number) => {
    setUserPickedYear(true);
    setAutoPicked(false);
    setYear(y);
  };

  const handleStateClick = (stateFips: string) => {
    // Toggle off when clicking the already-selected state.
    if (selectedState === stateFips && !selectedFips) {
      setSelectedState(null);
      return;
    }
    setSelectedState(stateFips);
    setSelectedFips(null);
  };

  const selectedCountyName = useMemo(
    () => (selectedFips ? countyNames[selectedFips] || null : null),
    [selectedFips, countyNames],
  );
  const selectedStateAlpha = useMemo(
    () =>
      selectedState
        ? STATE_FIPS_TO_ALPHA[selectedState] || null
        : selectedFips
          ? STATE_FIPS_TO_ALPHA[selectedFips.slice(0, 2)] || null
          : null,
    [selectedFips, selectedState],
  );
  const selectedStateName = useMemo(
    () => (selectedState ? STATE_FIPS_TO_NAME[selectedState] || null : null),
    [selectedState],
  );

  // Dropdown options: only states that have at least one county in the
  // current map slice. Sorted alphabetically by name.
  const availableStates = useMemo(() => {
    const seen = new Set<string>();
    for (const c of mapData) seen.add(c.fips.slice(0, 2));
    return Array.from(seen)
      .map((fips) => ({ fips, name: STATE_FIPS_TO_NAME[fips] || fips }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [mapData]);

  const empty = !loading && mapData.length === 0;
  const showLoading = loading && mapData.length === 0;
  const showMap = !loading && mapData.length > 0;

  const displayedWeek = userWeek ?? mapWeek;
  const sliderValue = userWeek ?? mapWeek ?? MAX_WEEK;
  const sliderDisabled = !showMap;

  return (
    <div
      className="p-5 rounded-[var(--radius-lg)] border"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
    >
      {/* Controls row */}
      <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
        <div className="flex items-center gap-4 flex-wrap">
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

          {/* State filter */}
          <div className="flex items-center gap-2 text-[12px]" style={{ fontFamily: 'var(--font-mono)' }}>
            <span style={{ color: 'var(--text3)' }}>State</span>
            <select
              value={selectedState ?? ''}
              onChange={(e) => {
                const v = e.target.value;
                setSelectedState(v || null);
                setSelectedFips(null);
              }}
              disabled={availableStates.length === 0}
              className="px-2 py-0.5 rounded-[var(--radius-sm)]"
              style={{
                background: 'var(--surface2)',
                color: 'var(--text)',
                border: '1px solid var(--border)',
                fontFamily: 'var(--font-mono)',
                fontSize: 12,
              }}
            >
              <option value="">All states</option>
              {availableStates.map((s) => (
                <option key={s.fips} value={s.fips}>
                  {s.name}
                </option>
              ))}
            </select>
            {selectedState && (
              <button
                onClick={() => {
                  setSelectedState(null);
                  setSelectedFips(null);
                }}
                className="text-[11px] px-1.5 py-0.5 rounded-[var(--radius-sm)]"
                style={{
                  background: 'transparent',
                  color: 'var(--text3)',
                  border: '1px solid var(--border)',
                }}
                title="Clear state filter"
              >
                Clear
              </button>
            )}
          </div>
        </div>

        {/* Status chip */}
        <div className="text-[11px]" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
          {loading
            ? 'Loading…'
            : displayedWeek
              ? `Week ${displayedWeek} · ${mapData.length} counties`
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
              selectedState={selectedState}
              onCountyClick={(fips) => {
                setSelectedFips(fips);
                setSelectedState(fips.slice(0, 2));
              }}
              onStateClick={handleStateClick}
              unit={crop === 'wheat' ? 'bu/ac' : 'bu/ac'}
            />

            {/* Week slider */}
            <div className="mt-4 px-1">
              <div
                className="flex items-center justify-between mb-1 text-[11px]"
                style={{ fontFamily: 'var(--font-mono)', color: 'var(--text3)' }}
              >
                <span>Week of growing season</span>
                <span style={{ color: 'var(--text2)' }}>
                  {displayedWeek ? `Week ${displayedWeek}` : '—'}
                  {userWeek === null && mapWeek ? ' (latest)' : ''}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span
                  className="text-[10px]"
                  style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
                >
                  W{MIN_WEEK}
                </span>
                <input
                  type="range"
                  min={MIN_WEEK}
                  max={MAX_WEEK}
                  step={1}
                  value={sliderValue}
                  disabled={sliderDisabled}
                  onChange={(e) => setUserWeek(Number(e.target.value))}
                  className="flex-1"
                  style={{ accentColor: 'var(--field)' }}
                  aria-label="Growing-season week"
                />
                <span
                  className="text-[10px]"
                  style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
                >
                  W{MAX_WEEK}
                </span>
                {userWeek !== null && (
                  <button
                    onClick={() => setUserWeek(null)}
                    className="text-[10px] px-1.5 py-0.5 rounded-[var(--radius-sm)]"
                    style={{
                      background: 'transparent',
                      color: 'var(--text3)',
                      border: '1px solid var(--border)',
                      fontFamily: 'var(--font-mono)',
                    }}
                    title="Reset to latest week"
                  >
                    Latest
                  </button>
                )}
              </div>
            </div>
          </div>
          <div>
            {selectedFips && forecast ? (
              <CountyYieldCard
                forecast={forecast}
                countyName={selectedCountyName}
                stateAlpha={selectedStateAlpha}
                loading={loading}
              />
            ) : selectedFips && loading ? (
              <CountyYieldCard
                forecast={null}
                countyName={selectedCountyName}
                stateAlpha={selectedStateAlpha}
                loading
              />
            ) : selectedState ? (
              <StateYieldCard
                stateFips={selectedState}
                stateName={selectedStateName}
                stateAlpha={selectedStateAlpha}
                counties={mapData}
                crop={crop}
                year={year}
                week={displayedWeek}
              />
            ) : (
              <CountyYieldCard
                forecast={null}
                countyName={null}
                stateAlpha={null}
                loading={false}
              />
            )}
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
