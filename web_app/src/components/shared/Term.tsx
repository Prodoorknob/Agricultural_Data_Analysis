'use client';

import { useState, useRef, useEffect } from 'react';
import glossary from '@/data/glossary.json';

interface TermProps {
  children: React.ReactNode;
  term?: string;  // override lookup key (defaults to children text, lowercased)
}

const glossaryMap = glossary as Record<string, string>;

export default function Term({ children, term }: TermProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const key = (term || (typeof children === 'string' ? children : '')).toLowerCase().trim();
  const definition = glossaryMap[key];

  // If term not in glossary, render as plain text
  if (!definition) return <>{children}</>;

  // Close on click outside
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (
        ref.current && !ref.current.contains(e.target as Node) &&
        popoverRef.current && !popoverRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  return (
    <span className="relative inline" ref={ref}>
      <span
        className="cursor-help"
        style={{
          borderBottom: '1px dashed var(--text3)',
          paddingBottom: '1px',
        }}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onClick={() => setOpen((o) => !o)}
      >
        {children}
      </span>

      {open && (
        <div
          ref={popoverRef}
          className="absolute z-50 p-3 rounded-[var(--radius-md)] border"
          style={{
            background: 'var(--surface)',
            borderColor: 'var(--border)',
            boxShadow: 'var(--shadow-md)',
            maxWidth: '320px',
            width: 'max-content',
            top: 'calc(100% + 6px)',
            left: 0,
            fontSize: '13px',
            lineHeight: 1.5,
            color: 'var(--text2)',
            fontFamily: 'var(--font-body)',
          }}
        >
          {definition}
        </div>
      )}
    </span>
  );
}
