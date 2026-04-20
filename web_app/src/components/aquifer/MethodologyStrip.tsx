export default function MethodologyStrip({ countyCount }: { countyCount: number }) {
  return (
    <section style={{
      background: 'var(--surface)',
      borderTop: '1px solid var(--border)',
      borderBottom: '1px solid var(--border)',
      marginTop: 56,
      padding: '48px 24px',
    }}>
      <div style={{ maxWidth: 1440, margin: '0 auto' }}>
        <div className="eyebrow">§ 05 Methodology</div>
        <div className="stat" style={{ fontSize: 30, fontWeight: 800, letterSpacing: '-0.01em', lineHeight: 1.15, marginTop: 8, maxWidth: 900 }}>
          Every number on screen traces to a row in{' '}
          <code className="mono" style={{ fontSize: '0.7em', background: 'var(--surface2)', padding: '2px 8px', borderRadius: 4, color: 'var(--field)' }}>
            docs/data_sources.md
          </code>
          .
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 40, marginTop: 32 }}>
          <Col
            num="16"
            label="Data sources"
            body="USGS HPA boundary, NWIS, Water Data OGC, USGS Water Use 2015, USDA NASS Census, IWMS 2023, ERS budgets, EPA eGRID, KGS WIMAS + WIZARD + Master Well Inventory + HPA bedrock, TX TWDB GWDB, NE DEE wells, USGS NGWMN."
          />
          <Col
            num="4"
            label="Model tiers"
            body="T1 Physics baseline (vol-balance, deterministic). T2 GBDT imputation for modeled_low counties (LOSO-CV). T3 Scenario deltas on T1 forward-sim. T4 Per-crop pumping attribution (pure arithmetic)."
          />
          <Col
            num="0.52×"
            label="USGS calibration"
            body="Our inferred pumping is ~half of USGS 2015 reported. Percentage deltas unaffected; absolute CO₂ numbers 2× understated. Surfaced in the UI as a conservative estimate — the honesty is the credibility feature."
          />
        </div>
        <div className="mono" style={{ display: 'flex', gap: 20, flexWrap: 'wrap', marginTop: 32, paddingTop: 24, borderTop: '1px solid var(--border)' }}>
          <Link href="#">docs/methodology.md</Link>
          <Link href="#">docs/limitations.md</Link>
          <Link href="#">{`baseline.parquet · ${countyCount || 606} rows · 38 cols`}</Link>
          <Link href="https://github.com/Vigneshwarr3/FusionHack_2026">GitHub · Vigneshwarr3/FusionHack_2026</Link>
        </div>
      </div>
    </section>
  );
}

function Col({ num, label, body }: { num: string; label: string; body: string }) {
  return (
    <div>
      <div className="stat" style={{ fontSize: 48, fontWeight: 900, color: 'var(--field)', lineHeight: 1, letterSpacing: '-0.02em' }}>{num}</div>
      <div style={{ fontSize: 12, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.14em', margin: '8px 0 10px' }}>{label}</div>
      <div style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.65 }}>{body}</div>
    </div>
  );
}

function Link({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      style={{
        fontSize: 10, color: 'var(--text3)', letterSpacing: '0.08em',
        textDecoration: 'none', padding: '4px 0',
        borderBottom: '1px solid transparent',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.color = 'var(--field)';
        e.currentTarget.style.borderColor = 'var(--field)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.color = 'var(--text3)';
        e.currentTarget.style.borderColor = 'transparent';
      }}
    >
      {children}
    </a>
  );
}
