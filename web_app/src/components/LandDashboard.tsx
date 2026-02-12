'use client';

import React, { useMemo } from 'react';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
    AreaChart, Area, Legend, ScatterChart, Scatter, ZAxis
} from 'recharts';
import { getTopCrops, getLandUseTrends, getLandUseComposition, getLandUseChange } from '../lib/processData';

interface LandDashboardProps {
    data: any[];
    landUseData: any[];
    year: number;
    stateName: string;
}

const COLORS = ['#2f855a', '#38a169', '#48bb78', '#68d391', '#9ae6b4', '#c6f6d5', '#f0fff4', '#e6fffa'];

export default function LandDashboard({ data, landUseData, year, stateName }: LandDashboardProps) {
    const HARVESTED_METRIC = 'AREA HARVESTED';

    // 1. Top Crops by Area Harvested
    const topLandCrops = useMemo(() => {
        return getTopCrops(data, year, HARVESTED_METRIC);
    }, [data, year]);

    // 2. Land Use Trends (Planted vs Harvested)
    const landUseTrends = useMemo(() => {
        return getLandUseTrends(data);
    }, [data]);

    // 3. National Land Use Composition (Stacked Area)
    const landUseComposition = useMemo(() => {
        if (!landUseData || !landUseData.length) return [];
        return getLandUseComposition(landUseData);
    }, [landUseData]);

    // 4. Cropland vs Urban Change Scatter
    const landUseChange = useMemo(() => {
        if (!landUseData || !landUseData.length) return [];
        return getLandUseChange(landUseData);
    }, [landUseData]);

    // Calculate current totals for cards
    const currentYearData = landUseTrends.find(d => d.year === year);
    const totalPlanted = currentYearData ? currentYearData.planted : 0;
    const totalHarvested = currentYearData ? currentYearData.harvested : 0;
    const efficiency = totalPlanted > 0 ? (totalHarvested / totalPlanted) * 100 : 0;

    if (!data.length) {
        return <div className="p-12 text-center text-slate-400">No data available for Land & Area visualization.</div>;
    }

    return (
        <div className="space-y-8">

            {/* KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <p className="text-sm text-slate-500 font-medium uppercase">Total Area Planted</p>
                    <p className="text-3xl font-bold text-slate-800 mt-2">{totalPlanted.toLocaleString()} <span className="text-sm font-normal text-slate-400">acres</span></p>
                </div>
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <p className="text-sm text-slate-500 font-medium uppercase">Total Area Harvested</p>
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
                <h3 className="text-xl font-semibold mb-1 text-slate-800">Land Use Trends</h3>
                <p className="text-sm text-slate-500 mb-6">Area Planted vs. Area Harvested (2001-2025)</p>
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
                                {topLandCrops.map((_, index) => (
                                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Row 3: Land Use Composition (National) */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                <h3 className="text-xl font-semibold mb-1 text-slate-800">National Land Use Composition</h3>
                <p className="text-sm text-slate-500 mb-6">Cropland vs. Urban Land Area (1945-2017)</p>
                <div className="h-[400px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart
                            data={landUseComposition}
                            margin={{ top: 10, right: 30, left: 20, bottom: 0 }}
                        >
                            <defs>
                                <linearGradient id="colorCrop" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#82ca9d" stopOpacity={0.8} />
                                    <stop offset="95%" stopColor="#82ca9d" stopOpacity={0} />
                                </linearGradient>
                                <linearGradient id="colorUrban" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#ffc658" stopOpacity={0.8} />
                                    <stop offset="95%" stopColor="#ffc658" stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <XAxis dataKey="year" />
                            <YAxis tickFormatter={(val) => `${(val / 1000000).toFixed(0)}M`} label={{ value: 'Acres', angle: -90, position: 'insideLeft' }} />
                            <CartesianGrid strokeDasharray="3 3" />
                            <Tooltip formatter={(val: number | undefined) => val?.toLocaleString() || '0'} />
                            <Legend />
                            <Area type="monotone" dataKey="Cropland" stackId="1" stroke="#82ca9d" fill="url(#colorCrop)" />
                            <Area type="monotone" dataKey="Urban Land" stackId="1" stroke="#ffc658" fill="url(#colorUrban)" />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Row 4: Cropland vs Urban Change Scatter */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                <h3 className="text-xl font-semibold mb-1 text-slate-800">Cropland vs. Urban Change</h3>
                <p className="text-sm text-slate-500 mb-6">Percentage change by State (1945-2017)</p>
                <div className="h-[500px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <ScatterChart
                            margin={{ top: 20, right: 20, bottom: 20, left: 20 }}
                        >
                            <CartesianGrid />
                            <XAxis type="number" dataKey="urbanChange" name="Urban Land Change" unit="%" label={{ value: 'Urban Land Change %', position: 'bottom', offset: 0 }} />
                            <YAxis type="number" dataKey="cropChange" name="Cropland Change" unit="%" label={{ value: 'Cropland Change %', angle: -90, position: 'insideLeft' }} />
                            <ZAxis type="number" range={[60, 400]} /> {/* Standard dot size */}
                            <Tooltip cursor={{ strokeDasharray: '3 3' }} content={({ active, payload }) => {
                                if (active && payload && payload.length) {
                                    const data = payload[0].payload;
                                    return (
                                        <div className="bg-white p-3 border border-slate-200 shadow-md rounded">
                                            <p className="font-bold">{data.state}</p>
                                            <p className="text-sm">Urban: {data.urbanChange.toFixed(1)}%</p>
                                            <p className="text-sm">Cropland: {data.cropChange.toFixed(1)}%</p>
                                        </div>
                                    );
                                }
                                return null;
                            }} />
                            <Legend />
                            <Scatter name="States" data={landUseChange} fill="#8884d8">
                                {landUseChange.map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={entry.cropChange > 0 ? '#82ca9d' : '#ef4444'} />
                                ))}
                            </Scatter>
                        </ScatterChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </div>
    );
}
