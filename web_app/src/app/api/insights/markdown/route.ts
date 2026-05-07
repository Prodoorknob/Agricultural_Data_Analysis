/**
 * GET /api/insights/markdown?slug=...&draft=1
 *
 * Thin proxy in front of the FastAPI markdown endpoint. Keeps S3 IAM on
 * the EC2 backend rather than needing AWS creds in Vercel.
 */

import { NextRequest, NextResponse } from 'next/server';

function backendBaseUrl(): string {
  const url = process.env.BACKEND_BASE_URL;
  if (!url) throw new Error('BACKEND_BASE_URL not set');
  return url.replace(/\/$/, '');
}

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const slug = searchParams.get('slug');
  const draft = searchParams.get('draft') === '1';
  if (!slug) {
    return NextResponse.json({ error: 'slug required' }, { status: 400 });
  }
  const url =
    `${backendBaseUrl()}/api/v1/agent/markdown/${encodeURIComponent(slug)}` +
    (draft ? '?draft=1' : '');
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) {
    return NextResponse.json({ error: 'fetch failed' }, { status: res.status });
  }
  const body = await res.text();
  return new NextResponse(body, {
    status: 200,
    headers: { 'Content-Type': 'text/markdown; charset=utf-8' },
  });
}
