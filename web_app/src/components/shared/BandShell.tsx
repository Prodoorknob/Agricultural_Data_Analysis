'use client';

import { useAgSeason } from '@/hooks/useAgSeason';
import type { AgSeason } from '@/types/filters';
import type { ReactNode } from 'react';

interface BandShellProps {
  children: ReactNode;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  empty?: boolean;
  emptyMessage?: string;
  /** If set, band renders only during these seasons */
  visibleSeasons?: AgSeason[];
  /** Message shown outside visible seasons */
  dormantMessage?: string;
  /** Compact summary of last completed cycle */
  dormantSummary?: ReactNode;
  /** Minimum height for skeleton shimmer */
  skeletonHeight?: number;
  className?: string;
}

export default function BandShell({
  children,
  loading = false,
  error = null,
  onRetry,
  empty = false,
  emptyMessage = 'No data available.',
  visibleSeasons,
  dormantMessage,
  dormantSummary,
  skeletonHeight = 200,
  className = '',
}: BandShellProps) {
  const { season } = useAgSeason();

  // Seasonal visibility check
  if (visibleSeasons && !visibleSeasons.includes(season)) {
    return (
      <div className={`py-8 ${className}`}>
        {dormantSummary && <div className="mb-3">{dormantSummary}</div>}
        {dormantMessage && (
          <p
            className="text-[14px] text-center"
            style={{ color: 'var(--text3)', fontFamily: 'var(--font-body)' }}
          >
            {dormantMessage}
          </p>
        )}
      </div>
    );
  }

  // Loading skeleton
  if (loading) {
    return (
      <div className={`${className}`}>
        <div className="skeleton" style={{ height: skeletonHeight }} />
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div
        className={`p-4 rounded-[var(--radius-md)] ${className}`}
        style={{ background: 'var(--soil-tint)', borderLeft: '3px solid var(--negative)' }}
      >
        <div className="flex items-start gap-3">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="var(--negative)">
            <path d="M10 0C4.48 0 0 4.48 0 10s4.48 10 10 10 10-4.48 10-10S15.52 0 10 0zm1 15H9v-2h2v2zm0-4H9V5h2v6z" />
          </svg>
          <div className="flex-1">
            <p className="text-[14px]" style={{ color: 'var(--text)' }}>
              {error}
            </p>
            {onRetry && (
              <button
                onClick={onRetry}
                className="mt-2 px-3 py-1 text-[13px] font-medium rounded-[var(--radius-sm)] border"
                style={{
                  color: 'var(--field)',
                  borderColor: 'var(--field)',
                  background: 'transparent',
                }}
              >
                Retry
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Empty state
  if (empty) {
    return (
      <div className={`py-12 text-center ${className}`}>
        <p className="text-[14px]" style={{ color: 'var(--text3)' }}>
          {emptyMessage}
        </p>
      </div>
    );
  }

  return <div className={className}>{children}</div>;
}
