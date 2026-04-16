'use client';

interface RangeChipsProps {
  selected: string;
  onSelect: (r: string) => void;
  options?: string[];
}

export default function RangeChips({
  selected,
  onSelect,
  options = ['1M', '6M', '1Y', '5Y', 'MAX'],
}: RangeChipsProps) {
  return (
    <div className="flex items-center gap-1">
      {options.map((r) => (
        <button
          key={r}
          onClick={() => onSelect(r)}
          className="px-2.5 py-1 text-[11px] font-bold rounded-[var(--radius-full)] border transition-all"
          style={{
            background: selected === r ? 'var(--field)' : 'transparent',
            color: selected === r ? '#FFFFFF' : 'var(--text3)',
            borderColor: selected === r ? 'var(--field)' : 'var(--border2)',
            fontFamily: 'var(--font-mono)',
            transitionDuration: 'var(--duration-fast)',
          }}
        >
          {r}
        </button>
      ))}
    </div>
  );
}
