'use client';

import { useState } from 'react';

interface Props {
  slug: string;
}

export default function DraftActions({ slug }: Props) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const post = async (path: string, body: object) => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setMsg(path.endsWith('approve') ? 'Approved + published.' : 'Rejected.');
      } else {
        setMsg(`Error: ${res.status}`);
      }
    } catch (err) {
      setMsg(err instanceof Error ? err.message : 'request failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fp-insights-draft-actions">
      <button
        className="fp-insights-btn fp-insights-btn-approve"
        disabled={busy}
        onClick={() => post('/api/insights/approve', { slug })}
      >
        Approve + publish
      </button>
      <button
        className="fp-insights-btn fp-insights-btn-reject"
        disabled={busy}
        onClick={() => {
          const reason = window.prompt('Reject reason (optional):') || undefined;
          post('/api/insights/reject', { slug, reason });
        }}
      >
        Reject
      </button>
      {msg && <span className="fp-insights-draft-msg">{msg}</span>}
    </div>
  );
}
