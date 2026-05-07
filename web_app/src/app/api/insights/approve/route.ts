/**
 * POST /api/insights/approve
 * Body: { slug: string }
 *
 * Verifies the draft cookie matches the requested slug, then forwards a
 * promote call to FastAPI with the server-only X-Agent-Token header.
 */

import { NextRequest, NextResponse } from 'next/server';
import { readDraftSession, callPromote } from '@/lib/insights';

export async function POST(req: NextRequest) {
  const session = await readDraftSession();
  if (!session) {
    return NextResponse.json({ error: 'unauthenticated' }, { status: 401 });
  }
  let body: { slug?: string; approved_by?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'invalid json' }, { status: 400 });
  }
  if (!body.slug || body.slug !== session.slug) {
    return NextResponse.json({ error: 'slug mismatch' }, { status: 403 });
  }
  const ok = await callPromote(session.run_id, body.approved_by || 'editor');
  if (!ok) {
    return NextResponse.json({ error: 'promote failed' }, { status: 500 });
  }
  return NextResponse.json({ ok: true, run_id: session.run_id });
}
