
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
        return <div className="p-12 text-center text-slate-400">No animal data available.</div>;
    }

    return (
        <div className="space-y-6">
            <div className="bg-white p-4 rounded-xl shadow-sm border border-slate-200 flex flex-wrap items-center gap-6">

                {/* Group Filter */}
                <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-slate-500 uppercase">Category</label>
                    <select
                        value={selectedGroup}
                        onChange={(e) => setSelectedGroup(e.target.value)}
                        className="p-2 border border-slate-300 rounded shadow-sm focus:ring-2 focus:ring-blue-500 outline-none bg-slate-50 min-w-[150px]"
                    >
                        {groups.map(g => <option key={g} value={g}>{g}</option>)}
                    </select>
                </div>

                {/* Commodity Filter */}
                <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-slate-500 uppercase">Livestock / Product</label>
                    <select
                        value={selectedCommodity}
                        onChange={(e) => setSelectedCommodity(e.target.value)}
                        className="p-2 border border-slate-300 rounded shadow-sm focus:ring-2 focus:ring-blue-500 outline-none min-w-[200px]"
                        disabled={!commodities.length}
                    >
                        {commodities.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                    {commodities.length === 0 && <span className="text-red-500 text-xs mt-1">No items found.</span>}
                </div>
            </div>

            {/* Key Metrics */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <p className="text-sm text-slate-500 font-semibold uppercase">Inventory ({year})</p>
                    <p className="text-3xl font-bold text-slate-800 mt-2">
                        {currentYearStats.inventory ? currentYearStats.inventory.toLocaleString() : 'N/A'}
                        <span className="text-sm text-slate-400 font-normal ml-2">HEAD</span>
                    </p>
                </div>
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <p className="text-sm text-slate-500 font-semibold uppercase">Sales Revenue ({year})</p>
                    <p className="text-3xl font-bold text-emerald-600 mt-2">
                        {currentYearStats.salesRevenue ? `$${currentYearStats.salesRevenue.toLocaleString()}` : 'N/A'}
                    </p>
                </div>
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <p className="text-sm text-slate-500 font-semibold uppercase">Production ({year})</p>
                    <p className="text-3xl font-bold text-blue-600 mt-2">
                        {currentYearStats.production ? currentYearStats.production.toLocaleString() : 'N/A'}
                        <span className="text-sm text-slate-400 font-normal ml-2">{currentYearStats.prodUnit}</span>
                    </p>
                </div>
            </div>

            {/* Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h3 className="text-lg font-semibold mb-4 text-slate-700">{selectedCommodity} Inventory Trend</h3>
                    <div className="h-[350px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={trendData}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                                <XAxis dataKey="year" axisLine={false} tickLine={false} />
                                <YAxis axisLine={false} tickLine={false} tickFormatter={(val) => val >= 1000 ? `${(val / 1000).toFixed(0)}k` : val} />
                                <Tooltip formatter={(val: any) => [val ? val.toLocaleString() : '0', 'Head']} />
                                <Line type="monotone" dataKey="inventory" stroke="#2563eb" strokeWidth={3} dot={{ r: 3 }} />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </div>

                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <h3 className="text-lg font-semibold mb-4 text-slate-700">{selectedCommodity} Sales Revenue Trend</h3>
                    <div className="h-[350px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={trendData}>
                                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                                <XAxis dataKey="year" axisLine={false} tickLine={false} />
                                <YAxis axisLine={false} tickLine={false} tickFormatter={(val) => val >= 1000000 ? `$${(val / 1000000).toFixed(0)}M` : `$${val}`} />
                                <Tooltip formatter={(val: any) => [`$${val.toLocaleString()}`, 'Revenue']} />
                                <Bar dataKey="salesRevenue" fill="#10b981" radius={[4, 4, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            </div>
        </div>
    );
}
