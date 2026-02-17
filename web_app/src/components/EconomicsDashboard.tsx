'use client';

import React, { useMemo } from 'react';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
    LineChart, Line, Legend
} from 'recharts';
import { getTopCrops, getTrendData, getBoomCrops } from '../utils/processData';
import { palette } from '../utils/design';

interface EconomicsDashboardProps {
    data: any[];
    year: number;
    stateName: string;
}

// Vibrant, diverse colors for different commodities
const COMMODITY_COLORS: Record<string, string> = {
    CORN: '#fbbf24',        // Amber/gold
    SOYBEANS: '#34d399',    // Emerald
    HAY: '#3b82f6',         // Blue
    WHEAT: '#f87171',       // Red/pink
    COTTON: '#a78bfa',      // Purple
    RICE: '#38bdf8',        // Sky blue
    SORGHUM: '#fb923c',     // Orange
    BARLEY: '#8b5cf6',      // Violet
};

const GROWTH_COLORS = [palette.positive, '#34d399', '#3b82f6', '#60a5fa'];
const NEG_GROWTH_COLORS = [palette.negative, '#ef4444', '#dc2626'];

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
        return (
            <div className="p-12 text-center">
                <span className="material-symbols-outlined text-gray-600 text-[64px] mb-4 block">monetization_on</span>
                <p className="text-gray-400">No data available for Economics visualization.</p>
            </div>
        );
    }

    return (
        <div className="space-y-8">
            {/* Header */}
            <div>
                <h2 className="text-2xl font-bold text-white flex items-center gap-3">
                    <span className="material-symbols-outlined text-[#19e63c] text-[32px]">monetization_on</span>
                    Economics Dashboard
                </h2>
                <p className="text-gray-400 text-sm mt-1">{stateName} • {year}</p>
            </div>

            {/* Row 1: Top Revenue */}
            <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030]">
                <div className="flex items-center gap-3 mb-4">
                    <span className="material-symbols-outlined text-[#19e63c] text-[28px]">bar_chart</span>
                    <div>
                        <h3 className="text-xl font-semibold text-white">Top Crops by Revenue</h3>
                        <p className="text-sm text-gray-400">Market value of agricultural products sold in {stateName}, {year}</p>
                    </div>
                </div>
                <div className="h-[400px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                            layout="vertical"
                            data={topRevenueCrops}
                            margin={{ top: 5, right: 30, left: 120, bottom: 5 }}
                        >
                            <CartesianGrid strokeDasharray="3 3" stroke={palette.border} horizontal={true} vertical={true} />
                            <XAxis 
                                type="number" 
                                tickFormatter={(val) => `$${(val / 1000000).toFixed(1)}M`}
                                stroke={palette.textMuted}
                                tick={{ fill: palette.textSecondary }}
                            />
                            <YAxis
                                type="category"
                                dataKey="commodity"
                                width={110}
                                tick={{ fontSize: 11, fill: palette.textSecondary }}
                                stroke={palette.textMuted}
                            />
                            <Tooltip
                                formatter={(val: number | undefined) => [val ? `$${val.toLocaleString()}` : '$0', 'Revenue']}
                                contentStyle={{
                                    backgroundColor: palette.bgCard,
                                    border: `1px solid ${palette.border}`,
                                    borderRadius: '8px',
                                    color: palette.textPrimary
                                }}
                                labelStyle={{ color: palette.textSecondary }}
                            />
                            <Bar dataKey="value" radius={[0, 8, 8, 0]}>
                                {topRevenueCrops.map((entry: any) => (
                                    <Cell 
                                        key={`cell-${entry.commodity}`} 
                                        fill={COMMODITY_COLORS[entry.commodity] || palette.textAccent} 
                                    />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Row 2: Trends */}
            <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030]">
                <div className="flex items-center gap-3 mb-4">
                    <span className="material-symbols-outlined text-[#19e63c] text-[28px]">show_chart</span>
                    <div>
                        <h3 className="text-xl font-semibold text-white">Revenue Trends</h3>
                        <p className="text-sm text-gray-400">Historical revenue performance for top commodities</p>
                    </div>
                </div>
                <div className="h-[400px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart
                            data={revenueTrends}
                            margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
                        >
                            <CartesianGrid strokeDasharray="3 3" stroke={palette.border} />
                            <XAxis dataKey="year" stroke={palette.textMuted} tick={{ fill: palette.textSecondary }} />
                            <YAxis 
                                tickFormatter={(val) => `$${(val / 1000000).toFixed(0)}M`}
                                stroke={palette.textMuted}
                                tick={{ fill: palette.textSecondary }}
                            />
                            <Tooltip 
                                formatter={(val: number | undefined) => [val ? `$${val.toLocaleString()}` : '$0', 'Revenue']}
                                contentStyle={{
                                    backgroundColor: palette.bgCard,
                                    border: `1px solid ${palette.border}`,
                                    borderRadius: '8px',
                                    color: palette.textPrimary
                                }}
                                labelStyle={{ color: palette.textSecondary }}
                            />
                            <Legend wrapperStyle={{ color: palette.textSecondary }} />
                            {trendKeys.map((key) => (
                                <Line
                                    key={key}
                                    type="monotone"
                                    dataKey={key}
                                    stroke={COMMODITY_COLORS[key] || palette.textAccent}
                                    strokeWidth={3}
                                    dot={{ r: 3, fill: COMMODITY_COLORS[key] || palette.textAccent, strokeWidth: 0 }}
                                    activeDot={{ r: 6, stroke: palette.bgCard, strokeWidth: 2 }}
                                />
                            ))}
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* Row 3: Boom Crops */}
            <div className="bg-[#1a1d24] p-6 rounded-xl border border-[#2a4030]">
                <div className="flex items-center gap-3 mb-4">
                    <span className="material-symbols-outlined text-[#19e63c] text-[28px]">rocket_launch</span>
                    <div>
                        <h3 className="text-xl font-semibold text-white">"Boom" Crops (High Growth)</h3>
                        <p className="text-sm text-gray-400">Top crops by 10-year revenue growth ({year - 10} vs {year})</p>
                    </div>
                </div>
                <div className="h-[400px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                            layout="vertical"
                            data={boomCrops}
                            margin={{ top: 5, right: 50, left: 120, bottom: 5 }}
                        >
                            <CartesianGrid strokeDasharray="3 3" stroke={palette.border} horizontal={true} vertical={true} />
                            <XAxis 
                                type="number" 
                                tickFormatter={(val) => `${val.toFixed(0)}%`}
                                stroke={palette.textMuted}
                                tick={{ fill: palette.textSecondary }}
                            />
                            <YAxis
                                type="category"
                                dataKey="commodity"
                                width={110}
                                tick={{ fontSize: 11, fill: palette.textSecondary }}
                                stroke={palette.textMuted}
                            />
                            <Tooltip
                                formatter={(val: number | undefined) => [val ? `${val.toFixed(1)}%` : '0%', 'Growth']}
                                labelFormatter={(label) => `${label} (${year - 10} - ${year})`}
                                contentStyle={{
                                    backgroundColor: palette.bgCard,
                                    border: `1px solid ${palette.border}`,
                                    borderRadius: '8px',
                                    color: palette.textPrimary
                                }}
                                labelStyle={{ color: palette.textSecondary }}
                            />
                            <Bar dataKey="growth" radius={[0, 8, 8, 0]}>
                                {boomCrops.map((entry: any) => (
                                    <Cell
                                        key={`cell-${entry.commodity}`}
                                        fill={entry.growth >= 0 ? (COMMODITY_COLORS[entry.commodity] || palette.positive) : palette.negative}
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
