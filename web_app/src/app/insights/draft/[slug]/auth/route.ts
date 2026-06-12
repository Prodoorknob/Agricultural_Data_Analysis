/**
 * Magic-link redemption route for FieldPulse drafts.
 *
 * The Slack draft-ready ping links here with `?t=<one-shot-token>`. This
 * handler exchanges the token with the backend (which consumes it once),
 * sets the signed `fp_draft_auth` HTTP-only cookie on the response, and
 * redirects to the gated reader page. Setting cookies requires a Route
 * Handler or Server Action, which is why the reader page itself cannot do
 * the exchange during render.
 */

import { NextRequest, NextResponse } from 'next/server';
import { consumeDraftToken, encodeDraftSession, COOKIE_NAME } from '@/lib/insights';

export const dynamic = 'force-dynamic';

const COOKIE_TTL_DAYS = 7;

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ slug: string }> }
) {
  const { slug } = await params;
  const token = req.nextUrl.searchParams.get('t');
  const draftUrl = new URL(`/insights/draft/${slug}`, req.url);

  if (!token) {
    draftUrl.searchParams.set('auth', 'missing');
    return NextResponse.redirect(draftUrl);
  }

  const result = await consumeDraftToken(slug, token);
  if (!result) {
    // Token invalid, already redeemed, or expired.
    draftUrl.searchParams.set('auth', 'failed');
    return NextResponse.redirect(draftUrl);
  }

  const exp = Math.floor(Date.now() / 1000) + 60 * 60 * 24 * COOKIE_TTL_DAYS;
  const value = encodeDraftSession({ run_id: result.run_id, slug: result.slug, exp });

  const res = NextResponse.redirect(draftUrl);
  res.cookies.set({
    name: COOKIE_NAME,
    value,
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    maxAge: 60 * 60 * 24 * COOKIE_TTL_DAYS,
    path: '/insights',
  });
  return res;
}
