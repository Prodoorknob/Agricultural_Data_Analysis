/**
 * POST /api/revalidate?path=/insights&secret=...
 *
 * Called by the Python publisher.promote() after an approve/auto-publish
 * to flush Next.js ISR caches. The shared secret is the first 24 chars of
 * FIELDPULSE_DRAFT_SECRET — same value publisher.py uses.
 */

import { NextRequest, NextResponse } from 'next/server';
import { revalidatePath } from 'next/cache';

export async function POST(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const path = searchParams.get('path');
  const secret = searchParams.get('secret');
  const expected = (process.env.FIELDPULSE_DRAFT_SECRET || '').slice(0, 24);
  if (!secret || !expected || secret !== expected) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }
  if (!path || !path.startsWith('/insights')) {
    return NextResponse.json(
      { error: 'path must start with /insights' },
      { status: 400 }
    );
  }
  try {
    revalidatePath(path);
    return NextResponse.json({ revalidated: true, path });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : 'revalidate failed' },
      { status: 500 }
    );
  }
}
