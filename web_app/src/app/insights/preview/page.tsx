/**
 * /insights/_preview — dev-only reader that renders the most recent dry-run
 * draft directly from backend/agent/data/last_draft.md. Lets us iterate on
 * the reader UI without needing a live agent_runs row + S3 upload.
 *
 * Disabled in production. The route still resolves but renders a 404 message.
 */

import path from 'path';
import fs from 'fs';
import { notFound } from 'next/navigation';
import IssueRenderer from '@/components/insights/IssueRenderer';
import IssueMeta from '@/components/insights/IssueMeta';

export const dynamic = 'force-dynamic';

export const metadata = {
  title: 'Preview — FieldPulse Weekly',
  robots: { index: false, follow: false },
};

async function loadDraft(): Promise<{
  markdown: string;
  factcheck: { passed: boolean; issues: Array<{ severity: string; source: string; detail: string }> } | null;
  mtime: string;
} | null> {
  if (process.env.NODE_ENV === 'production') return null;
  try {
    // web_app/.. = project root, then backend/agent/data/last_draft.md
    const root = path.resolve(process.cwd(), '..');
    const draftPath = path.join(root, 'backend', 'agent', 'data', 'last_draft.md');
    const factPath = path.join(root, 'backend', 'agent', 'data', 'last_factcheck.json');
    const markdown = await fs.promises.readFile(draftPath, 'utf-8');
    const stat = await fs.promises.stat(draftPath);
    let factcheck = null;
    try {
      const raw = await fs.promises.readFile(factPath, 'utf-8');
      factcheck = JSON.parse(raw);
    } catch {
      // factcheck.json optional
    }
    return { markdown, factcheck, mtime: stat.mtime.toISOString() };
  } catch {
    return null;
  }
}

export default async function PreviewPage() {
  const draft = await loadDraft();
  if (!draft) notFound();

  return (
    <main className="fp-insights-shell">
      <header className="fp-insights-draft-banner">
        <div>
          <span className="fp-insights-draft-pill">PREVIEW</span>{' '}
          <span className="fp-insights-draft-meta">
            local dry-run draft · last modified{' '}
            {new Date(draft.mtime).toLocaleString('en-US', {
              dateStyle: 'medium',
              timeStyle: 'short',
            })}
          </span>
        </div>
      </header>
      {draft.factcheck && !draft.factcheck.passed && (
        <details className="fp-insights-factcheck-callout">
          <summary>
            Fact-check flagged{' '}
            {draft.factcheck.issues.filter((i) => i.severity === 'major').length} major and{' '}
            {draft.factcheck.issues.filter((i) => i.severity === 'minor').length} minor issues
          </summary>
          <ul>
            {draft.factcheck.issues.map((i, idx) => (
              <li key={idx} className={`fp-factcheck-${i.severity}`}>
                <span className="fp-factcheck-tag">[{i.source}/{i.severity}]</span>{' '}
                {i.detail}
              </li>
            ))}
          </ul>
        </details>
      )}
      <IssueRenderer markdown={draft.markdown} />
      <IssueMeta
        run_date={draft.mtime}
        cost_usd={0.5}
        duration_sec={284}
        n_tool_calls={46}
        n_signals_scanned={20}
        approved_by="dry-run"
      />
    </main>
  );
}
