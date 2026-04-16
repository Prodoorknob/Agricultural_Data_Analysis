'use client';

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import CitationBlock from '@/components/shared/CitationBlock';

interface AccuracyItem {
  forecast_year: number;
  commodity: string;
  model_vs_actual_pct: number | null;
}

interface YieldAccuracyWeek {
  crop: string;
  week: number;
  avg_pct_error: number;
  baseline_rrmse: number;
}

interface AccuracyPanelProps {
  acreageAccuracy: AccuracyItem[];
  yieldAccuracy: YieldAccuracyWeek[];
}

export default function AccuracyPanel({ acreageAccuracy, yieldAccuracy }: AccuracyPanelProps) {
  const hasAcreage = acreageAccuracy.length > 0;
  const hasYield = yieldAccuracy.length > 0;

  if (!hasAcreage && !hasYield) {
    return (
      <div
        className="p-6 rounded-[var(--radius-lg)] border text-center"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
      >
        <p className="text-[14px]" style={{ color: 'var(--text3)' }}>
          Accuracy data loading from backend...
        </p>
      </div>
    );
  }

  return (
    <div className="mb-8">
      <h3
        className="text-[18px] font-bold mb-1"
        style={{ color: 'var(--text)', fontFamily: 'var(--font-body)' }}
      >
        Season-by-Season Accuracy
      </h3>
      <p className="text-[13px] mb-4" style={{ color: 'var(--text2)' }}>
        Walk-forward test results. No forecast without its track record.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Acreage accuracy */}
        {hasAcreage && (
          <div
            className="p-4 rounded-[var(--radius-lg)] border"
            style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
          >
            <p className="text-[11px] font-bold tracking-[0.1em] uppercase mb-3"
              style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
              Acreage · Model vs Actual %
            </p>
            <div style={{ height: 200 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={acreageAccuracy} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="forecast_year" axisLine={false} tickLine={false}
                    tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }} />
                  <YAxis axisLine={false} tickLine={false}
                    tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                    tickFormatter={(v) => `${v}%`} />
                  <Tooltip contentStyle={{
                    background: 'var(--surface)', border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--text)',
                  }} />
                  <Line type="monotone" dataKey="model_vs_actual_pct" stroke="var(--field)" strokeWidth={2} dot={{ r: 3, fill: 'var(--field)' }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Yield accuracy by week */}
        {hasYield && (
          <div
            className="p-4 rounded-[var(--radius-lg)] border"
            style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
          >
            <p className="text-[11px] font-bold tracking-[0.1em] uppercase mb-3"
              style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
              Yield · RRMSE by Week
            </p>
            <div style={{ height: 200 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={yieldAccuracy} margin={{ top: 5, right: 10, bottom: 5, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="week" axisLine={false} tickLine={false}
                    tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }} />
                  <YAxis axisLine={false} tickLine={false}
                    tick={{ fill: 'var(--text3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                    tickFormatter={(v) => `${v}%`} />
                  <Tooltip contentStyle={{
                    background: 'var(--surface)', border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-md)', fontSize: 12, color: 'var(--text)',
                  }} />
                  <Line type="monotone" dataKey="avg_pct_error" stroke="var(--field)" strokeWidth={2} name="Model RRMSE" dot={false} />
                  <Line type="monotone" dataKey="baseline_rrmse" stroke="var(--text3)" strokeWidth={1} strokeDasharray="4 3" name="Baseline" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </div>
      <CitationBlock source="Walk-forward backtest" vintage="2020–2025" />
    </div>
  );
}
