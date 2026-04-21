/**
 * Caption template engine for FieldPulse.
 * Each chart calls generateCaption(templateId, data) at render time.
 * Templates are keyed by band ID. Slot interpolation only — no HTML.
 */

const templates: Record<string, string> = {
  // Overview
  'overview-hero-sales':
    '{stateName} ranks #{salesRank} by total farm sales, {salesDirection} {salesGrowthPct}% since {salesCompareYear}.',
  'overview-hero-acres':
    '{acresDeltaDirection} {acresDeltaAbs} acres from {priorYear} — driven mostly by {acresDeltaDriver}.',
  'overview-hero-top-crop':
    '{topCrop} has been {stateName}\'s #1 crop {topCropStreakText}.',
  'overview-fingerprint-revenue':
    '{topTwoCrops} drive {topTwoPct}% of {stateName}\'s ag revenue.',
  'overview-peer-comparison':
    '{stateName}\'s {metric} is {deltaPct}% {comparison} {peerState}, ranking #{rank} of 50.',

  // Crops
  'crops-yield-trend':
    '{stateName} {commodity} yields have {direction} {pct}% since {startYear} ({percentile} percentile of the 25-year record).',
  'crops-anomaly':
    'Biggest dip: {anomalyYear} ({delta}%, {narrative}).',
  'crops-profit':
    'At ${price}/bu, margin per bushel is ${margin} — {marginContext}.',
  'crops-harvest-efficiency':
    '{commodity} harvest efficiency has averaged {avgPct}% over 25 years in {stateName}.',
  'crops-condition':
    'Condition is tracking {conditionDelta} points {conditionDirection} the 5-year average.',

  // Market
  'market-price-history':
    '{commodity} futures are {deltaDirection} {deltaPct}% {deltaComparison} their 5-year average for mid-{monthName}.',
  'market-wasde':
    'USDA {wasdeAction} {metric} from {oldVal} to {newVal} ({surprisePp} pp surprise, {percentileLabel}).',
  'market-ratio':
    'At {ratio} the ratio is in the {zone} zone. Historically ratios below 2.2 have shifted 2–4M acres to soybeans.',
  'market-input-cost':
    '{commodity} production cost is ${costPerBu}/bu. At today\'s ${futuresPrice} futures price, margin per bushel is ${margin} — {marginContext}.',
  'market-dxy':
    'The dollar has {dxyDirection} {dxyPct}% in 3 months — historically a {dxyImpact} for U.S. grain exports.',

  // Forecasts
  'forecasts-season-clock':
    'Today is {monthName} {day}. {acreageStatus}. {yieldStatus}.',
  'forecasts-acreage-usda':
    'USDA Prospective Plantings (Mar 31): {usdaVal}. Our forecast is {deltaPct}% {deltaDirection}.',
  'forecasts-accuracy-acreage':
    'Our acreage model {accuracySummary} for {commodity} {accuracyPeriod}.',

  // Land & Economy
  'land-operations':
    '{stateName} {operationsDirection} {operationsDelta} farms since {sinceYear} but average farm size {sizeDirection} {sizeDelta}% — {interpretation}.',
  'land-sprawl':
    '{sprawlCount} states lost cropland to urban growth between {startYear} and {endYear}. The steepest trade-off: {topStates}.',
  'land-wages':
    '{stateName} farm wages grew {wageGrowthPct}% over 10 years, {wageVsNational}pp {wageComparison} the national average.',
};

/**
 * Interpolate a caption template with data.
 * Returns empty string if template not found — never throws.
 */
export function generateCaption(
  templateId: string,
  data: Record<string, string | number>
): string {
  const tpl = templates[templateId];
  if (!tpl) return '';
  return tpl.replace(/\{(\w+)\}/g, (_, key) => {
    const val = data[key];
    return val !== undefined ? String(val) : `{${key}}`;
  });
}
