/**
 * Model issue data: the 2026-05-03 dry-run draft re-expressed as an IssueSpec.
 *
 * This file is what the agent's "issue composer" step would emit as JSON.
 * Prose is lifted verbatim from backend/agent/data/draft_model.md; chart and
 * KPI numbers come from the same draft. A few peripheral series points that
 * the draft only describes as ranges (e.g. ND 2021-24 individual years) are
 * plausible placeholders inside the stated range, and are flagged as such in
 * the figure source lines.
 */

import type { IssueSpec } from './types';

export const modelIssue: IssueSpec = {
  meta: {
    run_date: '2026-05-03',
    cost_usd: 0.5,
    duration_sec: 284,
    n_tool_calls: 46,
    n_signals_scanned: 20,
    approved_by: 'model issue',
  },
  blocks: [
    {
      kind: 'title',
      text: "North Dakota's Acreage Split, Montana's Model Puzzle, and the Export Floor Holding Wheat",
    },
    {
      kind: 'dek',
      text: 'Robust export commitments are cushioning Hard Red Spring wheat against a supply picture that remains genuinely uncertain, as model-vs-USDA acreage gaps of historic width persist across the northern High Plains heading into the June WASDE.',
    },
    {
      kind: 'kpis',
      title: 'This week at a glance',
      items: [
        {
          value: '1.04',
          label: 'Wheat stocks-to-use',
          caption: '2025-26 U.S. ratio, well above the 0.75 trough of 2022-23.',
        },
        {
          value: '24.3M',
          unit: 'MT',
          label: 'Export commitments',
          caption: 'Jun 2025/May 2026 marketing year, as of April 2.',
          tone: 'positive',
        },
        {
          value: '5.16M',
          unit: 'ac',
          label: 'ND wheat, 2026',
          caption: "Model forecast, 23% below the state's 2021-24 mean.",
          tone: 'negative',
        },
        {
          value: '30.3M',
          unit: 'ac',
          label: 'U.S. wheat, 2026',
          caption: 'National model forecast. P10-P90 range 27.7M to 32.9M.',
        },
      ],
    },
    {
      kind: 'section',
      lead: true,
      text: 'The 23% Gap That Was Right for the Wrong Reasons: North Dakota Spring Wheat 2025',
    },
    {
      kind: 'p',
      first: true,
      text: "North Dakota is the single most consequential state in the U.S. Hard Red Spring and durum supply chain, and heading into the 2025 season, the FieldPulse model and USDA's Prospective Plantings survey were separated by 1.19 million acres, a 23.5% divergence that forced a binary question: which number should traders trust?",
    },
    {
      kind: 'stat',
      value: '1.19M acres',
      label: 'Model vs USDA Prospective gap, North Dakota spring wheat 2025',
      detail: 'A 23.5% divergence, the widest in the 2025 candidate set outside Montana.',
    },
    {
      kind: 'p',
      text: "The model projected 6,236,516 planted acres for North Dakota spring wheat in 2025. USDA's Prospective Plantings (March 2025) put the figure at 5,050,000 acres. The USDA June Actual ultimately came in at 5,000,000 acres, meaning the model's final error against the realized number was only -3.0%, while USDA's own Prospective survey was essentially on top of the final figure. The model was directionally correct that USDA's early survey was anchored too low relative to recent history, but the June Actual validated USDA's range, not the model's 6.2M ceiling.",
    },
    {
      kind: 'figure',
      title: 'Three numbers, one acre fight',
      subtitle: 'North Dakota spring wheat 2025: planted acres by source',
      source: 'USDA NASS Crop Production; FieldPulse acreage model.',
      charts: [
        {
          type: 'bars',
          valueFormat: 'abs',
          unit: 'M acres',
          decimals: 2,
          height: 190,
          domain: [0, 7],
          data: [
            { label: 'FieldPulse model', value: 6.24, color: 'var(--field)' },
            { label: 'USDA Prospective (Mar)', value: 5.05, color: 'var(--harvest)' },
            { label: 'USDA June Actual', value: 5.0, color: 'var(--soil-light)' },
          ],
        },
      ],
    },
    {
      kind: 'p',
      text: "The historical context makes USDA's Prospective figure look genuinely anomalous. North Dakota's 4-year planted-acre mean from 2021 through 2024 was 6,683,750 acres (NASS Crop Production), with individual years ranging from 6.48M to 6.92M. The 2025 June Actual of 5.0M acres is roughly 25% below that 4-year mean, making it the lowest observation in the window by more than 1.3 million acres. The model, anchored to that 5-year average, was structurally unwilling to accept a contraction of that magnitude, and in most years that skepticism would have been rewarded. In 2025, the contraction was real.",
    },
    {
      kind: 'figure',
      title: 'The contraction the model would not accept',
      subtitle:
        'North Dakota spring wheat planted acres: 2021-2025 actual, 2026 model forecast with P10-P90 band',
      source:
        'USDA NASS; FieldPulse acreage model. 2021-24 yearly values are placeholders within the reported 6.48M-6.92M range; 2026 P10 is a placeholder (draft reports P90 only).',
      charts: [
        {
          type: 'trend_forecast',
          unit: 'M acres',
          height: 280,
          yDomain: [4, 7.4],
          refValue: 6.68,
          refLabel: '2021-24 mean 6.68M',
          actuals: [
            { year: 2021, value: 6.92 },
            { year: 2022, value: 6.48 },
            { year: 2023, value: 6.75 },
            { year: 2024, value: 6.59 },
            { year: 2025, value: 5.0 },
          ],
          forecast: { year: 2026, p50: 5.16, p10: 4.57, p90: 5.75 },
        },
      ],
    },
    {
      kind: 'p',
      text: "The supply-side implications run directly into the current WASDE balance sheet. The April 18, 2026 WASDE pegs 2025-26 U.S. wheat ending stocks at 25,517 thousand bushels with a stocks-to-use ratio of 1.04, well above the 2022-23 trough of 0.75 (USDA WASDE April release). On a comfortable balance sheet, any acreage upside surprise from North Dakota in 2026 would push supply further bearish. The model's 2026 North Dakota wheat forecast of 5,162,101 acres (P90: 5,751,988) sits above USDA's 2025 Prospective Plantings of 5,050,000 acres, continuing the pattern of the model holding a structurally higher view of ND acreage than USDA's early surveys across consecutive years.",
    },
    {
      kind: 'p',
      text: 'The demand side is providing the bullish offset. U.S. wheat export commitments for the Jun 2025/May 2026 marketing year totaled 24,273,980 MT as of April 2, 2026, with net weekly sales averaging approximately 316,000 MT over the prior four reporting weeks (USDA Export Sales Reporting). The 2025-26 WASDE projects U.S. wheat exports at 24,494 thousand bushels, up from 22,477 thousand in 2024-25 and the highest since the 2020-21 marketing year’s 27,048 thousand bushels (USDA WASDE April release). That export demand is the primary reason HRS basis has held up despite a stocks-to-use ratio that is not historically tight.',
    },
    {
      kind: 'watch',
      text: "The reconciliation signal that matters most before the June WASDE is USDA's weekly Crop Progress report for North Dakota spring wheat planting pace: if planted-area progress runs ahead of the 5-year average in the coming weeks, it will begin to close the gap between the model's higher structural view and USDA's still-cautious acreage baseline.",
    },
    { kind: 'hr' },
    { kind: 'section', text: 'Briefs' },
    {
      kind: 'brief',
      text: 'North Dakota Corn: The Model Is Low, and History Says USDA Wins Here',
    },
    {
      kind: 'p',
      first: true,
      text: "The same state producing the wheat acreage debate is generating an equally sharp corn signal, but in the opposite direction. The FieldPulse model's 2025 North Dakota corn forecast of 3,528,764 acres sits 671,236 acres, or 16.0%, below USDA's Prospective Plantings figure of 4,200,000 acres, the widest model-vs-USDA gap recorded for the state since 2021 (NASS Crop Production). The model is anchoring to North Dakota's 4-year historical average of roughly 3.575M acres (2021-2024), while USDA's 4.2M Prospective would represent a new multi-year high and a 10.5% increase over the 2024 June Actual of 3,800,000 acres.",
    },
    {
      kind: 'figure',
      title: 'A 671,000-acre disagreement in corn country',
      subtitle: 'North Dakota corn, and where ND ranks among the hardest states to call',
      source: 'USDA NASS Crop Production; FieldPulse accuracy database.',
      charts: [
        {
          type: 'bars',
          valueFormat: 'abs',
          unit: 'M acres',
          decimals: 2,
          height: 170,
          domain: [0, 4.7],
          caption: 'ND corn planted acres, 2025',
          data: [
            { label: 'FieldPulse model', value: 3.53, color: 'var(--field)' },
            { label: 'USDA Prospective', value: 4.2, color: 'var(--harvest)' },
            { label: '2024 June Actual', value: 3.8, color: 'var(--soil-light)' },
          ],
        },
        {
          type: 'bars',
          valueFormat: 'abs',
          unit: '%',
          decimals: 1,
          height: 170,
          domain: [0, 11.5],
          caption: '5-yr mean abs deviation vs USDA, corn',
          data: [
            { label: 'North Dakota', value: 10.2, color: 'var(--negative)' },
            { label: 'Kentucky', value: 10.1, color: 'var(--soil-light)' },
            { label: 'Pennsylvania', value: 8.6, color: 'var(--soil-light)' },
            { label: 'Colorado', value: 8.5, color: 'var(--soil-light)' },
          ],
        },
      ],
    },
    {
      kind: 'p',
      text: "The historical record is not encouraging for the model: in 3 of the 4 prior years where the model was below USDA's Prospective, the June Actual came in at or above USDA's number. North Dakota holds the highest 5-year mean absolute deviation vs. USDA of any corn-producing state in the accuracy database at 10.2%, above Kentucky (10.1%), Pennsylvania (8.6%), and Colorado (8.5%).",
    },
    {
      kind: 'watch',
      text: "Watch USDA's June Acreage report (released late June) for the first hard planted-acres read: if the June Actual again meets or exceeds 4.2M, it would add roughly 721,000 acres of corn supply to the balance sheet relative to the model's current anchor.",
    },
    {
      kind: 'brief',
      text: 'The High Plains Wheat Belt: Two Harvests, One Export Pipeline, One Weak Link',
    },
    {
      kind: 'p',
      first: true,
      text: "The High Plains wheat belt runs from Kansas hard red winter in the south to North Dakota hard red spring in the north, and the two sub-regions are telling different stories in 2026. Kansas, the belt's HRW anchor, averaged 7.6 million wheat acres over 2021-2024 (peak: 8.1M in 2023, NASS Crop Production), providing a relatively stable southern floor. Oklahoma has held planted area in a narrow 4.3M-4.6M band since 2021. The northern tier is where the structural adjustment is concentrated: North Dakota's 2026 wheat forecast of 5.16 million acres sits roughly 23% below its 2021-2024 four-year mean of 6.68 million acres, the sharpest implied pullback of any state in the belt.",
    },
    {
      kind: 'figure',
      title: 'Where the belt is shrinking',
      subtitle: '2026 model wheat acreage forecast vs 2021-24 average planted acres',
      source:
        'FieldPulse acreage model; USDA NASS. ND, KS, OK values from issue data; NE, CO, SD are illustrative placeholders for this model issue. Montana is flagged pending the model investigation covered below.',
      charts: [
        {
          type: 'region_map',
          metricLabel: '2026 forecast vs 2021-24 avg',
          unit: 'M ac',
          height: 460,
          states: [
            { fips: '38', abbr: 'ND', name: 'North Dakota', forecast: 5.16, baseline: 6.68 },
            { fips: '46', abbr: 'SD', name: 'South Dakota', forecast: 1.61, baseline: 1.74 },
            { fips: '31', abbr: 'NE', name: 'Nebraska', forecast: 0.93, baseline: 0.97 },
            { fips: '20', abbr: 'KS', name: 'Kansas', forecast: 7.5, baseline: 7.6 },
            { fips: '40', abbr: 'OK', name: 'Oklahoma', forecast: 4.4, baseline: 4.45 },
            { fips: '08', abbr: 'CO', name: 'Colorado', forecast: 2.05, baseline: 2.16 },
            {
              fips: '30',
              abbr: 'MT',
              name: 'Montana',
              forecast: null,
              baseline: 5.34,
              note: 'Model divergence flagged. See the Montana brief.',
            },
          ],
        },
      ],
    },
    {
      kind: 'p',
      text: 'The national wheat acreage model projects 30.3 million planted acres for 2026 (P10-P90 range: 27.7M-32.9M). The export pipeline gives the northern-tier gap real consequence: U.S. wheat accumulated exports for Jun 2025/May 2026 reached 20.2 million metric tons as of April 2, with 4.05 million MT in outstanding sales, a combined pipeline of roughly 24.3 million MT (USDA Export Sales Reporting). Kansas cannot substitute for the distinct HRS and durum classes that only North Dakota, Montana, and South Dakota produce for Asian and North African buyers.',
    },
    {
      kind: 'watch',
      text: "Watch USDA's weekly export inspections report for class-level breakdowns: if HRS and durum inspections begin lagging hard red winter, it will be the first data confirmation that the northern-tier acreage gap is transmitting into the export pipeline.",
    },
    {
      kind: 'brief',
      text: 'Montana Spring Wheat: When the Model Is 137% Above USDA and Still Closer to Right',
    },
    {
      kind: 'p',
      first: true,
      text: "Montana's 2025 spring wheat model forecast of 5.09 million acres stands 136.9% above USDA's Prospective Plantings estimate of 2.15 million acres, the widest model-vs-USDA gap in the 2025 candidate set. The gap is not a one-year anomaly: the 2024 model-vs-USDA gap was +97.0%, and the same structural divergence appears in Montana winter wheat, where the 2024 model forecast of 5.20M acres sat +166.9% above USDA Prospective Plantings of 1.95M (NASS Crop Production). The explanation is visible in the data: Montana's observed all-wheat planted acres averaged 5.34 million per year from 2021-2024, nearly identical to the model's spring-wheat-only forecast of 5.09M, strongly implying the model is drawing on undifferentiated wheat acreage history rather than spring-specific survey data.",
    },
    {
      kind: 'figure',
      title: 'Huge survey gaps, tiny final errors',
      subtitle:
        "The model appears to track Montana's all-wheat acreage, not spring-specific surveys",
      source: 'USDA NASS Crop Production; FieldPulse accuracy database.',
      charts: [
        {
          type: 'bars',
          valueFormat: 'signed_pct',
          decimals: 1,
          height: 190,
          caption: 'Model gap vs USDA Prospective',
          data: [
            { label: 'MT winter 2024', value: 166.9, color: 'var(--harvest)' },
            { label: 'MT spring 2025', value: 136.9, color: 'var(--harvest)' },
            { label: 'MT spring 2024', value: 97.0, color: 'var(--harvest)' },
            { label: 'ND spring 2025', value: 23.5, color: 'var(--soil-light)' },
          ],
        },
        {
          type: 'bars',
          valueFormat: 'signed_pct',
          decimals: 2,
          height: 190,
          domain: [-5, 1.6],
          caption: 'Model final error vs June Actual',
          data: [
            { label: 'MT spring 2024', value: -0.22, color: 'var(--field)' },
            { label: 'ND spring 2025', value: -3.0, color: 'var(--field)' },
            { label: 'MT spring 2025', value: -3.72, color: 'var(--field)' },
          ],
        },
      ],
    },
    {
      kind: 'p',
      text: "USDA's June Actual for Montana spring wheat moved only modestly from Prospective Plantings in both available years, a revision range of roughly 7%, far too small to close a 137% gap. The model's final error against June actuals was only -3.72% in 2025 and -0.22% in 2024, but those small percentage errors mask a roughly 2.8M-acre absolute overshoot.",
    },
    {
      kind: 'watch',
      text: "Watch USDA's Crop Progress report for Montana spring wheat planting pace: if planted acreage runs materially above the 2.15M Prospective baseline, it would be the first field-level signal that the model's higher acreage view has any empirical support.",
    },
    { kind: 'hr' },
  ],
};
