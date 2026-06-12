/**
 * /insights/model — the model newsletter: a fully designed reference issue
 * showing what the chart-enabled publisher step should produce. Content is
 * the 2026-05-03 dry-run draft, re-expressed as a typed IssueSpec and
 * rendered with live Recharts charts, KPI strips, stat callouts, and a
 * county-textured region map instead of {{chart_N}} placeholders.
 */

import Link from 'next/link';
import ModelIssue from '@/components/insights/model/ModelIssue';
import IssueMeta from '@/components/insights/IssueMeta';
import { modelIssue } from '@/components/insights/model/data';

export const metadata = {
  title: 'Model Issue — FieldPulse Weekly',
  robots: { index: false, follow: false },
};

export default function ModelIssuePage() {
  return (
    <main className="fp-insights-shell">
      <nav className="fp-insights-nav">
        <Link href="/insights" className="fp-insights-nav-back">
          ← All issues
        </Link>
        <span className="fp-insights-nav-slug">2026-05-03 / model</span>
      </nav>
      <header className="fpn-banner">
        <span className="fpn-banner-pill">MODEL ISSUE</span>
        <span className="fpn-banner-text">
          Design reference for the chart-enabled publisher step. Prose is the 2026-05-03 dry-run
          draft; a few peripheral series values are illustrative placeholders, flagged in each
          figure&apos;s source line.
        </span>
      </header>
      <ModelIssue spec={modelIssue} />
      <IssueMeta
        run_date={modelIssue.meta.run_date}
        cost_usd={modelIssue.meta.cost_usd}
        duration_sec={modelIssue.meta.duration_sec}
        n_tool_calls={modelIssue.meta.n_tool_calls}
        n_signals_scanned={modelIssue.meta.n_signals_scanned}
        approved_by={modelIssue.meta.approved_by}
      />
    </main>
  );
}
