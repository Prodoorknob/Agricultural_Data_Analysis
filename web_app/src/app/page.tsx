
'use client';

import USMap from '@/components/USMap';
import EconomicsDashboard from '@/components/EconomicsDashboard';
import LandDashboard from '@/components/LandDashboard';
import LaborDashboard from '@/components/LaborDashboard';
import CropsDashboard from '@/components/CropsDashboard';
import AnimalsDashboard from '@/components/AnimalsDashboard';
import React, { useState, useEffect, useMemo } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  BarChart, Bar, Cell
} from 'recharts';
import { fetchStateData, fetchNationalCrops, fetchLandUseData, fetchLaborData } from '../utils/serviceData';
import { getMapData, getLandUseTrends, getBoomCrops, filterData } from '../utils/processData';

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
    // 0. Base Filter (Removal of totals etc via processData util)
    // Note: fetchStateData returns raw parquet array. processData functions usually apply filterData.
    // But for Dashboard props, we want to pass pre-filtered data if possible, OR rely on components.
    // Here we apply GLOBAL UI filters (Sector/Group).

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
      // Logic: "All Crop Groups" (contains 'All') -> pass
      // specific group -> match d.group_desc
      if (selectedSubGroup && !selectedSubGroup.includes('All')) {
        // Handle minor naming mismatches if any. 
        // DB usually Uppercase: FIELD CROPS, VEGETABLES
        // UI: Field Crops
        const formattedUI = selectedSubGroup.toUpperCase();
        const dbGroup = d.group_desc?.toUpperCase();
        if (dbGroup !== formattedUI) {
          // Try exact match or contains?
          // Some groups might be distinct.
          // Let's rely on exact match for robust filters.
          // Exception: 'Fruit & Tree Nuts' vs 'FRUIT & TREE NUTS'
          if (dbGroup !== formattedUI) return false;
        }
      }
      return true;
    });
  };

  const filteredStateData = useMemo(() => {
    if (!stateData.length) return [];
    // Also apply 'filterData' to remove totals/invalid rows globally
    const clean = filterData(stateData);
    return filterByGroup(clean);
  }, [stateData, selectedSector, selectedSubGroup]);

  // For Map: Need state-level aggregates from National file (where state_alpha != 'US')
  const filteredMapSource = useMemo(() => {
    if (!nationalData.length) return [];
    // filterData removes 'Totals'.
    // We need to keep State rows (agg_level_desc='STATE')
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
    // Map needs Global Filtering?
    // Usually Map reflects "All US" for the selected measure.
    // If User selects "Crops" sector, map should show Crop Area.
    // If User selects "Corn", map should show Corn.
    // But map filter is currently high-level (Metric).
    // Let's pass the Group filtered data to Map generation.
    // But 'filteredMapSource' contains ALL states.
    // We must apply the current sector/group filter to it.
    const relevant = filterByGroup(filteredMapSource);
    return getMapData(relevant, selectedYear, mapMetric);
  }, [filteredMapSource, selectedYear, mapMetric, selectedSector, selectedSubGroup]);

  // --- Derived Data for Overview Charts ---

  // 1. Fastest Growing (Boom Crops)
  const overviewBoomCrops = useMemo(() => {
    // Use State Data if selected, else National Summary
    // But 'Boom Crops' usually needs distinct commodities. 
    // State data is best.
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

  const renderSidebar = () => (
    <div className="w-64 bg-slate-200 border-r border-slate-300 flex flex-col h-screen fixed left-0 top-0 overflow-y-auto p-4 z-20 shadow-lg">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-slate-800 leading-tight">USDA SURVEY <br /> STATISTICS</h1>
        <p className="text-xs text-slate-500 mt-2">Understanding farming one stat at a time</p>
      </div>

      {/* Filters */}
      <div className="space-y-4 mb-8">
        <div>
          <label className="text-xs font-semibold text-slate-600 mb-1 block">Year</label>
          <select
            value={selectedYear}
            onChange={(e) => setSelectedYear(Number(e.target.value))}
            className="w-full p-2 rounded border border-slate-300 text-sm"
          >
            <option value={0}>All Years</option>
            {YEARS.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>

        <div>
          <label className="text-xs font-semibold text-slate-600 mb-1 block">Sector</label>
          <select
            value={selectedSector}
            onChange={(e) => setSelectedSector(e.target.value)}
            className="w-full p-2 rounded border border-slate-300 text-sm"
          >
            {SECTORS.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        <div>
          <label className="text-xs font-semibold text-slate-600 mb-1 block">Group</label>
          <select
            value={selectedSubGroup}
            onChange={(e) => setSelectedSubGroup(e.target.value)}
            className="w-full p-2 rounded border border-slate-300 text-sm"
            disabled={currentGroupOptions.length <= 1}
          >
            {currentGroupOptions.map(g => <option key={g} value={g}>{g}</option>)}
          </select>
        </div>

        <div>
          <label className="text-xs font-semibold text-slate-600 mb-1 block">Map Metric</label>
          <select
            value={selectedMeasure}
            onChange={(e) => setSelectedMeasure(e.target.value)}
            className="w-full p-2 rounded border border-slate-300 text-sm"
          >
            {MEASURES.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
      </div>

      {/* Navigation */}
      <nav className="space-y-1">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Dashboards</p>
        {[
          { key: 'OVERVIEW', label: 'Overview', icon: '📊' },
          { key: 'CROPS', label: 'Crops', icon: '🌾' },
          { key: 'ANIMALS', label: 'Animals & Livestock', icon: '🐄' },
          { key: 'LAND', label: 'Land & Area', icon: '🗺️' },
          { key: 'LABOR', label: 'Labor & Operations', icon: '👷' },
          { key: 'ECONOMICS', label: 'Economics', icon: '💰' },
        ].map(({ key, label, icon }) => (
          <button
            key={key}
            onClick={() => setViewMode(key as ViewMode)}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all duration-150 ${viewMode === key
                ? 'bg-blue-600 text-white font-semibold shadow-md shadow-blue-600/20'
                : 'text-slate-600 hover:bg-slate-200 hover:text-slate-800'
              }`}
          >
            <span className="text-base">{icon}</span>
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="mt-auto pt-6 text-xs text-slate-400">
        Data Source: USDA Quickstats (Survey)
      </div>
    </div>
  );

  return (
    <div className={`flex min-h-screen ${viewMode === 'CROPS' ? 'bg-[#0f1117]' : 'bg-slate-50'}`} style={{ transition: 'background-color 0.3s ease' }}>
      {renderSidebar()}

      <div className={`flex-1 ml-64 p-8 ${viewMode === 'CROPS' ? 'text-slate-200' : ''}`}>
        {/* Header */}
        <div className="flex justify-between items-end mb-8 border-b border-slate-200 pb-4">
          <div>
            <h2 className="text-3xl font-bold text-slate-800">
              {viewMode === 'OVERVIEW' ? 'Agricultural Overview' :
                viewMode === 'CROPS' ? 'Crop Production' :
                  viewMode === 'ANIMALS' ? 'Livestock & Animals' :
                    viewMode === 'LAND' ? 'Land Use & Area' :
                      viewMode === 'LABOR' ? 'Labor & Operations' : 'Farm Economics'}
            </h2>
            <p className="text-slate-500 mt-1">
              {selectedState ? `Analyzing data for ` : 'National View'}
              <span className="font-bold text-blue-600">{selectedState ? selectedState : 'United States'}</span>
              <span className="mx-2">•</span>
              {selectedYear > 0 ? selectedYear : 'All Years'}
            </p>
          </div>
        </div>

        {/* Persistent Map */}
        <div className="mb-8">
          <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-semibold text-slate-700">US Agricultural Map - {selectedState || 'National View'}</h3>
              <span className="text-xs text-slate-500 bg-slate-100 px-2 py-1 rounded">Click a state to filter dashboard</span>
            </div>
            <div className="h-[600px]">
              <USMap
                data={mapData}
                selectedState={selectedState}
                onStateSelect={setSelectedState}
              />
            </div>
          </div>
        </div>

        {/* Content Area */}
        {viewMode === 'OVERVIEW' && (
          <div className="space-y-6">

            {/* Area Trends Chart */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
              <div className="flex justify-between items-center mb-2">
                <h3 className="text-lg font-semibold text-slate-700">
                  Area Trends Over Time
                  {overviewCommodity && <span className="text-blue-600 ml-2">({overviewCommodity})</span>}
                </h3>
                {overviewCommodity && (
                  <button
                    onClick={() => setOverviewCommodity(null)}
                    className="text-xs text-red-500 hover:underline"
                  >
                    Clear Filter
                  </button>
                )}
              </div>
              <div className="mb-4 space-y-1">
                <p className="text-xs text-slate-400">
                  Only crops with <strong>both</strong> Planted &amp; Harvested data
                  ({(overviewAreaTrends as any).excludedCropCount ?? '?'} harvest-only crops excluded)
                </p>
                {((overviewAreaTrends as any).multiHarvestCrops?.length > 0) && (
                  <p className="text-xs text-amber-600 font-medium">
                    ⚡ Multi-harvest: {(overviewAreaTrends as any).multiHarvestCrops.join(', ')} — harvested may exceed planted
                  </p>
                )}
              </div>
              <div className="h-[400px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={overviewAreaTrends}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                    <XAxis
                      dataKey="year"
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: '#64748b', fontSize: 12 }}
                      dy={10}
                    />
                    <YAxis
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: '#64748b', fontSize: 12 }}
                      tickFormatter={(val) => val >= 1000000 ? `${(val / 1000000).toFixed(1)}M` : val >= 1000 ? `${(val / 1000).toFixed(0)}k` : val}
                    />
                    <Tooltip
                      formatter={(val: number | string | undefined) => [new Intl.NumberFormat('en-US').format(Number(val || 0)) + ' acres', '']}
                      contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                    />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="planted"
                      name="Area Planted"
                      stroke="#3b82f6"
                      strokeWidth={3}
                      dot={{ r: 4, fill: '#3b82f6', strokeWidth: 0 }}
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

            {/* Fastest Growing Crops Chart */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
              <h3 className="text-lg font-semibold mb-4 text-slate-700">Fastest Growing Crops (2001-2023 Growth %) - Click bar to filter trend</h3>
              <div className="h-[500px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    layout="vertical"
                    data={overviewBoomCrops}
                    margin={{ top: 5, right: 30, left: 40, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke="#e2e8f0" />
                    <XAxis type="number" hide />
                    <YAxis
                      type="category"
                      dataKey="commodity"
                      width={120}
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: '#475569', fontSize: 11, fontWeight: 500 }}
                    />
                    <Tooltip
                      cursor={{ fill: '#f1f5f9' }}
                      formatter={(val: number | string | undefined) => [`${Number(val || 0).toFixed(1)}%`, 'Growth']}
                      contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
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
                        <Cell key={`cell-${index}`} fill={entry.growth > 0 ? '#10b981' : '#ef4444'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

          </div>
        )}

        {viewMode === 'CROPS' && (
          <div style={{ margin: '-32px', padding: '32px', background: '#0f1117', minHeight: 'calc(100vh - 0px)', borderRadius: '0' }}>
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
            data={filteredStateData} // Filtered data will now contain wage rates correctly filtered
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
