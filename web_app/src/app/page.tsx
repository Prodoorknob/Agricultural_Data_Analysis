'use client';

import USMap from '@/components/USMap';
import EconomicsDashboard from '@/components/EconomicsDashboard';
import LandDashboard from '@/components/LandDashboard';
import LaborDashboard from '@/components/LaborDashboard';
import React, { useState, useEffect, useMemo } from 'react';
import { fetchStateData, fetchNationalCrops, fetchLandUseData, fetchLaborData } from '@/lib/data-service';
import { getMapData } from '@/lib/data-processing';

// --- Types ---
type ViewMode = 'OVERVIEW' | 'LAND' | 'LABOR' | 'ECONOMICS';

// --- Filter Options ---
const YEARS = Array.from({ length: 25 }, (_, i) => 2025 - i); // 2025 down to 2001
const SECTORS = ['All Sectors', 'Crops', 'Animals & Products', 'Economics'];
const CROP_GROUPS = ['All Crop Groups', 'Field Crops', 'Vegetables', 'Fruit & Tree Nuts', 'Horticulture'];
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
  const [selectedCropGroup, setSelectedCropGroup] = useState<string>('All Crop Groups');
  const [selectedMeasure, setSelectedMeasure] = useState<string>('Area Harvested (acres)');
  const [viewMode, setViewMode] = useState<ViewMode>('OVERVIEW');
  const [jumpToCrop, setJumpToCrop] = useState<string>('');

  // Data State
  const [nationalData, setNationalData] = useState<any[]>([]);
  const [stateData, setStateData] = useState<any[]>([]);
  const [landUseData, setLandUseData] = useState<any[]>([]);
  const [laborData, setLaborData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // --- Data Loading ---
  useEffect(() => {
    async function loadNational() {
      try {
        const national = await fetchNationalCrops();
        setNationalData(national);

        const landUse = await fetchLandUseData();
        setLandUseData(landUse);

        const labor = await fetchLaborData();
        setLaborData(labor);

        if (selectedState) {
          const state = await fetchStateData(selectedState);
          setStateData(state);
        } else {
          setStateData([]);
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
  }, [selectedState]);

  // --- Data Filtering ---
  const filteredStateData = useMemo(() => {
    if (!stateData.length) return [];

    return stateData.filter(d => {
      // Filter by Sector
      if (selectedSector !== 'All Sectors') {
        const sectorMap: Record<string, string> = {
          'Crops': 'CROPS',
          'Animals & Products': 'ANIMALS & PRODUCTS',
          'Economics': 'ECONOMICS'
        };
        // Case-insensitive check just in case
        if (d.sector_desc?.toUpperCase() !== sectorMap[selectedSector]) return false;
      }

      // Filter by Crop Group
      if (selectedCropGroup !== 'All Crop Groups') {
        // Direct match (assuming UPPERCASE in DB)
        if (d.group_desc?.toUpperCase() !== selectedCropGroup.toUpperCase()) return false;
      }

      return true;
    });
  }, [stateData, selectedSector, selectedCropGroup]);

  // --- Derived Data for Map ---
  // Map Metric Mapping: Map "Area Harvested (acres)" -> "AREA HARVESTED"
  const mapMetric = useMemo(() => {
    if (selectedMeasure.includes('Revenue')) return 'SALES';
    if (selectedMeasure.includes('Harvested')) return 'AREA HARVESTED';
    if (selectedMeasure.includes('Planted')) return 'AREA PLANTED';
    if (selectedMeasure.includes('Operations')) return 'OPERATIONS';
    if (selectedMeasure.includes('Inventory')) return 'INVENTORY';
    return 'AREA HARVESTED';
  }, [selectedMeasure]);

  const filteredNationalData = useMemo(() => {
    if (!nationalData.length) return [];

    return nationalData.filter(d => {
      // Filter by Sector
      if (selectedSector !== 'All Sectors') {
        const sectorMap: Record<string, string> = {
          'Crops': 'CROPS',
          'Animals & Products': 'ANIMALS & PRODUCTS',
          'Economics': 'ECONOMICS'
        };
        if (d.sector_desc?.toUpperCase() !== sectorMap[selectedSector]) return false;
      }

      // Filter by Crop Group
      if (selectedCropGroup !== 'All Crop Groups') {
        if (d.group_desc?.toUpperCase() !== selectedCropGroup.toUpperCase()) return false;
      }
      return true;
    });
  }, [nationalData, selectedSector, selectedCropGroup]);

  const mapData = useMemo(() => {
    if (!filteredNationalData.length) return {};
    return getMapData(filteredNationalData, selectedYear, mapMetric);
  }, [filteredNationalData, selectedYear, mapMetric]);

  // --- Render Helpers ---
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
          <label className="text-xs font-semibold text-slate-600 mb-1 block">Crop Group</label>
          <select
            value={selectedCropGroup}
            onChange={(e) => setSelectedCropGroup(e.target.value)}
            className="w-full p-2 rounded border border-slate-300 text-sm"
          >
            {CROP_GROUPS.map(g => <option key={g} value={g}>{g}</option>)}
          </select>
        </div>

        <div>
          <label className="text-xs font-semibold text-slate-600 mb-1 block">Measure</label>
          <select
            value={selectedMeasure}
            onChange={(e) => setSelectedMeasure(e.target.value)}
            className="w-full p-2 rounded border border-slate-300 text-sm"
          >
            {MEASURES.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
          <div className="mt-2 text-[10px] text-slate-500 bg-white p-2 rounded border border-slate-200">
            <p className="font-semibold mb-1">Measure Guide:</p>
            <ul className="list-disc pl-3 space-y-1">
              <li>Overview: {selectedMeasure}</li>
              <li>Labor: Operations</li>
              <li>Economics: Revenue</li>
            </ul>
          </div>
        </div>
      </div>

      {/* View Mode */}
      <div className="mb-8">
        <label className="text-xs font-semibold text-slate-600 mb-2 block">View Mode</label>
        <div className="space-y-2">
          {['OVERVIEW', 'LAND', 'LABOR', 'ECONOMICS'].map((mode) => (
            <label key={mode} className="flex items-center gap-2 cursor-pointer group">
              <input
                type="radio"
                name="viewMode"
                checked={viewMode === mode}
                onChange={() => setViewMode(mode as ViewMode)}
                className="accent-slate-700"
              />
              <span className={`text-sm ${viewMode === mode ? 'font-bold text-blue-800' : 'text-slate-600 group-hover:text-slate-900'}`}>
                {mode === 'OVERVIEW' ? 'Overview' :
                  mode === 'LAND' ? 'Land & Area' :
                    mode === 'LABOR' ? 'Labor & Operations' : 'Economics & Profitability'}
              </span>
            </label>
          ))}
        </div>
      </div>

      {/* Search & State */}
      <div className="mt-auto space-y-4">
        <div>
          <label className="text-xs font-semibold text-slate-600 mb-1 block">Jump to Crop</label>
          <input
            type="text"
            placeholder="Search crops..."
            value={jumpToCrop}
            onChange={(e) => setJumpToCrop(e.target.value)}
            className="w-full p-2 rounded border border-slate-300 text-sm"
          />
        </div>
        <div className="bg-white p-3 rounded border border-slate-300 shadow-sm">
          <p className="text-xs text-slate-500 font-bold uppercase">State</p>
          <p className="text-sm font-medium text-slate-800">{selectedState || 'None'}</p>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen bg-gray-50 font-sans text-slate-800">
      {renderSidebar()}

      <main className="ml-64 w-full p-8">
        {/* Helper Header */}
        <div className="mb-6 flex justify-between items-center">
          <h2 className="text-2xl font-bold text-slate-700">
            {viewMode === 'OVERVIEW' ? `US Agricultural Overview - ${selectedState || 'National'}` :
              viewMode === 'LAND' ? `Land Use & Area Analysis - ${selectedState || 'National'}` :
                viewMode === 'LABOR' ? `Labor & Operations Analysis - ${selectedState || 'National'}` :
                  `Economics & Profitability - ${selectedState || 'National'}`}
          </h2>
          <div className="text-xs text-slate-400">
            Data Sources: USDA NASS Quick Stats, USDA ERS Major Land Uses
          </div>
        </div>

        {/* Content Area */}
        {viewMode === 'OVERVIEW' && (
          <div className="space-y-6">
            <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200 min-h-[500px]">
              <h3 className="text-lg font-semibold mb-4">US States - Click to View Data</h3>
              <USMap
                data={mapData}
                selectedState={selectedState}
                onStateSelect={setSelectedState}
              />
            </div>
          </div>
        )}

        {viewMode === 'ECONOMICS' && (
          <EconomicsDashboard
            data={filteredStateData}
            year={selectedYear}
            stateName={selectedState || 'National'}
          />
        )}

        {/* Other placeholders */}
        {viewMode === 'LAND' && (
          <LandDashboard
            data={filteredStateData}
            landUseData={landUseData}
            year={selectedYear}
            stateName={selectedState || 'National'}
          />
        )}

        {viewMode === 'LABOR' && (
          <LaborDashboard
            laborData={laborData}
            year={selectedYear}
            stateName={selectedState || 'National'}
          />
        )}

      </main>
    </div>
  );
}
