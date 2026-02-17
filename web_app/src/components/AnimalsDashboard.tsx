
'use client';

import React, { useState, useMemo, useEffect } from 'react';
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
    BarChart, Bar, Cell
} from 'recharts';
import * as d3 from 'd3-array';
import { cleanValue, filterData } from '../utils/processData';

interface AnimalsDashboardProps {
    data: any[];
    year: number;
    stateName: string;
}

export default function AnimalsDashboard({ data, year, stateName }: AnimalsDashboardProps) {
    // 1. Filter for Animals Sector — apply filterData first to remove Census duplicates
    const allAnimalsData = useMemo(() => {
        return filterData(data).filter(d => d.sector_desc === 'ANIMALS & PRODUCTS');
    }, [data]);

    // 2. Get Unique Groups (Livestock, Poultry, Dairy, etc.)
    const groups = useMemo(() => {
        const unique = new Set(allAnimalsData.map(d => d.group_desc));
        const arr = Array.from(unique).filter(Boolean).sort();
        return ['All Categories', ...arr];
    }, [allAnimalsData]);

    const [selectedGroup, setSelectedGroup] = useState<string>('All Categories');

    // 3. Filter by Selected Group
    const filteredAnimalsData = useMemo(() => {
        if (selectedGroup === 'All Categories') return allAnimalsData;
        return allAnimalsData.filter(d => d.group_desc === selectedGroup);
    }, [allAnimalsData, selectedGroup]);

    // 4. Get Unique Commodities (from filtered set)
    const commodities = useMemo(() => {
        const unique = new Set(filteredAnimalsData.map(d => d.commodity_desc));
        return Array.from(unique).sort();
    }, [filteredAnimalsData]);

    const [selectedCommodity, setSelectedCommodity] = useState<string>('CATTLE');

    useEffect(() => {
        if (!commodities.includes(selectedCommodity)) {
            if (commodities.length > 0) {
                // Try smarter defaults based on selection
                if (commodities.includes('CATTLE')) setSelectedCommodity('CATTLE');
                else if (commodities.includes('HOGS')) setSelectedCommodity('HOGS');
                else if (commodities.includes('CHICKENS')) setSelectedCommodity('CHICKENS');
                else setSelectedCommodity(commodities[0]);
            } else {
                setSelectedCommodity('');
            }
        }
    }, [commodities, selectedCommodity]);

    // 5. Get Commodity Specific Data
    const commodityData = useMemo(() => {
        return filteredAnimalsData.filter(d => d.commodity_desc === selectedCommodity);
    }, [filteredAnimalsData, selectedCommodity]);

    // 6. Time Series Data
    const trendData = useMemo(() => {
        const yearGroups = d3.group(commodityData, d => d.year);
        const trends: any[] = [];

        yearGroups.forEach((rows, year) => {
            // Inventory (Head)
            const inventory = d3.sum(
                rows.filter(r => r.statisticcat_desc === 'INVENTORY' && r.unit_desc === 'HEAD'),
                r => cleanValue(r.value_num || r.Value)
            );

            // Sales (Head)
            const salesHead = d3.sum(
                rows.filter(r => r.statisticcat_desc === 'SALES' && r.unit_desc === 'HEAD'),
                r => cleanValue(r.value_num || r.Value)
            );

            // Sales ($)
            const salesRevenue = d3.sum(
                rows.filter(r => r.statisticcat_desc === 'SALES' && r.unit_desc === '$'),
                r => cleanValue(r.value_num || r.Value)
            );

            // Production (LB or generic)
            const production = d3.sum(
                rows.filter(r => r.statisticcat_desc === 'PRODUCTION'),
                r => cleanValue(r.value_num || r.Value)
            );
            const prodUnit = rows.find(r => r.statisticcat_desc === 'PRODUCTION')?.unit_desc || '';

            if (inventory > 0 || salesRevenue > 0 || production > 0) {
                trends.push({
                    year,
                    inventory,
                    salesHead,
                    salesRevenue,
                    production,
                    prodUnit
                });
            }
        });

        return trends.sort((a, b) => a.year - b.year);
    }, [commodityData]);

    const currentYearStats = useMemo(() => {
        return trendData.find(d => d.year === year) || {};
    }, [trendData, year]);

    if (!allAnimalsData.length) {
        return (
            <div className="p-12 text-center">
                <span className="material-symbols-outlined text-gray-600 text-[64px] mb-4 block">pets</span>
                <p className="text-gray-400">No animal data available.</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h2 className="text-2xl font-bold text-white flex items-center gap-3">
                    <span className="material-symbols-outlined text-[#19e63c] text-[32px]">pets</span>
                    Livestock & Animals Dashboard
                </h2>
                <p className="text-gray-400 text-sm mt-1">{stateName} • {year}</p>
            </div>

            {/* Filters */}
            <div className="bg-[#1a1d24] p-4 rounded-xl border border-[#2a4030] flex flex-wrap items-center gap-6">
                {/* Group Filter */}
                <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-gray-400 uppercase">Category</label>
                    <select
                        value={selectedGroup}
                        onChange={(e) => setSelectedGroup(e.target.value)}
                        className="bg-[#0f1117] border border-[#2a4030] text-white text-sm rounded-lg px-4 py-2 focus:ring-2 focus:ring-[#19e63c] appearance-none cursor-pointer min-w-[150px]"
                    >
                        {groups.map(g => <option key={g} value={g}>{g}</option>)}
                    </select>
                </div>

                {/* Commodity Filter */}
                <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-gray-400 uppercase">Livestock / Product</label>
                    <select
                        value={selectedCommodity}
                        onChange={(e) => setSelectedCommodity(e.target.value)}
                        className="bg-[#0f1117] border border-[#2a4030] text-white text-sm rounded-lg px-4 py-2 focus:ring-2 focus:ring-[#19e63c] appearance-none cursor-pointer min-w-[200px]"
                        disabled={!commodities.length}
                    >
                        {commodities.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                    {commodities.length === 0 && <span className="text-red-500 text-xs mt-1">No items found.</span>}
                </div>
            </div>

            {/* Key Metrics */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030] relative overflow-hidden">
                    <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-[#19e63c] to-transparent opacity-60"></div>
                    <div className="flex items-center gap-3 mb-4">
                        <div className="size-10 bg-[#19e63c]/20 rounded-lg flex items-center justify-center">
                            <span className="material-symbols-outlined text-[#19e63c] text-[24px]">warehouse</span>
                        </div>
                        <p className="text-gray-400 text-xs font-semibold uppercase tracking-wider">Inventory ({year})</p>
                    </div>
                    <p className="text-3xl font-bold text-white">
                        {currentYearStats.inventory ? currentYearStats.inventory.toLocaleString() : 'N/A'}
                    </p>
                    <p className="text-sm text-gray-500 mt-1">HEAD</p>
                </div>
                
                <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030] relative overflow-hidden">
                    <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-[#19e63c] to-transparent opacity-60"></div>
                    <div className="flex items-center gap-3 mb-4">
                        <div className="size-10 bg-[#19e63c]/20 rounded-lg flex items-center justify-center">
                            <span className="material-symbols-outlined text-[#19e63c] text-[24px]">monetization_on</span>
                        </div>
                        <p className="text-gray-400 text-xs font-semibold uppercase tracking-wider">Sales Revenue ({year})</p>
                    </div>
                    <p className="text-3xl font-bold text-[#19e63c]">
                        {currentYearStats.salesRevenue ? `$${currentYearStats.salesRevenue.toLocaleString()}` : 'N/A'}
                    </p>
                </div>
                
                <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030] relative overflow-hidden">
                    <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-[#19e63c] to-transparent opacity-60"></div>
                    <div className="flex items-center gap-3 mb-4">
                        <div className="size-10 bg-[#19e63c]/20 rounded-lg flex items-center justify-center">
                            <span className="material-symbols-outlined text-[#19e63c] text-[24px]">inventory_2</span>
                        </div>
                        <p className="text-gray-400 text-xs font-semibold uppercase tracking-wider">Production ({year})</p>
                    </div>
                    <p className="text-3xl font-bold text-white">
                        {currentYearStats.production ? currentYearStats.production.toLocaleString() : 'N/A'}
                    </p>
                    <p className="text-sm text-gray-500 mt-1">{currentYearStats.prodUnit}</p>
                </div>
            </div>

            {/* Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030]">
                    <div className="flex items-center gap-3 mb-4">
                        <span className="material-symbols-outlined text-[#19e63c] text-[24px]">show_chart</span>
                        <h3 className="text-lg font-semibold text-white">{selectedCommodity} Inventory Trend</h3>
                    </div>
                    <div className="h-[350px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={trendData}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#2a4030" />
                                <XAxis 
                                    dataKey="year" 
                                    axisLine={false} 
                                    tickLine={false}
                                    stroke="#718096"
                                    tick={{ fill: '#9ca3af' }}
                                />
                                <YAxis 
                                    axisLine={false} 
                                    tickLine={false} 
                                    tickFormatter={(val) => val >= 1000 ? `${(val / 1000).toFixed(0)}k` : val}
                                    stroke="#718096"
                                    tick={{ fill: '#9ca3af' }}
                                />
                                <Tooltip 
                                    formatter={(val: any) => [val ? val.toLocaleString() : '0', 'Head']}
                                    contentStyle={{
                                        backgroundColor: '#1a1d24',
                                        border: '1px solid #2a4030',
                                        borderRadius: '8px',
                                        color: '#fff'
                                    }}
                                    labelStyle={{ color: '#9ca3af' }}
                                />
                                <Line 
                                    type="monotone" 
                                    dataKey="inventory" 
                                    stroke="#19e63c" 
                                    strokeWidth={3} 
                                    dot={{ r: 4, fill: '#19e63c', strokeWidth: 2 }}
                                    activeDot={{ r: 6 }}
                                />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030]">
                    <div className="flex items-center gap-3 mb-4">
                        <span className="material-symbols-outlined text-[#19e63c] text-[24px]">bar_chart</span>
                        <h3 className="text-lg font-semibold text-white">{selectedCommodity} Sales Revenue Trend</h3>
                    </div>
                    <div className="h-[350px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={trendData}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#2a4030" />
                                <XAxis 
                                    dataKey="year" 
                                    axisLine={false} 
                                    tickLine={false}
                                    stroke="#718096"
                                    tick={{ fill: '#9ca3af' }}
                                />
                                <YAxis 
                                    axisLine={false} 
                                    tickLine={false} 
                                    tickFormatter={(val) => val >= 1000000 ? `$${(val / 1000000).toFixed(0)}M` : `$${val}`}
                                    stroke="#718096"
                                    tick={{ fill: '#9ca3af' }}
                                />
                                <Tooltip 
                                    formatter={(val: any) => [`$${val.toLocaleString()}`, 'Revenue']}
                                    contentStyle={{
                                        backgroundColor: '#1a1d24',
                                        border: '1px solid #2a4030',
                                        borderRadius: '8px',
                                        color: '#fff'
                                    }}
                                    labelStyle={{ color: '#9ca3af' }}
                                />
                                <Bar dataKey="salesRevenue" fill="#19e63c" radius={[8, 8, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>
        </div>
    );
}
