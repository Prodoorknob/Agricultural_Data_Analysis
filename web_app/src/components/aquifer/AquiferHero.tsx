export default function AquiferHero() {
  return (
    <section style={{ position: 'relative', padding: '56px 0 40px', overflow: 'hidden' }}>
      <div>
        <div className="eyebrow">High Plains Aquifer · 8 states · 606 counties</div>
        <h1
          className="stat"
          style={{
            fontSize: 'clamp(48px, 6vw, 88px)',
            fontWeight: 800,
            lineHeight: 0.98,
            letterSpacing: '-0.02em',
            margin: '14px 0 20px',
            color: 'var(--text)',
            textWrap: 'balance',
          }}
        >
          The Ogallala is draining.<br />
          <em style={{ fontStyle: 'italic', fontWeight: 400, color: 'var(--field)' }}>Here is the receipt.</em>
        </h1>
        <p style={{ maxWidth: 720, color: 'var(--text2)', fontSize: 16, lineHeight: 1.6 }}>
          A county-level accountability map of the aquifer that sustains{' '}
          <strong style={{ color: 'var(--text)', fontWeight: 700 }}>$35 billion</strong>{' '}
          in annual agricultural production across the High Plains. Real measurements from 202 of 606 counties,
          physics-first depletion math, and a scenario engine that makes the trade-offs of inaction visible.
        </p>
        <div
          style={{
            display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
            marginTop: 48,
            borderTop: '1px solid var(--border2)',
            borderBottom: '1px solid var(--border2)',
          }}
        >
          <Kpi eyebrow="Counties measured" value="202" suffix="/606" desc="33% ground-truthed thickness + decline" />
          <Kpi eyebrow="Pumping estimate" value="9.5" suffix="M AF/yr" desc="0.52× USGS 2015 · conservative" />
          <Kpi eyebrow="Fastest decline" value="−0.97" suffix="m/yr" desc="worst county, over the past decade" valueColor="var(--negative)" />
          <Kpi eyebrow="Simulation horizon" value="1950—2100" suffix="" desc="annual · per county · 6 scenarios" last />
        </div>
      </div>
      <svg
        viewBox="0 0 1600 60"
        preserveAspectRatio="none"
        style={{ position: 'absolute', bottom: 0, left: 0, width: '100%', height: 60, pointerEvents: 'none' }}
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

function Kpi({
  eyebrow,
  value,
  suffix,
  desc,
  valueColor,
  last,
}: {
  eyebrow: string;
  value: string;
  suffix: string;
  desc: string;
  valueColor?: string;
  last?: boolean;
}) {
  return (
    <div style={{ padding: '24px 28px 24px 0', borderRight: last ? 'none' : '1px solid var(--border)' }}>
      <div className="eyebrow">{eyebrow}</div>
      <div
        className="stat"
        style={{
          fontSize: 48, fontWeight: 800, lineHeight: 1, marginTop: 6,
          color: valueColor ?? 'var(--text)',
          letterSpacing: '-0.01em',
        }}
      >
        {value}
        {suffix && <span style={{ fontSize: 16, color: 'var(--text3)', marginLeft: 6, fontWeight: 500 }}>{suffix}</span>}
      </div>
      <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 6, lineHeight: 1.4 }}>{desc}</div>
    </div>
  );
}
