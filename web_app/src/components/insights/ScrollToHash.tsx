'use client';

import { useEffect } from 'react';

/**
 * Scrolls to the URL hash after mount. Needed because the issue body is
 * server-streamed: the browser's single native anchor-scroll attempt fires
 * before the #story-N element exists, then never retries. Retries across
 * animation frames until the element renders (or gives up after ~2s).
 */
export default function ScrollToHash() {
  useEffect(() => {
    const hash = decodeURIComponent(window.location.hash.slice(1));
    if (!hash) return;
    let tries = 0;
    let cancelled = false;
    const attempt = () => {
      if (cancelled) return;
      const el = document.getElementById(hash);
      if (el) {
        // 'instant', not 'auto': the page sets `scroll-behavior: smooth`,
        // and smooth scrolls are animation frames that never advance in a
        // hidden or backgrounded tab, leaving the jump stuck at the top.
        el.scrollIntoView({ behavior: 'instant', block: 'start' });
        return;
      }
      // setTimeout, not rAF: rAF is throttled to zero in background tabs.
      if (++tries < 40) setTimeout(attempt, 50);
    };
    attempt();
    return () => {
      cancelled = true;
    };
  }, []);
  return null;
}
