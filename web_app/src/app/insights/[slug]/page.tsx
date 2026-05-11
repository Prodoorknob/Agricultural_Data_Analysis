import { notFound } from 'next/navigation';
import { fetchIssueMarkdown, fetchRunBySlug } from '@/lib/insights';
import IssueRenderer from '@/components/insights/IssueRenderer';
import IssueMeta from '@/components/insights/IssueMeta';

export const dynamic = 'force-dynamic';

interface Params {
  params: Promise<{ slug: string }>;
}

export async function generateMetadata({ params }: Params) {
  const { slug } = await params;
  return {
    title: `${slug} — FieldPulse Weekly`,
  };
}

export default async function IssuePage({ params }: Params) {
  const { slug } = await params;
  const run = await fetchRunBySlug(slug);
  if (!run || run.status !== 'published') {
    notFound();
  }
  const markdown = await fetchIssueMarkdown(slug);
  if (!markdown) {
    notFound();
  }

  // Rewrite chart URLs from the publisher's `/insights/charts/<slug>/<id>.png`
  // to our backend proxy that streams from S3.
  const rewritten = markdown.replace(
    /\/insights\/charts\/(?:draft\/)?([^/]+)\/([^)]+\.png)/g,
    (_match, chartSlug, name) =>
      `${process.env.NEXT_PUBLIC_BACKEND_BASE_URL || ''}/api/v1/agent/chart/${chartSlug}/${name}`
  );

  return (
    <main className="fp-insights-shell">
      <nav className="fp-insights-nav">
        <a href="/insights" className="fp-insights-nav-back">
          ← All issues
        </a>
        <span className="fp-insights-nav-slug">{slug}</span>
      </nav>
      <IssueRenderer markdown={rewritten} />
      <IssueMeta
        run_date={run.run_date}
        cost_usd={run.cost_usd}
        duration_sec={run.duration_sec}
        n_tool_calls={run.n_tool_calls}
        approved_by={run.approved_by}
      />
    </main>
  );
}
