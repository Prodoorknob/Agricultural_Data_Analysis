
'use client';

import React, { useMemo } from 'react';
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
    BarChart, Bar
} from 'recharts';
import { getLaborTrends } from '../utils/processData';

interface LaborDashboardProps {
    data: any[]; // Was laborData in props but passed as data={filteredStateData} from page.tsx
    year: number;
    stateName: string;
}

export default function LaborDashboard({ data, year, stateName }: LaborDashboardProps) {

    // 1. Labor Wage Trends (National vs State vs Key States)
    const laborTrends = useMemo(() => {
        if (!data || !data.length) return [];
        // Note: stateName is usually 'IN' (code) or 'National'.
        // getLaborTrends handles the 'cleanState' logic.
        return getLaborTrends(data, stateName);
    }, [data, stateName]);




    // Calculate stats for cards (Latest Year)
    const latestData = laborTrends[laborTrends.length - 1];
    const latestYear = latestData?.year;

    // Helper to safely get value or 'N/A'
    const formatWage = (val: number | null | undefined) => {
        return val ? `$${val.toFixed(2)}` : 'N/A';
    };

    const stateWage = latestData ? latestData[stateName.toUpperCase()] : null;
    const nationalWage = latestData ? latestData['National Avg'] : null;

    if (!data.length) {
        return (
            <div className="p-12 text-center">
                <span className="material-symbols-outlined text-gray-600 text-[64px] mb-4 block">work</span>
                <p className="text-gray-400">No data available for Labor visualization.</p>
            </div>
        );
    }

    return (
        <div className="space-y-8">
            {/* Header */}
            <div>
                <h2 className="text-2xl font-bold text-white flex items-center gap-3">
                    <span className="material-symbols-outlined text-[#19e63c] text-[32px]">work</span>
                    Labor & Workforce Dashboard
                </h2>
                <p className="text-gray-400 text-sm mt-1">{stateName} • {latestYear}</p>
            </div>

            {/* KPI Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030] relative overflow-hidden">
                    <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-[#19e63c] to-transparent opacity-60"></div>
                    <div className="flex items-center gap-3 mb-4">
                        <div className="size-10 bg-[#19e63c]/20 rounded-lg flex items-center justify-center">
                            <span className="material-symbols-outlined text-[#19e63c] text-[24px]">payments</span>
                        </div>
                        <p className="text-gray-400 text-xs font-semibold uppercase tracking-wider">{stateName} Avg Wage ({latestYear})</p>
                    </div>
                    <p className="text-3xl font-bold text-white">{formatWage(stateWage)}</p>
                    <p className="text-sm text-gray-500 mt-1">per hour</p>
                </div>
                <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030] relative overflow-hidden">
                    <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-[#19e63c] to-transparent opacity-60"></div>
                    <div className="flex items-center gap-3 mb-4">
                        <div className="size-10 bg-[#19e63c]/20 rounded-lg flex items-center justify-center">
                            <span className="material-symbols-outlined text-[#19e63c] text-[24px]">public</span>
                        </div>
                        <p className="text-gray-400 text-xs font-semibold uppercase tracking-wider">National Avg Wage ({latestYear})</p>
                    </div>
                    <p className="text-3xl font-bold text-white">{formatWage(nationalWage)}</p>
                    <p className="text-sm text-gray-500 mt-1">per hour</p>
                </div>
            </div>

            {/* Row 1: Wage Trends */}
            {(() => {
                const compStates: string[] = (laborTrends as any).comparisonStates || ['CA', 'TX', 'IA'];
                const compColors = ['#60a5fa', '#a78bfa', '#f59e0b'];
                return (
                    <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030]">
                        <div className="flex items-center gap-3 mb-4">
                            <span className="material-symbols-outlined text-[#19e63c] text-[28px]">trending_up</span>
                            <div>
                                <h3 className="text-xl font-semibold text-white">Farm Labor Wage Trends</h3>
                                <p className="text-sm text-gray-400">{stateName} vs. National Average &amp; Regional Peers ({compStates.join(', ')})</p>
                            </div>
                        </div>
                        <div className="h-[500px] w-full">
                            <ResponsiveContainer width="100%" height="100%">
                                <LineChart
                                    data={laborTrends}
                                    margin={{ top: 10, right: 30, left: 10, bottom: 0 }}
                                >
                                    <CartesianGrid strokeDasharray="3 3" stroke="#2a4030" vertical={false} />
                                    <XAxis dataKey="year" stroke="#718096" tick={{ fill: '#9ca3af' }} />
                                    <YAxis
                                        domain={['auto', 'auto']}
                                        tickFormatter={(val) => `$${val}`}
                                        label={{
                                            value: 'Wage Rate ($/hour)',
                                            angle: -90,
                                            position: 'insideLeft',
                                            style: { fill: '#9ca3af' }
                                        }}
                                        stroke="#718096"
                                        tick={{ fill: '#9ca3af' }}
                                    />
                                    <Tooltip
                                        formatter={(val: number | string | Array<number | string> | undefined) => {
                                            if (val === undefined || val === null) return ['N/A', 'Wage Rate'];
                                            if (typeof val === 'number') return [`$${val.toFixed(2)}`, 'Wage Rate'];
                                            return [val, 'Wage Rate'];
                                        }}
                                        contentStyle={{
                                            backgroundColor: '#1a1d24',
                                            border: '1px solid #2a4030',
                                            borderRadius: '8px',
                                            color: '#fff'
                                        }}
                                        labelStyle={{ color: '#9ca3af' }}
                                    />
                                    <Legend wrapperStyle={{ color: '#9ca3af' }} />

                                    {/* Dynamic Regional Comparison States (Dotted) */}
                                    {compStates.map((st, i) => (
                                        <Line key={st} type="monotone" dataKey={st} stroke={compColors[i % compColors.length]} strokeDasharray="3 3" dot={false} strokeWidth={2} name={st} />
                                    ))}

                                    {/* National Average (Dashed Bold) */}
                                    <Line type="monotone" dataKey="National Avg" stroke="#3b82f6" strokeDasharray="5 5" strokeWidth={3} dot={{ r: 4 }} name="National Avg" />

                                    {/* Selected State (Solid Bold Green) */}
                                    <Line
                                        type="monotone"
                                        dataKey={stateName.toUpperCase()}
                                        stroke="#19e63c"
                                        strokeWidth={4}
                                        dot={{ r: 6, strokeWidth: 2, fill: '#0f1117' }}
                                        activeDot={{ r: 8 }}
                                        name={`${stateName} (Selected)`}
                                    />
                                </LineChart>
                            </ResponsiveContainer>
                        </div>
                    </div>
                );
            })()}


        </div>
    );
}
