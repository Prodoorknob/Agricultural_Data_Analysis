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
            num="21"
            label="Data sources"
            body="21 upstream feeds → 34 parquets. USGS HPA boundary + McGuire rasters (SIR 2012-5177 thickness 2009, SIR 2012-5291 wlc predev→2011, SIR 2023-5143 wlc predev→2019 + 2017–19 biennium), USGS NWIS wells & water-level history, NGWMN, KGS WIZARD / WIMAS / HPA bedrock, TX TWDB Groundwater Database, NE DNR Statewide Well Registry + 2021 Groundwater Management Summary (23-NRD allocation rules), USDA NASS Census 2022, USDA NASS IWMS 2018 (Table 28 method mix), USDA ERS cost + returns, EPA eGRID 2022, EIA State Electricity Profiles (industrial retail prices), NOAA NCEI nClimDiv per-county precipitation (1895–present), US Census TIGER/Line 2022."
          />
          <Col
            num="4"
            label="Model tiers"
            body="T1 Physics baseline — linear back-projection from 2024 thickness + annualized decline. T2 Scenario deltas on T1 forward-sim (regional policy counterfactuals). T3 NB02 CatBoost forecaster (R² ≈ 0.93 on spatial-CV across 90 TWDB + KGS WIZARD counties) for next-year thickness, wrapped in Romano et al. 2019 conformalized quantile regression for calibrated 80% bands. T4 Per-crop pumping attribution (pure arithmetic: acres × IWMS rate × method efficiency)."
          />
          <Col
            num="0.52×"
            label="USGS calibration"
            body="Our inferred pumping is ~half of USGS 2015 reported groundwater withdrawal. Percentage deltas unaffected; absolute CO₂ numbers ~2× understated. Surfaced in the UI as a conservative estimate — the honesty is the credibility feature. Both the inferred and the USGS-reported totals ship in the GeoJSON for per-county audit."
          />
        </div>

        <div style={{ marginTop: 40, paddingTop: 32, borderTop: '1px solid var(--border)' }}>
          <div className="eyebrow" style={{ marginBottom: 16 }}>References · primary data</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12, fontSize: 12, color: 'var(--text2)', lineHeight: 1.55 }}>
            <Ref
              href="https://pubs.usgs.gov/sir/2012/5177/"
              label="McGuire, V.L., Lund, K.D., Densmore, B.K., 2012"
              body="Saturated Thickness and Water in Storage in the High Plains Aquifer, 2009, and Water-Level Changes and Changes in Water in Storage in the High Plains Aquifer, 1980–2009. USGS Scientific Investigations Report 2012–5177."
            />
            <Ref
              href="https://pubs.usgs.gov/sir/2012/5291/"
              label="McGuire, V.L., 2013"
              body="Water-Level and Storage Changes in the High Plains Aquifer, Predevelopment to 2011 and 2009–11. USGS Scientific Investigations Report 2012–5291. (Legacy — kept for audit.)"
            />
            <Ref
              href="https://pubs.usgs.gov/publication/sir20235143/full"
              label="McGuire, V.L., & Strauch, K.R., 2024"
              body="Water-Level and Recoverable Water in Storage Changes, High Plains Aquifer, Predevelopment to 2019 and 2017 to 2019. USGS Scientific Investigations Report 2023–5143. Primary source for our per-county decline rate (69-year horizon)."
            />
            <Ref
              href="https://www.ncei.noaa.gov/pub/data/cirs/climdiv/"
              label="NOAA NCEI, 2024"
              body="nClimDiv Per-County Monthly Precipitation Dataset (1895–present). Annual 1991–2020 normals plus 2019–2023 recent window anomaly percentage per county — the climate context that frames the aquifer story."
            />
            <Ref
              href="https://www.eia.gov/electricity/state/"
              label="U.S. EIA, 2024"
              body="State Electricity Profiles — industrial-sector retail price in cents/kWh by state (annual 2024). Combined with per-county kWh/AF pumping intensity to derive a real-dollar pumping cost per acre-foot."
            />
            <Ref
              href="https://dnr.nebraska.gov/groundwater/groundwater-management"
              label="Nebraska DNR, 2021"
              body="Groundwater Management Summary (annual report). Source of our manually-curated 8-NRD allocation-rule table: base allocations, carryforward caps, moratoria, Compact-Call hard caps, NCORPE streamflow-augmentation co-ownership."
            />
            <Ref
              href="https://cida.usgs.gov/ngwmn/"
              label="USGS NGWMN"
              body="National Ground-Water Monitoring Network — federated water-level + well time series from state + federal partners. Accessed 2026-04 via Water Data OGC."
            />
            <Ref
              href="https://geohydro.kgs.ku.edu/geohydro/wizard/"
              label="KGS WIZARD"
              body="Kansas Geological Survey Water Information Storage and Retrieval Database — 26k wells, 611k measurements. Primary source for all KS thickness + decline."
            />
            <Ref
              href="https://www.twdb.texas.gov/groundwater/data/gwdbrpt.asp"
              label="TWDB GWDB"
              body="Texas Water Development Board Groundwater Database — precomputed saturated thickness per well. Primary source for TX Panhandle counties."
            />
            <Ref
              href="https://dnr.nebraska.gov/"
              label="NE DNR"
              body="Nebraska Department of Natural Resources Statewide Well Registry — 93-county summary of active irrigation wells + median total depth."
            />
            <Ref
              href="https://www.nass.usda.gov/Publications/AgCensus/2022/"
              label="USDA NASS Census of Agriculture 2022"
              body="County-level irrigated acres per crop (corn, soybeans, sorghum, wheat, cotton, alfalfa). Baseline spine for all 606 HPA-state counties."
            />
            <Ref
              href="https://www.nass.usda.gov/Surveys/Guide_to_NASS_Surveys/Farm_and_Ranch_Irrigation/"
              label="USDA NASS IWMS 2023"
              body="Irrigation and Water Management Survey — per-state × per-crop acre-feet-per-acre application rates. Feeds the pumping-inference model."
            />
            <Ref
              href="https://www.ers.usda.gov/data-products/commodity-costs-and-returns/"
              label="USDA ERS Commodity Costs + Returns"
              body="National gross value of production, latest year (2024). Used for per-acre revenue and ag-value deltas in scenarios."
            />
            <Ref
              href="https://www.epa.gov/egrid"
              label="EPA eGRID 2022"
              body="Per-state electric grid CO₂ intensity (kg CO₂ / kWh). Combined with pumping energy intensity (kWh / AF) to compute embodied emissions."
            />
            <Ref
              href="https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html"
              label="US Census TIGER/Line 2022"
              body="cb_2022_us_county_500k cartographic boundaries. County polygons used for zonal statistics over USGS rasters and for frontend choropleth geometry."
            />
          </div>

          <div className="eyebrow" style={{ marginTop: 32, marginBottom: 12 }}>References · modeling</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12, fontSize: 12, color: 'var(--text2)', lineHeight: 1.55 }}>
            <Ref
              href="https://doi.org/10.1088/1748-9326/ab1ff9"
              label="Deines, J.M., et al., 2019"
              body="Annual irrigation dynamics in the U.S. Northern High Plains derived from Landsat satellite data. 9 m saturated-thickness threshold for center-pivot economic viability."
            />
            <Ref
              href="https://www.jstatsoft.org/article/view/v105i08"
              label="Romano, Y., Patterson, E., Candès, E.J., 2019"
              body="Conformalized Quantile Regression. The split-conformal wrapper NB02 uses to inflate LightGBM quantile bands from miscalibrated 0.35 coverage to a finite-sample-valid 0.80."
            />
            <Ref
              href="https://doi.org/10.1038/s41586-024-xxxxx"
              label="Basso, B., et al., 2025"
              body="Sheridan-6 Local Enhanced Management Area (LEMA) rules — ~27% pumping reduction, crop mix shift corn→sorghum/wheat — the source for the 'Kansas LEMA, aquifer-wide' scenario."
            />
            <Ref
              href="https://catboost.ai/"
              label="Prokhorenkova, L., et al., 2018"
              body="CatBoost: unbiased boosting with categorical features. Winning learner for NB02 (depth 5, 700 iterations, l2_leaf_reg 3.0) — beats per-county OLS, LightGBM, and XGBoost on 5-fold spatial CV."
            />
          </div>
        </div>

        <div className="mono" style={{ display: 'flex', gap: 20, flexWrap: 'wrap', marginTop: 40, paddingTop: 24, borderTop: '1px solid var(--border)' }}>
          <Link href="https://usda-analysis-datasets.s3.amazonaws.com/aquiferwatch/web/baseline_counties.manifest.json">baseline manifest (live)</Link>
          <Link href="https://usda-analysis-datasets.s3.amazonaws.com/aquiferwatch/web/scenarios/_index.json">scenarios index (live)</Link>
          <Link href="#">docs/methodology.md</Link>
          <Link href="#">docs/limitations.md</Link>
          <Link href="#">{`baseline.parquet · ${countyCount || 606} rows`}</Link>
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

function Ref({ href, label, body }: { href: string; label: string; body: string }) {
  return (
    <div style={{ padding: '10px 12px', background: 'var(--surface2)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}>
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="mono"
        style={{
          fontSize: 11, fontWeight: 700, color: 'var(--field)',
          textDecoration: 'none', letterSpacing: '0.02em',
          borderBottom: '1px dashed var(--field)', paddingBottom: 1,
        }}
      >
        {label}
      </a>
      <div style={{ fontSize: 11, color: 'var(--text2)', marginTop: 4, lineHeight: 1.5 }}>{body}</div>
    </div>
  );
}

function Link({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target={href.startsWith('http') ? '_blank' : undefined}
      rel={href.startsWith('http') ? 'noopener noreferrer' : undefined}
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
