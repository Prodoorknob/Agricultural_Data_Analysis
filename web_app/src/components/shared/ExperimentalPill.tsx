'use client';

interface ExperimentalPillProps {
  onClick?: () => void;
}

export default function ExperimentalPill({ onClick }: ExperimentalPillProps) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center px-2 py-0.5 rounded-[var(--radius-full)] border cursor-pointer"
      style={{
        background: 'var(--surface2)',
        borderColor: 'var(--harvest-subtle)',
        color: 'var(--harvest-dark)',
        fontFamily: 'var(--font-mono)',
        fontSize: '10px',
        fontWeight: 700,
        letterSpacing: '0.12em',
        textTransform: 'uppercase' as const,
      }}
      title="Experimental \u2014 see accuracy modal"
    >
      EXPERIMENTAL
    </button>
  );
}
