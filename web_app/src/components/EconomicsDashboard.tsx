'use client';

import React, { useMemo } from 'react';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
    LineChart, Line, Legend
} from 'recharts';
import { getTopCrops, getTrendData, getBoomCrops } from '../utils/processData';

interface EconomicsDashboardProps {
    data: any[];
    year: number;
    stateName: string;
}

const COLORS = ['#2c5282', '#2b6cb0', '#4299e1', '#63b3ed', '#90cdf4', '#a3bffa', '#c3dafe', '#ebf8ff'];
const GROWTH_COLORS = ['#48bb78', '#38a169', '#2f855a', '#276749', '#22543d'];
const NEG_GROWTH_COLORS = ['#f56565', '#e53e3e', '#c53030', '#9b2c2c'];

export default function EconomicsDashboard({ data, year, stateName }: EconomicsDashboardProps) {
    const METRIC = 'SALES'; // Economics focuses on Sales/Revenue

    // 1. Top Crops by Revenue
    const topRevenueCrops = useMemo(() => {
        return getTopCrops(data, year, METRIC);
    }, [data, year]);

    // 2. Revenue Trends
    const revenueTrends = useMemo(() => {
        const top5 = topRevenueCrops.slice(0, 5).map(c => c.commodity);
        return getTrendData(data, METRIC, top5);
    }, [data, topRevenueCrops]);

    const trendKeys = useMemo(() => {
        return topRevenueCrops.slice(0, 5).map(c => c.commodity);
    }, [topRevenueCrops]);

    // 3. Boom Crops (Growth 2012 vs 2022 -> 10 year growth)
    // Dynamic based on year: compares [year] vs [year - 10]
    const boomCrops = useMemo(() => {
        return getBoomCrops(data, METRIC, year, year - 10); // 10-year growth
    }, [data, year]);

    if (!data.length) {
        return <div className="p-12 text-center text-slate-400">No data available for Economics visualization.</div>;
    }

    return (
        <div className="space-y-8">

            {/* Row 1: Top Revenue */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                <h3 className="text-xl font-semibold mb-1 text-slate-800">Top Crops by Revenue</h3>
                <p className="text-sm text-slate-500 mb-6">Market value of agricultural products sold in {stateName}, {year}</p>
                <div className="h-[400px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                            layout="vertical"
                            data={topRevenueCrops}
                            margin={{ top: 5, right: 30, left: 100, bottom: 5 }}
                        >
                            <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={true} stroke="#e2e8f0" />
                            <XAxis type="number" tickFormatter={(val) => `$${(val / 1000000).toFixed(1)}M`} />
                            <YAxis
                                type="category"
                                dataKey="commodity"
                                width={120}
                                tick={{ fontSize: 11, fill: '#4a5568' }}
                            />
                            <Tooltip
                                formatter={(val: number | undefined) => [val ? `$${val.toLocaleString()}` : '$0', 'Revenue']}
                                contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}
                            />
                            <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                                {topRevenueCrops.map((_, index) => (
                                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Row 2: Trends */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                <h3 className="text-xl font-semibold mb-1 text-slate-800">Revenue Trends</h3>
                <p className="text-sm text-slate-500 mb-6">Historical revenue performance for top commodities</p>
                <div className="h-[400px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart
                            data={revenueTrends}
                            margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                        >
                            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                            <XAxis dataKey="year" />
                            <YAxis tickFormatter={(val) => `$${(val / 1000000).toFixed(0)}M`} />
                            <Tooltip formatter={(val: number | undefined) => [val ? `$${val.toLocaleString()}` : '$0', 'Revenue']} />
                            <Legend />
                            {trendKeys.map((key, index) => (
                                <Line
                                    key={key}
                                    type="monotone"
                                    dataKey={key}
                                    stroke={COLORS[index % COLORS.length]}
                                    strokeWidth={3}
                                    dot={{ r: 4, fill: COLORS[index % COLORS.length] }}
                                    activeDot={{ r: 6 }}
                                />
                            ))}
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Row 3: Boom Crops */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                <h3 className="text-xl font-semibold mb-1 text-slate-800">"Boom" Crops (High Growth)</h3>
                <p className="text-sm text-slate-500 mb-6">Top crops by 10-year revenue growth ({year - 10} vs {year})</p>
                <div className="h-[400px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                            layout="vertical"
                            data={boomCrops}
                            margin={{ top: 5, right: 50, left: 100, bottom: 5 }}
                        >
                            <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={true} stroke="#e2e8f0" />
                            <XAxis type="number" tickFormatter={(val) => `${val.toFixed(0)}%`} />
                            <YAxis
                                type="category"
                                dataKey="commodity"
                                width={120}
                                tick={{ fontSize: 11, fill: '#4a5568' }}
                            />
                            <Tooltip
                                formatter={(val: number | undefined) => [val ? `${val.toFixed(1)}%` : '0%', 'Growth']}
                                labelFormatter={(label) => `${label} (${year - 10} - ${year})`}
                            />
                            <Bar dataKey="growth" radius={[0, 4, 4, 0]}>
                                {boomCrops.map((entry, index) => (
                                    <Cell
                                        key={`cell-${index}`}
                                        fill={entry.growth >= 0 ? GROWTH_COLORS[index % GROWTH_COLORS.length] : NEG_GROWTH_COLORS[0]}
                                    />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </div>
    );
}
