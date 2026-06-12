import { notFound, redirect } from 'next/navigation';
import { fetchIssueMarkdown, readDraftSession } from '@/lib/insights';
import IssueRenderer from '@/components/insights/IssueRenderer';
import DraftActions from './DraftActions';

export const dynamic = 'force-dynamic';

interface Params {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ t?: string; auth?: string }>;
}

export async function generateMetadata({ params }: Params) {
  const { slug } = await params;
  return {
    title: `${slug} (DRAFT) — FieldPulse Weekly`,
  };
}

export default async function DraftPage({ params, searchParams }: Params) {
  const { slug } = await params;
  const session = await readDraftSession();
  if (!session || session.slug !== slug) {
    // A magic link may land here with `?t=<token>` (the cookie isn't set yet).
    // Cookies can't be written during a Server Component render, so hand off
    // to the /auth route handler, which redeems the token and sets the cookie.
    const { t, auth } = await searchParams;
    if (t && auth !== 'failed') {
      redirect(`/insights/draft/${slug}/auth?t=${encodeURIComponent(t)}`);
    }
    return (
      <main className="fp-insights-shell">
        <header className="fp-insights-draft-banner fp-insights-draft-banner--locked">
          Draft not authorized.
        </header>
        <p className="fp-insights-empty">
          Open the draft from the link in the FieldPulse Slack channel. The
          token is single-use; once redeemed it sets a 7-day cookie that
          authorizes this page.
        </p>
      </main>
    );
  }

  const markdown = await fetchIssueMarkdown(slug, { draft: true });
  if (!markdown) {
    notFound();
  }

  // Rewrite chart URLs to the FastAPI proxy with ?draft=1 (charts live in
  // newsletters/draft/<slug>/ until promote).
  const rewritten = markdown.replace(
    /\/insights\/charts\/(?:draft\/)?([^/]+)\/([^)]+\.png)/g,
    (_match, chartSlug, name) =>
      `${process.env.NEXT_PUBLIC_BACKEND_BASE_URL || ''}/api/v1/agent/chart/${chartSlug}/${name}?draft=1`
  );

  return (
    <main className="fp-insights-shell">
      <header className="fp-insights-draft-banner">
        <div>
          <span className="fp-insights-draft-pill">DRAFT</span>{' '}
          <span className="fp-insights-draft-meta">
            run #{session.run_id} · slug <code>{slug}</code>
          </span>
        </div>
        <DraftActions slug={slug} />
      </header>
      <IssueRenderer markdown={rewritten} />
    </main>
  );
}
