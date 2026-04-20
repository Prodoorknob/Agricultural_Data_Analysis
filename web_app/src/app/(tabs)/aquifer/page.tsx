import { AquiferMap } from '@/components/aquifer';

export default function AquiferPage() {
  return (
    <div className="flex flex-col gap-4">
      <header>
        <div
          className="text-[11px] uppercase tracking-wider"
          style={{ color: 'var(--text2)', fontFamily: 'var(--font-body)' }}
        >
          High Plains Aquifer · 8 states · 606 counties
        </div>
        <h1
          className="text-[28px] font-bold tracking-[-0.02em] mt-1"
          style={{ color: 'var(--text)' }}
        >
          Ogallala depletion
        </h1>
        <p
          className="mt-1 text-[14px] max-w-[680px]"
          style={{ color: 'var(--text2)', fontFamily: 'var(--font-body)' }}
        >
          Click a county for thickness, decline, years-to-depletion, and data-
          quality provenance. Rust-colored counties are already below 5 m of
          saturated thickness — functionally depleted.
        </p>
      </header>

      <AquiferMap />
    </div>
  );
}
