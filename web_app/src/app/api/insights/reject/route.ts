/**
 * POST /api/insights/reject
 * Body: { slug: string, reason?: string }
 */

import { NextRequest, NextResponse } from 'next/server';
import { readDraftSession, callReject } from '@/lib/insights';

export async function POST(req: NextRequest) {
  const session = await readDraftSession();
  if (!session) {
    return NextResponse.json({ error: 'unauthenticated' }, { status: 401 });
  }
  let body: { slug?: string; reason?: string; rejected_by?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'invalid json' }, { status: 400 });
  }
  if (!body.slug || body.slug !== session.slug) {
    return NextResponse.json({ error: 'slug mismatch' }, { status: 403 });
  }
  const ok = await callReject(
    session.run_id,
    body.rejected_by || 'editor',
    body.reason
  );
  if (!ok) {
    return NextResponse.json({ error: 'reject failed' }, { status: 500 });
  }
  return NextResponse.json({ ok: true, run_id: session.run_id });
}
