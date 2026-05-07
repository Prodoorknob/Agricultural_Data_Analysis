/**
 * GET /api/insights/auth?slug=...&t=...
 *
 * Validates a one-shot magic-link token via the backend, then sets the
 * fp_draft_auth signed cookie and redirects to /insights/draft/<slug>.
 *
 * Used by the Slack draft-ready button. Token is consumed on first hit;
 * subsequent visits to /insights/draft/<slug> rely on the cookie.
 */

import { NextRequest, NextResponse } from 'next/server';
import {
  consumeDraftToken,
  encodeDraftSession,
  COOKIE_NAME,
  nextSessionExp,
} from '@/lib/insights';

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const slug = searchParams.get('slug');
  const token = searchParams.get('t');
  if (!slug || !token) {
    return NextResponse.json(
      { error: 'slug and t query params required' },
      { status: 400 }
    );
  }

  const result = await consumeDraftToken(slug, token);
  if (!result) {
    return NextResponse.json(
      { error: 'token invalid, expired, or already used' },
      { status: 410 }
    );
  }

  const exp = nextSessionExp();
  const cookieValue = encodeDraftSession({
    run_id: result.run_id,
    slug: result.slug,
    exp,
  });

  // Strip token from URL on redirect; the cookie is what authorizes now.
  const redirectUrl = new URL(`/insights/draft/${slug}`, req.url);
  const res = NextResponse.redirect(redirectUrl);
  res.cookies.set({
    name: COOKIE_NAME,
    value: cookieValue,
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    maxAge: 60 * 60 * 24 * 7,
    path: '/insights',
  });
  return res;
}
