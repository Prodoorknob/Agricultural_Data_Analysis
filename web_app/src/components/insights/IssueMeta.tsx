/**
 * Bottom-of-issue transparency strip — what it cost, how long it took, how
 * many signals were considered, how many tool calls the researcher made.
 * Hover-tooltip explains each metric for newsletter readers who haven't
 * read the project page.
 */

import React from 'react';

interface Props {
  cost_usd?: number | null;
  duration_sec?: number | null;
  n_tool_calls?: number | null;
  n_signals_scanned?: number | null;
  run_date?: string | null;
  approved_by?: string | null;
}

function formatDuration(sec: number): string {
  if (sec < 60) return `${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return s ? `${m}m ${s}s` : `${m}m`;
}

export default function IssueMeta(props: Props) {
  const items: { label: string; value: string }[] = [];
  if (props.run_date) {
    items.push({
      label: 'Generated',
      value: new Date(props.run_date).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
      }),
    });
  }
  if (typeof props.cost_usd === 'number') {
    items.push({ label: 'LLM cost', value: `$${props.cost_usd.toFixed(2)}` });
  }
  if (typeof props.duration_sec === 'number') {
    items.push({
      label: 'Generation time',
      value: formatDuration(props.duration_sec),
    });
  }
  if (typeof props.n_tool_calls === 'number') {
    items.push({ label: 'Tool calls', value: String(props.n_tool_calls) });
  }
  if (typeof props.n_signals_scanned === 'number') {
    items.push({
      label: 'Signals scanned',
      value: String(props.n_signals_scanned),
    });
  }
  if (props.approved_by && props.approved_by !== 'auto') {
    items.push({ label: 'Approved by', value: props.approved_by });
  }
  if (!items.length) return null;
  return (
    <footer className="fp-issue-meta">
      {items.map((it) => (
        <div className="fp-issue-meta-item" key={it.label}>
          <span className="fp-issue-meta-label">{it.label}</span>
          <span className="fp-issue-meta-value">{it.value}</span>
        </div>
      ))}
    </footer>
  );
}
