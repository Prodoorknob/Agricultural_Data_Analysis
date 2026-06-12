'use client';

/**
 * Spec-driven issue renderer: takes an IssueSpec (the JSON contract the
 * chart-enabled publisher step emits) and renders the full newsletter.
 *
 * Prose blocks reuse the .fp-issue typography classes from IssueRenderer so
 * a spec-rendered issue reads identically to a markdown one. Rich blocks
 * (KPI strips, stat callouts, chart figures, region maps) use the .fpn-*
 * classes added in globals.css.
 */

import React from 'react';
import type { Block, ChartSpec, IssueSpec, Tone } from './types';
import { BarsBlock, TrendForecastBlock } from './charts';
import RegionMap from './RegionMap';

function renderInline(text: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let remainder = text;
  let key = 0;
  const PATTERN = /(\*\*([^*]+)\*\*|\*([^*]+)\*)/;
  while (remainder) {
    const m = PATTERN.exec(remainder);
    if (!m) {
      out.push(remainder);
      break;
    }
    if (m.index > 0) out.push(remainder.slice(0, m.index));
    if (m[2] !== undefined) out.push(<strong key={key++}>{m[2]}</strong>);
    else if (m[3] !== undefined) out.push(<em key={key++}>{m[3]}</em>);
    remainder = remainder.slice(m.index + m[0].length);
  }
  return out;
}

const TONE_CLASS: Record<Tone, string> = {
  default: '',
  positive: 'fpn-kpi-value--positive',
  negative: 'fpn-kpi-value--negative',
  harvest: 'fpn-kpi-value--harvest',
};

function Chart({ spec }: { spec: ChartSpec }) {
  switch (spec.type) {
    case 'bars':
      return <BarsBlock chart={spec} />;
    case 'trend_forecast':
      return <TrendForecastBlock chart={spec} />;
    case 'region_map':
      return <RegionMap chart={spec} />;
  }
}

function renderBlock(b: Block, i: number): React.ReactNode {
  switch (b.kind) {
    case 'title':
      return (
        <h1 key={i} className="fp-issue-title">
          {renderInline(b.text)}
        </h1>
      );
    case 'dek':
      return (
        <p key={i} className="fp-issue-dek">
          {renderInline(b.text)}
        </p>
      );
    case 'section':
      return (
        <h2 key={i} className={`fp-issue-h2 ${b.lead ? 'fp-issue-h2--lead' : ''}`}>
          {b.lead && <span className="fp-issue-lead-pill">LEAD</span>}
          {renderInline(b.text)}
        </h2>
      );
    case 'brief':
      return (
        <h3 key={i} className="fp-issue-h3">
          {renderInline(b.text)}
        </h3>
      );
    case 'p':
      return (
        <p key={i} className={`fp-issue-p ${b.first ? 'fp-issue-p--first' : ''}`}>
          {renderInline(b.text)}
        </p>
      );
    case 'watch':
      return (
        <p key={i} className="fp-issue-p fp-issue-p--watch">
          <span className="fp-issue-watch-tag">WHAT TO WATCH</span>
          {renderInline(b.text)}
        </p>
      );
    case 'kpis':
      return (
        <section key={i} className="fpn-glance">
          {b.title && <div className="fpn-glance-title">{b.title}</div>}
          <div className="fpn-kpis">
            {b.items.map((item) => (
              <div key={item.label} className="fpn-kpi">
                <div className="fpn-kpi-label">{item.label}</div>
                <div>
                  <span className={`fpn-kpi-value ${TONE_CLASS[item.tone ?? 'default']}`}>
                    {item.value}
                  </span>
                  {item.unit && <span className="fpn-kpi-unit">{item.unit}</span>}
                </div>
                {item.caption && <div className="fpn-kpi-caption">{item.caption}</div>}
              </div>
            ))}
          </div>
        </section>
      );
    case 'stat':
      return (
        <aside key={i} className="fpn-stat">
          <div className="fpn-stat-value">{b.value}</div>
          <div className="fpn-stat-label">{b.label}</div>
          {b.detail && <div className="fpn-stat-detail">{b.detail}</div>}
        </aside>
      );
    case 'figure':
      return (
        <figure key={i} className="fpn-figure">
          <div className="fpn-figure-head">
            <div className="fpn-figure-title">{b.title}</div>
            {b.subtitle && <div className="fpn-figure-sub">{b.subtitle}</div>}
          </div>
          <div className={`fpn-figure-body ${b.charts.length === 2 ? 'fpn-figure-grid' : ''}`}>
            {b.charts.map((c, ci) => (
              <Chart key={ci} spec={c} />
            ))}
          </div>
          {b.source && <div className="fpn-figure-source">{b.source}</div>}
        </figure>
      );
    case 'hr':
      return <hr key={i} className="fp-issue-hr" />;
  }
}

export default function ModelIssue({ spec }: { spec: IssueSpec }) {
  return <article className="fp-issue">{spec.blocks.map(renderBlock)}</article>;
}
