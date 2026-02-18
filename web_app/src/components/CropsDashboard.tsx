
'use client';

import React, { useState, useMemo, useEffect, useCallback } from 'react';
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
    BarChart, Bar, Cell, AreaChart, Area, ReferenceLine
} from 'recharts';
import * as d3 from 'd3-array';
import { cleanValue, getCommodityStory, getTopCrops } from '../utils/processData';
import { palette, chartDefaults, formatCompact, formatCurrency, formatDelta } from '../utils/design';

interface CropsDashboardProps {
    data: any[];
    allData?: any[]; // All state data (unfiltered by sector) for cross-sector revenue lookups
    year: number;
    stateName: string;
}

// ─── Sparkline Micro-Component ──────────────────────────────────
function Sparkline({ data, dataKey, color, height = 32 }: { data: any[]; dataKey: string; color: string; height?: number }) {
    return (
        <ResponsiveContainer width="100%" height={height}>
            <AreaChart data={data} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
                <defs>
                    <linearGradient id={`spark-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={color} stopOpacity={0.3} />
                        <stop offset="100%" stopColor={color} stopOpacity={0} />
                    </linearGradient>
                </defs>
                <Area
                    type="monotone"
                    dataKey={dataKey}
                    stroke={color}
                    strokeWidth={1.5}
                    fill={`url(#spark-${dataKey})`}
                    dot={false}
                    isAnimationActive={false}
                />
            </AreaChart>
        </ResponsiveContainer>
    );
}

// ─── KPI Card ────────────────────────────────────────────────────
function KpiCard({ label, value, unit, delta, sparkData, sparkKey, color, delay }: {
    label: string; value: string; unit: string;
    delta?: { text: string; positive: boolean };
    sparkData?: any[]; sparkKey?: string;
    color: string; delay: number;
}) {
    return (
        <div
            className="card-animate"
            style={{
                background: palette.bgCard,
                border: `1px solid ${palette.border}`,
                borderRadius: '14px',
                padding: '20px',
                animationDelay: `${delay}ms`,
                position: 'relative',
                overflow: 'hidden',
            }}
        >
            {/* Glow accent */}
            <div style={{
                position: 'absolute', top: 0, left: 0, right: 0, height: '2px',
                background: `linear-gradient(90deg, transparent, ${color}, transparent)`,
                opacity: 0.6,
            }} />
            <p style={{ color: palette.textMuted, fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                {label}
            </p>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginTop: '8px' }}>
                <span style={{ color: palette.textPrimary, fontSize: '28px', fontWeight: 700 }}>{value}</span>
                <span style={{ color: palette.textMuted, fontSize: '12px' }}>{unit}</span>
            </div>
            {delta && (
                <span style={{
                    color: delta.positive ? palette.positive : palette.negative,
                    fontSize: '12px', fontWeight: 600, marginTop: '4px', display: 'inline-block',
                }}>
                    {delta.text} vs prev year
                </span>
            )}
            {sparkData && sparkKey && (
                <div style={{ marginTop: '8px' }}>
                    <Sparkline data={sparkData} dataKey={sparkKey} color={color} />
                </div>
            )}
        </div>
    );
}

// ─── Custom Tooltip ──────────────────────────────────────────────
function StoryTooltip({ active, payload, label, anomalyYears }: any) {
    if (!active || !payload?.length) return null;
    const isAnomaly = anomalyYears?.includes(label);
    return (
        <div style={{
            ...chartDefaults.tooltipStyle.contentStyle,
            padding: '12px 16px',
            minWidth: '180px',
        }}>
            <p style={{ color: isAnomaly ? palette.anomaly : palette.textPrimary, fontWeight: 700, marginBottom: '8px' }}>
                {label} {isAnomaly && '⚠ Anomaly Year'}
            </p>
            {payload.map((p: any, i: number) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', marginBottom: '3px' }}>
                    <span style={{ color: p.color, fontSize: '12px' }}>● {p.name}</span>
                    <span style={{ color: palette.textPrimary, fontSize: '12px', fontWeight: 600 }}>
                        {typeof p.value === 'number' ? p.value.toLocaleString() : p.value}
                    </span>
                </div>
            ))}
        </div>
    );
}

// ─── Custom Anomaly Dot ──────────────────────────────────────────
function AnomalyDot(props: any) {
    const { cx, cy, payload } = props;
    if (!cx || !cy) return null;
    if (payload?.isAnomaly) {
        return (
            <g>
                <circle cx={cx} cy={cy} r={7} fill={palette.anomaly} opacity={0.2} />
                <circle cx={cx} cy={cy} r={4} fill={palette.anomaly} stroke={palette.bgCard} strokeWidth={2} />
            </g>
        );
    }
    return <circle cx={cx} cy={cy} r={3} fill={palette.yield} stroke={palette.bgCard} strokeWidth={1.5} />;
}

// ═════════════════════════════════════════════════════════════════
// ─── MAIN COMPONENT ─────────────────────────────────────────────
// ═════════════════════════════════════════════════════════════════
export default function CropsDashboard({ data, allData, year, stateName }: CropsDashboardProps) {

    // ─── Filter for CROPS sector ──────────────────────────────────
    const cropsData = useMemo(() => {
        return data.filter(d => d.sector_desc === 'CROPS');
    }, [data]);

    // ─── Unique Commodities ───────────────────────────────────────
    const commodities = useMemo(() => {
        const unique = new Set(cropsData.map(d => d.commodity_desc));
        return Array.from(unique).sort();
    }, [cropsData]);

    const [selectedCommodity, setSelectedCommodity] = useState<string>('CORN');
    const [focusYear, setFocusYear] = useState<number | null>(null);

    useEffect(() => {
        if (!commodities.includes(selectedCommodity)) {
            if (commodities.includes('CORN')) setSelectedCommodity('CORN');
            else if (commodities.length > 0) setSelectedCommodity(commodities[0]);
        }
    }, [commodities, selectedCommodity]);

    // ─── Unified Story Data ───────────────────────────────────────
    const { story, anomalyYears } = useMemo(() => {
        // Pass allData (cross-sector) so revenue from ECONOMICS sector is found
        return getCommodityStory(allData || data, selectedCommodity);
    }, [allData, data, selectedCommodity]);

    // ─── Current & Previous Year Stats ────────────────────────────
    const currentStats = useMemo(() => story.find(d => d.year === year) || {} as any, [story, year]);
    const prevStats = useMemo(() => story.find(d => d.year === year - 1) || {} as any, [story, year]);

    // ─── Last 10 years for sparklines ─────────────────────────────
    const sparkData = useMemo(() => {
        return story.filter(d => d.year >= year - 9 && d.year <= year);
    }, [story, year]);

    // ─── Top crops for "Relative Position" ────────────────────────
    const topCropsRanking = useMemo(() => {
        return getTopCrops(data, year, 'AREA HARVESTED').slice(0, 10);
    }, [data, year]);

    // ─── Chart click handler ──────────────────────────────────────
    const handleChartClick = useCallback((data: any) => {
        if (!data || !data.year) return;
        const clickedYear = Number(data.year);
        if (clickedYear && !isNaN(clickedYear)) {
            setFocusYear(prev => prev === clickedYear ? null : clickedYear);
        }
    }, []);

    // ─── Empty state ──────────────────────────────────────────────
    if (!cropsData.length) {
        return (
            <div style={{ padding: '48px', textAlign: 'center', color: palette.textMuted, background: palette.bg, borderRadius: '16px' }}>
                No crop data available.
            </div>
        );
    }

    return (
        <div style={{ fontFamily: "'Inter', system-ui, sans-serif" }} className="crops-story">

            {/* ── Commodity Selector ───────────────────────────────── */}
            <div style={{
                background: palette.bgCard,
                border: `1px solid ${palette.border}`,
                borderRadius: '14px',
                padding: '16px 20px',
                display: 'flex',
                alignItems: 'center',
                gap: '16px',
                marginBottom: '24px',
            }}>
                <label style={{ color: palette.textSecondary, fontWeight: 600, fontSize: '13px' }}>Commodity</label>
                <select
                    value={selectedCommodity}
                    onChange={(e) => { setSelectedCommodity(e.target.value); setFocusYear(null); }}
                    style={{
                        background: palette.bgInput,
                        color: palette.textPrimary,
                        border: `1px solid ${palette.border}`,
                        borderRadius: '8px',
                        padding: '8px 12px',
                        fontSize: '13px',
                        outline: 'none',
                        cursor: 'pointer',
                        minWidth: '180px',
                    }}
                >
                    {commodities.map(c => <option key={c} value={c}>{c}</option>)}
                </select>

                {/* Breadcrumb context */}
                <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {[stateName || 'National', 'Crops', selectedCommodity].map((crumb, i, arr) => (
                        <React.Fragment key={i}>
                            <span style={{
                                color: i === arr.length - 1 ? palette.textAccent : palette.textMuted,
                                fontSize: '12px',
                                fontWeight: i === arr.length - 1 ? 600 : 400,
                            }}>{crumb}</span>
                            {i < arr.length - 1 && <span style={{ color: palette.textMuted, fontSize: '12px' }}>›</span>}
                        </React.Fragment>
                    ))}
                </div>

                {focusYear && (
                    <button
                        onClick={() => setFocusYear(null)}
                        style={{
                            background: palette.anomalyBg,
                            color: palette.anomaly,
                            border: `1px solid rgba(248,113,113,0.3)`,
                            borderRadius: '6px',
                            padding: '4px 10px',
                            fontSize: '11px',
                            cursor: 'pointer',
                        }}
                    >
                        Clear {focusYear} focus ×
                    </button>
                )}
            </div>

            {/* ── KPI Cards with Sparklines ─────────────────────── */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '28px' }}>
                <KpiCard
                    label={`Production (${year})`}
                    value={currentStats.production ? formatCompact(currentStats.production) : 'N/A'}
                    unit={currentStats.prodUnit || ''}
                    delta={currentStats.production && prevStats.production ? formatDelta(currentStats.production, prevStats.production) : undefined}
                    sparkData={sparkData} sparkKey="production"
                    color={palette.production} delay={0}
                />
                <KpiCard
                    label={`Yield (${year})`}
                    value={currentStats.yield ? currentStats.yield.toFixed(1) : 'N/A'}
                    unit={currentStats.yieldUnit || 'BU/ACRE'}
                    delta={currentStats.yield && prevStats.yield ? formatDelta(currentStats.yield, prevStats.yield) : undefined}
                    sparkData={sparkData} sparkKey="yield"
                    color={palette.yield} delay={80}
                />
                <KpiCard
                    label={`Area Harvested (${year})`}
                    value={currentStats.areaHarvested ? formatCompact(currentStats.areaHarvested) : 'N/A'}
                    unit="ACRES"
                    delta={currentStats.areaHarvested && prevStats.areaHarvested ? formatDelta(currentStats.areaHarvested, prevStats.areaHarvested) : undefined}
                    sparkData={sparkData} sparkKey="areaHarvested"
                    color={palette.areaHarvested} delay={160}
                />
                <KpiCard
                    label={`Revenue (${year})`}
                    value={currentStats.revenue ? formatCurrency(currentStats.revenue) : 'N/A'}
                    unit=""
                    delta={currentStats.revenue && prevStats.revenue ? formatDelta(currentStats.revenue, prevStats.revenue) : undefined}
                    sparkData={sparkData} sparkKey="revenue"
                    color={palette.revenue} delay={240}
                />
            </div>

            {/* ════════════════════════════════════════════════════ */}
            {/* SECTION 1: Yield & Production Performance           */}
            {/* ════════════════════════════════════════════════════ */}
            <div className="story-section card-animate" style={{
                background: palette.bgCard,
                border: `1px solid ${palette.border}`,
                borderRadius: '14px',
                padding: '24px',
                marginBottom: '20px',
                animationDelay: '200ms',
            }}>
                <div style={{ marginBottom: '16px' }}>
                    <h3 style={{ color: palette.textPrimary, fontSize: '18px', fontWeight: 700, margin: 0 }}>
                        How is yield performing?
                    </h3>
                    <p style={{ color: palette.textSecondary, fontSize: '13px', marginTop: '4px' }}>
                        {selectedCommodity} yield over time — click any year to focus across all charts
                    </p>
                    {anomalyYears.length > 0 && (
                        <div style={{
                            marginTop: '8px',
                            padding: '8px 12px',
                            background: palette.anomalyBg,
                            borderRadius: '8px',
                            border: `1px solid rgba(248,113,113,0.2)`,
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '8px',
                        }}>
                            <span style={{ color: palette.anomaly, fontSize: '14px' }}>⚠</span>
                            <span style={{ color: palette.anomaly, fontSize: '12px', fontWeight: 500 }}>
                                Yield dips detected in {anomalyYears.join(', ')}
                            </span>
                        </div>
                    )}
                </div>

                <div style={{ height: '360px' }}>
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={story}>
                            <defs>
                                <linearGradient id="yieldGrad" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor={palette.yield} stopOpacity={0.2} />
                                    <stop offset="100%" stopColor={palette.yield} stopOpacity={0} />
                                </linearGradient>
                                <linearGradient id="prodGrad" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor={palette.production} stopOpacity={0.1} />
                                    <stop offset="100%" stopColor={palette.production} stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid {...chartDefaults.grid} />
                            <XAxis dataKey="year" type="number" domain={['dataMin', 'dataMax']} {...chartDefaults.axisStyle} tickCount={10} />
                            <YAxis
                                yAxisId="left" orientation="left"
                                {...chartDefaults.axisStyle}
                                tickFormatter={formatCompact}
                                label={{ value: 'Production', angle: -90, position: 'insideLeft', style: { fill: palette.production, fontSize: 11 } }}
                            />
                            <YAxis
                                yAxisId="right" orientation="right"
                                {...chartDefaults.axisStyle}
                                domain={['auto', 'auto']}
                                label={{ value: 'Yield', angle: 90, position: 'insideRight', style: { fill: palette.yield, fontSize: 11 } }}
                            />
                            <Tooltip content={<StoryTooltip anomalyYears={anomalyYears} />} />
                            <Legend
                                verticalAlign="top" align="right" height={36}
                                wrapperStyle={{ color: palette.textSecondary, fontSize: '12px' }}
                            />

                            {/* Focus year highlight */}
                            {focusYear && (
                                <ReferenceLine
                                    x={focusYear}
                                    yAxisId="left"
                                    stroke={palette.textAccent} strokeWidth={2}
                                    strokeOpacity={0.6}
                                    label={{ value: `${focusYear}`, position: 'top', fill: palette.textAccent, fontSize: 11 }}
                                />
                            )}

                            {/* Anomaly reference lines */}
                            {anomalyYears.map((ay: number) => (
                                <ReferenceLine
                                    key={ay}
                                    x={ay}
                                    yAxisId="left"
                                    stroke={palette.anomaly}
                                    strokeDasharray="4 4"
                                    strokeOpacity={0.5}
                                />
                            ))}

                            <Area
                                yAxisId="left" type="monotone" dataKey="production" name="Production"
                                stroke={palette.production} strokeWidth={2.5}
                                fill="url(#prodGrad)"
                                dot={{ r: 3, fill: palette.production, strokeWidth: 0 }}
                                activeDot={{ r: 5, stroke: palette.bgCard, strokeWidth: 2 }}
                                animationDuration={chartDefaults.animationDuration}
                                onClick={handleChartClick}
                                style={{ cursor: 'pointer' }}
                            />
                            <Line
                                yAxisId="right" type="monotone" dataKey="yield" name="Yield"
                                stroke={palette.yield} strokeWidth={2.5}
                                dot={<AnomalyDot />}
                                activeDot={{ r: 6, stroke: palette.bgCard, strokeWidth: 2 }}
                                animationDuration={chartDefaults.animationDuration}
                                onClick={handleChartClick}
                                style={{ cursor: 'pointer' }}
                            />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* ════════════════════════════════════════════════════ */}
            {/* SECTION 2: Was Less Planted?                        */}
            {/* ════════════════════════════════════════════════════ */}
            <div className="story-section card-animate" style={{
                background: palette.bgCard,
                border: `1px solid ${palette.border}`,
                borderRadius: '14px',
                padding: '24px',
                marginBottom: '20px',
                animationDelay: '350ms',
            }}>
                <div style={{ marginBottom: '16px' }}>
                    <h3 style={{ color: palette.textPrimary, fontSize: '18px', fontWeight: 700, margin: 0 }}>
                        Was less planted in those years?
                    </h3>
                    <p style={{ color: palette.textSecondary, fontSize: '13px', marginTop: '4px' }}>
                        Area planted vs. harvested — gaps indicate crop loss or abandonment
                    </p>
                    {story.some(d => d.areaHarvested > d.areaPlanted && d.areaPlanted > 0) && (
                        <div style={{
                            marginTop: '8px',
                            padding: '8px 12px',
                            background: 'rgba(251, 191, 36, 0.08)',
                            borderRadius: '8px',
                            border: '1px solid rgba(251, 191, 36, 0.2)',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '8px',
                        }}>
                            <span style={{ color: '#fbbf24', fontSize: '14px' }}>ℹ</span>
                            <span style={{ color: '#fbbf24', fontSize: '12px', fontWeight: 500 }}>
                                Harvested area exceeds planted for {selectedCommodity} in some years. This is common for crops reported across multiple categories (e.g., grain vs. silage) or with multi-harvest practices.
                            </span>
                        </div>
                    )}
                </div>

                <div style={{ height: '320px' }}>
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={story}>
                            <defs>
                                <linearGradient id="plantedGrad" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor={palette.areaPlanted} stopOpacity={0.15} />
                                    <stop offset="100%" stopColor={palette.areaPlanted} stopOpacity={0} />
                                </linearGradient>
                                <linearGradient id="harvestedGrad" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="0%" stopColor={palette.areaHarvested} stopOpacity={0.15} />
                                    <stop offset="100%" stopColor={palette.areaHarvested} stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid {...chartDefaults.grid} />
                            <XAxis dataKey="year" type="number" domain={['dataMin', 'dataMax']} {...chartDefaults.axisStyle} tickCount={10} />
                            <YAxis {...chartDefaults.axisStyle} tickFormatter={formatCompact} />
                            <Tooltip content={<StoryTooltip anomalyYears={anomalyYears} />} />
                            <Legend
                                verticalAlign="top" align="right" height={36}
                                wrapperStyle={{ color: palette.textSecondary, fontSize: '12px' }}
                            />

                            {focusYear && (
                                <ReferenceLine
                                    x={focusYear}
                                    stroke={palette.textAccent} strokeWidth={2} strokeOpacity={0.6}
                                />
                            )}
                            {anomalyYears.map((ay: number) => (
                                <ReferenceLine key={ay} x={ay} stroke={palette.anomaly} strokeDasharray="4 4" strokeOpacity={0.4} />
                            ))}

                            <Area
                                type="monotone" dataKey="areaPlanted" name="Area Planted"
                                stroke={palette.areaPlanted} strokeWidth={2}
                                fill="url(#plantedGrad)"
                                dot={{ r: 2.5, fill: palette.areaPlanted, strokeWidth: 0 }}
                                animationDuration={chartDefaults.animationDuration}
                                onClick={handleChartClick}
                                style={{ cursor: 'pointer' }}
                            />
                            <Area
                                type="monotone" dataKey="areaHarvested" name="Area Harvested"
                                stroke={palette.areaHarvested} strokeWidth={2}
                                fill="url(#harvestedGrad)"
                                dot={{ r: 2.5, fill: palette.areaHarvested, strokeWidth: 0 }}
                                animationDuration={chartDefaults.animationDuration}
                                onClick={handleChartClick}
                                style={{ cursor: 'pointer' }}
                            />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
            </div>

            {/* ════════════════════════════════════════════════════ */}
            {/* SECTION 3: Economic Impact                          */}
            {/* ════════════════════════════════════════════════════ */}
            {story.some(d => d.revenue > 0) && (
                <div className="story-section card-animate" style={{
                    background: palette.bgCard,
                    border: `1px solid ${palette.border}`,
                    borderRadius: '14px',
                    padding: '24px',
                    marginBottom: '20px',
                    animationDelay: '500ms',
                }}>
                    <div style={{ marginBottom: '16px' }}>
                        <h3 style={{ color: palette.textPrimary, fontSize: '18px', fontWeight: 700, margin: 0 }}>
                            How did this affect revenue?
                        </h3>
                        <p style={{ color: palette.textSecondary, fontSize: '13px', marginTop: '4px' }}>
                            {selectedCommodity} sales revenue — does price compensate for low yield?
                        </p>
                    </div>

                    <div style={{ height: '300px' }}>
                        <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={story}>
                                <defs>
                                    <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="0%" stopColor={palette.revenue} stopOpacity={0.2} />
                                        <stop offset="100%" stopColor={palette.revenue} stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid {...chartDefaults.grid} />
                                <XAxis dataKey="year" type="number" domain={['dataMin', 'dataMax']} {...chartDefaults.axisStyle} tickCount={10} />
                                <YAxis {...chartDefaults.axisStyle} tickFormatter={formatCurrency} />
                                <Tooltip content={<StoryTooltip anomalyYears={anomalyYears} />} />

                                {focusYear && (
                                    <ReferenceLine
                                        x={focusYear}
                                        stroke={palette.textAccent} strokeWidth={2} strokeOpacity={0.6}
                                    />
                                )}
                                {anomalyYears.map((ay: number) => (
                                    <ReferenceLine key={ay} x={ay} stroke={palette.anomaly} strokeDasharray="4 4" strokeOpacity={0.4} />
                                ))}

                                <Area
                                    type="monotone" dataKey="revenue" name="Revenue ($)"
                                    stroke={palette.revenue} strokeWidth={2.5}
                                    fill="url(#revGrad)"
                                    dot={{ r: 3, fill: palette.revenue, strokeWidth: 0 }}
                                    activeDot={{ r: 5, stroke: palette.bgCard, strokeWidth: 2 }}
                                    animationDuration={chartDefaults.animationDuration}
                                    onClick={handleChartClick}
                                    style={{ cursor: 'pointer' }}
                                />
                            </AreaChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            )}

            {/* ════════════════════════════════════════════════════ */}
            {/* SECTION 4: Relative Position — Top Crops Ranking    */}
            {/* ════════════════════════════════════════════════════ */}
            <div className="story-section card-animate" style={{
                background: palette.bgCard,
                border: `1px solid ${palette.border}`,
                borderRadius: '14px',
                padding: '24px',
                animationDelay: '650ms',
            }}>
                <div style={{ marginBottom: '16px' }}>
                    <h3 style={{ color: palette.textPrimary, fontSize: '18px', fontWeight: 700, margin: 0 }}>
                        How does {selectedCommodity} compare?
                    </h3>
                    <p style={{ color: palette.textSecondary, fontSize: '13px', marginTop: '4px' }}>
                        Top 10 crops by area harvested in {stateName}, {year}
                    </p>
                </div>

                <div style={{ height: '400px' }}>
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                            layout="vertical" data={topCropsRanking}
                            margin={{ top: 0, right: 30, left: 10, bottom: 0 }}
                        >
                            <CartesianGrid {...chartDefaults.grid} horizontal />
                            <XAxis type="number" {...chartDefaults.axisStyle} tickFormatter={formatCompact} />
                            <YAxis
                                type="category" dataKey="commodity" width={120}
                                tick={{ fill: palette.textSecondary, fontSize: 11 }}
                                axisLine={false} tickLine={false}
                            />
                            <Tooltip
                                {...chartDefaults.tooltipStyle}
                                formatter={(val: any) => [val ? val.toLocaleString() + ' acres' : '0', 'Area Harvested']}
                            />
                            <Bar dataKey="value" radius={[0, 6, 6, 0]} barSize={24}
                                animationDuration={chartDefaults.animationDuration}
                            >
                                {topCropsRanking.map((entry: any, index: number) => (
                                    <Cell
                                        key={index}
                                        fill={entry.commodity === selectedCommodity ? palette.yield : palette.rank[index % palette.rank.length]}
                                        opacity={entry.commodity === selectedCommodity ? 1 : 0.7}
                                        stroke={entry.commodity === selectedCommodity ? palette.yield : 'transparent'}
                                        strokeWidth={entry.commodity === selectedCommodity ? 2 : 0}
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
