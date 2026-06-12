/**
 * FieldPulse Insights — shared helpers (server-only).
 *
 * Cookie format: HMAC-signed payload `{run_id}.{slug}.{exp_unix}.{sig}`.
 * Secret is FIELDPULSE_DRAFT_SECRET (server-only). Cookies are HTTP-only,
 * SameSite=Lax, 7-day expiry.
 */

import { cookies } from 'next/headers';
import { createHmac, timingSafeEqual } from 'crypto';

export const COOKIE_NAME = 'fp_draft_auth';
const COOKIE_TTL_DAYS = 7;

interface DraftSession {
  run_id: number;
  slug: string;
  exp: number;
}

function getSecret(): string {
  const s = process.env.FIELDPULSE_DRAFT_SECRET;
  if (!s) {
    throw new Error('FIELDPULSE_DRAFT_SECRET not set');
  }
  return s;
}

function backendBaseUrl(): string {
  const url = process.env.BACKEND_BASE_URL;
  if (!url) {
    throw new Error('BACKEND_BASE_URL not set');
  }
  return url.replace(/\/$/, '');
}

function sign(payload: string, secret: string): string {
  return createHmac('sha256', secret).update(payload).digest('hex');
}

export function encodeDraftSession(session: DraftSession): string {
  const payload = `${session.run_id}.${session.slug}.${session.exp}`;
  const sig = sign(payload, getSecret());
  return `${payload}.${sig}`;
}

export function verifyDraftCookie(value: string | undefined): DraftSession | null {
  if (!value) return null;
  const parts = value.split('.');
  if (parts.length !== 4) return null;
  const [runIdStr, slug, expStr, sig] = parts;
  const payload = `${runIdStr}.${slug}.${expStr}`;
  const expected = sign(payload, getSecret());
  try {
    if (!timingSafeEqual(Buffer.from(sig, 'hex'), Buffer.from(expected, 'hex'))) {
      return null;
    }
  } catch {
    return null;
  }
  const exp = parseInt(expStr, 10);
  if (!Number.isFinite(exp) || exp < Math.floor(Date.now() / 1000)) {
    return null;
  }
  const runId = parseInt(runIdStr, 10);
  if (!Number.isFinite(runId)) return null;
  return { run_id: runId, slug, exp };
}

export async function readDraftSession(): Promise<DraftSession | null> {
  const c = (await cookies()).get(COOKIE_NAME);
  return verifyDraftCookie(c?.value);
}

export async function setDraftSession(session: DraftSession): Promise<void> {
  const value = encodeDraftSession(session);
  const store = await cookies();
  store.set({
    name: COOKIE_NAME,
    value,
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    maxAge: 60 * 60 * 24 * COOKIE_TTL_DAYS,
    // Site-wide path: the reader lives under /insights but the approve/reject
    // API routes are under /api/insights, so a /insights-scoped cookie would
    // not be sent to them (browser path-match), breaking the action buttons.
    path: '/',
  });
}

export async function clearDraftSession(): Promise<void> {
  const store = await cookies();
  store.delete(COOKIE_NAME);
}

// ---------------------------------------------------------------------------
// Backend bridges (server-only).
// ---------------------------------------------------------------------------

export async function fetchPublishedRuns(limit = 20): Promise<Run[]> {
  const all = await fetchAllRuns(limit);
  return all.filter((r) => r.status === 'published');
}

export async function fetchRunBySlug(slug: string): Promise<Run | null> {
  const all = await fetchAllRuns(100);
  return all.find((r) => r.slug === slug) ?? null;
}

export async function fetchAllRuns(limit = 100): Promise<Run[]> {
  // The backend may be unreachable (local dev, EC2 outage, etc). The
  // /insights pages should degrade to an empty state, not a 500.
  try {
    const res = await fetch(
      `${backendBaseUrl()}/api/v1/agent/runs?limit=${limit}`,
      { cache: 'no-store' }
    );
    if (!res.ok) return [];
    return (await res.json()) as Run[];
  } catch {
    return [];
  }
}

export async function fetchIssueMarkdown(
  slug: string,
  options: { draft?: boolean } = {}
): Promise<string | null> {
  // Server-side fetch directly from FastAPI; no need to round-trip through
  // our own /api/insights/markdown route during SSR.
  try {
    const url =
      `${backendBaseUrl()}/api/v1/agent/markdown/${encodeURIComponent(slug)}` +
      (options.draft ? '?draft=1' : '');
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) return null;
    return await res.text();
  } catch {
    return null;
  }
}

export async function callPromote(
  runId: number,
  approvedBy: string
): Promise<boolean> {
  const url =
    `${backendBaseUrl()}/api/v1/agent/promote/${runId}` +
    `?approved_by=${encodeURIComponent(approvedBy)}`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'X-Agent-Token': getSecret() },
  });
  return res.ok;
}

export async function callReject(
  runId: number,
  rejectedBy: string,
  reason?: string
): Promise<boolean> {
  const params = new URLSearchParams({ rejected_by: rejectedBy });
  if (reason) params.set('reason', reason);
  const url = `${backendBaseUrl()}/api/v1/agent/reject/${runId}?${params}`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'X-Agent-Token': getSecret() },
  });
  return res.ok;
}

export async function consumeDraftToken(
  slug: string,
  token: string
): Promise<{ run_id: number; slug: string; status: string } | null> {
  const url = `${backendBaseUrl()}/api/v1/agent/draft/${slug}/auth?t=${encodeURIComponent(token)}`;
  const res = await fetch(url, { method: 'GET', cache: 'no-store' });
  if (!res.ok) return null;
  return (await res.json()) as { run_id: number; slug: string; status: string };
}

export interface Run {
  id: number;
  run_date: string;
  status: 'pending' | 'draft' | 'approved' | 'rejected' | 'published' | 'failed';
  slug: string | null;
  newsletter_path: string | null;
  cost_usd: number | null;
  n_tool_calls: number | null;
  duration_sec: number | null;
  approved_by: string | null;
  approved_at: string | null;
}

export function nextSessionExp(): number {
  return Math.floor(Date.now() / 1000) + 60 * 60 * 24 * COOKIE_TTL_DAYS;
}
