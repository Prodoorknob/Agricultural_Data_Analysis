/**
 * Minimal markdown renderer scoped to FieldPulse Weekly's output format.
 *
 * The writer prompt constrains output to: # / ## / ### headings, *italic*
 * deks, paragraphs, {{chart_N}} placeholders or ![](url) images, --- rules.
 * We don't need a full CommonMark renderer — a tight inline implementation
 * gives us full control over styling.
 *
 * Structural awareness:
 *   - "Lead:" prefix on the lead H2 is stripped (it's redundant — readers
 *     know which is the lead from position + typography).
 *   - The FIRST paragraph after a lead H2 gets the `is-first` class so we
 *     can drop-cap or accent it.
 *   - The LAST paragraph before an HR / next heading gets `is-watch` so we
 *     can render the writer's "what to watch" forward-looking line as a
 *     callout.
 *   - `{{chart_N}}` placeholders are detected and rendered as a styled
 *     block, even when the publisher hasn't resolved them to images yet
 *     (e.g. in the dev preview route).
 *
 * NOTE: the parsing + watch heuristics here are mirrored in Python by
 * backend/agent/composer.py (parse_markdown_blocks) for the IssueSpec
 * publishing path. Keep the two in sync when changing either.
 */

import React from 'react';

type Block =
  | { type: 'h1'; text: string }
  | { type: 'h2'; text: string; isLead?: boolean }
  | { type: 'h3'; text: string }
  | { type: 'dek'; text: string }
  | { type: 'p'; text: string; isFirst?: boolean; isWatch?: boolean }
  | { type: 'img'; alt: string; src: string }
  | { type: 'chart_placeholder'; id: string }
  | { type: 'hr' };

const HEADING_RE = /^(#{1,3})\s+(.*)$/;
const IMAGE_RE = /^!\[(.*?)\]\((.+?)\)\s*$/;
const ITALIC_DEK_RE = /^\*(.+)\*\s*$/;
const CHART_PLACEHOLDER_RE = /^\{\{(chart_\w+)\}\}\s*$/;
const LEAD_PREFIX_RE = /^Lead\s*:\s*/i;

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
      return;
    }
    // Single-paragraph briefs often pack their "what to watch" forward look
    // into the final sentence. Detect and split so the callout treatment
    // applies even when the section is a single paragraph.
    const split = _splitTrailingWatchSentence(text);
    if (split) {
      blocks.push({ type: 'p', text: split.body });
      blocks.push({ type: 'p', text: split.watch, isWatch: true });
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
    const chart = CHART_PLACEHOLDER_RE.exec(line);
    if (chart) {
      flushParagraph();
      blocks.push({ type: 'chart_placeholder', id: chart[1] });
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
      let text = heading[2];
      if (level === 1) {
        blocks.push({ type: 'h1', text });
      } else if (level === 2) {
        // Detect "Lead:" prefix and strip it.
        const m = LEAD_PREFIX_RE.exec(text);
        const isLead = !!m;
        if (isLead) text = text.replace(LEAD_PREFIX_RE, '').trim();
        blocks.push({ type: 'h2', text, isLead });
      } else {
        blocks.push({ type: 'h3', text });
      }
      continue;
    }
    buf.push(line);
  }
  flushParagraph();

  // Second pass: tag first/last paragraphs per section.
  return annotateSections(blocks);
}

function annotateSections(blocks: Block[]): Block[] {
  const isSectionHeading = (b: Block) =>
    b.type === 'h2' || b.type === 'h3';

  // Walk blocks. For each section, find the first paragraph and the last
  // paragraph BEFORE the next section heading or hr.
  const indices: { firstP: number | null; lastP: number | null }[] = [];
  let curFirst: number | null = null;
  let curLast: number | null = null;

  const flushSection = () => {
    indices.push({ firstP: curFirst, lastP: curLast });
    curFirst = null;
    curLast = null;
  };

  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i];
    if (isSectionHeading(b) || b.type === 'hr') {
      flushSection();
      continue;
    }
    if (b.type === 'p') {
      if (curFirst === null) curFirst = i;
      curLast = i;
    }
  }
  flushSection();

  const firstSet = new Set<number>();
  const lastSet = new Set<number>();
  for (const { firstP, lastP } of indices) {
    if (firstP !== null) firstSet.add(firstP);
    if (lastP !== null && lastP !== firstP) lastSet.add(lastP);
    // Only tag lastP as "watch" if the section has > 1 paragraph (single-
    // paragraph briefs shouldn't have their only paragraph turned into a
    // callout).
  }

  return blocks.map((b, i) => {
    if (b.type !== 'p') return b;
    return {
      ...b,
      isFirst: firstSet.has(i),
      isWatch: lastSet.has(i) && _looksLikeWatch(b.text),
    };
  });
}

/**
 * If a paragraph ends with a "what to watch" sentence (e.g. "Watch USDA's
 * Crop Progress..."), split it off so the renderer can call it out.
 *
 * Returns { body, watch } when a split is appropriate, or null to keep the
 * paragraph as-is. We only split when the body still has at least 80 chars
 * of substance — we don't want to leave a one-clause stub behind.
 */
function _splitTrailingWatchSentence(text: string): { body: string; watch: string } | null {
  // Find sentence boundaries. Reverse-walk looking for ". " then check if
  // the trailing sentence matches the watch pattern.
  const MIN_BODY = 80;
  // Crude sentence splitter — find ". " or ".\n" preceded by non-uppercase
  // (to avoid splitting on initials like "U.S.").
  const matches: number[] = [];
  for (let i = 1; i < text.length - 1; i++) {
    if (text[i] !== '.') continue;
    if (text[i + 1] !== ' ' && text[i + 1] !== '\n') continue;
    // Skip if next char is a lowercase letter (abbreviation mid-word).
    const next = text[i + 2];
    if (next && next === next.toLowerCase() && /[a-z]/.test(next)) continue;
    matches.push(i);
  }
  for (let i = matches.length - 1; i >= 0; i--) {
    const idx = matches[i];
    const body = text.slice(0, idx + 1).trim();
    const tail = text.slice(idx + 2).trim();
    if (body.length < MIN_BODY) break;
    if (tail.length < 30) continue; // need a real sentence to be a callout
    if (_looksLikeWatch(tail)) {
      return { body, watch: tail };
    }
    // Stop after checking the LAST sentence only — we don't want to split
    // mid-paragraph at an interior watch-flavored sentence.
    break;
  }
  return null;
}


function _looksLikeWatch(text: string): boolean {
  // Writer prompt explicitly asks for a "what to watch" forward-looking line
  // as the last sentence of each story. Heuristic: starts with "Watch",
  // "The reconciliation signal", "If", or contains a future-tense modal
  // phrase + a report name.
  const t = text.toLowerCase();
  if (
    /^(watch\b|the reconciliation|the next signal|the signal that matters|if (planted|the))/i.test(text)
  ) {
    return true;
  }
  if (
    /\b(watch|track|monitor)\b/i.test(text) &&
    /\b(usda|wasde|nass|fas|crop progress|prospective|acreage|export sales|cattle on feed)\b/i.test(text)
  ) {
    return true;
  }
  return false;
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
    <article className="fp-issue">
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
              <h2
                key={i}
                className={`fp-issue-h2 ${b.isLead ? 'fp-issue-h2--lead' : ''}`}
              >
                {b.isLead && <span className="fp-issue-lead-pill">LEAD</span>}
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
          case 'p': {
            const cls = [
              'fp-issue-p',
              b.isFirst ? 'fp-issue-p--first' : '',
              b.isWatch ? 'fp-issue-p--watch' : '',
            ]
              .filter(Boolean)
              .join(' ');
            return (
              <p key={i} className={cls}>
                {b.isWatch && (
                  <span className="fp-issue-watch-tag">WHAT TO WATCH</span>
                )}
                {renderInline(b.text)}
              </p>
            );
          }
          case 'img':
            // eslint-disable-next-line @next/next/no-img-element
            return (
              <figure key={i} className="fp-issue-chart">
                <img src={b.src} alt={b.alt || ''} />
                {b.alt && <figcaption>{b.alt}</figcaption>}
              </figure>
            );
          case 'chart_placeholder':
            return (
              <figure key={i} className="fp-issue-chart fp-issue-chart--placeholder">
                <div className="fp-issue-chart-label">
                  <span className="fp-issue-chart-id">{b.id}</span>
                  <span className="fp-issue-chart-hint">
                    Chart will render here in the published issue.
                  </span>
                </div>
              </figure>
            );
          case 'hr':
            return <hr key={i} className="fp-issue-hr" />;
        }
      })}
    </article>
  );
}
