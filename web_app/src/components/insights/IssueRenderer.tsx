/**
 * Minimal markdown renderer scoped to FieldPulse Weekly's output format.
 *
 * The writer prompt constrains output to: # / ## / ### headings, *italic*
 * deks, paragraphs, ![](url) images for chart placeholders, and --- rules.
 * We don't need a full CommonMark renderer — a tight inline implementation
 * gives us full control over styling and avoids a runtime dep.
 */

import React from 'react';

type Block =
  | { type: 'h1'; text: string }
  | { type: 'h2'; text: string }
  | { type: 'h3'; text: string }
  | { type: 'dek'; text: string }
  | { type: 'p'; text: string }
  | { type: 'img'; alt: string; src: string }
  | { type: 'hr' };

const HEADING_RE = /^(#{1,3})\s+(.*)$/;
const IMAGE_RE = /^!\[(.*?)\]\((.+?)\)\s*$/;
const ITALIC_DEK_RE = /^\*(.+)\*\s*$/;

function parseMarkdown(md: string): Block[] {
  const lines = md.replace(/\r\n/g, '\n').split('\n');
  const blocks: Block[] = [];
  let buf: string[] = [];

  const flushParagraph = () => {
    if (!buf.length) return;
    const text = buf.join(' ').trim();
    buf = [];
    if (!text) return;
    const m = ITALIC_DEK_RE.exec(text);
    if (m) {
      blocks.push({ type: 'dek', text: m[1] });
    } else {
      blocks.push({ type: 'p', text });
    }
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      flushParagraph();
      continue;
    }
    if (line === '---') {
      flushParagraph();
      blocks.push({ type: 'hr' });
      continue;
    }
    const img = IMAGE_RE.exec(line);
    if (img) {
      flushParagraph();
      blocks.push({ type: 'img', alt: img[1], src: img[2] });
      continue;
    }
    const heading = HEADING_RE.exec(line);
    if (heading) {
      flushParagraph();
      const level = heading[1].length;
      const text = heading[2];
      if (level === 1) blocks.push({ type: 'h1', text });
      else if (level === 2) blocks.push({ type: 'h2', text });
      else blocks.push({ type: 'h3', text });
      continue;
    }
    buf.push(line);
  }
  flushParagraph();
  return blocks;
}

function renderInline(text: string): React.ReactNode[] {
  // Bold (**...**) and italic (*...*) — emit React fragments. Order matters:
  // tokenize by alternating ** and * boundaries.
  const out: React.ReactNode[] = [];
  let remainder = text;
  let key = 0;
  const PATTERN = /(\*\*([^*]+)\*\*|\*([^*]+)\*)/;
  while (remainder) {
    const m = PATTERN.exec(remainder);
    if (!m) {
      out.push(remainder);
      break;
    }
    if (m.index > 0) {
      out.push(remainder.slice(0, m.index));
    }
    if (m[2] !== undefined) {
      out.push(<strong key={key++}>{m[2]}</strong>);
    } else if (m[3] !== undefined) {
      out.push(<em key={key++}>{m[3]}</em>);
    }
    remainder = remainder.slice(m.index + m[0].length);
  }
  return out;
}

export default function IssueRenderer({ markdown }: { markdown: string }) {
  const blocks = parseMarkdown(markdown);
  return (
    <article className="prose-fp">
      {blocks.map((b, i) => {
        switch (b.type) {
          case 'h1':
            return (
              <h1 key={i} className="fp-issue-title">
                {renderInline(b.text)}
              </h1>
            );
          case 'h2':
            return (
              <h2 key={i} className="fp-issue-h2">
                {renderInline(b.text)}
              </h2>
            );
          case 'h3':
            return (
              <h3 key={i} className="fp-issue-h3">
                {renderInline(b.text)}
              </h3>
            );
          case 'dek':
            return (
              <p key={i} className="fp-issue-dek">
                {renderInline(b.text)}
              </p>
            );
          case 'p':
            return (
              <p key={i} className="fp-issue-p">
                {renderInline(b.text)}
              </p>
            );
          case 'img':
            // eslint-disable-next-line @next/next/no-img-element
            return (
              <img
                key={i}
                src={b.src}
                alt={b.alt || ''}
                className="fp-issue-chart"
              />
            );
          case 'hr':
            return <hr key={i} className="fp-issue-hr" />;
        }
      })}
    </article>
  );
}
