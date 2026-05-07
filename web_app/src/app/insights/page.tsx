import Link from 'next/link';
import { fetchPublishedRuns } from '@/lib/insights';

export const dynamic = 'force-dynamic';

export const metadata = {
  title: 'FieldPulse Weekly — Insights',
  description:
    'Weekly analyst-agent newsletter covering U.S. row-crop and livestock market signals.',
};

export default async function InsightsIndex() {
  const runs = await fetchPublishedRuns(20);

  return (
    <main className="fp-insights-shell">
      <header className="fp-insights-hero">
        <div className="fp-insights-hero-eyebrow">Module 05</div>
        <h1 className="fp-insights-hero-title">FieldPulse Weekly</h1>
        <p className="fp-insights-hero-dek">
          A weekly autonomous synthesis of U.S. row-crop and livestock market
          signals. Generated every Sunday from yield, acreage, price,
          drought, and export data.
        </p>
      </header>

      <section className="fp-insights-list">
        <h2 className="fp-insights-list-heading">Recent issues</h2>
        {runs.length === 0 ? (
          <p className="fp-insights-empty">
            No issues published yet. The first run lands the Sunday after
            launch.
          </p>
        ) : (
          <ul className="fp-insights-list-items">
            {runs.map((r) => (
              <li key={r.id} className="fp-insights-row">
                <Link href={`/insights/${r.slug}`} className="fp-insights-link">
                  <div className="fp-insights-row-date">
                    {new Date(r.run_date).toLocaleDateString('en-US', {
                      year: 'numeric',
                      month: 'short',
                      day: 'numeric',
                    })}
                  </div>
                  <div className="fp-insights-row-slug">{r.slug}</div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
