'use client';

import React, { useMemo } from 'react';
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts';
import { getLaborTrends } from '../utils/processData';

interface LaborDashboardProps {
    laborData: any[];
    year: number;
    stateName: string;
}

export default function LaborDashboard({ laborData, year, stateName }: LaborDashboardProps) {

    // 1. Labor Wage Trends (National vs State vs Key States)
    const laborTrends = useMemo(() => {
        if (!laborData || !laborData.length) return [];
        return getLaborTrends(laborData, stateName);
    }, [laborData, stateName]);


    // Calculate stats for cards (Latest Year)
    const latestData = laborTrends[laborTrends.length - 1];
    const latestYear = latestData?.year;

    // Helper to safely get value or 'N/A'
    const formatWage = (val: number | null | undefined) => {
        return val ? `$${val.toFixed(2)}` : 'N/A';
    };

    const stateWage = latestData ? latestData[stateName.toUpperCase()] : null;
    const nationalWage = latestData ? latestData['National Avg'] : null;

    if (!laborData.length) {
        return <div className="p-12 text-center text-slate-400">No data available for Labor visualization.</div>;
    }

    return (
        <div className="space-y-8">

            {/* KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <p className="text-sm text-slate-500 font-medium uppercase">{stateName} Avg Wage ({latestYear})</p>
                    <p className="text-3xl font-bold text-slate-800 mt-2">{formatWage(stateWage)} <span className="text-sm font-normal text-slate-400">/ hour</span></p>
                </div>
                <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                    <p className="text-sm text-slate-500 font-medium uppercase">National Avg Wage ({latestYear})</p>
                    <p className="text-3xl font-bold text-slate-800 mt-2">{formatWage(nationalWage)} <span className="text-sm font-normal text-slate-400">/ hour</span></p>
                </div>
            </div>

            {/* Row 1: Wage Trends */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
                <h3 className="text-xl font-semibold mb-1 text-slate-800">Farm Labor Wage Trends</h3>
                <p className="text-sm text-slate-500 mb-6">{stateName} vs. National Average & Key States</p>
                <div className="h-[500px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart
                            data={laborTrends}
                            margin={{ top: 10, right: 30, left: 10, bottom: 0 }}
                        >
                            <CartesianGrid strokeDasharray="3 3" vertical={false} />
                            <XAxis dataKey="year" />
                            <YAxis
                                domain={['auto', 'auto']}
                                tickFormatter={(val) => `$${val}`}
                                label={{ value: 'Wage Rate ($/hour)', angle: -90, position: 'insideLeft' }}
                            />
                            <Tooltip
                                formatter={(val: number | string | Array<number | string> | undefined) => {
                                    if (val === undefined || val === null) return ['N/A', 'Wage Rate'];
                                    if (typeof val === 'number') return [`$${val.toFixed(2)}`, 'Wage Rate'];
                                    return [val, 'Wage Rate'];
                                }}
                                labelStyle={{ color: '#2d3748' }}
                            />
                            <Legend />

                            {/* Comparison States (Dotted) */}
                            <Line type="monotone" dataKey="CALIFORNIA" stroke="#90cdf4" strokeDasharray="3 3" dot={false} strokeWidth={2} name="CA" />
                            <Line type="monotone" dataKey="FLORIDA" stroke="#90cdf4" strokeDasharray="3 3" dot={false} strokeWidth={2} name="FL" />
                            <Line type="monotone" dataKey="HAWAII" stroke="#90cdf4" strokeDasharray="3 3" dot={false} strokeWidth={2} name="HI" />

                            {/* National Average (Dashed Bold) */}
                            <Line type="monotone" dataKey="National Avg" stroke="#3182ce" strokeDasharray="5 5" strokeWidth={3} dot={{ r: 4 }} name="National Avg" />

                            {/* Selected State (Solid Bold Red) */}
                            <Line
                                type="monotone"
                                dataKey={stateName.toUpperCase()}
                                stroke="#f56565"
                                strokeWidth={4}
                                dot={{ r: 6, strokeWidth: 2, fill: '#fff' }}
                                activeDot={{ r: 8 }}
                                name={`${stateName} (Selected)`}
                            />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </div>
    );
}
