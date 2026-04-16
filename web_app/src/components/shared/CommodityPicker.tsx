'use client';

import { CROP_COMMODITIES } from '@/lib/constants';

interface CommodityPickerProps {
  selected: string;
  onSelect: (id: string) => void;
  /** Subset of commodity IDs to show. If omitted, shows all 11. */
  commodities?: readonly { id: string; label: string; color: string }[];
}

export default function CommodityPicker({
  selected,
  onSelect,
  commodities = CROP_COMMODITIES,
}: CommodityPickerProps) {
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {commodities.map((c) => {
        const active = selected.toLowerCase() === c.id.toLowerCase();
        return (
          <button
            key={c.id}
            onClick={() => onSelect(c.id)}
            className="px-3 py-1.5 text-[13px] font-medium rounded-[var(--radius-full)] border transition-all"
            style={{
              background: active ? c.color : 'transparent',
              color: active ? '#FFFFFF' : 'var(--text2)',
              borderColor: active ? c.color : 'var(--border2)',
              fontFamily: 'var(--font-body)',
              transitionDuration: 'var(--duration-fast)',
            }}
          >
            {c.label}
          </button>
        );
      })}
    </div>
  );
}
