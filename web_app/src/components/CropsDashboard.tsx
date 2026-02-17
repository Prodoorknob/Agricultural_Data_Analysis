
'use client';

import React, { useState, useMemo, useEffect } from 'react';
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
    BarChart, Bar, Cell
} from 'recharts';
import * as d3 from 'd3-array';
import { cleanValue } from '../utils/processData';

interface CropsDashboardProps {
    data: any[];
    year: number;
    stateName: string;
}

export default function CropsDashboard({ data, year, stateName }: CropsDashboardProps) {
    // 1. Filter for Crops Sector
    // Ensure we are filtering strictly
    const cropsData = useMemo(() => {
        return data.filter(d => d.sector_desc === 'CROPS');
    }, [data]);

    // 2. Get Unique Commodities
    // This now depends on 'data' passed from page.tsx, so if 'Crop Group' filter is applied there,
    // this list will automatically update.
    const commodities = useMemo(() => {
        const unique = new Set(cropsData.map(d => d.commodity_desc));
        return Array.from(unique).sort();
    }, [cropsData]);

    // State for selected commodity
    const [selectedCommodity, setSelectedCommodity] = useState<string>('CORN');

    // Update selected if list changes
    useEffect(() => {
        if (!commodities.includes(selectedCommodity)) {
            if (commodities.length > 0) {
                // Ideally default to CORN if available
                if (commodities.includes('CORN')) setSelectedCommodity('CORN');
                else setSelectedCommodity(commodities[0]);
            } else {
                setSelectedCommodity('');
            }
        }
    }, [commodities, selectedCommodity]);

    // 3. Get Commodity Specific Data
    const commodityData = useMemo(() => {
        return cropsData.filter(d => d.commodity_desc === selectedCommodity);
    }, [cropsData, selectedCommodity]);

    // 4. Time Series Data for Charts
    const trendData = useMemo(() => {
        const yearGroups = d3.group(commodityData, d => d.year);
        const trends: any[] = [];

        yearGroups.forEach((rows, year) => {
            // Sum metrics for this year
            const production = d3.sum(
                rows.filter(r => r.statisticcat_desc === 'PRODUCTION'),
                r => cleanValue(r.value_num || r.Value)
            );
            const yieldVal = d3.mean( // Yield is usually an average or single value
                rows.filter(r => r.statisticcat_desc === 'YIELD'),
                r => cleanValue(r.value_num || r.Value)
            );
            const areaHarvested = d3.sum(
                rows.filter(r => r.statisticcat_desc === 'AREA HARVESTED'),
                r => cleanValue(r.value_num || r.Value)
            );

            // Get units (take first found)
            const prodUnit = rows.find(r => r.statisticcat_desc === 'PRODUCTION')?.unit_desc || '';
            const yieldUnit = rows.find(r => r.statisticcat_desc === 'YIELD')?.unit_desc || '';

            if (production > 0 || areaHarvested > 0 || (yieldVal !== undefined && yieldVal > 0)) {
                trends.push({
                    year,
                    production,
                    yield: yieldVal || 0,
                    areaHarvested,
                    prodUnit,
                    yieldUnit
                });
            }
        });

        return trends.sort((a, b) => a.year - b.year);
    }, [commodityData]);

    const currentYearStats = useMemo(() => {
        return trendData.find(d => d.year === year) || {};
    }, [trendData, year]);

    if (!cropsData.length) {
        return <div className="p-12 text-center text-slate-400">No crop data available.</div>;
    }

    // Determine Y-Axis domains roughly
    const maxProduction = d3.max(trendData, d => d.production) || 100;
    const maxYield = d3.max(trendData, d => d.yield) || 100;

    return (
        <div className="space-y-6">
            {/* Controls */}
            <div className="bg-white p-4 rounded-xl shadow-sm border border-slate-200 flex items-center gap-4">
                <label className="font-semibold text-slate-700">Select Commodity:</label>
                <select
                    value={selectedCommodity}
                    onChange={(e) => setSelectedCommodity(e.target.value)}
                    className="p-2 border border-slate-300 rounded shadow-sm focus:ring-2 focus:ring-blue-500 outline-none"
                    disabled={!commodities.length}
                >
                    {commodities.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
                {commodities.length === 0 && <span className="text-red-500 text-sm">No commodities found for selected group.</span>}
            </div>

            {/* Key Metrics Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <p className="text-sm text-slate-500 font-semibold uppercase">Production ({year})</p>
                    <p className="text-3xl font-bold text-slate-800 mt-2">
                        {currentYearStats.production ? currentYearStats.production.toLocaleString() : 'N/A'}
                        <span className="text-sm text-slate-400 font-normal ml-2">{currentYearStats.prodUnit}</span>
                    </p>
                </div>
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <p className="text-sm text-slate-500 font-semibold uppercase">Yield ({year})</p>
                    <p className="text-3xl font-bold text-emerald-600 mt-2">
                        {currentYearStats.yield ? currentYearStats.yield.toLocaleString() : 'N/A'}
                        <span className="text-sm text-slate-400 font-normal ml-2">{currentYearStats.yieldUnit}</span>
                    </p>
                </div>
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <p className="text-sm text-slate-500 font-semibold uppercase">Area Harvested ({year})</p>
                    <p className="text-3xl font-bold text-blue-600 mt-2">
                        {currentYearStats.areaHarvested ? currentYearStats.areaHarvested.toLocaleString() : 'N/A'}
                        <span className="text-sm text-slate-400 font-normal ml-2">ACRES</span>
                    </p>
                </div>
            </div>

            {/* Dual Axis Chart: Production & Yield */}
            <div className="grid grid-cols-1 gap-6">
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h3 className="text-lg font-semibold mb-4 text-slate-700">{selectedCommodity} Production vs Yield Trend</h3>
                    <div className="h-[400px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={trendData}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                                <XAxis dataKey="year" axisLine={false} tickLine={false} />
                                <YAxis
                                    yAxisId="left"
                                    orientation="left"
                                    axisLine={false}
                                    tickLine={false}
                                    tickFormatter={(val) => val >= 1000000 ? `${(val / 1000000).toFixed(1)}M` : val.toLocaleString()}
                                    label={{ value: 'Production', angle: -90, position: 'insideLeft', style: { fill: '#2563eb' } }}
                                />
                                <YAxis
                                    yAxisId="right"
                                    orientation="right"
                                    axisLine={false}
                                    tickLine={false}
                                    domain={['auto', 'auto']}
                                    label={{ value: 'Yield', angle: 90, position: 'insideRight', style: { fill: '#059669' } }}
                                />
                                <Tooltip
                                    formatter={(val: any, name: any) => [
                                        val ? val.toLocaleString() : '0',
                                        name === 'production' ? 'Production' : 'Yield'
                                    ]}
                                    labelStyle={{ color: '#64748b' }}
                                />
                                <Legend />
                                <Line
                                    yAxisId="left"
                                    type="monotone"
                                    dataKey="production"
                                    name="Production"
                                    stroke="#2563eb"
                                    strokeWidth={3}
                                    dot={{ r: 3 }}
                                />
                                <Line
                                    yAxisId="right"
                                    type="monotone"
                                    dataKey="yield"
                                    name="Yield"
                                    stroke="#059669"
                                    strokeWidth={3}
                                    dot={{ r: 3 }}
                                />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>

            {/* Area Harvested Trend */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                <h3 className="text-lg font-semibold mb-4 text-slate-700">{selectedCommodity} Area Harvested Trend</h3>
                <div className="h-[350px]">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={trendData}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                            <XAxis dataKey="year" axisLine={false} tickLine={false} />
                            <YAxis axisLine={false} tickLine={false} tickFormatter={(val) => val >= 1000 ? `${(val / 1000).toFixed(0)}k` : val} />
                            <Tooltip
                                formatter={(val: any) => [val ? val.toLocaleString() : '0', 'Acres']}
                                labelStyle={{ color: '#64748b' }}
                                cursor={{ fill: '#f8fafc' }}
                            />
                            <Bar dataKey="areaHarvested" fill="#cbd5e1" radius={[4, 4, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </div>
    );
}
