'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import CitationBlock from '@/components/shared/CitationBlock';
import { COMMODITY_COLORS } from '@/lib/constants';

/**
 * Retrospective view of the yield model's walk-forward performance.
 *
 * The live yield forecast doesn't start until mid-May (week 1 of each crop's
 * growing season), so during off-season we surface the 2024-2025 test-set
 * results instead — it's honest about the model's limits and still shows the
 * full pipeline actually produced measurable numbers.
 *
 * Endpoints used:
 *   GET /api/v1/predict/yield/accuracy?crop=X  -> per-week avg RRMSE + baseline
 *   GET /api/v1/predict/yield/metadata?crop=X  -> aggregate gate status
 */

type CropKey = 'corn' | 'soybean' | 'wheat';

interface AccuracyWeek {
  crop: string;
  week: number;
  avg_pct_error: number | null;
  avg_coverage: number | null;
  baseline_rrmse: number | null;
  n_counties: number;
}

interface ModelMetadata {
  crop: string;
  model_ver: string | null;
  n_weeks: number;
  n_weeks_pass_gate: number;
  gate_status: 'pass' | 'partial' | 'fail';
  avg_val_rrmse: number | null;
  avg_test_rrmse: number | null;
  avg_baseline_rrmse: number | null;
  has_weather_features: boolean;
  gate_threshold_pct: number | null;
}

const API_BASE =
  process.env.NEXT_PUBLIC_PREDICTION_API_URL || 'http://localhost:8000';

const CROP_TABS: { id: CropKey; label: string }[] = [
  { id: 'corn', label: 'Corn' },
  { id: 'soybean', label: 'Soybean' },
  { id: 'wheat', label: 'Wheat' },
];

export default function YieldSeasonReview() {
  const [crop, setCrop] = useState<CropKey>('corn');
  const [accuracy, setAccuracy] = useState<AccuracyWeek[]>([]);
  const [metadata, setMetadata] = useState<ModelMetadata | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    const fetchJson = async <T,>(path: string): Promise<T | null> => {
      try {
        const resp = await fetch(`${API_BASE}${path}`, { signal: controller.signal });
        if (!resp.ok) return null;
        return (await resp.json()) as T;
      } catch (err) {
        if ((err as { name?: string })?.name === 'AbortError') throw err;
        return null;
      }
    };

    Promise.all([
      fetchJson<AccuracyWeek[]>(`/api/v1/predict/yield/accuracy?crop=${crop}&split=test`),
      fetchJson<ModelMetadata>(`/api/v1/predict/yield/metadata?crop=${crop}`),
    ])
      .then(([acc, meta]) => {
        if (controller.signal.aborted) return;
        setAccuracy(acc || []);
        setMetadata(meta);
        if (!acc && !meta) {
          setError('Retrospective data not available — check that the backend is running and yield models are trained.');
        }
      })
      .catch((err: unknown) => {
        if ((err as { name?: string })?.name !== 'AbortError') {
          setError('Failed to load retrospective data.');
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [crop]);

  const chartColor = COMMODITY_COLORS[crop] || 'var(--field)';

  const chartData = useMemo(
    () =>
      accuracy
        .filter((r) => r.avg_pct_error !== null)
        .sort((a, b) => a.week - b.week)
        .map((r) => ({
          week: r.week,
          model: r.avg_pct_error,
          baseline: r.baseline_rrmse,
        })),
    [accuracy],
  );

  const bestWeek = useMemo(() => {
    const candidates = accuracy.filter((r) => r.avg_pct_error !== null);
    if (!candidates.length) return null;
    return candidates.reduce((best, r) =>
      (r.avg_pct_error ?? Infinity) < (best.avg_pct_error ?? Infinity) ? r : best,
    );
  }, [accuracy]);

  const gatePill = metadata ? renderGatePill(metadata.gate_status) : null;

  return (
    <div
      className="p-5 rounded-[var(--radius-lg)] border"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
    >
      {/* Header: crop tabs */}
      <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
        <div>
          <p
            className="text-[11px] font-bold tracking-[0.1em] uppercase"
            style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
          >
            2024–2025 Season Review
          </p>
          <p className="text-[13px] mt-1" style={{ color: 'var(--text2)' }}>
            Walk-forward test results. County-level model predictions vs realized yields,
            averaged across every county in the training panel.
          </p>
        </div>
        <div className="flex items-center gap-1 p-1 rounded-[var(--radius-full)]"
             style={{ background: 'var(--surface2)' }}>
          {CROP_TABS.map((t) => {
            const active = t.id === crop;
            return (
              <button
                key={t.id}
                onClick={() => setCrop(t.id)}
                className="px-3 py-1 rounded-[var(--radius-full)] text-[12px] font-semibold transition-colors"
                style={{
                  background: active ? 'var(--surface)' : 'transparent',
                  color: active ? 'var(--text)' : 'var(--text3)',
                  fontFamily: 'var(--font-mono)',
                  border: active ? '1px solid var(--border)' : '1px solid transparent',
                }}
              >
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Body */}
      {loading ? (
        <div className="h-64 flex items-center justify-center" style={{ color: 'var(--text3)' }}>
          Loading {crop} retrospective…
        </div>
      ) : error ? (
        <div className="h-64 flex items-center justify-center text-center text-[13px]"
             style={{ color: 'var(--text3)' }}>
          {error}
        </div>
      ) : !chartData.length && !metadata ? (
        <div className="h-64 flex items-center justify-center text-center text-[13px]"
             style={{ color: 'var(--text3)' }}>
          No retrospective data for {crop}. Run{' '}
          <code>python -m backend.models.train_yield --persist-accuracy</code> to populate.
        </div>
      ) : (
        <>
          {/* KPI strip */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
            <KpiTile
              label="Test MAPE"
              value={fmtPct(metadata?.avg_test_rrmse)}
              footnote={metadata?.avg_baseline_rrmse !== null && metadata?.avg_baseline_rrmse !== undefined
                ? `vs ${metadata.avg_baseline_rrmse.toFixed(1)}% baseline`
                : '—'}
              color={chartColor}
            />
            <KpiTile
              label="Gate status"
              value={metadata ? `${metadata.n_weeks_pass_gate}/${metadata.n_weeks}` : '—'}
              footnote="weeks beat baseline"
              pill={gatePill}
            />
            <KpiTile
              label="Best week"
              value={bestWeek ? `wk ${bestWeek.week}` : '—'}
              footnote={bestWeek ? `${fmtPct(bestWeek.avg_pct_error)} MAPE` : '—'}
            />
            <KpiTile
              label="Model features"
              value={metadata?.has_weather_features ? 'NASS + weather' : 'NASS only'}
              footnote={metadata?.model_ver ? `v${metadata.model_ver}` : '—'}
            />
          </div>

          {/* Chart */}
          {chartData.length > 0 && (
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis
                    dataKey="week"
                    stroke="var(--text3)"
                    tick={{ fill: 'var(--text3)', fontSize: 11 }}
                    label={{ value: 'Week of season', position: 'insideBottom', offset: -5,
                             fill: 'var(--text3)', fontSize: 11 }}
                  />
                  <YAxis
                    stroke="var(--text3)"
                    tick={{ fill: 'var(--text3)', fontSize: 11 }}
                    tickFormatter={(v: number) => `${v}%`}
                    label={{ value: 'RRMSE', angle: -90, position: 'insideLeft',
                             fill: 'var(--text3)', fontSize: 11 }}
                  />
                  <Tooltip
                    contentStyle={{
                      background: 'var(--surface)',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: 12,
                    }}
                    formatter={(v: unknown) => {
                      const num = Number(v);
                      return Number.isFinite(num) ? `${num.toFixed(2)}%` : '—';
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line
                    type="monotone"
                    dataKey="model"
                    name="Model"
                    stroke={chartColor}
                    strokeWidth={2}
                    dot={{ r: 3 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="baseline"
                    name="County 5-yr mean (baseline)"
                    stroke="var(--text3)"
                    strokeWidth={1}
                    strokeDasharray="4 3"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Honesty note for partial/fail */}
          {metadata && metadata.gate_status !== 'pass' && (
            <p className="mt-3 text-[11px]" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
              {metadata.gate_status === 'fail'
                ? 'Model did not beat the county 5-yr baseline on any week — treat predictions as experimental.'
                : `${metadata.n_weeks - metadata.n_weeks_pass_gate} of ${metadata.n_weeks} weeks underperformed the baseline.`}
            </p>
          )}
        </>
      )}

      <CitationBlock
        source="FieldPulse yield ensemble · walk-forward test (2024–2025)"
        vintage={metadata?.model_ver || 'unknown'}
      />
    </div>
  );
}

function KpiTile({
  label,
  value,
  footnote,
  color,
  pill,
}: {
  label: string;
  value: string;
  footnote: string;
  color?: string;
  pill?: React.ReactNode;
}) {
  return (
    <div
      className="p-3 rounded-[var(--radius-md)] border"
      style={{ background: 'var(--surface2)', borderColor: 'var(--border)' }}
    >
      <div className="flex items-center gap-2 mb-1">
        <p
          className="text-[10px] font-bold tracking-[0.1em] uppercase"
          style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
        >
          {label}
        </p>
        {pill}
      </div>
      <p
        className="text-[20px] font-extrabold tracking-[-0.01em]"
        style={{
          fontFamily: 'var(--font-stat)',
          color: color || 'var(--text)',
        }}
      >
        {value}
      </p>
      <p className="text-[11px] mt-0.5" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
        {footnote}
      </p>
    </div>
  );
}

function renderGatePill(status: 'pass' | 'partial' | 'fail') {
  const styles: Record<typeof status, { bg: string; fg: string; label: string }> = {
    pass: { bg: 'var(--field-subtle)', fg: 'var(--field-dark)', label: 'PASS' },
    partial: { bg: 'var(--harvest-subtle)', fg: 'var(--harvest-dark)', label: 'PARTIAL' },
    fail: { bg: 'var(--surface2)', fg: 'var(--negative)', label: 'EXPERIMENTAL' },
  };
  const s = styles[status];
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded-[var(--radius-full)]"
      style={{
        background: s.bg,
        color: s.fg,
        fontFamily: 'var(--font-mono)',
        fontSize: '9px',
        fontWeight: 700,
        letterSpacing: '0.12em',
      }}
    >
      {s.label}
    </span>
  );
}

function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return `${v.toFixed(1)}%`;
}
