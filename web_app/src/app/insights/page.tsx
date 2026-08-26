import Link from 'next/link';
import { fetchPublishedRuns, fetchStories, type Story } from '@/lib/insights';

export const dynamic = 'force-dynamic';

export const metadata = {
  title: 'FieldPulse Weekly — Insights',
  description:
    'Weekly analyst-agent newsletter covering U.S. row-crop and livestock market signals.',
};

const DOMAIN_LABELS: Record<string, string> = {
  'feature-explainer': 'Explainer',
  'feature-region': 'Region spotlight',
  'feature-trend': 'State trend',
  yield: 'Yield',
  price: 'Price',
  futures: 'Price',
  wasde: 'WASDE',
  'composite-wasde': 'WASDE',
  exports: 'Exports',
  'composite-exports': 'Exports',
  drought: 'Weather',
  weather: 'Weather',
  'composite-drought': 'Weather',
  'composite-weather': 'Weather',
  acreage: 'Acreage',
  accuracy: 'Model report card',
  trend_break: 'Trend break',
  calendar: 'Calendar',
};

function domainLabel(domain: string): string {
  return DOMAIN_LABELS[domain] ?? domain.replace(/^composite-/, '').replace(/-/g, ' ');
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function StoryCard({ story }: { story: Story }) {
  const title = story.story_title ?? story.headline ?? story.slug;
  return (
    <li className="fp-story-card">
      <Link
        href={`/insights/${story.slug}#story-${story.story_index}`}
        className="fp-story-link"
      >
        <div className="fp-story-tags">
          <span
            className={`fp-story-tag ${
              story.category === 'educational'
                ? 'fp-story-tag--edu'
                : 'fp-story-tag--perf'
            }`}
          >
            {domainLabel(story.signal_domain)}
          </span>
          {story.role === 'lead' && (
            <span className="fp-story-tag fp-story-tag--lead">Lead</span>
          )}
        </div>
        <div className="fp-story-title">{title}</div>
        <div className="fp-story-meta">{fmtDate(story.run_date)}</div>
      </Link>
    </li>
  );
}

function StoryFeed({
  heading,
  dek,
  stories,
  emptyText,
}: {
  heading: string;
  dek: string;
  stories: Story[];
  emptyText: string;
}) {
  return (
    <section className="fp-feed">
      <h2 className="fp-feed-heading">{heading}</h2>
      <p className="fp-feed-dek">{dek}</p>
      {stories.length === 0 ? (
        <p className="fp-insights-empty">{emptyText}</p>
      ) : (
        <ul className="fp-feed-list">
          {stories.slice(0, 12).map((s) => (
            <StoryCard key={`${s.run_id}-${s.story_index}`} story={s} />
          ))}
        </ul>
      )}
    </section>
  );
}

export default async function InsightsIndex() {
  const [runs, stories] = await Promise.all([
    fetchPublishedRuns(20),
    fetchStories(80),
  ]);

  const educational = stories.filter((s) => s.category === 'educational');
  const performance = stories.filter((s) => s.category === 'performance');

  return (
    <main className="fp-insights-shell">
      <header className="fp-insights-hero">
        <div className="fp-insights-hero-eyebrow">Module 05</div>
        <h1 className="fp-insights-hero-title">FieldPulse Weekly</h1>
        <p className="fp-insights-hero-dek">
          A weekly autonomous synthesis of U.S. agriculture. Every issue pairs
          what moved this week (yields, prices, WASDE, exports, weather) with
          a piece that teaches how the system works.
        </p>
      </header>

      <div className="fp-feeds">
        <StoryFeed
          heading="This week in the field"
          dek="Current crop and market performance: anomalies, report reactions, and what to watch."
          stories={performance}
          emptyText="No performance stories yet."
        />
        <StoryFeed
          heading="Learn U.S. agriculture"
          dek="Evergreen explainers, regional spotlights, and long-arc state trends. Start anywhere."
          stories={educational}
          emptyText="Educational features publish with each weekly issue. First ones land soon."
        />
      </div>

      <section className="fp-insights-list">
        <h2 className="fp-insights-list-heading">All issues</h2>
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
                    {fmtDate(r.run_date)}
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
