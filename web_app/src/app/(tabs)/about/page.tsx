'use client';

import { useEffect, useState } from 'react';
import CitationBlock from '@/components/shared/CitationBlock';
import SectionHeading from '@/components/shared/SectionHeading';

interface ModelItem {
  task: 'price' | 'acreage' | 'yield';
  commodity: string;
  horizon: string | null;
  model_ver: string | null;
  test_metric_name: string | null;
  test_metric_value: number | null;
  baseline_metric_value: number | null;
  beats_baseline: boolean;
  gate_status: 'pass' | 'borderline' | 'fail' | string;
  coverage: number | null;
  n_train: number | null;
  n_val: number | null;
  n_test: number | null;
  n_features: number | null;
  top_features: string[];
  artifact_exists: boolean;
}

interface ModelsMeta {
  as_of: string;
  models: ModelItem[];
  summary: {
    total_models: number;
    passing_gate: number;
    borderline_gate: number;
    failing_gate: number;
    partial_gate: number;
    price_models: number;
    acreage_models: number;
    yield_crops: number;
  };
}

const GATE_COLORS: Record<string, string> = {
  pass: 'var(--positive)',
  borderline: 'var(--harvest)',
  fail: 'var(--negative)',
  partial: 'var(--harvest)',
};

const GATE_LABELS: Record<string, string> = {
  pass: 'PASS',
  borderline: 'BORDERLINE',
  fail: 'FAIL',
  partial: 'PARTIAL',
};

// NASS, ERS, CME, FRED, NOAA, NASA, USDM, RMA, FSA, FAS, BLS QCEW.
const DATA_SOURCES = [
  { name: 'USDA NASS QuickStats', role: 'Backbone dataset — state/county yields, acreage, operations, sales, crop progress, prices received.' },
  { name: 'USDA ERS', role: 'Per-acre production costs by commodity (Excel release, annual).' },
  { name: 'CME Group (via Yahoo Finance)', role: 'Daily settle prices for futures contracts (corn, soy, wheat, cotton).' },
  { name: 'FRED', role: 'Daily U.S. Dollar Index (DXY) as a macro feature.' },
  { name: 'NOAA GHCN-Daily', role: 'Daily TMAX / TMIN / PRCP at weather stations — crunched into county GDD and precip deficit features.' },
  { name: 'NASA POWER', role: 'Gridded solar radiation and VPD (vapor pressure deficit) for yield stress features.' },
  { name: 'US Drought Monitor (USDM)', role: 'Weekly county-level D0–D4 drought severity — fall/winter drought is an acreage-intent signal.' },
  { name: 'USDA RMA Summary of Business', role: 'Crop insurance-insured acres by (state, crop, year) — a revealed-preference signal for planting intent.' },
  { name: 'USDA FSA', role: 'CRP (Conservation Reserve Program) enrollment and contract expirations — constrains land supply.' },
  { name: 'USDA FAS ESRQS', role: 'Weekly export commitments by commodity and marketing year — demand-pipeline context.' },
  { name: 'BLS QCEW', role: 'Quarterly Census of Employment & Wages — establishment counts and avg_annual_pay for NAICS 111 (crop workers).' },
];

function GateBadge({ status }: { status: string }) {
  const color = GATE_COLORS[status] ?? 'var(--text3)';
  const label = GATE_LABELS[status] ?? status.toUpperCase();
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-[var(--radius-full)] text-[10px] font-bold"
      style={{
        color,
        border: `1px solid ${color}`,
        background: 'transparent',
        fontFamily: 'var(--font-mono)',
      }}
    >
      {label}
    </span>
  );
}

function ModelTile({ m }: { m: ModelItem }) {
  const test = m.test_metric_value;
  const base = m.baseline_metric_value;
  const metricName = m.test_metric_name ?? 'metric';
  const fmt = (v: number | null) => (v == null ? '—' : v.toFixed(2));
  const label = [m.commodity, m.horizon].filter(Boolean).join(' · ');

  return (
    <div
      className="p-3 rounded-[var(--radius-md)] border"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
    >
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span
          className="text-[13px] font-bold tracking-[-0.01em]"
          style={{ color: 'var(--text)', fontFamily: 'var(--font-body)' }}
        >
          {label || m.commodity}
        </span>
        <GateBadge status={m.gate_status} />
      </div>
      <div className="flex items-baseline gap-3">
        <span
          style={{
            fontFamily: 'var(--font-stat)',
            fontSize: '20px',
            fontWeight: 800,
            color: 'var(--text)',
          }}
        >
          {fmt(test)}
        </span>
        <span
          className="text-[11px]"
          style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
        >
          {metricName} · baseline {fmt(base)}
        </span>
      </div>
      <p
        className="mt-1.5 text-[11px]"
        style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
      >
        {m.model_ver ? `v${m.model_ver}` : 'unversioned'}
        {m.n_train != null && ` · n=${m.n_train}/${m.n_val ?? '—'}/${m.n_test ?? '—'}`}
      </p>
    </div>
  );
}

function ModelsByTaskSection({ title, models }: { title: string; models: ModelItem[] }) {
  if (models.length === 0) return null;
  return (
    <div className="mb-5">
      <SectionHeading>{title}</SectionHeading>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mt-2">
        {models.map((m) => (
          <ModelTile key={`${m.task}-${m.commodity}-${m.horizon ?? 'none'}`} m={m} />
        ))}
      </div>
    </div>
  );
}

export default function AboutPage() {
  const [meta, setMeta] = useState<ModelsMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const base = process.env.NEXT_PUBLIC_PREDICTION_API_URL || 'http://localhost:8000';
    const controller = new AbortController();
    fetch(`${base}/api/v1/meta/models`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((d: ModelsMeta | null) => {
        if (d) setMeta(d);
        else setError('Backend is unreachable — model metadata unavailable.');
      })
      .catch((e: unknown) => {
        if ((e as { name?: string })?.name !== 'AbortError') {
          setError('Backend is unreachable — model metadata unavailable.');
        }
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  const priceModels = meta?.models.filter((m) => m.task === 'price') ?? [];
  const acreageModels = meta?.models.filter((m) => m.task === 'acreage') ?? [];
  const yieldModels = meta?.models.filter((m) => m.task === 'yield') ?? [];

  return (
    <div className="max-w-[900px]">
      <h1
        className="text-[28px] font-extrabold tracking-[-0.02em] mb-4"
        style={{ color: 'var(--text)', fontFamily: 'var(--font-body)' }}
      >
        About FieldPulse
      </h1>

      {/* 1. What this is */}
      <section className="mb-8">
        <p className="text-[15px] leading-[1.6]" style={{ color: 'var(--text2)' }}>
          FieldPulse is a U.S. agricultural intelligence dashboard: a blend of
          long-run USDA reference data, daily market indicators, and
          conformal-calibrated forecasts for price, planted acreage, and county
          yield. Everything in the app is backed by public data sources that are
          refreshed on a pipeline cadence, and every forecast ships with its
          walk-forward track record so you can see where the model works and
          where it doesn't.
        </p>
      </section>

      {/* 2. Data sources */}
      <section className="mb-8">
        <SectionHeading>Data Sources</SectionHeading>
        <dl className="mt-3 space-y-2">
          {DATA_SOURCES.map((s) => (
            <div key={s.name}>
              <dt
                className="text-[13px] font-bold inline"
                style={{ color: 'var(--text)', fontFamily: 'var(--font-body)' }}
              >
                {s.name}
              </dt>
              <dd className="text-[13px] inline ml-2" style={{ color: 'var(--text2)' }}>
                — {s.role}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      {/* 3. Pipeline */}
      <section className="mb-8">
        <SectionHeading>Pipeline</SectionHeading>
        <p className="mt-2 text-[14px] leading-[1.6]" style={{ color: 'var(--text2)' }}>
          A Python ingest (EC2 cron, 15th of each month) pulls NASS QuickStats
          by source, aggregation level, and stat-category chunks, applies a
          tier-aware canonical aggregation (SURVEY &gt; CENSUS &gt; DERIVED; dedup
          on (state, year, commodity, stat_cat, unit)), and writes
          state-partitioned Parquet files to S3 in two layouts: browser-friendly
          for the dashboard and Athena-optimized for ad-hoc SQL. Market data
          (futures via Yahoo, DXY via FRED) refreshes on weekdays; WASDE + ERS
          production costs on monthly / annual cadences. Structured data
          (training labels, model predictions, walk-forward accuracy) lives in
          PostgreSQL on RDS; heavy raw data stays on S3.
        </p>
      </section>

      {/* 4. Architecture */}
      <section className="mb-8">
        <SectionHeading>Architecture</SectionHeading>
        <div
          className="mt-2 rounded-[var(--radius-lg)] border overflow-hidden"
          style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
        >
          <iframe
            src="/cloud-architecture-diagram.html"
            title="Cloud architecture diagram"
            style={{ width: '100%', height: 560, border: 0, display: 'block' }}
            loading="lazy"
          />
        </div>
      </section>

      {/* 5. Forecast models */}
      <section className="mb-8">
        <SectionHeading>Forecast Models</SectionHeading>

        <h4 className="text-[14px] font-bold mt-3 mb-1" style={{ color: 'var(--text)' }}>
          Price (Module 02)
        </h4>
        <p className="text-[13px] leading-[1.6]" style={{ color: 'var(--text2)' }}>
          Targets the 1/3/6-month-ahead log return on the nearby CME futures
          contract. Features cover market microstructure (spot, deferred,
          term-spread, open-interest change, basis), fundamentals (WASDE
          stocks-to-use + surprise vs prior release), macro (DXY and 30-day
          change), production cost (ERS per-bushel cost, price/cost ratio), and
          cross-commodity interaction (corn/soy ratio). Ensemble: SARIMAX +
          LightGBM point regressor + LightGBM quantile + Ridge meta-learner +
          isotonic probability calibrator. Regime detection via regularized
          Mahalanobis distance on recent observations.
        </p>

        <h4 className="text-[14px] font-bold mt-4 mb-1" style={{ color: 'var(--text)' }}>
          Acreage (Module 03)
        </h4>
        <p className="text-[13px] leading-[1.6]" style={{ color: 'var(--text2)' }}>
          State-panel regression of planted acres by (state, year, crop), 15
          core states for corn/soy and 5 states for wheat_spring. 23 features
          spanning price ratios, input costs, prior-year planted acres, yield
          trend, rotation, drought (USDM DSCI), insured acres (RMA), CRP
          expirations (FSA), and export commitments (FAS). Ensemble: Ridge +
          LightGBM point + LightGBM quantile (p10/p90) + split conformal
          calibration. A soft cropland cap constrains the national rollup.
          Mixed target config: corn on absolute acres; soybean, wheat_winter,
          and wheat_spring on residual-vs-3yr-average (empirically the best fit).
        </p>

        <h4 className="text-[14px] font-bold mt-4 mb-1" style={{ color: 'var(--text)' }}>
          Yield (Module 04)
        </h4>
        <p className="text-[13px] leading-[1.6]" style={{ color: 'var(--text2)' }}>
          County-level yield forecast by week of the growing season (weeks 1–20),
          per crop. 60 models in total (3 crops × 20 weeks), each a LightGBM
          quantile regressor for p10/p50/p90. Features include NASS context
          (historical yield mean, prior year, acres planted) and weather to
          date (GDD, CCI from NASS weekly crop conditions, precipitation deficit
          vs PRISM normals, VPD stress days, drought D3/D4 coverage, soil AWC
          and drainage class from SSURGO). Confidence tier is week-indexed:
          &lt; 8 low, 8–15 medium, ≥ 16 high.
        </p>
      </section>

      {/* 6. Accuracy methodology */}
      <section className="mb-8">
        <SectionHeading>Accuracy Methodology</SectionHeading>
        <p className="mt-2 text-[14px] leading-[1.6]" style={{ color: 'var(--text2)' }}>
          All three modules use walk-forward evaluation: training years end at
          2019, validation covers 2020–2022, test covers 2023–2025 (acreage
          and yield) or 2020–2024 (price). Baselines are stable and honest:
          futures + 1.5pp for price, persistence and 5-year mean for acreage,
          county 5-year mean for yield. A model is &quot;PASS&quot; when its
          test metric beats the baseline by more than a small threshold,
          &quot;BORDERLINE&quot; when it&apos;s within a rounding error of the
          baseline, &quot;FAIL&quot; when it&apos;s clearly worse.
          &quot;EXPERIMENTAL&quot; tags on cards flag models whose test metric
          is within the threshold but whose validation-year behavior was
          volatile. Conformal intervals are fit on a held-out half of validation
          and reported coverage is measured on the other half.
        </p>
      </section>

      {/* 7. Known limitations */}
      <section className="mb-8">
        <SectionHeading>Known Limitations</SectionHeading>
        <ul className="mt-2 text-[14px] leading-[1.6] list-disc pl-5 space-y-1.5" style={{ color: 'var(--text2)' }}>
          <li>
            Acreage forecasts are a top-15-state sum times a national-rollup
            multiplier. They systematically miss long-tail states (Kentucky,
            Mississippi, Louisiana for wheat) and can drift 5–10% below
            USDA Prospective Plantings in heavy-planting years.
          </li>
          <li>
            <code style={{ fontFamily: 'var(--font-mono)' }}>wheat_spring</code>{' '}
            has only 5 training states (125 rows), so the model barely beats a
            5-year-average baseline. Flagged EXPERIMENTAL.
          </li>
          <li>
            Conformal prediction intervals under-cover their nominal level in
            2024 yield out-of-sample (finding from 2026-04-14). The validation
            set is small relative to county variance — recalibration is a known
            follow-up.
          </li>
          <li>
            County drought and FAS export APIs have quirks (case-sensitive
            response keys for USDM, ESRQS limits for FAS historical backfill)
            that are worked around in the ETL but could bite if the APIs
            change.
          </li>
          <li>
            The USDA NASS parquets we ingest don&apos;t publish{' '}
            <code style={{ fontFamily: 'var(--font-mono)' }}>OPERATIONS</code>{' '}
            by individual crop — that&apos;s why the Crops tab&apos;s
            &quot;Operations&quot; KPI silently hides when no data is
            available for the selected crop and state.
          </li>
        </ul>
      </section>

      {/* 8. Glossary pointer */}
      <section className="mb-8">
        <SectionHeading>Glossary</SectionHeading>
        <p className="mt-2 text-[14px]" style={{ color: 'var(--text2)' }}>
          Dashed underlines on terms (e.g. <em>WASDE</em>, <em>80% interval</em>,
          <em> corn/soy ratio</em>) throughout the app are glossary entries — hover
          to read the plain-English definition.
        </p>
      </section>

      {/* Live model metadata strip */}
      <section className="mb-8">
        <SectionHeading>Live Model Inventory</SectionHeading>
        {loading && (
          <p className="mt-2 text-[13px]" style={{ color: 'var(--text3)' }}>
            Loading model metadata…
          </p>
        )}
        {error && !loading && (
          <p className="mt-2 text-[13px]" style={{ color: 'var(--negative)' }}>
            {error}
          </p>
        )}
        {meta && !loading && (
          <>
            <p
              className="mt-2 mb-4 text-[13px]"
              style={{ color: 'var(--text2)', fontFamily: 'var(--font-body)' }}
            >
              {meta.summary.total_models} models live as of{' '}
              <span style={{ fontFamily: 'var(--font-mono)' }}>{meta.as_of}</span>{' '}
              —{' '}
              <span style={{ color: GATE_COLORS.pass, fontWeight: 700 }}>
                {meta.summary.passing_gate} pass
              </span>
              ,{' '}
              <span style={{ color: GATE_COLORS.borderline, fontWeight: 700 }}>
                {meta.summary.borderline_gate} borderline
              </span>
              ,{' '}
              <span style={{ color: GATE_COLORS.fail, fontWeight: 700 }}>
                {meta.summary.failing_gate} fail
              </span>
              . {meta.summary.price_models} price, {meta.summary.acreage_models} acreage,{' '}
              {meta.summary.yield_crops} yield (one per crop, averaged across weeks).
            </p>

            <ModelsByTaskSection title="Price" models={priceModels} />
            <ModelsByTaskSection title="Acreage" models={acreageModels} />
            <ModelsByTaskSection title="Yield" models={yieldModels} />
          </>
        )}
        <CitationBlock
          source="GET /api/v1/meta/models"
          vintage="Updated on every model retrain"
        />
      </section>
    </div>
  );
}
