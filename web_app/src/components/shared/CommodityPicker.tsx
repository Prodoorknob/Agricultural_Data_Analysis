'use client';

import { CROP_COMMODITIES } from '@/lib/constants';
import type { CropOptionGroup } from '@/utils/processData';

interface CommodityPickerProps {
  selected: string;
  onSelect: (id: string) => void;
  /** Subset of commodity IDs to show as chips. If omitted, shows all 11.
   *  Ignored when `groups` is provided. */
  commodities?: readonly { id: string; label: string; color: string }[];
  /** Grouped options (Field Crops / Fruits & Nuts / Vegetables). When set,
   *  renders one compact dropdown per group instead of chips. */
  groups?: CropOptionGroup[];
}

function Chip({
  id,
  label,
  color,
  active,
  onSelect,
}: {
  id: string;
  label: string;
  color: string;
  active: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <button
      onClick={() => onSelect(id)}
      className="px-3 py-1.5 text-[13px] font-medium rounded-[var(--radius-full)] border transition-all"
      style={{
        background: active ? color : 'transparent',
        color: active ? '#FFFFFF' : 'var(--text2)',
        borderColor: active ? color : 'var(--border2)',
        fontFamily: 'var(--font-body)',
        transitionDuration: 'var(--duration-fast)',
      }}
    >
      {label}
    </button>
  );
}

function GroupDropdown({
  group,
  selected,
  onSelect,
}: {
  group: CropOptionGroup;
  selected: string;
  onSelect: (id: string) => void;
}) {
  const sel = selected.toLowerCase();
  const active = group.options.some((o) => o.id.toLowerCase() === sel);

  return (
    <div className="relative inline-flex">
      <select
        value={active ? group.options.find((o) => o.id.toLowerCase() === sel)!.id : ''}
        onChange={(e) => { if (e.target.value) onSelect(e.target.value); }}
        aria-label={group.label}
        className="appearance-none text-[13px] font-medium rounded-[var(--radius-full)] border pl-3.5 pr-8 py-1.5 cursor-pointer transition-all focus:outline-none"
        style={{
          background: active ? group.color : 'var(--surface)',
          color: active ? '#FFFFFF' : 'var(--text2)',
          borderColor: active ? group.color : 'var(--border2)',
          fontFamily: 'var(--font-body)',
          transitionDuration: 'var(--duration-fast)',
        }}
      >
        <option value="">{group.label}</option>
        {group.options.map((o) => (
          <option key={o.id} value={o.id}>{o.label}</option>
        ))}
      </select>
      {/* Chevron */}
      <svg
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2"
        width="10" height="10" viewBox="0 0 10 10" fill="none"
        style={{ color: active ? '#FFFFFF' : 'var(--text3)' }}
        aria-hidden="true"
      >
        <path d="M2 3.5 5 6.5 8 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

export default function CommodityPicker({
  selected,
  onSelect,
  commodities = CROP_COMMODITIES,
  groups,
}: CommodityPickerProps) {
  const sel = selected.toLowerCase();

  // Grouped layout — one dropdown per group. Used by the Crops tab once
  // specialty crops are in play (too many to show as chips).
  if (groups && groups.length > 0) {
    return (
      <div className="flex items-center gap-2.5 flex-wrap">
        {groups.map((g) => (
          <GroupDropdown key={g.id} group={g} selected={selected} onSelect={onSelect} />
        ))}
      </div>
    );
  }

  // Flat chip fallback (Market tab / pre-derivation short lists).
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {commodities.map((c) => (
        <Chip
          key={c.id}
          id={c.id}
          label={c.label}
          color={c.color}
          active={sel === c.id.toLowerCase()}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}
