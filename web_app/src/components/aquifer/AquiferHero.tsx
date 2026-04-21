export default function AquiferHero() {
  return (
    <section style={{ position: 'relative', padding: '48px 0 32px', overflow: 'hidden' }}>
      <div>
        <div className="eyebrow">High Plains Aquifer · 8 states · 227 counties on footprint</div>
        <h1
          className="stat"
          style={{
            fontSize: 'clamp(44px, 5.5vw, 76px)',
            fontWeight: 800,
            lineHeight: 0.98,
            letterSpacing: '-0.02em',
            margin: '14px 0 18px',
            color: 'var(--text)',
            textWrap: 'balance',
          }}
        >
          The Ogallala is draining.
        </h1>
        <p style={{ maxWidth: 720, color: 'var(--text2)', fontSize: 15, lineHeight: 1.6 }}>
          A county-level accountability map of the aquifer that sustains{' '}
          <strong style={{ color: 'var(--text)', fontWeight: 700 }}>$35 billion</strong>{' '}
          in annual agricultural production across the High Plains. Thickness + decline from 208 measurement-backed counties,
          plus 19 more sampled from USGS McGuire&apos;s published rasters (SIR 2012-5177 / 5291). NB02 CatBoost forecaster with
          conformal 80% bands on 89 counties. Every number traces to a source.
        </p>

        {/* Inline KPI pills */}
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: 0,
            marginTop: 20,
            fontSize: 13,
            lineHeight: 1.4,
          }}
        >
          <Pill label="Counties on footprint" value="227" suffix="/606" />
          <Sep />
          <Pill label="Pumping estimate" value="9.5" suffix="M AF/yr" />
          <Sep />
          <Pill label="NB02 spatial-CV R²" value="0.93" valueColor="var(--field)" />
          <Sep />
          <Pill label="Simulation horizon" value="1950—2100" />
        </div>
      </div>
      <svg
        viewBox="0 0 1600 60"
        preserveAspectRatio="none"
        style={{ position: 'absolute', bottom: 0, left: 0, width: '100%', height: 40, pointerEvents: 'none' }}
      >
        <path
          d="M0 30 Q 200 10, 400 30 T 800 30 T 1200 30 T 1600 30 L 1600 60 L 0 60 Z"
          fill="var(--field-tint)"
          opacity="0.5"
        />
        <path
          d="M0 40 Q 200 22, 400 40 T 800 40 T 1200 40 T 1600 40 L 1600 60 L 0 60 Z"
          fill="var(--field-tint)"
          opacity="0.8"
        />
      </svg>
    </section>
  );
}

function Pill({
  label,
  value,
  suffix,
  valueColor,
}: {
  label: string;
  value: string;
  suffix?: string;
  valueColor?: string;
}) {
  return (
    <div style={{ display: 'inline-flex', alignItems: 'baseline', gap: 6, padding: '2px 0' }}>
      <span
        className="mono"
        style={{
          fontSize: 10,
          color: 'var(--text3)',
          textTransform: 'uppercase',
          letterSpacing: '0.1em',
        }}
      >
        {label}
      </span>
      <span
        className="stat"
        style={{
          fontSize: 16,
          fontWeight: 800,
          color: valueColor ?? 'var(--text)',
          letterSpacing: '-0.01em',
        }}
      >
        {value}
        {suffix && <span style={{ fontSize: 11, color: 'var(--text3)', marginLeft: 2, fontWeight: 500 }}>{suffix}</span>}
      </span>
    </div>
  );
}

function Sep() {
  return (
    <span
      aria-hidden
      style={{
        display: 'inline-block',
        width: 1,
        height: 18,
        background: 'var(--border2)',
        margin: '0 14px',
      }}
    />
  );
}
