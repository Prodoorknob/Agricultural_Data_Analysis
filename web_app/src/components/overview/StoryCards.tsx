'use client';

import { useAgSeason } from '@/hooks/useAgSeason';
import { useFilters } from '@/hooks/useFilters';
import SectionHeading from '@/components/shared/SectionHeading';
import type { Tab } from '@/types/filters';

interface StoryCard {
  id: string;
  headline: string;
  hook: string;
  targetTab: Tab;
  targetFilters: Record<string, string>;
  seasonal?: boolean;
}

const BASE_STORIES: StoryCard[] = [
  {
    id: 'labor-costs',
    headline: '42%',
    hook: 'Where farm labor got expensive fastest — state wage growth leaderboard.',
    targetTab: 'land-economy',
    targetFilters: { section: 'labor' },
  },
  {
    id: 'farmland-sprawl',
    headline: '32 states',
    hook: 'Lost cropland to urban growth between 2001 and 2022.',
    targetTab: 'land-economy',
    targetFilters: { section: 'land-use' },
  },
  {
    id: 'disappearing-crops',
    headline: '-38%',
    hook: 'Tobacco operations since 2001 — the steepest decline of any U.S. crop.',
    targetTab: 'crops',
    targetFilters: { commodity: 'tobacco' },
  },
];

const SEASONAL_CARDS: Record<string, StoryCard> = {
  'pre-plant': {
    id: 'seasonal-revenue',
    headline: 'Revenue Recap',
    hook: 'Last year\'s farm revenue outcomes by state and commodity.',
    targetTab: 'overview',
    targetFilters: {},
    seasonal: true,
  },
  planting: {
    id: 'seasonal-plantings',
    headline: 'Mar 31',
    hook: 'USDA Prospective Plantings — what farmers intend to plant this year.',
    targetTab: 'forecasts',
    targetFilters: { section: 'acreage' },
    seasonal: true,
  },
  'early-growth': {
    id: 'seasonal-emergence',
    headline: 'Emergence',
    hook: 'Planting completion and early crop condition reports are starting.',
    targetTab: 'crops',
    targetFilters: { commodity: 'corn' },
    seasonal: true,
  },
  'mid-season': {
    id: 'seasonal-condition',
    headline: 'Condition',
    hook: 'Weekly crop condition ratings are driving yield expectations.',
    targetTab: 'crops',
    targetFilters: { commodity: 'corn' },
    seasonal: true,
  },
  harvest: {
    id: 'seasonal-harvest',
    headline: 'Harvest',
    hook: 'Harvest progress is underway — tracking yield outcomes by county.',
    targetTab: 'crops',
    targetFilters: { commodity: 'corn' },
    seasonal: true,
  },
  'post-harvest': {
    id: 'seasonal-review',
    headline: 'Year in Review',
    hook: 'The season is complete — revenue outcomes and yield records.',
    targetTab: 'overview',
    targetFilters: {},
    seasonal: true,
  },
};

export default function StoryCards() {
  const { season } = useAgSeason();
  const { switchTab } = useFilters();

  const seasonalCard = SEASONAL_CARDS[season];
  const cards = [...BASE_STORIES, ...(seasonalCard ? [seasonalCard] : [])];

  return (
    <section className="mt-8">
      <SectionHeading className="mb-4">Stories</SectionHeading>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((card, i) => (
          <button
            key={card.id}
            onClick={() => switchTab(card.targetTab)}
            className="text-left p-5 rounded-[var(--radius-lg)] border card-hover card-animate"
            style={{
              background: 'var(--surface)',
              borderColor: 'var(--border)',
              animationDelay: `${i * 80}ms`,
            }}
          >
            <span
              className="block text-[32px] font-extrabold leading-none mb-2"
              style={{ fontFamily: 'var(--font-stat)', color: 'var(--field)' }}
            >
              {card.headline}
            </span>
            <span
              className="block text-[13px] leading-relaxed"
              style={{ color: 'var(--text2)' }}
            >
              {card.hook}
            </span>
            <span
              className="inline-block mt-3 text-[12px] font-semibold"
              style={{ color: 'var(--field)' }}
            >
              Explore &rarr;
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
