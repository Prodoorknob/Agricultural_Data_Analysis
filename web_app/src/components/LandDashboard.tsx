
'use client';

import React, { useState, useMemo, useEffect } from 'react';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
    AreaChart, Area, Legend
} from 'recharts';
import { getTopCrops, getLandUseTrends } from '../utils/processData';

interface LandDashboardProps {
    data: any[];
    year: number;
    stateName: string;
}

const COLORS = ['#2f855a', '#38a169', '#48bb78', '#68d391', '#9ae6b4', '#c6f6d5', '#f0fff4', '#e6fffa'];

// Composition chart colors (ordered to match categories)
const COMP_COLORS: Record<string, string> = {
    'Cropland': '#48bb78',
    'Grassland & Pasture': '#ecc94b',
    'Forest': '#2f855a',
    'Special Uses': '#805ad5',
    'Urban': '#ed8936',
    'Other': '#a0aec0',
};

export default function LandDashboard({ data, year, stateName }: LandDashboardProps) {
    const HARVESTED_METRIC = 'AREA HARVESTED';

    // ---- Major Land Use Data (separate JSON source) ----
    const [landUseJson, setLandUseJson] = useState<any>(null);

    useEffect(() => {
        fetch(`/data/land_use.json?t=${Date.now()}`)
            .then(res => res.ok ? res.json() : null)
            .then(data => {
                if (data) setLandUseJson(data);
            })
            .catch(err => console.warn('Failed to load land_use.json:', err));
    }, []);

    // 1. Get Commodities for Filter
    const commodities = useMemo(() => {
        const unique = new Set(data.map(d => d.commodity_desc));
        return Array.from(unique).filter(Boolean).sort();
    }, [data]);

    const [selectedCommodity, setSelectedCommodity] = useState<string>('All Crops');

    // 2. Filter Data by Commodity (if not 'All Crops')
    const filteredData = useMemo(() => {
        if (selectedCommodity === 'All Crops') return data;
        return data.filter(d => d.commodity_desc === selectedCommodity);
    }, [data, selectedCommodity]);

    // 3. Top Crops by Area Harvested
    const topLandCrops = useMemo(() => {
        return getTopCrops(data, year, HARVESTED_METRIC);
    }, [data, year]);

    // 4. Land Use Trends (Planted vs Harvested) -> Uses filteredData
    const landUseTrends = useMemo(() => {
        return getLandUseTrends(filteredData);
    }, [filteredData]);

    // 5. National Land Use Composition from JSON
    const landUseComposition = landUseJson?.composition || [];

    // 6. State-level Cropland vs Urban Change from JSON
    const landUseChange = landUseJson?.stateChange || [];

    // Calculate current totals for cards
    const currentYearData = landUseTrends.find(d => d.year === year);
    const totalPlanted = currentYearData ? currentYearData.planted : 0;
    const totalHarvested = currentYearData ? currentYearData.harvested : 0;
    const efficiency = totalPlanted > 0 ? (totalHarvested / totalPlanted) * 100 : 0;

    // Composition chart categories (for stacked area)
    const compositionCategories = ['Cropland', 'Grassland & Pasture', 'Forest', 'Special Uses', 'Urban', 'Other'];

    if (!data.length) {
        return <div className="p-12 text-center text-slate-400">No data available for Land & Area visualization.</div>;
    }

    return (
        <div className="space-y-8">

            {/* Filter Control */}
            <div className="bg-white p-4 rounded-xl shadow-sm border border-slate-200 flex items-center gap-4">
                <label className="font-semibold text-slate-700">Filter Trend by Crop:</label>
                <select
                    value={selectedCommodity}
                    onChange={(e) => setSelectedCommodity(e.target.value)}
                    className="p-2 border border-slate-300 rounded shadow-sm focus:ring-2 focus:ring-blue-500 outline-none max-w-xs"
                >
                    <option value="All Crops">All Crops</option>
                    {commodities.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
            </div>

            {/* KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <p className="text-sm text-slate-500 font-medium uppercase">Total Area Planted ({selectedCommodity === 'All Crops' ? 'All' : selectedCommodity})</p>
                    <p className="text-3xl font-bold text-slate-800 mt-2">{totalPlanted.toLocaleString()} <span className="text-sm font-normal text-slate-400">acres</span></p>
                </div>
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <p className="text-sm text-slate-500 font-medium uppercase">Total Area Harvested ({selectedCommodity === 'All Crops' ? 'All' : selectedCommodity})</p>
                    <p className="text-3xl font-bold text-slate-800 mt-2">{totalHarvested.toLocaleString()} <span className="text-sm font-normal text-slate-400">acres</span></p>
                </div>
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <p className="text-sm text-slate-500 font-medium uppercase">Harvest Efficiency</p>
                    <p className={`text-3xl font-bold mt-2 ${efficiency >= 90 ? 'text-green-600' : 'text-yellow-600'}`}>
                        {efficiency.toFixed(1)}%
                    </p>
                    <p className="text-xs text-slate-400 mt-1">% of planted area successfully harvested</p>
                </div>
            </div>

            {/* Row 1: Planted vs Harvested Trend */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                <div className="flex justify-between items-center mb-2">
                    <div>
                        <h3 className="text-xl font-semibold text-slate-800">Land Use Trends {selectedCommodity !== 'All Crops' && `(${selectedCommodity})`}</h3>
                        <p className="text-sm text-slate-500">Area Planted vs. Area Harvested (2001-2025)</p>
                    </div>
                </div>
                {/* Data integrity note */}
                <div className="mb-4 space-y-1">
                    <p className="text-xs text-slate-400">
                        Only showing {(landUseTrends as any).pairedCropCount ?? '?'} crops with <strong>both</strong> Planted &amp; Harvested data
                        ({(landUseTrends as any).excludedCropCount ?? '?'} harvest-only crops excluded)
                    </p>
                    {((landUseTrends as any).multiHarvestCrops?.length > 0) && (
                        <p className="text-xs text-amber-600 font-medium">
                            ⚡ Multi-harvest crops detected: {(landUseTrends as any).multiHarvestCrops.join(', ')}
                            — harvested area may exceed planted area due to multiple cuttings per season
                        </p>
                    )}
                </div>
                <div className="h-[400px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart
                            data={landUseTrends}
                            margin={{ top: 10, right: 30, left: 20, bottom: 0 }}
                        >
                            <defs>
                                <linearGradient id="colorPlanted" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#3182ce" stopOpacity={0.8} />
                                    <stop offset="95%" stopColor="#3182ce" stopOpacity={0} />
                                </linearGradient>
                                <linearGradient id="colorHarvested" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#38a169" stopOpacity={0.8} />
                                    <stop offset="95%" stopColor="#38a169" stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <XAxis dataKey="year" />
                            <YAxis tickFormatter={(val) => `${(val / 1000000).toFixed(1)}M`} />
                            <CartesianGrid strokeDasharray="3 3" vertical={false} />
                            <Tooltip
                                formatter={(val: number | undefined) => [val ? `${val.toLocaleString()} acres` : '0', '']}
                                labelStyle={{ color: '#2d3748' }}
                            />
                            <Legend />
                            <Area
                                type="monotone"
                                dataKey="planted"
                                name="Area Planted"
                                stroke="#3182ce"
                                fillOpacity={1}
                                fill="url(#colorPlanted)"
                            />
                            <Area
                                type="monotone"
                                dataKey="harvested"
                                name="Area Harvested"
                                stroke="#38a169"
                                fillOpacity={1}
                                fill="url(#colorHarvested)"
                            />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Row 2: Top Crops by Area */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                <h3 className="text-xl font-semibold mb-1 text-slate-800">Top Crops by Area Harvested</h3>
                <p className="text-sm text-slate-500 mb-6">Largest crops by acreage in {stateName}, {year}</p>
                <div className="h-[400px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                            layout="vertical"
                            data={topLandCrops}
                            margin={{ top: 5, right: 30, left: 100, bottom: 5 }}
                        >
                            <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={true} stroke="#e2e8f0" />
                            <XAxis type="number" tickFormatter={(val: number) => `${(val / 1000).toFixed(0)}k`} />
                            <YAxis
                                type="category"
                                dataKey="commodity"
                                width={120}
                                tick={{ fontSize: 11, fill: '#4a5568' }}
                            />
                            <Tooltip
                                formatter={(val: number | undefined) => [val ? `${val.toLocaleString()} acres` : '0', 'Area Harvested']}
                                contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                            />
                            <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                                {topLandCrops.map((_: any, index: number) => (
                                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Row 3: National Land Use Composition (from MajorLandUse.csv) */}
            {landUseComposition.length > 0 && (
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h3 className="text-xl font-semibold mb-1 text-slate-800">National Land Use Composition</h3>
                    <p className="text-sm text-slate-500 mb-6">How America&apos;s 2.3 billion acres are used (1945-2017)</p>
                    <div className="h-[450px] w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart
                                data={landUseComposition}
                                margin={{ top: 10, right: 30, left: 20, bottom: 0 }}
                            >
                                <XAxis dataKey="year" />
                                <YAxis
                                    tickFormatter={(val) => `${(val / 1000000000).toFixed(1)}B`}
                                    label={{ value: 'Acres', angle: -90, position: 'insideLeft' }}
                                />
                                <CartesianGrid strokeDasharray="3 3" />
                                <Tooltip
                                    formatter={(val: any, name: any) => [
                                        val ? `${(val / 1000000).toFixed(1)}M acres` : '0',
                                        name
                                    ]}
                                />
                                <Legend />
                                {compositionCategories.map(cat => (
                                    <Area
                                        key={cat}
                                        type="monotone"
                                        dataKey={cat}
                                        stackId="1"
                                        stroke={COMP_COLORS[cat]}
                                        fill={COMP_COLORS[cat]}
                                        fillOpacity={0.7}
                                    />
                                ))}
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            )}

            {/* Row 4: Cropland vs Urban Change by State */}
            {landUseChange.length > 0 && (
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h3 className="text-xl font-semibold mb-1 text-slate-800">Cropland vs. Urban Change by State</h3>
                    <p className="text-sm text-slate-500 mb-6">Percentage change 1945-2017 (Top 15 states by urban growth)</p>
                    <div className="h-[500px] w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart
                                layout="vertical"
                                data={landUseChange.sort((a: any, b: any) => b.urbanChange - a.urbanChange).slice(0, 15)}
                                margin={{ top: 5, right: 30, left: 100, bottom: 5 }}
                            >
                                <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={true} stroke="#e2e8f0" />
                                <XAxis type="number" tickFormatter={(val) => `${val.toFixed(0)}%`} />
                                <YAxis
                                    type="category"
                                    dataKey="state"
                                    width={120}
                                    tick={{ fontSize: 11, fill: '#4a5568' }}
                                />
                                <Tooltip
                                    formatter={(val: number | undefined) => [val !== undefined ? `${val.toFixed(1)}%` : '0%', 'Change']}
                                    contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                                />
                                <Legend />
                                <Bar dataKey="urbanChange" name="Urban Land Change" fill="#ed8936" radius={[0, 4, 4, 0]} barSize={12} />
                                <Bar dataKey="cropChange" name="Cropland Change" fill="#48bb78" radius={[0, 4, 4, 0]} barSize={12} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            )}
        </div>
    );
}
