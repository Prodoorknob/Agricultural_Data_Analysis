'use client';

interface InputCostCardProps {
  commodity: string;
  productionCostPerBu: number | null;
  currentFuturesPrice: number | null;
  marginPerBu: number | null;
  fertilizer: {
    anhydrousAmmonia: number | null;
    dap: number | null;
    potash: number | null;
  } | null;
}

export default function InputCostCard({
  commodity,
  productionCostPerBu,
  currentFuturesPrice,
  marginPerBu,
  fertilizer,
}: InputCostCardProps) {
  const hasCost = productionCostPerBu !== null;
  const hasMargin = marginPerBu !== null;

  return (
    <div
      className="p-5 rounded-[var(--radius-lg)] border flex-1"
      style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
    >
      <p
        className="text-[11px] font-bold tracking-[0.1em] uppercase mb-3"
        style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}
      >
        Input Costs
      </p>

      {/* Production cost headline */}
      {hasCost && (
        <div className="mb-3">
          <span
            style={{
              fontFamily: 'var(--font-stat)',
              fontSize: '32px',
              fontWeight: 800,
              color: 'var(--text)',
            }}
          >
            ${productionCostPerBu.toFixed(2)}
          </span>
          <span className="text-[12px] ml-1" style={{ color: 'var(--text3)', fontFamily: 'var(--font-mono)' }}>
            /bu production cost
          </span>
        </div>
      )}

      {/* Fertilizer rows */}
      {fertilizer && (
        <div className="flex flex-col gap-2 mb-3">
          {fertilizer.anhydrousAmmonia !== null && (
            <FertRow label="Anhydrous ammonia" value={`$${fertilizer.anhydrousAmmonia.toFixed(0)}/ton`} />
          )}
          {fertilizer.dap !== null && (
            <FertRow label="DAP" value={`$${fertilizer.dap.toFixed(0)}/ton`} />
          )}
          {fertilizer.potash !== null && (
            <FertRow label="Potash" value={`$${fertilizer.potash.toFixed(0)}/ton`} />
          )}
        </div>
      )}

      {/* Margin caption */}
      {hasMargin && currentFuturesPrice !== null && (
        <p className="text-[13px]" style={{ color: 'var(--text2)' }}>
          At today's ${currentFuturesPrice.toFixed(2)} futures, margin per bushel is{' '}
          <span
            className="font-bold"
            style={{ color: marginPerBu >= 0 ? 'var(--positive)' : 'var(--negative)' }}
          >
            ${marginPerBu.toFixed(2)}
          </span>.
        </p>
      )}

      {!hasCost && (
        <p className="text-[13px]" style={{ color: 'var(--text3)' }}>
          Cost data unavailable for {commodity}.
        </p>
      )}
    </div>
  );
}

function FertRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-[12px]" style={{ color: 'var(--text2)' }}>{label}</span>
      <span className="text-[13px] font-medium" style={{ color: 'var(--text)', fontFamily: 'var(--font-mono)' }}>
        {value}
      </span>
    </div>
  );
}
