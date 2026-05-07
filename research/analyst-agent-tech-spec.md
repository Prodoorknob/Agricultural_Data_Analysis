# FieldPulse Weekly — Analyst Agent — Tech Spec (v0.3)
**Module:** Agricultural Dashboard · Module 05
**Version:** 0.3 | **Date:** 2026-05-06
**Author:** Rajashekar Reddy Vedire
**Stack:** Python + Claude API + existing RDS / S3 / FastAPI / `slack_sdk` (Knowledge Curator pipeline)
**Status:** Ready for implementation — v1 decisions locked (§11), feasibility pass complete (§15)

---

## 1. Overview

A weekly autonomous agent that plays the role of a junior analyst. Each Sunday it synthesizes a "current mood" from market + data context, scans every signal we have (yield forecasts, acreage forecasts, price forecasts, WASDE surprises, drought, CCI, exports, weather anomalies, long-history trend breaks), picks the most newsworthy 1 lead story + 2-3 briefs, pulls supporting evidence, and publishes a 600-1200 word markdown newsletter to the dashboard at `/insights`.

Brand: **FieldPulse Weekly** (cohesive with the FieldPulse design system).

The agent is not a chatbot. It runs on a cron, produces a single artifact, and exits. Reasoning is multi-step (mood → scan → pick → research → draft → fact-check) with tool-use against the existing data layer.

### 1.1 Why an LLM (and not just a templated report)

Templated weekly reports are the obvious baseline. They fail on three things:
1. **Selection** — which of 3,000 county-level signals matters this week, in narrative terms
2. **Synthesis** — connecting a Kansas drought reading, a wheat futures move, and a WASDE surprise into one story
3. **Voice** — readable analyst prose, not a stat dump

An LLM with tool-use handles all three. The agent's job is editorial judgement plus prose, grounded in numbers it must fetch (never invent).

### 1.2 What stays deterministic

- The **signal scan** (§4) is pure Python — z-scores, thresholds, ranking. The LLM never decides what counts as anomalous; it picks among pre-ranked candidates.
- The **fact-check** (§8) is a regex extractor + cross-check against tool-call results. Hallucinated numbers fail the gate.
- The **chart generation** is matplotlib, parameterized by JSON the LLM produces.

The LLM only gets to: synthesize mood, pick stories, write prose, decide what to research next.

### 1.3 v1 vs v2 scope

**v1 (this spec):** internal audience, `/insights` route only, draft-then-approve publish mode.
**v2 (later):** public subscribers, email distribution, LinkedIn auto-draft, RSS feed, branding/compliance polish. Carved out in §14.

---

## 2. Stack Additions

| Component | Addition | Why |
|---|---|---|
| Python packages | `anthropic`, `jinja2`, `markdown-it-py`, `matplotlib`, `slack_sdk` | Claude API + templating + charts + Slack |
| Postgres | 3 new tables: `agent_runs`, `agent_picks`, `agent_mood` | Run history + dedup memory + mood log |
| S3 prefix | `newsletters/YYYY/MM/` | Published markdown + chart PNGs |
| Frontend | 1 new route `/insights` + approval UI at `/insights/draft` | Reader + 1-click approval |
| Cron | 1 new weekly job (Sun 18:00 ET) | Generate + publish |
| Slack | New channel `#fieldpulse-weekly` via the **Knowledge Curator** Slack pipeline (Python `slack_sdk` + bot token, server-side, no MCP) | Failure alerts + draft-ready pings |

No new infra — runs on existing EC2.

---

## 3. Architecture

```
┌────────────────────────────────────────────────────────────────┐
│ Sun 18:00 ET cron — agent.run()                                │
└──────────────┬─────────────────────────────────────────────────┘
               │
               ▼
   ┌─────────────────────────┐
   │ Step 1: SignalBoard     │  pure Python — query all sources,
   │  (deterministic)        │  compute anomaly scores, rank top-N
   └────────────┬────────────┘
                │  candidates: 12-20 ranked signals
                ▼
   ┌─────────────────────────┐
   │ Step 2: MoodSynthesizer │  Claude — reads recent WASDE
   │  (LLM, no tools)        │  narrative + futures recap +
   │                         │  season calendar, emits mood tags
   └────────────┬────────────┘  → rescores signals via mood match
                │
                ▼
   ┌─────────────────────────┐
   │ Step 3: Editor          │  Claude — JSON-only response
   │  (LLM, no tools)        │  picks 1 lead + 2-3 briefs
   └────────────┬────────────┘  with rationale
                │
                ▼
   ┌─────────────────────────┐
   │ Step 4: Researcher      │  Claude with tool-use loop
   │  (LLM, tools)           │  iterative: query → reason → query
   └────────────┬────────────┘  collects research dossier
                │
                ▼
   ┌─────────────────────────┐
   │ Step 5: Writer          │  Claude — markdown draft
   │  (LLM, dossier only)    │  embeds {{chart_id}} placeholders
   └────────────┬────────────┘
                │
                ▼
   ┌─────────────────────────┐
   │ Step 6: FactChecker     │  deterministic + LLM critique
   │  (Python + LLM)         │  every number traces to dossier
   └────────────┬────────────┘
                │  pass → publish   fail → Slack + email alert
                ▼
   ┌─────────────────────────┐
   │ Step 7: Publisher       │  render charts → stage to draft
   │  (deterministic)        │  → Slack ping → await approval
   └─────────────────────────┘  (auto-publish after trust period)
```

Each step is a pure function. Failures at any step write a partial run to `agent_runs` with a `failed_at_step` field — no half-baked newsletters get published.

---

## 4. Signal Board (deterministic Python)

All signals normalized to a common shape:

```python
@dataclass
class Signal:
    id: str                      # stable identifier for dedup
    domain: str                  # 'yield' | 'price' | 'acreage' | 'weather' | ...
    scope: str                   # 'national' | 'state:IA' | 'county:19153' | ...
    headline: str                # 1-line factual summary
    score: float                 # 0-100 newsworthiness (pre-mood)
    mood_boost: float            # 0-30 bonus from mood match (§5)
    final_score: float           # score + mood_boost, used for ranking
    direction: str               # 'positive' | 'negative' | 'neutral'
    evidence: dict               # raw numbers — handed to LLM as ground truth
    sources: list[str]           # table names / S3 paths used
    valid_until: date            # when this signal becomes stale
```

### 4.1 Signal sources (v1)

| # | Source | Trigger | Scope |
|---|---|---|---|
| 1 | `yield_forecasts` week-over-week p50 delta > 5% | Weekly during Apr-Oct | County |
| 2 | `acreage_forecasts` model vs USDA prospective gap > 5% | After Mar/Jun reports | State |
| 3 | `price_forecasts` regime distance > 3σ | Daily | National |
| 4 | `wasde_releases` stocks-to-use surprise > X bps | Monthly post-WASDE | National |
| 5 | `drought_index` DSCI jump > 20 in major producer state | Weekly | State |
| 6 | NASS CCI week-over-week drop > 10 pts | Weekly Apr-Oct | State |
| 7 | `export_commitments` pace vs 5yr > ±15% | Weekly | National |
| 8 | `futures_daily` 5-day move > 2σ historical | Daily | National |
| 9 | NOAA precip anomaly > 30% from normal in major producer | Weekly | County rollup |
| 10 | Long-history trend break (acres/yield z > 2 vs 30yr) | Monthly | State |
| 11 | Forecast-vs-realized accuracy outlier (model big miss) | Weekly | County |
| 12 | Calendar proximity (next WASDE, Plantings report < 7d) | Weekly | National |

### 4.2 Scoring (pre-mood)

Each signal gets a 0-100 `score` combining:
- **Magnitude** (50%) — z-score or % deviation
- **Reach** (25%) — how big the affected region is (acres, $ value)
- **Novelty** (15%) — penalty if the signal's domain+scope pair fired in last 8 weeks
- **Calendar fit** (10%) — bonus if it ties to an upcoming USDA report

Calibrate weights once on 6 months of historical signals (manual labelling of "would this have been a story?").

### 4.3 Dedup memory

`agent_picks` table: every published lead/brief logs its `signal.domain` + `signal.scope` + week. Editor step (§6) gets the last **8 weeks' picks** as context and is instructed to avoid the same `(domain, scope)` pair unless the magnitude has *materially* increased (>1.5x prior publication).

---

## 5. Mood Synthesizer (LLM pre-step)

**Purpose:** let the agent form a weekly "lens" that biases signal selection toward the current narrative arc. Prevents the editor from myopically picking the single highest-scored signal when the broader context points elsewhere.

**Input (all numeric — already in our DB; no PDF ingest required):**
- Season calendar entry (planting / emergence / pollination / grain-fill / harvest / post-harvest / winter) — derived from `date.today()`
- **WASDE numeric deltas** for the last two releases, per major commodity: stocks-to-use change, ending-stocks change, world STU change, surprise vs prior-month forecast. All available in `wasde_releases` (already populated by `backend/etl/ingest_wasde.py`). The agent renders these into a short factual prose block ("Apr WASDE: corn STU −1.8 pp m/m, soy STU −0.4 pp m/m, world wheat STU +0.9 pp …") and passes that to the LLM as the WASDE input. Cheaper, more reliable, and avoids parsing the WASDE PDF.
- Futures 30-day recap: price moves, volatility, open-interest shifts (from `futures_daily`)
- Macro: DXY 30-day change (from `dxy_daily`); Fed-move flag deferred to v2 (no FOMC ingest yet)
- Drought regime snapshot (national DSCI percentile, computed from `drought_index`)
- Export commitment pace vs 5yr (from `export_commitments`)

**Output (strict JSON):**
```json
{
  "mood_tags": ["harvest-pressure", "export-uncertainty", "dry-finish"],
  "primary_narrative": "Late-season drought pinching final corn fill in western Belt while export pace softens on strong dollar",
  "biases": {
    "yield": 1.2,         // boost multiplier for yield-domain signals
    "drought": 1.4,
    "export": 1.15,
    "price": 1.0,
    "acreage": 0.85,
    "weather": 1.3
  },
  "avoid_unless_dramatic": ["acreage"]   // suppress boring domains this week
}
```

The deterministic `SignalBoard.mood_boost` then computes `mood_boost = clamp(score * (bias - 1.0), -30, 30)`, and final ranking is on `final_score = score + mood_boost`. Worked example: `score=80, bias=1.4` → `80 * 0.4 = 32` → clamped to `+30`. `score=40, bias=1.2` → `40 * 0.2 = 8` → no clamp. `score=80, bias=0.85` → `80 * -0.15 = -12` → no clamp. (v0.2 of this spec had a stray `* 30` factor which made the cap dominate every signal — fixed in v0.3.)

### 5.1 Why LLM here, not rules?

Rules can encode "it's harvest season, boost yield". But synthesizing "Black Sea tensions + DXY spike + late drought = export-uncertainty lens" requires integrating text + numbers + context. One Claude call, cached prompt prefix, ~$0.03/run.

### 5.2 Mood log

`agent_mood` table stores the weekly JSON — useful for auditing drift ("did the editor really over-weight drought for 6 weeks straight?") and for future feedback-loop tuning.

---

## 6. Editor Step (LLM, no tools)

**Input:** mood-rescored signal list + last 8 weeks' picks + mood JSON.
**Output:** strict JSON with `lead`, `briefs[]`, each containing `signal_id` and `editorial_angle` (the human-interest framing).

System prompt sketch:

> You are the editor of FieldPulse Weekly, an agricultural analytics newsletter. You have N candidate signals from this week's data scan, ranked by a model that already factored in this week's mood. You also have last 8 weeks' published topics — do not repeat the same (domain, scope) pair unless magnitude has materially shifted. Pick exactly 1 lead and 2-3 briefs. The lead should reward 400 words of analysis; briefs should be punchy and self-contained. Reply ONLY with JSON matching this schema: {...}

**Why a separate step:** keeps selection cheap (no tool calls), gives a clean handoff to research, and the JSON is auditable.

---

## 7. Researcher Step (LLM with tool-use)

**Input:** editor's JSON picks.
**Output:** research dossier — a dict per story containing every fact the writer is allowed to use.

### 7.1 Tools exposed

Every tool takes a mandatory `as_of_date: date` parameter so the same agent code can run live (today) or backfill (frozen historical Sundays — §11.11). Implementation contract: each tool's underlying query MUST filter `WHERE created_at <= :as_of_date` (forecast tables) or `WHERE date <= :as_of_date` (raw observation tables) before any aggregation. The agent runner injects `as_of_date = run_date` once at startup and the LLM does not control it (the parameter is omitted from the tool schema exposed to Claude — the runtime fills it via partial application).

```python
@tool
def query_sql(sql: str, *, as_of_date: date) -> list[dict]:
    """Read-only access to analytics views. SELECT only.
    Runtime rewrites the SQL to inject `AND <table>.created_at <= :as_of_date`
    on every FROM/JOIN clause via sqlglot AST traversal.
    Rejects INSERT/UPDATE/DELETE/DDL."""

@tool
def get_forecast(commodity: str, kind: Literal['yield','acreage','price'],
                 scope: str, horizon: int | None = None,
                 *, as_of_date: date) -> dict:
    """Wraps existing /api/v1/predict/* endpoints; appends &as_of=YYYY-MM-DD
    which the routers must honor (small router patch, §13 step 1)."""

@tool
def get_history(commodity: str, scope: str, metric: str,
                start_year: int, end_year: int,
                *, as_of_date: date) -> list[dict]:
    """NASS long-history pull from S3 parquets. Filtered to year <= as_of_date.year
    and (year == as_of_date.year => row publish_date <= as_of_date)."""

@tool
def get_weather(fips: str, start: date, end: date,
                *, as_of_date: date) -> dict:
    """NOAA county precip + temp + drought for a county-date range,
    clamped to end <= as_of_date."""

@tool
def compare_peers(scope: str, metric: str, n: int = 5,
                  *, as_of_date: date) -> list[dict]:
    """Top/bottom N peers for a state or county on a given metric,
    using only data available at as_of_date."""
```

All tools are **read-only**. SQL is restricted via a separate Postgres role (`agent_reader`) with `SELECT` grants only on a curated allowlist of analytics views (raw forecast tables exposed via views that already embed the `as_of_date` filter as a parameterized predicate).

### 7.2 Loop

Standard tool-use loop with **two budgets**:

- **Per-story cap:** 8 tool calls each. On cap hit the agent must finalize that story.
- **Per-run global cap:** 30 tool calls across all stories (1 lead + up to 3 briefs). Hard ceiling to keep cost predictable.

The 30-call ceiling is the figure used in the §12 cost table. Each tool call's full request + response is logged to the dossier so the fact-checker can verify claims; the dossier doubles as the audit trail in `agent_runs`.

### 7.3 Dossier schema

```python
{
  "lead": {
    "signal": Signal,
    "facts": [{"claim": "Iowa corn yield p50 dropped 6.3% w/w", "source_call": "tool_call_3"}],
    "tool_calls": [...],   # full request/response log
    "chart_specs": [...],  # JSON specs for matplotlib renderer
  },
  "briefs": [...]
}
```

---

## 8. Writer + Fact-Check

### 8.1 Writer

Claude gets the dossier and a strict instruction: **every numeric claim must come from `dossier.facts` or `dossier.tool_calls`**. The writer outputs markdown with `{{chart_1}}` placeholders for charts.

System prompt enforces:
- 400-600 words for lead, 100-150 for each brief
- No em dashes (project convention — see memory)
- Numbers always cite source ("USDA WASDE April release")
- One clear "what to watch" forward-looking line per story

### 8.2 Fact-check

Two passes:

1. **Number extraction (deterministic).** A unit-aware tokenizer (not a one-shot regex) pulls every numeric claim from the markdown:
   - Tokens recognized: `$N`, `N%`, `N pp` (percentage points), `N bu/ac`, `N cwt/ac`, `N lb/ac`, `Nx` / `N×`, `±N`, `N million|M|billion|B|thousand|K`, ISO years (e.g. `2026`, `2026/27`), and bare decimals adjacent to commodity unit nouns ("acres", "bushels", "tons", "head").
   - Each token is normalized to `(value, unit)` in canonical SI/USDA units (e.g. all area → acres, all yield → bu/ac for grains, all weight → lb).
   - Each normalized claim is matched against the dossier's pre-extracted fact set (also normalized) with **±2% relative tolerance for absolute values** and **±0.5 pp absolute tolerance for percentage-point claims**.
   - Year tokens (`2026`, `Q3`, `MY 2026/27`) are matched as exact strings.
   - **Whitelisted bypass:** numbers inside fenced code blocks, inline `code` spans, or following the literal phrase "approximately" / "roughly" / "about" use a wider ±5% tolerance.
   - Unmatched numbers fail the run; the failure payload includes the offending sentence + nearest dossier values for fast triage.
2. **LLM critique.** Claude Haiku 4.5 reviews the draft against the dossier and flags any claim that's directionally off, unsupported, or invents context (e.g. unstated causation). Output is `{passed: bool, issues: [{quote: str, dossier_ref: str | null, severity: 'minor'|'major'}]}`. Major issues fail the run; minor issues land in the Slack ping but do not block.

The deterministic pass is the primary gate (it catches hallucinated digits hard); the LLM critique catches wording-level drift the regex can't see. Both must pass for auto-publish; only the deterministic pass is required for draft staging during the trust period.

If either gate fails, the run logs the failure and sends a Slack + email notification (§9.2). The draft stays in `newsletters/draft/` for manual review; it does not publish.

---

## 9. Publisher

### 9.1 Normal path

- Render chart specs → PNG via matplotlib (project palette from `web_app/src/utils/design.ts`)
- Stage markdown + PNGs to S3 `newsletters/draft/YYYY-MM-DD.md`
- Insert row into `agent_runs` with status, dossier hash, token usage, cost
- Insert N rows into `agent_picks` (1 per story) for dedup memory
- Insert mood JSON into `agent_mood`
- **During trust period (first 4-8 weeks):** Slack ping to `#fieldpulse-weekly` with draft link; awaits 1-click approval button on `/insights/draft/[slug]` page before promoting to `newsletters/YYYY/MM/` and revalidating `/insights`
- **After trust period:** auto-promote to published path, still Slack-ping as an "FYI published" notification

**Trust-period exit trigger (v0.3 lock):** auto-publish flips on when the **last 6 consecutive runs all reached `status='approved'` with no `failed_at_step`** (regardless of wall-clock weeks). Implemented as a single Postgres query at the start of the publisher step; result drives the `auto_publish` boolean for the run. Operator override: a `agent_settings.force_manual = true` row pins draft mode regardless of streak (kill-switch for re-introducing a human after a known regression).

**Promote logic location:** lives in the publisher (`backend/agent/publisher.py`) and is invoked in two ways:
1. **Auto path:** publisher runs in the same Python process as the agent, immediately after fact-check passes, conditional on `auto_publish=True`.
2. **Manual path (trust period):** the Approve button POSTs to a thin Next.js API route `web_app/src/app/api/insights/approve/route.ts` which (a) verifies the signed cookie (§9.3), (b) calls a new FastAPI endpoint `POST /api/v1/agent/promote/{run_id}` on the EC2 backend, which (c) imports and runs the same `publisher.promote(run_id)` function. Single source of truth, no duplicated logic.

`promote(run_id)` is idempotent: copies `newsletters/draft/<slug>.md` + chart PNGs to `newsletters/YYYY/MM/<slug>.md`, updates `agent_runs.status='published'` and `approved_at=now()`, and triggers a Next.js `revalidatePath('/insights')` via the standard Next ISR webhook.

### 9.2 Failure path

On fact-check fail or any step exception:
- Write `agent_runs` row with `status='failed'`, `failed_at_step`, and issues list
- Slack message to `#fieldpulse-weekly` with the failure summary + draft link + issues list
- Email to `rajashekarreddy091@gmail.com` with the same payload
- Draft remains at `newsletters/draft/` — you can fix, approve-anyway, or delete

Slack integration reuses the **Knowledge Curator** pipeline pattern: `slack_sdk.WebClient` with a bot token (`SLACK_BOT_TOKEN`) and target channel ID (`SLACK_CHANNEL_FIELDPULSE`) sourced from `.env`. This runs server-side from the EC2 cron — no MCP, no Claude Desktop dependency. A small helper (`backend/agent/notify.py`) wraps `chat_postMessage` for both success/draft-ready and failure payloads.

### 9.3 Frontend routes

- `web_app/src/app/insights/page.tsx` — list view with title + date + lead-paragraph snippet
- `web_app/src/app/insights/[slug]/page.tsx` — markdown reader with embedded charts
- `web_app/src/app/insights/draft/[slug]/page.tsx` — same reader + Approve / Reject buttons

**Auth on `/insights/draft` (v0.3 lock):** a signed HTTP-only cookie (`fp_draft_auth`), HMAC-SHA256 over `(slug + run_id + expiry_ts)` using a server-only secret (`FIELDPULSE_DRAFT_SECRET` in `.env`), set when the operator clicks the magic link in the Slack ping. Slack message contains `https://<host>/insights/draft/<slug>?t=<one-shot-token>`; the page exchanges the one-shot token for the cookie on first load (server action), then deletes the token row. No secrets in URLs after first hit; cookie expires in 7 days; logging out clears the cookie. Reject button POSTs to the same Next.js API route as Approve and sets `agent_runs.status='rejected'`. Proper user-account auth deferred to v2 once the dashboard has a user model.

Markdown rendering via `react-markdown` + `remark-gfm`. Chart placeholders (`{{chart_1}}`, etc.) are resolved server-side at render time by a small remark plugin that swaps each placeholder for an `![](chart_url)` image node referencing the staged PNG in S3 (or `/insights/charts/<slug>/<chart_id>.png` after promote).

---

## 10. Database Schema

```sql
CREATE TABLE agent_runs (
    id              BIGSERIAL PRIMARY KEY,
    run_date        DATE          NOT NULL UNIQUE,
    status          VARCHAR(20)   NOT NULL,    -- 'success' | 'draft' | 'failed' | 'published'
    failed_at_step  VARCHAR(30),
    newsletter_path TEXT,                       -- S3 key
    n_signals_scanned INTEGER,
    n_tool_calls    INTEGER,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cost_usd        NUMERIC(8,4),
    duration_sec    INTEGER,
    dossier_hash    VARCHAR(64),
    approved_by     VARCHAR(50),                -- null until approved
    approved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE agent_picks (
    id              BIGSERIAL PRIMARY KEY,
    run_id          BIGINT REFERENCES agent_runs(id) ON DELETE CASCADE,
    role            VARCHAR(10) NOT NULL,       -- 'lead' | 'brief'
    signal_id       VARCHAR(100) NOT NULL,
    signal_domain   VARCHAR(20) NOT NULL,
    signal_scope    VARCHAR(50) NOT NULL,
    score           NUMERIC(5,2),
    mood_boost      NUMERIC(5,2),
    headline        TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_agent_picks_domain_scope ON agent_picks(signal_domain, signal_scope, created_at DESC);

CREATE TABLE agent_mood (
    id              BIGSERIAL PRIMARY KEY,
    run_id          BIGINT REFERENCES agent_runs(id) ON DELETE CASCADE,
    mood_tags       JSONB NOT NULL,
    primary_narrative TEXT,
    biases          JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 11. Resolved Decisions (v1)

Locked from design walkthrough 2026-04-24:

| # | Decision | Choice |
|---|---|---|
| 1 | Audience | Internal v1, public v2 (subscribers + compliance in phase 2) |
| 2 | Channel | Frontend `/insights` route only |
| 3 | Publish mode | Draft-then-approve for 4-8 weeks, then auto |
| 4 | Scope per issue | Let signal score + mood decide, not rotation |
| 5 | Mood source | LLM synthesizes from data + WASDE narrative (no external news API in v1) |
| 6 | LLM provider | Claude Sonnet 4.6 via API (Haiku for fact-check critique only) |
| 7 | Charts | Server-rendered PNG via matplotlib |
| 8 | Dedup | 8-week window, `(domain, scope)` match |
| 9 | Failure mode | Slack `#fieldpulse-weekly` + email to rajashekarreddy091@gmail.com; draft stays for manual review |
| 10 | Name | FieldPulse Weekly |
| 11 | Backfill | 12 weeks of historical issues to seed `/insights` archive |

---

## 12. LLM Cost

Claude Sonnet 4.6 ($3/$15 per M tokens) with prompt caching, Haiku 4.5 for fact-check critique. Researcher loop budget is the §7.2 global cap of 30 tool calls per run. Each loop turn carries the accumulated tool-result history forward, so per-call input grows roughly linearly across the loop — the figures below average that growth.

| Step | Model | Calls/run | Avg input | Avg output | With caching | Cost/run |
|---|---|---|---|---|---|---|
| Mood Synthesizer | Sonnet 4.6 | 1 | 5K | 0.5K | yes | $0.04 |
| Editor | Sonnet 4.6 | 1 | 8K | 1K | yes | $0.04 |
| Researcher | Sonnet 4.6 | up to 30 (loop) | 6K avg (grows from 4K → 14K) | 0.8K each | yes | $0.55 |
| Writer | Sonnet 4.6 | 1 | 8K | 2K | partial | $0.07 |
| Fact-check critique | Haiku 4.5 | 1 | 8K | 0.5K | yes | $0.01 |
| **Total** | | **~34** | | | | **~$0.71** |

- **Annual steady-state:** ~$37 at 52 runs/year
- **12-week backfill** one-time: ~$9
- **Grand total year 1:** **~$45–55**, padding for prompt-template iteration during the first month

Cost is still negligible relative to the rest of the stack (RDS $15/mo, EC2 $6/mo). The primary risk is unbounded researcher loops — the 30-call global cap (§7.2) is the cost ceiling that matters.

---

## 13. Implementation Order

Suggested 8-step build, ~2.5 weeks of focused work:

1. **Schema + as-of-date plumbing.** Alembic migration for the 3 agent tables. Patch the 3 prediction routers (`price`, `acreage`, `yield_forecast`) to accept an optional `as_of` query param and forward it to the model-loading + DB-read paths. Create the `agent_reader` Postgres role + curated read-only views. ~1.5 days.
2. **Signal board + weight calibration.** Implement the 12 signal sources from §4.1 as pure Python. **Weight calibration:** label ~6 months of historical signals (manually mark which ones "would have been a story") and fit the §4.2 weights via simple grid search or logistic regression over the labels. Calibration is a real ~1-day task in itself, separate from coding. ~2.5 days total (1.5 implement + 1 label/calibrate).
3. **Mood synthesizer + editor.** WASDE-numeric-delta input renderer (§5), Claude call with cached prefix, mood JSON validation. Editor JSON-only step. ~1.5 days.
4. **Researcher loop.** 5 tools with `as_of_date` partial application, sqlglot-based SQL injection guard, 8-per-story / 30-per-run caps. Mock writer (dump dossier as markdown) for smoke test. ~2 days.
5. **Writer + fact-checker.** Unit-aware tokenizer with the §8.2 token grammar + tolerance rules + Haiku critique. Full pipeline producing publishable markdown. ~1.5 days.
6. **Publisher + chart renderer + Slack/email hooks.** Matplotlib chart spec → PNG, S3 upload, DB writes, `slack_sdk` notify helper, SES (or SMTP) email. Includes the `promote()` function and `POST /api/v1/agent/promote/{run_id}` endpoint. ~1.5 days.
7. **Frontend `/insights` + `/insights/draft` routes.** Index, markdown reader with chart-placeholder remark plugin, approval UI with signed-cookie + one-shot-token magic-link flow. ~2 days.
8. **Cron + monitoring + 12-week backfill.** Sunday schedule, SNS alert on total failure, cost tracking. Replay agent over 12 historical Sundays with frozen `as_of_date`. ~1 day + ~$9 LLM spend.

Total: ~13-14 working days for v1.

---

## 14. v2 Roadmap (carved out)

Parked for a phase-2 effort once v1 proves the concept:

- **Public subscribers + email.** Resend or Postmark, subscribe form on the landing page, unsubscribe compliance, "not investment advice" footer.
- **LinkedIn auto-draft.** Reuse the `linkedin-milestone-post` skill pattern to produce a LinkedIn-ready version per issue.
- **RSS feed.** Static XML at `/insights/feed.xml`.
- **Reader feedback loop.** Thumbs up/down per issue → feeds back into signal scoring weights + mood bias calibration.
- **News-API mood source.** Pull headlines (NewsAPI / Google News RSS), categorize into themes, add as a third mood input alongside WASDE + futures.
- **Themed editions.** "Drought watch" deep-dive week, "Harvest preview" week — manual override of mood + editor step.
- **Voice variants.** 60-second audio version via TTS for podcast-style distribution.
- **Personalization.** Per-subscriber state preference — different lead story per user.
- **Auth on `/insights/draft`.** Move from signed-cookie + magic-link to proper user-account auth once a user model exists.

---

## 15. Changelog

### v0.3 — 2026-05-06 (feasibility-pass revisions)

Applied after a focused review of v0.2 against the current codebase. All changes are spec-only; no code shipped yet.

- **§2, §9.** Slack delivery rewritten: replaced "existing Slack MCP" (which was a chat-time Claude tool, not callable from a server-side Python cron) with the **Knowledge Curator pipeline** — `slack_sdk.WebClient` + bot token, server-side, no MCP. Added `slack_sdk` to the package list and `backend/agent/notify.py` as the wrapper.
- **§5.** **Mood-boost formula corrected:** `score * (bias - 1.0) * 30 capped ±30` → `clamp(score * (bias - 1.0), -30, 30)`. The v0.2 formula made the cap dominate every signal regardless of `score`. Added a worked example.
- **§5.** **Mood input swapped from WASDE narrative PDFs to WASDE numeric deltas** already in `wasde_releases` (populated by `backend/etl/ingest_wasde.py`). PDFs would have required a new ingest pipeline; numeric deltas are zero-marginal-cost and carry the same signal for "what changed this month." Fed-move flag deferred to v2.
- **§7.1.** **Every researcher tool now takes a mandatory `as_of_date`** filled by the runtime via partial application (LLM does not control it). SQL tool gains a sqlglot-based AST rewrite that injects `created_at <= :as_of_date` on every FROM/JOIN. Required for the §11.11 backfill to actually work without leakage. Listed the small router patch needed in §13 step 1.
- **§7.2 ↔ §12.** **Reconciled tool-call budgets:** 8 calls per story, 30 calls per run global ceiling. Cost table now uses 30 not 12.
- **§8.2.** **Fact-check tokenizer specified** beyond "regex pulls every numeric token" — token grammar (`$N`, `N%`, `N pp`, `N bu/ac`, etc.), unit normalization, ±2% relative / ±0.5 pp absolute tolerance, "approximately"-style soft-match bypass. Two-pass gate (deterministic + Haiku critique) with severity levels.
- **§9.1.** **Auto-promote trigger defined:** 6 consecutive `approved` runs with no `failed_at_step`, with an `agent_settings.force_manual` kill-switch. Promote logic location pinned to `backend/agent/publisher.py::promote(run_id)` with a Next.js → FastAPI bridge for the manual-approve path.
- **§9.3.** **Approval auth tightened:** signed HTTP-only cookie (`fp_draft_auth`, HMAC-SHA256) + one-shot magic-link token in the Slack ping. No secrets in URLs after first hit. Replaces the v0.2 shared-secret query param.
- **§9.3.** **Chart placeholder resolution specified:** small remark plugin swaps `{{chart_id}}` for `![](url)` image nodes at render time, pointing to staged S3 PNGs (draft) or `/insights/charts/<slug>/<id>.png` (published).
- **§12.** **Cost table updated** for the 30-call researcher cap, growing per-call input across the loop, and Sonnet 4.6 pricing. New estimate ~$0.71/run (was $0.31), ~$45-55/year (was ~$20). Still negligible.
- **§13.** **Implementation order expanded** from 7 steps / 8-9 days to 8 steps / 13-14 days. Added explicit time for the as-of-date router patch (step 1) and the §4.2 weight-calibration labelling effort (step 2). Backfill LLM spend updated to ~$9.
