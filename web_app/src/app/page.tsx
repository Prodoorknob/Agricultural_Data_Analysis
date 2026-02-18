'use client';

import USMap from '@/components/USMap';
import EconomicsDashboard from '@/components/EconomicsDashboard';
import LandDashboard from '@/components/LandDashboard';
import LaborDashboard from '@/components/LaborDashboard';
import CropsDashboard from '@/components/CropsDashboard';
import AnimalsDashboard from '@/components/AnimalsDashboard';
import StateInfoPanel from '@/components/StateInfoPanel';
import StateSingleMap from '@/components/StateSingleMap';
import React, { useState, useEffect, useMemo } from 'react';
import { US_STATES } from '../utils/serviceData';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, Cell, AreaChart, Area
} from 'recharts';
import { fetchStateData, fetchNationalCrops, fetchLandUseData, fetchLaborData } from '../utils/serviceData';
import { getMapData, getLandUseTrends, getBoomCrops, filterData, getCropConditionTrends, getCropProgressSummary } from '../utils/processData';

// --- Types ---
type ViewMode = 'OVERVIEW' | 'CROPS' | 'ANIMALS' | 'LAND' | 'LABOR' | 'ECONOMICS';

// --- Filter Options ---
const YEARS = Array.from({ length: 25 }, (_, i) => 2025 - i); // 2025 down to 2001
const SECTORS = ['All Sectors', 'Crops', 'Animals & Products', 'Economics'];

// Dynamic Group Options
const GROUP_OPTIONS: Record<string, string[]> = {
  'All Sectors': ['All Groups'],
  'Crops': ['All Crop Groups', 'Field Crops', 'Vegetables', 'Fruit & Tree Nuts', 'Horticulture'],
  'Animals & Products': ['All Animal Groups', 'Livestock', 'Poultry', 'Dairy'],
  'Economics': ['All Economics', 'Expenses', 'Income']
};

const MEASURES = [
  'Area Harvested (acres)',
  'Area Planted (acres)',
  'Revenue (USD)',
  'Operations',
  'Ops per 1,000 Acres'
];

export default function Home() {
  // --- State ---
  const [selectedState, setSelectedState] = useState<string | undefined>('IN');
  const [selectedYear, setSelectedYear] = useState<number>(2022);
  const [selectedSector, setSelectedSector] = useState<string>('All Sectors');
  const [selectedSubGroup, setSelectedSubGroup] = useState<string>('All Groups'); // Unified Group Filter
  const [selectedMeasure, setSelectedMeasure] = useState<string>('Area Harvested (acres)');
  const [viewMode, setViewMode] = useState<ViewMode>('OVERVIEW');

  // Overview Interaction State
  const [overviewCommodity, setOverviewCommodity] = useState<string | null>(null);

  // Data State
  const [nationalData, setNationalData] = useState<any[]>([]);
  const [stateData, setStateData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // --- Reset SubGroup when Sector Changes ---
  useEffect(() => {
    // Default to first option in list (usually 'All ...')
    const options = GROUP_OPTIONS[selectedSector] || ['All Groups'];
    setSelectedSubGroup(options[0]);
  }, [selectedSector]);


  // --- Data Loading ---
  useEffect(() => {
    async function loadNational() {
      try {
        const national = await fetchNationalCrops(); // Now returns separate 'US' and State rows
        setNationalData(national);

        // Initial State Load (Parallel)
        if (selectedState) {
          const state = await fetchStateData(selectedState);
          setStateData(state);
        }
      } catch (e) {
        console.error('Failed to load initial data', e);
      } finally {
        setLoading(false);
      }
    }
    loadNational();
  }, []);

  useEffect(() => {
    async function loadData() {
      if (!selectedState) return;
      setLoading(true);
      try {
        const data = await fetchStateData(selectedState);
        setStateData(data);
      } catch (err) {
        console.error("Failed to load state data", err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
    // Reset overview interaction on state change
    setOverviewCommodity(null);
  }, [selectedState]);

  // --- Global Filtering Logic ---
  const filterByGroup = (data: any[]) => {
    return data.filter(d => {
      // Filter by Sector
      if (selectedSector !== 'All Sectors') {
        const sectorMap: Record<string, string> = {
          'Crops': 'CROPS',
          'Animals & Products': 'ANIMALS & PRODUCTS',
          'Economics': 'ECONOMICS'
        };
        if (d.sector_desc?.toUpperCase() !== sectorMap[selectedSector]) return false;
      }

      // Filter by SubGroup
      if (selectedSubGroup && !selectedSubGroup.includes('All')) {
        const formattedUI = selectedSubGroup.toUpperCase();
        const dbGroup = d.group_desc?.toUpperCase();
        if (dbGroup !== formattedUI) {
          if (dbGroup !== formattedUI) return false;
        }
      }
      return true;
    });
  };

  const filteredStateData = useMemo(() => {
    if (!stateData.length) return [];
    const clean = filterData(stateData);
    return filterByGroup(clean);
  }, [stateData, selectedSector, selectedSubGroup]);

  // For Map: Need state-level aggregates from National file
  const filteredMapSource = useMemo(() => {
    if (!nationalData.length) return [];
    return filterData(nationalData).filter(d => d.state_alpha !== 'US');
  }, [nationalData]);

  // For National Summaries: Need 'US' rows
  const filteredNationalSummary = useMemo(() => {
    if (!nationalData.length) return [];
    return filterData(nationalData).filter(d => d.state_alpha === 'US');
  }, [nationalData]);


  // --- Derived Data for Map ---
  const mapMetric = useMemo(() => {
    if (selectedMeasure.includes('Revenue')) return 'SALES';
    if (selectedMeasure.includes('Harvested')) return 'AREA HARVESTED';
    if (selectedMeasure.includes('Planted')) return 'AREA PLANTED';
    if (selectedMeasure.includes('Operations')) return 'OPERATIONS';
    if (selectedMeasure.includes('Inventory')) return 'INVENTORY';
    return 'AREA HARVESTED';
  }, [selectedMeasure]);

  const mapData = useMemo(() => {
    const relevant = filterByGroup(filteredMapSource);
    return getMapData(relevant, selectedYear, mapMetric);
  }, [filteredMapSource, selectedYear, mapMetric, selectedSector, selectedSubGroup]);

  // --- Derived Data for Overview Charts ---

  // 1. Fastest Growing (Boom Crops)
  const overviewBoomCrops = useMemo(() => {
    const source = filteredStateData.length ? filteredStateData : filterByGroup(filteredNationalSummary);
    return getBoomCrops(source, 'AREA HARVESTED', 2023, 2001);
  }, [filteredStateData, filteredNationalSummary, selectedSector, selectedSubGroup]);

  // 2. Area Trends (Interactive)
  const overviewAreaTrends = useMemo(() => {
    let source = filteredStateData.length ? filteredStateData : filterByGroup(filteredNationalSummary);

    // Interaction: If a commodity is clicked in Boom Chart, filter trends to that commodity
    if (overviewCommodity) {
      source = source.filter(d => d.commodity_desc === overviewCommodity);
    }

    return getLandUseTrends(source);
  }, [filteredStateData, filteredNationalSummary, overviewCommodity, selectedSector, selectedSubGroup]);


  // --- Render Helpers ---
  const currentGroupOptions = GROUP_OPTIONS[selectedSector] || ['All Groups'];

  const renderHeader = () => (
    <header className="sticky top-0 z-50 bg-[#0f1117]/95 backdrop-blur-md border-b border-[#1f2937]">
      <div className="px-4 lg:px-8 py-3 flex items-center justify-between max-w-[1800px] mx-auto">
        {/* Left: Logo and Nav */}
        <div className="flex items-center gap-8">
          <div className="flex items-center gap-3">
            <div className="size-8 text-[#19e63c]">
              <span className="material-symbols-outlined text-[32px]">agriculture</span>
            </div>
            <h1 className="text-xl font-bold tracking-tight text-white">
              QuickStats <span className="font-normal text-gray-400">Analytics</span>
            </h1>
          </div>
          <nav className="hidden lg:flex items-center gap-6">
            <button
              onClick={() => setViewMode('OVERVIEW')}
              className={`text-sm font-medium transition-colors pb-1 ${viewMode === 'OVERVIEW'
                ? 'text-[#19e63c] border-b-2 border-[#19e63c]'
                : 'text-gray-400 hover:text-white'
                }`}
            >
              Dashboard
            </button>
            <button
              onClick={() => setViewMode('CROPS')}
              className={`text-sm font-medium transition-colors pb-1 ${viewMode === 'CROPS'
                ? 'text-[#19e63c] border-b-2 border-[#19e63c]'
                : 'text-gray-400 hover:text-white'
                }`}
            >
              Crops
            </button>
            <button
              onClick={() => setViewMode('ANIMALS')}
              className={`text-sm font-medium transition-colors pb-1 ${viewMode === 'ANIMALS'
                ? 'text-[#19e63c] border-b-2 border-[#19e63c]'
                : 'text-gray-400 hover:text-white'
                }`}
            >
              Livestock
            </button>
            <button
              onClick={() => setViewMode('LAND')}
              className={`text-sm font-medium transition-colors pb-1 ${viewMode === 'LAND'
                ? 'text-[#19e63c] border-b-2 border-[#19e63c]'
                : 'text-gray-400 hover:text-white'
                }`}
            >
              Land & Area
            </button>
            <button
              onClick={() => setViewMode('LABOR')}
              className={`text-sm font-medium transition-colors pb-1 ${viewMode === 'LABOR'
                ? 'text-[#19e63c] border-b-2 border-[#19e63c]'
                : 'text-gray-400 hover:text-white'
                }`}
            >
              Labor
            </button>
            <button
              onClick={() => setViewMode('ECONOMICS')}
              className={`text-sm font-medium transition-colors pb-1 ${viewMode === 'ECONOMICS'
                ? 'text-[#19e63c] border-b-2 border-[#19e63c]'
                : 'text-gray-400 hover:text-white'
                }`}
            >
              Economics
            </button>
          </nav>
        </div>

        {/* Right: Search, Notifications, Profile */}
        <div className="flex items-center gap-4">
          <div className="relative hidden md:block">
            <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-gray-500">
              <span className="material-symbols-outlined text-[20px]">search</span>
            </span>
            <input
              className="block w-64 rounded-lg border-0 bg-[#1f2937] py-2 pl-10 pr-4 text-sm text-white placeholder:text-gray-500 focus:ring-2 focus:ring-[#19e63c] transition-all"
              placeholder="Search data..."
              type="text"
            />
          </div>
          <button className="relative p-2 text-gray-400 hover:text-white hover:bg-[#1f2937] rounded-lg transition-colors">
            <span className="material-symbols-outlined">notifications</span>
            <span className="absolute top-2 right-2 h-2 w-2 rounded-full bg-red-500 ring-2 ring-[#0f1117]"></span>
          </button>
          <div className="h-9 w-9 rounded-full bg-[#19e63c]/20 border border-[#19e63c]/30 flex items-center justify-center text-[#19e63c] font-bold">
            {selectedState || 'US'}
          </div>
        </div>
      </div>

      {/* Breadcrumbs & Filters Bar */}
      <div className="px-4 lg:px-8 py-3 bg-[#1a1d24] border-t border-[#1f2937]">
        <div className="max-w-[1800px] mx-auto">
          {/* Breadcrumbs */}
          <div className="flex items-center gap-2 text-sm text-gray-400 mb-3">
            <span className="hover:text-[#19e63c] cursor-pointer transition-colors">Home</span>
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
            <span className="text-white font-medium">
              {viewMode === 'OVERVIEW' ? 'Executive Snapshot' :
                viewMode === 'CROPS' ? 'Crop Analysis' :
                  viewMode === 'ANIMALS' ? 'Livestock Monitor' :
                    viewMode === 'LAND' ? 'Land Use' :
                      viewMode === 'LABOR' ? 'Labor Statistics' : 'Farm Economics'}
            </span>
            {selectedState && (
              <>
                <span className="material-symbols-outlined text-[14px]">chevron_right</span>
                <span className="text-[#19e63c]">{selectedState}</span>
              </>
            )}
          </div>

          {/* Filters */}
          <div className="flex flex-wrap items-center gap-3">
            {/* State Selector */}
            <div className="relative">
              <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-gray-500 pointer-events-none">
                <span className="material-symbols-outlined text-[18px]">location_on</span>
              </span>
              <select
                value={selectedState || ''}
                onChange={(e) => setSelectedState(e.target.value || undefined)}
                className="bg-[#0f1117] border border-[#2a4030] text-white text-sm rounded-lg pl-10 pr-8 py-2 focus:ring-2 focus:ring-[#19e63c] appearance-none cursor-pointer"
              >
                <option value="">National View</option>
                {Object.entries(US_STATES).map(([code, name]) => (
                  <option key={code} value={code}>{name}</option>
                ))}
              </select>
            </div>

            {/* Year Filter */}
            <div className="relative">
              <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-gray-500 pointer-events-none">
                <span className="material-symbols-outlined text-[18px]">calendar_today</span>
              </span>
              <select
                value={selectedYear}
                onChange={(e) => setSelectedYear(Number(e.target.value))}
                className="bg-[#0f1117] border border-[#2a4030] text-white text-sm rounded-lg pl-10 pr-8 py-2 focus:ring-2 focus:ring-[#19e63c] appearance-none cursor-pointer"
              >
                <option value={0}>All Years</option>
                {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
              </select>
            </div>

            {/* Sector Filter */}
            <div className="relative">
              <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-gray-500 pointer-events-none">
                <span className="material-symbols-outlined text-[18px]">category</span>
              </span>
              <select
                value={selectedSector}
                onChange={(e) => setSelectedSector(e.target.value)}
                className="bg-[#0f1117] border border-[#2a4030] text-white text-sm rounded-lg pl-10 pr-8 py-2 focus:ring-2 focus:ring-[#19e63c] appearance-none cursor-pointer"
              >
                {SECTORS.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>

            {/* Group Filter */}
            <div className="relative">
              <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-gray-500 pointer-events-none">
                <span className="material-symbols-outlined text-[18px]">filter_list</span>
              </span>
              <select
                value={selectedSubGroup}
                onChange={(e) => setSelectedSubGroup(e.target.value)}
                className="bg-[#0f1117] border border-[#2a4030] text-white text-sm rounded-lg pl-10 pr-8 py-2 focus:ring-2 focus:ring-[#19e63c] appearance-none cursor-pointer disabled:opacity-50"
                disabled={currentGroupOptions.length <= 1}
              >
                {currentGroupOptions.map(g => <option key={g} value={g}>{g}</option>)}
              </select>
            </div>

            {/* Map Metric Filter */}
            <div className="relative">
              <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-gray-500 pointer-events-none">
                <span className="material-symbols-outlined text-[18px]">straighten</span>
              </span>
              <select
                value={selectedMeasure}
                onChange={(e) => setSelectedMeasure(e.target.value)}
                className="bg-[#0f1117] border border-[#2a4030] text-white text-sm rounded-lg pl-10 pr-8 py-2 focus:ring-2 focus:ring-[#19e63c] appearance-none cursor-pointer"
              >
                {MEASURES.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>

            {/* Live Status Indicator */}
            <div className="ml-auto flex items-center gap-2 text-xs font-medium text-gray-400 bg-[#0f1117] px-3 py-2 rounded-lg border border-[#2a4030]">
              <span className="w-2 h-2 rounded-full bg-[#19e63c] animate-pulse"></span>
              Last updated: {new Date().toLocaleDateString()}
            </div>
          </div>
        </div>
      </div>
    </header>
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-[#0f1117] via-[#1a1d24] to-[#0f1117]">
      {renderHeader()}

      <div className="px-4 lg:px-8 py-8 max-w-[1800px] mx-auto">
        {/* State Selector Section */}
        <div className="mb-8 grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left: State Info Panel */}
          <div className="h-[500px]">
            <StateInfoPanel
              selectedState={selectedState}
              selectedYear={selectedYear}
              selectedSector={selectedSector}
              selectedCommodity={overviewCommodity}
              stateData={stateData}
            />
          </div>

          {/* Right: State Map */}
          <div className="h-[500px]">
            <StateSingleMap
              selectedState={selectedState}
              mapData={mapData}
            />
          </div>
        </div>

        {/* Content Area */}
        {viewMode === 'OVERVIEW' && (
          <div className="space-y-6">

            {/* Area Trends Chart */}
            <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030]">
              <div className="flex justify-between items-center mb-2">
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <span className="material-symbols-outlined text-[#19e63c]">trending_up</span>
                  Area Trends Over Time
                  {overviewCommodity && <span className="text-[#19e63c] ml-2">({overviewCommodity})</span>}
                </h3>
                {overviewCommodity && (
                  <button
                    onClick={() => setOverviewCommodity(null)}
                    className="text-xs text-red-400 hover:text-red-300 bg-red-500/10 px-3 py-1 rounded-lg transition-colors"
                  >
                    Clear Filter ×
                  </button>
                )}
              </div>
              <div className="mb-4 space-y-1">
                <p className="text-xs text-gray-400">
                  Only crops with <strong>both</strong> Planted &amp; Harvested data
                  ({(overviewAreaTrends as any).excludedCropCount ?? '?'} harvest-only crops excluded)
                </p>
                {((overviewAreaTrends as any).multiHarvestCrops?.length > 0) && (
                  <p className="text-xs text-amber-400 font-medium flex items-center gap-1">
                    <span className="material-symbols-outlined text-[16px]">warning</span>
                    Multi-harvest: {(overviewAreaTrends as any).multiHarvestCrops.join(', ')} — harvested may exceed planted
                  </p>
                )}
              </div>
              <div className="h-[400px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={overviewAreaTrends}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#2a4030" />
                    <XAxis
                      dataKey="year"
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: '#9ca3af', fontSize: 12 }}
                      dy={10}
                    />
                    <YAxis
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: '#9ca3af', fontSize: 12 }}
                      tickFormatter={(val) => val >= 1000000 ? `${(val / 1000000).toFixed(1)}M` : val >= 1000 ? `${(val / 1000).toFixed(0)}k` : val}
                    />
                    <Tooltip
                      formatter={(val: number | string | undefined) => [new Intl.NumberFormat('en-US').format(Number(val || 0)) + ' acres', '']}
                      contentStyle={{ backgroundColor: '#1a1d24', border: '1px solid #2a4030', borderRadius: '8px', color: '#fff' }}
                    />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="planted"
                      name="Area Planted"
                      stroke="#19e63c"
                      strokeWidth={3}
                      dot={{ r: 4, fill: '#19e63c', strokeWidth: 0 }}
                      activeDot={{ r: 6 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="harvested"
                      name="Area Harvested"
                      stroke="#10b981"
                      strokeWidth={3}
                      dot={{ r: 4, fill: '#10b981', strokeWidth: 0 }}
                      activeDot={{ r: 6 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Crop Health & Progress Section */}
            {(() => {
              const conditionData = getCropConditionTrends(
                filteredStateData.length ? filteredStateData : filteredNationalSummary
              );
              const progressData = getCropProgressSummary(
                filteredStateData.length ? filteredStateData : filteredNationalSummary
              );
              const latestProgress = progressData.length > 0 ? progressData[progressData.length - 1] : null;

              const CONDITION_COLORS: Record<string, string> = {
                excellent: '#22c55e',
                good: '#86efac',
                fair: '#fbbf24',
                poor: '#f97316',
                very_poor: '#ef4444',
              };

              if (!conditionData.length && !latestProgress) return null;

              return (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Crop Condition Trends */}
                  {conditionData.length > 0 && (
                    <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030]">
                      <div className="flex items-center gap-2 mb-4">
                        <span className="material-symbols-outlined text-[#19e63c]">health_metrics</span>
                        <h3 className="text-lg font-semibold text-white">Crop Condition Trends</h3>
                      </div>
                      <p className="text-xs text-gray-400 mb-4">Average % of crops rated in each condition category by year</p>
                      <div className="h-[350px]">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={conditionData} stackOffset="expand">
                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#2a4030" />
                            <XAxis dataKey="year" axisLine={false} tickLine={false} tick={{ fill: '#9ca3af', fontSize: 11 }} />
                            <YAxis axisLine={false} tickLine={false} tick={{ fill: '#9ca3af', fontSize: 11 }} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
                            <Tooltip
                              formatter={(val: any, name?: string) => [`${Math.round(Number(val))}%`, (name || '').replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())]}
                              contentStyle={{ backgroundColor: '#1a1d24', border: '1px solid #2a4030', borderRadius: '8px', color: '#fff' }}
                            />
                            <Legend wrapperStyle={{ color: '#9ca3af', fontSize: '11px' }} formatter={(v: string) => v.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())} />
                            <Area type="monotone" dataKey="excellent" stackId="1" stroke={CONDITION_COLORS.excellent} fill={CONDITION_COLORS.excellent} fillOpacity={0.8} />
                            <Area type="monotone" dataKey="good" stackId="1" stroke={CONDITION_COLORS.good} fill={CONDITION_COLORS.good} fillOpacity={0.8} />
                            <Area type="monotone" dataKey="fair" stackId="1" stroke={CONDITION_COLORS.fair} fill={CONDITION_COLORS.fair} fillOpacity={0.8} />
                            <Area type="monotone" dataKey="poor" stackId="1" stroke={CONDITION_COLORS.poor} fill={CONDITION_COLORS.poor} fillOpacity={0.8} />
                            <Area type="monotone" dataKey="very_poor" stackId="1" stroke={CONDITION_COLORS.very_poor} fill={CONDITION_COLORS.very_poor} fillOpacity={0.8} />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  )}

                  {/* Crop Progress Snapshot */}
                  {latestProgress && latestProgress.crops.length > 0 && (
                    <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030]">
                      <div className="flex items-center gap-2 mb-4">
                        <span className="material-symbols-outlined text-[#19e63c]">sprint</span>
                        <h3 className="text-lg font-semibold text-white">Crop Progress ({latestProgress.year})</h3>
                      </div>
                      <p className="text-xs text-gray-400 mb-4">Peak season completion % for top crops</p>
                      <div className="h-[350px]">
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart
                            layout="vertical"
                            data={latestProgress.crops.slice(0, 12)}
                            margin={{ top: 5, right: 30, left: 60, bottom: 5 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" horizontal={false} vertical={true} stroke="#2a4030" />
                            <XAxis type="number" domain={[0, 100]} tickFormatter={(v) => `${v}%`} axisLine={false} tickLine={false} tick={{ fill: '#9ca3af', fontSize: 11 }} />
                            <YAxis type="category" dataKey="commodity" axisLine={false} tickLine={false} tick={{ fill: '#9ca3af', fontSize: 11, fontWeight: 500 }} width={100} />
                            <Tooltip
                              formatter={(val: any) => [`${Number(val).toFixed(1)}%`, 'Completion']}
                              contentStyle={{ backgroundColor: '#1a1d24', border: '1px solid #2a4030', borderRadius: '8px', color: '#fff' }}
                            />
                            <Bar dataKey="progress" radius={[0, 6, 6, 0]} barSize={20}>
                              {latestProgress.crops.slice(0, 12).map((_: any, index: number) => (
                                <Cell key={`cell-${index}`} fill={index < 4 ? '#19e63c' : index < 8 ? '#10b981' : '#047857'} />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  )}
                </div>
              );
            })()}

            {/* Fastest Growing Crops Chart */}
            <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030]">
              <h3 className="text-lg font-semibold mb-4 text-white flex items-center gap-2">
                <span className="material-symbols-outlined text-[#19e63c]">rocket_launch</span>
                Fastest Growing Crops (2001-2023 Growth %) - Click bar to filter trend
              </h3>
              <div className="h-[500px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    layout="vertical"
                    data={overviewBoomCrops}
                    margin={{ top: 5, right: 30, left: 40, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke="#2a4030" />
                    <XAxis type="number" hide />
                    <YAxis
                      type="category"
                      dataKey="commodity"
                      width={120}
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: '#9ca3af', fontSize: 11, fontWeight: 500 }}
                    />
                    <Tooltip
                      cursor={{ fill: '#1f2937' }}
                      formatter={(val: number | string | undefined) => [`${Number(val || 0).toFixed(1)}%`, 'Growth']}
                      contentStyle={{ backgroundColor: '#1a1d24', border: '1px solid #2a4030', borderRadius: '8px', color: '#fff' }}
                    />
                    <Bar
                      dataKey="growth"
                      name="Growth %"
                      radius={[0, 4, 4, 0]}
                      barSize={24}
                      onClick={(data: any) => {
                        if (data && data.commodity) {
                          setOverviewCommodity(data.commodity);
                        }
                      }}
                      className="cursor-pointer hover:opacity-80 transition-opacity"
                    >
                      {overviewBoomCrops.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.growth > 0 ? '#19e63c' : '#ef4444'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

          </div>
        )}

        {viewMode === 'CROPS' && (
          <div className="bg-[#0f1117] -mx-4 lg:-mx-8 px-4 lg:px-8 py-8">
            <CropsDashboard
              data={filteredStateData}
              year={selectedYear}
              stateName={selectedState || 'National'}
            />
          </div>
        )}

        {viewMode === 'ANIMALS' && (
          <AnimalsDashboard
            data={filteredStateData}
            year={selectedYear}
            stateName={selectedState || 'National'}
          />
        )}

        {viewMode === 'LAND' && (
          <LandDashboard
            data={filteredStateData}
            year={selectedYear}
            stateName={selectedState || 'National'}
          />
        )}

        {viewMode === 'LABOR' && (
          <LaborDashboard
            data={filteredStateData}
            year={selectedYear}
            stateName={selectedState || 'National'}
          />
        )}

        {viewMode === 'ECONOMICS' && (
          <EconomicsDashboard
            data={filteredStateData}
            year={selectedYear}
            stateName={selectedState || 'National'}
          />
        )}

      </div>
    </div >
  );
}
