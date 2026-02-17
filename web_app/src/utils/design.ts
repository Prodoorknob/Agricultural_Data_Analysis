/**
 * Design System — Modern Agricultural Dashboard
 * Shared tokens for colors, animations, chart styling.
 */

// ─── Color Palette ────────────────────────────────────────────
export const palette = {
    // Core
    bg: '#0f1117',
    bgCard: '#1a1d27',
    bgCardHover: '#1f2233',
    bgSidebar: '#141720',
    bgInput: '#232738',
    border: '#2a2e3d',
    borderHover: '#3d4256',

    // Text
    textPrimary: '#e8eaed',
    textSecondary: '#9ca3af',
    textMuted: '#6b7280',
    textAccent: '#60a5fa',

    // Chart Colors — Vibrant, modern
    yield: '#34d399',         // Emerald green
    yieldGradient: 'rgba(52, 211, 153, 0.15)',
    production: '#60a5fa',    // Blue
    productionGradient: 'rgba(96, 165, 250, 0.12)',
    areaHarvested: '#a78bfa', // Purple
    areaPlanted: '#38bdf8',   // Sky blue
    revenue: '#fbbf24',       // Amber/gold
    revenueGradient: 'rgba(251, 191, 36, 0.12)',

    // Semantic
    positive: '#34d399',
    negative: '#f87171',
    warning: '#fbbf24',
    anomaly: '#f87171',
    anomalyBg: 'rgba(248, 113, 113, 0.08)',
    highlight: 'rgba(96, 165, 250, 0.12)',

    // Rank chart (gradient blue → teal)
    rank: ['#3b82f6', '#2563eb', '#1d4ed8', '#1e40af', '#1e3a8a',
        '#0d9488', '#0f766e', '#115e59', '#134e4a', '#064e3b'],
};

// ─── Chart Shared Style Props ────────────────────────────────
export const chartDefaults = {
    animationDuration: 800,
    animationEasing: 'ease-out' as const,

    grid: {
        strokeDasharray: '3 3',
        stroke: '#2a2e3d',
        vertical: false,
    },

    axisStyle: {
        axisLine: false,
        tickLine: false,
        tick: { fill: '#6b7280', fontSize: 11 },
    },

    tooltipStyle: {
        contentStyle: {
            background: '#1a1d27',
            border: '1px solid #2a2e3d',
            borderRadius: '10px',
            boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
            color: '#e8eaed',
            fontSize: '12px',
        },
        labelStyle: { color: '#9ca3af' },
        cursor: { fill: 'rgba(96, 165, 250, 0.06)' },
    },

    dotStyle: {
        r: 3,
        strokeWidth: 0,
    },

    activeDotStyle: {
        r: 6,
        strokeWidth: 2,
        stroke: '#1a1d27',
    },
};

// ─── Number Formatting ───────────────────────────────────────
export function formatCompact(val: number): string {
    if (Math.abs(val) >= 1e9) return `${(val / 1e9).toFixed(1)}B`;
    if (Math.abs(val) >= 1e6) return `${(val / 1e6).toFixed(1)}M`;
    if (Math.abs(val) >= 1e3) return `${(val / 1e3).toFixed(0)}K`;
    return val.toLocaleString();
}

export function formatCurrency(val: number): string {
    if (Math.abs(val) >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
    if (Math.abs(val) >= 1e6) return `$${(val / 1e6).toFixed(1)}M`;
    if (Math.abs(val) >= 1e3) return `$${(val / 1e3).toFixed(0)}K`;
    return `$${val.toLocaleString()}`;
}

export function formatDelta(current: number, previous: number): { text: string; positive: boolean; pct: number } {
    if (!previous || previous === 0) return { text: 'N/A', positive: true, pct: 0 };
    const pct = ((current - previous) / previous) * 100;
    return {
        text: `${pct >= 0 ? '▲' : '▼'} ${Math.abs(pct).toFixed(1)}%`,
        positive: pct >= 0,
        pct,
    };
}
