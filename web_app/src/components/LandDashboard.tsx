'use client';

import React, { useState, useMemo, useEffect } from 'react';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
    AreaChart, Area, Legend, ScatterChart, Scatter, ZAxis, ReferenceLine, Label
} from 'recharts';
import { getTopCrops, getLandUseTrends } from '../utils/processData';
import { palette, chartDefaults } from '../utils/design';

interface LandDashboardProps {
    data: any[];
    year: number;
    stateName: string;
}

const COLORS = ['#19e63c', '#16c934', '#13ac2c', '#109024', '#0d731c', '#0a5614', '#073a0c', '#041d06'];

// Composition chart colors for National Land Use
const COMP_COLORS: Record<string, string> = {
    'Cropland': '#19e63c',
    'Grassland & Pasture': '#ecc94b',
    'Forest': '#2f855a',
    'Special Uses': '#805ad5',
    'Urban': '#ed8936',
    'Other': '#718096',
};

// Quadrant colors for scatter chart
const QUADRANT_COLORS = {
    urbanSprawl: '#ef4444',    // Lost cropland, gained urban
    growingBoth: '#22c55e',    // Gained both
    farmlandFocus: '#3b82f6',  // Gained cropland, lost urban
    declining: '#6b7280',      // Lost both
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
    const [excludeMultiHarvest, setExcludeMultiHarvest] = useState<boolean>(false);

    // 2. Compute multi-harvest information first (needed for toggle)
    const rawLandUseTrends = useMemo(() => {
        return getLandUseTrends(data);
    }, [data]);

    const multiHarvestCrops: string[] = (rawLandUseTrends as any).multiHarvestCrops || [];

    // 3. Filter Data by Commodity + optional multi-harvest exclusion
    const filteredData = useMemo(() => {
        let result = data;
        if (selectedCommodity !== 'All Crops') {
            result = result.filter(d => d.commodity_desc === selectedCommodity);
        }
        if (excludeMultiHarvest && multiHarvestCrops.length > 0) {
            result = result.filter(d => !multiHarvestCrops.includes(d.commodity_desc));
        }
        return result;
    }, [data, selectedCommodity, excludeMultiHarvest, multiHarvestCrops]);

    // 4. Top Crops by Area Harvested
    const topLandCrops = useMemo(() => {
        return getTopCrops(data, year, HARVESTED_METRIC);
    }, [data, year]);

    // 5. Land Use Trends (Planted vs Harvested) -> Uses filteredData
    const landUseTrends = useMemo(() => {
        return getLandUseTrends(filteredData);
    }, [filteredData]);

    // 6. National Land Use Composition from JSON
    const landUseComposition = landUseJson?.composition || [];

    // 7. State-level Cropland vs Urban Change from JSON
    const landUseChange = landUseJson?.stateChange || [];

    // Calculate current totals for cards
    const currentYearData = landUseTrends.find(d => d.year === year);
    const totalPlanted = currentYearData ? currentYearData.planted : 0;
    const totalHarvested = currentYearData ? currentYearData.harvested : 0;
    const efficiency = totalPlanted > 0 ? (totalHarvested / totalPlanted) * 100 : 0;

    // Composition chart categories (for stacked area)
    const compositionCategories = ['Cropland', 'Grassland & Pasture', 'Forest', 'Special Uses', 'Urban', 'Other'];

    // Scatter data with quadrant classification
    const scatterData = useMemo(() => {
        return landUseChange.map((d: any) => ({
            ...d,
            quadrant: d.urbanChange >= 0 && d.cropChange < 0
                ? 'urbanSprawl'
                : d.urbanChange >= 0 && d.cropChange >= 0
                    ? 'growingBoth'
                    : d.urbanChange < 0 && d.cropChange >= 0
                        ? 'farmlandFocus'
                        : 'declining',
        }));
    }, [landUseChange]);

    if (!data.length) {
        return (
            <div className="p-12 text-center">
                <span className="material-symbols-outlined text-gray-600 text-[64px] mb-4 block">landscape</span>
                <p className="text-gray-400">No data available for Land & Area visualization.</p>
            </div>
        );
    }

    return (
        <div className="space-y-8">
            {/* Header with Filter + Multi-Harvest Toggle */}
            <div className="flex items-center justify-between gap-4 flex-wrap">
                <div>
                    <h2 className="text-2xl font-bold text-white flex items-center gap-3">
                        <span className="material-symbols-outlined text-[#19e63c] text-[32px]">landscape</span>
                        Land & Area Dashboard
                    </h2>
                    <p className="text-gray-400 text-sm mt-1">{stateName} • {year}</p>
                </div>

                <div className="flex items-center gap-4">
                    {/* Multi-harvest toggle */}
                    {multiHarvestCrops.length > 0 && (
                        <button
                            onClick={() => setExcludeMultiHarvest(!excludeMultiHarvest)}
                            className={`flex items-center gap-2 text-xs font-medium px-3 py-2 rounded-lg border transition-all ${excludeMultiHarvest
                                    ? 'bg-amber-500/20 border-amber-500/40 text-amber-300'
                                    : 'bg-[#0f1117] border-[#2a4030] text-gray-400 hover:text-white'
                                }`}
                        >
                            <span className="material-symbols-outlined text-[16px]">
                                {excludeMultiHarvest ? 'filter_alt' : 'filter_alt_off'}
                            </span>
                            {excludeMultiHarvest ? 'Multi-harvest excluded' : 'Exclude multi-harvest'}
                        </button>
                    )}

                    {/* Commodity filter */}
                    <div className="flex items-center gap-3">
                        <label className="text-gray-400 text-sm font-semibold">Filter by Crop:</label>
                        <select
                            value={selectedCommodity}
                            onChange={(e) => setSelectedCommodity(e.target.value)}
                            className="bg-[#0f1117] border border-[#2a4030] text-white text-sm rounded-lg px-4 py-2 focus:ring-2 focus:ring-[#19e63c] appearance-none cursor-pointer min-w-[180px]"
                        >
                            <option value="All Crops">All Crops</option>
                            {commodities.map(c => <option key={c} value={c}>{c}</option>)}
                        </select>
                    </div>
                </div>
            </div>

            {/* KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030] relative overflow-hidden">
                    <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-[#19e63c] to-transparent opacity-60"></div>
                    <div className="flex items-center gap-3 mb-4">
                        <div className="size-10 bg-[#19e63c]/20 rounded-lg flex items-center justify-center">
                            <span className="material-symbols-outlined text-[#19e63c] text-[24px]">eco</span>
                        </div>
                        <p className="text-gray-400 text-xs font-semibold uppercase tracking-wider">Total Area Planted</p>
                    </div>
                    <p className="text-3xl font-bold text-white">{totalPlanted.toLocaleString()}</p>
                    <p className="text-sm text-gray-500 mt-1">acres</p>
                    <p className="text-xs text-gray-600 mt-2">{selectedCommodity === 'All Crops' ? 'All Crops' : selectedCommodity}</p>
                </div>

                <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030] relative overflow-hidden">
                    <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-[#19e63c] to-transparent opacity-60"></div>
                    <div className="flex items-center gap-3 mb-4">
                        <div className="size-10 bg-[#19e63c]/20 rounded-lg flex items-center justify-center">
                            <span className="material-symbols-outlined text-[#19e63c] text-[24px]">agriculture</span>
                        </div>
                        <p className="text-gray-400 text-xs font-semibold uppercase tracking-wider">Area Harvested</p>
                    </div>
                    <p className="text-3xl font-bold text-white">{totalHarvested.toLocaleString()}</p>
                    <p className="text-sm text-gray-500 mt-1">acres</p>
                </div>

                <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030] relative overflow-hidden">
                    <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-[#19e63c] to-transparent opacity-60"></div>
                    <div className="flex items-center gap-3 mb-4">
                        <div className="size-10 bg-[#19e63c]/20 rounded-lg flex items-center justify-center">
                            <span className="material-symbols-outlined text-[#19e63c] text-[24px]">trending_up</span>
                        </div>
                        <p className="text-gray-400 text-xs font-semibold uppercase tracking-wider">Harvest Efficiency</p>
                    </div>
                    <p className={`text-3xl font-bold ${efficiency >= 90 ? 'text-[#19e63c]' : 'text-yellow-500'}`}>
                        {efficiency.toFixed(1)}%
                    </p>
                    <p className="text-xs text-gray-500 mt-2">% of planted area successfully harvested</p>
                </div>
            </div>

            {/* Row 1: Planted vs Harvested Trend */}
            <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030]">
                <div className="flex items-center gap-3 mb-4">
                    <span className="material-symbols-outlined text-[#19e63c] text-[28px]">show_chart</span>
                    <div>
                        <h3 className="text-xl font-semibold text-white">
                            Land Use Trends {selectedCommodity !== 'All Crops' && `(${selectedCommodity})`}
                        </h3>
                        <p className="text-sm text-gray-400">Area Planted vs. Area Harvested (2001-2025)</p>
                    </div>
                </div>
                {/* Data integrity note */}
                <div className="mb-4 space-y-1">
                    <p className="text-xs text-gray-500">
                        Only showing {(landUseTrends as any).pairedCropCount ?? '?'} crops with <strong>both</strong> Planted &amp; Harvested data
                        ({(landUseTrends as any).excludedCropCount ?? '?'} harvest-only crops excluded)
                    </p>
                    {((landUseTrends as any).multiHarvestCrops?.length > 0) && (
                        <p className="text-xs text-amber-500 font-medium">
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
                                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8} />
                                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.1} />
                                </linearGradient>
                                <linearGradient id="colorHarvested" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#19e63c" stopOpacity={0.8} />
                                    <stop offset="95%" stopColor="#19e63c" stopOpacity={0.1} />
                                </linearGradient>
                            </defs>
                            <XAxis dataKey="year" stroke="#718096" tick={{ fill: '#9ca3af' }} />
                            <YAxis
                                tickFormatter={(val) => `${(val / 1000000).toFixed(1)}M`}
                                stroke="#718096"
                                tick={{ fill: '#9ca3af' }}
                            />
                            <CartesianGrid strokeDasharray="3 3" stroke="#2a4030" vertical={false} />
                            <Tooltip
                                formatter={(val: number | undefined) => [val ? `${val.toLocaleString()} acres` : '0', '']}
                                contentStyle={{
                                    backgroundColor: '#1a1d24',
                                    border: '1px solid #2a4030',
                                    borderRadius: '8px',
                                    color: '#fff'
                                }}
                                labelStyle={{ color: '#9ca3af' }}
                            />
                            <Legend wrapperStyle={{ color: '#9ca3af' }} />
                            <Area
                                type="monotone"
                                dataKey="planted"
                                name="Area Planted"
                                stroke="#3b82f6"
                                strokeWidth={2}
                                fillOpacity={1}
                                fill="url(#colorPlanted)"
                            />
                            <Area
                                type="monotone"
                                dataKey="harvested"
                                name="Area Harvested"
                                stroke="#19e63c"
                                strokeWidth={2}
                                fillOpacity={1}
                                fill="url(#colorHarvested)"
                            />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Row 2: Top Crops by Area — CLICKABLE to filter trends */}
            <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030]">
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                        <span className="material-symbols-outlined text-[#19e63c] text-[28px]">bar_chart</span>
                        <div>
                            <h3 className="text-xl font-semibold text-white">Top Crops by Area Harvested</h3>
                            <p className="text-sm text-gray-400">Click a bar to filter Land Use Trends • {stateName}, {year}</p>
                        </div>
                    </div>
                    {selectedCommodity !== 'All Crops' && (
                        <button
                            onClick={() => setSelectedCommodity('All Crops')}
                            className="flex items-center gap-1 text-xs font-medium px-3 py-1.5 rounded-lg bg-[#19e63c]/10 border border-[#19e63c]/30 text-[#19e63c] hover:bg-[#19e63c]/20 transition-all"
                        >
                            <span className="material-symbols-outlined text-[14px]">close</span>
                            Clear: {selectedCommodity}
                        </button>
                    )}
                </div>
                <div className="h-[400px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                            layout="vertical"
                            data={topLandCrops}
                            margin={{ top: 5, right: 30, left: 120, bottom: 5 }}
                        >
                            <CartesianGrid strokeDasharray="3 3" stroke="#2a4030" horizontal={true} vertical={true} />
                            <XAxis
                                type="number"
                                tickFormatter={(val: number) => `${(val / 1000).toFixed(0)}k`}
                                stroke="#718096"
                                tick={{ fill: '#9ca3af' }}
                            />
                            <YAxis
                                type="category"
                                dataKey="commodity"
                                width={110}
                                tick={{ fontSize: 11, fill: '#9ca3af' }}
                                stroke="#718096"
                            />
                            <Tooltip
                                formatter={(val: number | undefined) => [val ? `${val.toLocaleString()} acres` : '0', 'Area Harvested']}
                                contentStyle={{
                                    backgroundColor: '#1a1d24',
                                    border: '1px solid #2a4030',
                                    borderRadius: '8px',
                                    color: '#fff'
                                }}
                            />
                            <Bar
                                dataKey="value"
                                radius={[0, 8, 8, 0]}
                                onClick={(barData: any) => {
                                    if (barData?.commodity) {
                                        setSelectedCommodity(
                                            selectedCommodity === barData.commodity ? 'All Crops' : barData.commodity
                                        );
                                    }
                                }}
                                className="cursor-pointer"
                            >
                                {topLandCrops.map((entry: any, index: number) => (
                                    <Cell
                                        key={`cell-${index}`}
                                        fill={entry.commodity === selectedCommodity ? '#19e63c' : COLORS[index % COLORS.length]}
                                        opacity={selectedCommodity !== 'All Crops' && entry.commodity !== selectedCommodity ? 0.4 : 1}
                                        stroke={entry.commodity === selectedCommodity ? '#19e63c' : 'transparent'}
                                        strokeWidth={entry.commodity === selectedCommodity ? 2 : 0}
                                    />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Row 3: National Land Use Composition (from MajorLandUse.csv) */}
            {landUseComposition.length > 0 && (
                <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030]">
                    <div className="flex items-center gap-3 mb-4">
                        <span className="material-symbols-outlined text-[#19e63c] text-[28px]">public</span>
                        <div>
                            <h3 className="text-xl font-semibold text-white">National Land Use Composition</h3>
                            <p className="text-sm text-gray-400">How America&apos;s 2.3 billion acres are used (1945-2017)</p>
                        </div>
                    </div>
                    <div className="h-[450px] w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart
                                data={landUseComposition}
                                margin={{ top: 10, right: 30, left: 20, bottom: 0 }}
                            >
                                <XAxis
                                    dataKey="year"
                                    stroke="#718096"
                                    tick={{ fill: '#9ca3af' }}
                                />
                                <YAxis
                                    tickFormatter={(val) => `${(val / 1000000000).toFixed(1)}B`}
                                    label={{
                                        value: 'Acres',
                                        angle: -90,
                                        position: 'insideLeft',
                                        style: { fill: '#9ca3af' }
                                    }}
                                    stroke="#718096"
                                    tick={{ fill: '#9ca3af' }}
                                />
                                <CartesianGrid strokeDasharray="3 3" stroke="#2a4030" />
                                <Tooltip
                                    formatter={(val: any, name: any) => [
                                        val ? `${(val / 1000000).toFixed(1)}M acres` : '0',
                                        name
                                    ]}
                                    contentStyle={{
                                        backgroundColor: '#1a1d24',
                                        border: '1px solid #2a4030',
                                        borderRadius: '8px',
                                        color: '#fff'
                                    }}
                                    labelStyle={{ color: '#9ca3af' }}
                                />
                                <Legend wrapperStyle={{ color: '#9ca3af' }} />
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

            {/* Row 4: Cropland vs Urban — Scatter Quadrant Chart */}
            {scatterData.length > 0 && (
                <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030]">
                    <div className="flex items-center gap-3 mb-4">
                        <span className="material-symbols-outlined text-[#19e63c] text-[28px]">scatter_plot</span>
                        <div>
                            <h3 className="text-xl font-semibold text-white">Cropland vs. Urban Growth by State</h3>
                            <p className="text-sm text-gray-400">Each dot is a state — % change from 1945 to 2017</p>
                        </div>
                    </div>

                    {/* Quadrant legend */}
                    <div className="flex flex-wrap gap-4 mb-4">
                        {[
                            { label: '🏙️ Urban Sprawl', desc: '+Urban, −Cropland', color: QUADRANT_COLORS.urbanSprawl },
                            { label: '📈 Growing Both', desc: '+Urban, +Cropland', color: QUADRANT_COLORS.growingBoth },
                            { label: '🌾 Farmland Focus', desc: '−Urban, +Cropland', color: QUADRANT_COLORS.farmlandFocus },
                            { label: '📉 Declining', desc: '−Urban, −Cropland', color: QUADRANT_COLORS.declining },
                        ].map(q => (
                            <div key={q.label} className="flex items-center gap-2 text-xs">
                                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: q.color }}></div>
                                <span className="text-gray-300 font-medium">{q.label}</span>
                                <span className="text-gray-500">({q.desc})</span>
                            </div>
                        ))}
                    </div>

                    <div className="h-[500px] w-full">
                        <ResponsiveContainer width="100%" height="100%">
                            <ScatterChart margin={{ top: 20, right: 40, bottom: 30, left: 40 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#2a4030" />
                                <XAxis
                                    type="number"
                                    dataKey="urbanChange"
                                    name="Urban Change"
                                    tickFormatter={(val) => `${val.toFixed(0)}%`}
                                    stroke="#718096"
                                    tick={{ fill: '#9ca3af', fontSize: 11 }}
                                >
                                    <Label value="Urban Land Change (%)" position="bottom" offset={10} style={{ fill: '#9ca3af', fontSize: 12 }} />
                                </XAxis>
                                <YAxis
                                    type="number"
                                    dataKey="cropChange"
                                    name="Cropland Change"
                                    tickFormatter={(val) => `${val.toFixed(0)}%`}
                                    stroke="#718096"
                                    tick={{ fill: '#9ca3af', fontSize: 11 }}
                                >
                                    <Label value="Cropland Change (%)" angle={-90} position="insideLeft" offset={10} style={{ fill: '#9ca3af', fontSize: 12 }} />
                                </YAxis>
                                <ZAxis range={[80, 80]} />
                                {/* Quadrant reference lines */}
                                <ReferenceLine x={0} stroke="#4a5568" strokeDasharray="4 4" />
                                <ReferenceLine y={0} stroke="#4a5568" strokeDasharray="4 4" />
                                <Tooltip
                                    cursor={{ strokeDasharray: '3 3', stroke: '#4a5568' }}
                                    content={({ active, payload }: any) => {
                                        if (!active || !payload?.length) return null;
                                        const d = payload[0].payload;
                                        return (
                                            <div className="bg-[#1a1d24] border border-[#2a4030] rounded-lg px-4 py-3 text-sm">
                                                <p className="text-white font-bold mb-1">{d.state}</p>
                                                <p className="text-gray-300">Urban: <span className={d.urbanChange >= 0 ? 'text-orange-400' : 'text-blue-400'}>{d.urbanChange > 0 ? '+' : ''}{d.urbanChange?.toFixed(1)}%</span></p>
                                                <p className="text-gray-300">Cropland: <span className={d.cropChange >= 0 ? 'text-green-400' : 'text-red-400'}>{d.cropChange > 0 ? '+' : ''}{d.cropChange?.toFixed(1)}%</span></p>
                                            </div>
                                        );
                                    }}
                                />
                                <Scatter
                                    data={scatterData}
                                    shape={(props: any) => {
                                        const { cx, cy, payload } = props;
                                        const color = QUADRANT_COLORS[payload.quadrant as keyof typeof QUADRANT_COLORS] || '#6b7280';
                                        return (
                                            <g>
                                                <circle cx={cx} cy={cy} r={6} fill={color} opacity={0.8} stroke={color} strokeWidth={1} />
                                                <text x={cx + 9} y={cy + 4} fill="#9ca3af" fontSize={9} fontWeight={500}>
                                                    {payload.state?.slice(0, 2)}
                                                </text>
                                            </g>
                                        );
                                    }}
                                />
                            </ScatterChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            )}
        </div>
    );
}
