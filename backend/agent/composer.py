"""Composer: assembles a typed IssueSpec from the fact-checked draft.

Two halves, by design:
  1. Deterministic prose conversion — a Python port of the markdown parsing
     in web_app/src/components/insights/IssueRenderer.tsx. Prose text is
     carried into the spec byte-identical, so the fact-check verdict on the
     markdown still covers every sentence the reader sees.
  2. One LLM call ("visual designer") that only emits rich blocks — kpis,
     stat callouts, figures with chart data — anchored into the prose
     skeleton. It never writes prose. Its numbers are re-verified against
     the dossier by a deterministic guard; ungroundable blocks are dropped.

A composer failure of any kind must degrade to spec=None (the publisher
falls back to today's markdown + PNG path).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import ValidationError

from backend.agent.factcheck import (
    dossier_tokens,
    extract_tokens,
    has_match,
    is_derivable,
    magnitude_pool,
)
from backend.agent.issue_spec import (
    FigureBlock,
    IssueSpec,
    KpisBlock,
    StatBlock,
)
from backend.agent.llm import CallStats, call_json, load_prompt
from backend.agent.researcher import FullDossier
from backend.agent.signals._fips_label import STATE_FIPS_TO_ABBREV
from backend.agent.writer import WrittenDraft, _scrub_em_dashes

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deterministic markdown -> prose blocks.
# Port of IssueRenderer.tsx parseMarkdown/annotateSections — keep the two in
# sync (the TSX file carries the matching cross-reference comment).
# ---------------------------------------------------------------------------


HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$")
IMAGE_RE = re.compile(r"^!\[(.*?)\]\((.+?)\)\s*$")
ITALIC_DEK_RE = re.compile(r"^\*(.+)\*\s*$")
CHART_PLACEHOLDER_RE = re.compile(r"^\{\{(chart_\w+)\}\}\s*$")
LEAD_PREFIX_RE = re.compile(r"^Lead\s*:\s*", re.IGNORECASE)

_WATCH_PREFIX_RE = re.compile(
    r"^(watch\b|the reconciliation|the next signal|the signal that matters|if (planted|the))",
    re.IGNORECASE,
)
_WATCH_VERB_RE = re.compile(r"\b(watch|track|monitor)\b", re.IGNORECASE)
_WATCH_REPORT_RE = re.compile(
    r"\b(usda|wasde|nass|fas|crop progress|prospective|acreage|export sales|cattle on feed)\b",
    re.IGNORECASE,
)


def _looks_like_watch(text: str) -> bool:
    if _WATCH_PREFIX_RE.search(text):
        return True
    return bool(_WATCH_VERB_RE.search(text) and _WATCH_REPORT_RE.search(text))


def _split_trailing_watch_sentence(text: str) -> tuple[str, str] | None:
    """Split a trailing "what to watch" sentence off a paragraph.

    Returns (body, watch) or None. Body must keep >= 80 chars of substance,
    the watch tail needs >= 30 chars, and only the LAST sentence boundary is
    considered (no mid-paragraph splits).
    """
    min_body = 80
    boundaries: list[int] = []
    for i in range(1, len(text) - 1):
        if text[i] != ".":
            continue
        if text[i + 1] not in (" ", "\n"):
            continue
        nxt = text[i + 2] if i + 2 < len(text) else ""
        if nxt and "a" <= nxt <= "z":  # abbreviation mid-sentence ("U.S. corn")
            continue
        boundaries.append(i)
    for idx in reversed(boundaries):
        body = text[: idx + 1].strip()
        tail = text[idx + 2 :].strip()
        if len(body) < min_body:
            break
        if len(tail) < 30:
            continue
        if _looks_like_watch(tail):
            return body, tail
        break  # only the last real sentence may become a callout
    return None


def parse_markdown_blocks(markdown: str) -> list[dict[str, Any]]:
    """Parse FieldPulse markdown into IssueSpec prose blocks.

    Output kinds: title / dek / section / brief / p / watch / hr, plus the
    internal {"kind": "chart_anchor", "id": "chart_N"} marker (consumed by
    compose_issue, never emitted into a spec).
    """
    lines = markdown.replace("\r\n", "\n").split("\n")
    blocks: list[dict[str, Any]] = []
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        if not buf:
            return
        text = " ".join(buf).strip()
        buf = []
        if not text:
            return
        m = ITALIC_DEK_RE.match(text)
        if m:
            blocks.append({"kind": "dek", "text": m.group(1)})
            return
        split = _split_trailing_watch_sentence(text)
        if split:
            # The watch flag itself is decided in _annotate_sections (the
            # split tail is its section's last paragraph and matches the
            # watch heuristic, so it comes back as a watch block).
            blocks.append({"kind": "p", "text": split[0]})
            blocks.append({"kind": "p", "text": split[1]})
        else:
            blocks.append({"kind": "p", "text": text})

    for raw in lines:
        line = raw.strip()
        if not line:
            flush()
            continue
        if line == "---":
            flush()
            blocks.append({"kind": "hr"})
            continue
        chart = CHART_PLACEHOLDER_RE.match(line)
        if chart:
            flush()
            blocks.append({"kind": "chart_anchor", "id": chart.group(1)})
            continue
        img = IMAGE_RE.match(line)
        if img:
            # Pre-publish markdown should not contain resolved images; the
            # spec path drops them (the PNG fallback keeps rendering them).
            flush()
            logger.warning("composer: dropping resolved image line: %s", line[:80])
            continue
        heading = HEADING_RE.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            text = heading.group(2)
            if level == 1:
                blocks.append({"kind": "title", "text": text})
            elif level == 2:
                is_lead = bool(LEAD_PREFIX_RE.match(text))
                if is_lead:
                    text = LEAD_PREFIX_RE.sub("", text).strip()
                blk: dict[str, Any] = {"kind": "section", "text": text}
                if is_lead:
                    blk["lead"] = True
                blocks.append(blk)
            else:
                blocks.append({"kind": "brief", "text": text})
            continue
        buf.append(line)
    flush()

    return _annotate_sections(blocks)


def _annotate_sections(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tag the first paragraph per section, and turn each section's last
    watch-flavored paragraph into a watch block (mirrors annotateSections).
    """
    first_set: set[int] = set()
    last_set: set[int] = set()
    cur_first: int | None = None
    cur_last: int | None = None

    def flush_section() -> None:
        nonlocal cur_first, cur_last
        if cur_first is not None:
            first_set.add(cur_first)
        if cur_last is not None and cur_last != cur_first:
            last_set.add(cur_last)
        cur_first = None
        cur_last = None

    for i, b in enumerate(blocks):
        if b["kind"] in ("section", "brief", "hr"):
            flush_section()
            continue
        if b["kind"] == "p":
            if cur_first is None:
                cur_first = i
            cur_last = i
    flush_section()

    out: list[dict[str, Any]] = []
    for i, b in enumerate(blocks):
        if b["kind"] != "p":
            out.append(b)
            continue
        is_watch = i in last_set and _looks_like_watch(b["text"])
        if is_watch:
            out.append({"kind": "watch", "text": b["text"]})
        else:
            blk = {"kind": "p", "text": b["text"]}
            if i in first_set:
                blk["first"] = True
            out.append(blk)
    return out


# ---------------------------------------------------------------------------
# Numeric guard: rich-block numbers must be grounded in the dossier.
# ---------------------------------------------------------------------------


_NUMBER_RE = re.compile(r"\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?")
# Researcher chart values may be expressed at a different unit scale than the
# raw tool output (5.16 "M acres" vs 5160000). Accept any power-of-1000 match.
_SCALES = (1.0, 1e3, 1e6, 1e9, 1e-3, 1e-6, 1e-9)

# Pairwise derivation checks are O(n^2); cap the operand pool so a verbose
# tool log can't blow up guard time.
_MAX_DERIVATION_POOL = 600


def _raw_number_pool(dossier: FullDossier) -> list[float]:
    """Every number in the dossier text + tool outputs, commas stripped.

    Wider than the factcheck token pool on purpose: bare integers (row
    counts, raw acres) don't tokenize there but are legitimate chart values.
    """
    blobs: list[str] = []
    for story in dossier.all():
        blobs.extend([story.headline, story.editorial_angle, story.what_to_watch])
        blobs.extend(story.claims)
        blobs.extend(story.peer_context)
        for entry in story.tool_log:
            try:
                blobs.append(json.dumps(entry.get("output"), default=str))
            except Exception:  # noqa: BLE001
                pass
        try:
            blobs.append(json.dumps(story.chart_specs, default=str))
        except Exception:  # noqa: BLE001
            pass
    pool: set[float] = set()
    for blob in blobs:
        if not isinstance(blob, str):
            continue
        for m in _NUMBER_RE.finditer(blob):
            try:
                pool.add(float(m.group(0).replace(",", "")))
            except ValueError:
                continue
    return [v for v in pool if v != 0]


def _value_grounded(value: float, pool: list[float], tol: float = 0.02) -> bool:
    if value == 0:
        return True
    av = abs(value)
    for s in _SCALES:
        target = av * s
        for p in pool:
            if abs(abs(p) - target) <= target * tol:
                return True
    return False


@dataclass
class _GuardCtx:
    tokens: list[dict[str, Any]]
    magnitudes: list[float]
    pool: list[float]


def _string_grounded(text: str, g: _GuardCtx) -> bool:
    """Every numeric token in a string must be groundable in the dossier."""
    for tok in extract_tokens(text):
        if tok["unit"] == "year":
            continue
        if has_match(tok, g.tokens):
            continue
        if is_derivable(tok, g.magnitudes):
            continue
        if _value_grounded(float(tok["value"]), g.pool):
            continue
        return False
    return True


def _chart_values(chart: dict[str, Any]) -> list[float]:
    """Numeric claims inside a chart spec (years/styling fields exempt)."""
    vals: list[float] = []
    t = chart.get("type")
    if t == "bars":
        vals.extend(float(d["value"]) for d in chart.get("data", []))
    elif t == "trend_forecast":
        vals.extend(float(p["value"]) for p in chart.get("actuals", []))
        fc = chart.get("forecast", {})
        vals.extend(float(fc[k]) for k in ("p50", "p10", "p90") if k in fc)
        if chart.get("refValue") is not None:
            vals.append(float(chart["refValue"]))
    elif t == "region_map":
        for st in chart.get("states", []):
            for k in ("forecast", "baseline"):
                if st.get(k) is not None:
                    vals.append(float(st[k]))
    return vals


def _block_strings(block: dict[str, Any]) -> list[str]:
    """Caption-style strings in a rich block that can carry numeric claims."""
    out: list[str] = []
    kind = block.get("kind")
    if kind == "kpis":
        for item in block.get("items", []):
            out.extend(filter(None, [item.get("value"), item.get("caption"), item.get("label")]))
    elif kind == "stat":
        out.extend(filter(None, [block.get("value"), block.get("label"), block.get("detail")]))
    elif kind == "figure":
        out.extend(filter(None, [block.get("title"), block.get("subtitle"), block.get("caption")]))
        for chart in block.get("charts", []):
            out.extend(filter(None, [chart.get("caption"), chart.get("refLabel")]))
    return out


def _guard_rich_blocks(
    blocks: list[dict[str, Any]], dossier: FullDossier
) -> tuple[list[dict[str, Any]], list[str]]:
    """Drop rich blocks (or KPI items) whose numbers can't be grounded."""
    tokens = dossier_tokens(dossier)
    pool = _raw_number_pool(dossier)
    # Derivations (gaps, %-changes) need the raw pool too: bare integers like
    # "6,236,516" don't tokenize in factcheck but are legitimate operands.
    magnitudes = list(dict.fromkeys(magnitude_pool(tokens) + pool))[:_MAX_DERIVATION_POOL]
    g = _GuardCtx(tokens=tokens, magnitudes=magnitudes, pool=pool)
    kept: list[dict[str, Any]] = []
    dropped: list[str] = []

    for block in blocks:
        kind = block.get("kind")
        if kind == "kpis":
            ok_items = []
            for item in block.get("items", []):
                strings = [s for s in (item.get("value"), item.get("caption"), item.get("label")) if s]
                if all(_string_grounded(s, g) for s in strings):
                    ok_items.append(item)
                else:
                    dropped.append(f"kpi item '{item.get('label', '?')}': ungrounded number")
            if len(ok_items) >= 2:
                kept.append({**block, "items": ok_items})
            elif block.get("items"):
                dropped.append("kpis strip: fewer than 2 grounded items remain")
            continue

        bad = [s for s in _block_strings(block) if not _string_grounded(s, g)]
        if not bad and kind == "figure":
            for chart in block.get("charts", []):
                ungrounded = [v for v in _chart_values(chart) if not _value_grounded(v, g.pool)]
                if ungrounded:
                    bad.append(f"chart values {ungrounded[:3]}")
                    break
        if bad:
            label = block.get("title") or block.get("label") or kind
            dropped.append(f"{kind} '{label}': ungrounded ({str(bad[0])[:80]})")
        else:
            kept.append(block)
    return kept, dropped


# ---------------------------------------------------------------------------
# LLM design call + assembly.
# ---------------------------------------------------------------------------


_DESIGN_SCHEMA_HINT = """{
  "kpis": {"after_block": <int>, "title": "THE WEEK AT A GLANCE",
           "items": [{"value": "24.3M", "unit": "MT", "label": "...",
                      "caption": "...", "tone": "positive|negative|harvest|default"}]} | null,
  "stats": [{"after_block": <int>, "value": "+9.4%", "label": "...", "detail": "..."}],
  "figures": [{"chart_id": "chart_1", "after_block": <int, only if no placeholder exists>,
               "title": "...", "subtitle": "...", "source": "...",
               "charts": [<ChartSpec: see system prompt>]}]
}"""


@dataclass
class ComposedIssue:
    """Validated, json-ready IssueSpec plus a log of guard/validation drops."""

    spec: dict[str, Any]
    dropped: list[str] = field(default_factory=list)


def compose_issue(
    draft: WrittenDraft,
    *,
    dossier: FullDossier,
    as_of_date: date,
    stats: CallStats | None = None,
) -> ComposedIssue | None:
    parsed = parse_markdown_blocks(draft.markdown)

    # Strip chart anchors out of the prose list, remembering where they stood.
    prose: list[dict[str, Any]] = []
    anchor_pos: dict[str, int] = {}
    for b in parsed:
        if b["kind"] == "chart_anchor":
            anchor_pos.setdefault(b["id"], len(prose))
        else:
            prose.append(b)
    if not prose:
        logger.warning("composer: no prose blocks parsed; skipping")
        return None

    design = _call_designer(prose, draft.chart_specs, dossier, stats=stats)
    if design is None:
        return None

    rich, invalid_drops = _validate_rich_blocks(design)
    rich, guard_drops = _guard_rich_blocks(rich, dossier)
    dropped = invalid_drops + guard_drops
    for d in dropped:
        logger.info("composer: dropped rich block — %s", d)

    has_figures = any(b["kind"] == "figure" for b in rich)
    if not has_figures and draft.chart_specs:
        # The markdown + PNG path will show the charts; a chartless spec would
        # silently lose them. Prefer the fallback.
        logger.info(
            "composer: no figures survived but draft has %d chart spec(s); "
            "falling back to markdown publish", len(draft.chart_specs),
        )
        return None

    blocks = _splice(prose, rich, anchor_pos)
    spec_payload = {
        "blocks": blocks,
        "meta": {"run_date": as_of_date.isoformat()},
    }
    spec_payload = _scrub_spec_strings(spec_payload)
    try:
        model = IssueSpec.model_validate(spec_payload)
    except ValidationError as exc:
        logger.warning("composer: final IssueSpec validation failed: %s", exc)
        return None
    return ComposedIssue(spec=model.model_dump(exclude_none=True), dropped=dropped)


def _call_designer(
    prose: list[dict[str, Any]],
    chart_specs: list[dict[str, Any]],
    dossier: FullDossier,
    *,
    stats: CallStats | None,
) -> dict[str, Any] | None:
    from backend.agent.factcheck import _dossier_summary

    skeleton = "\n".join(
        f"[{i}] ({b['kind']}) {b.get('text', '---')}" for i, b in enumerate(prose)
    )
    user = (
        f"PROSE_BLOCKS (numbered, final, read-only):\n{skeleton}\n\n"
        f"CHART_SPECS (researcher data, copy values unchanged):\n"
        f"{json.dumps(chart_specs, default=str, indent=1)}\n\n"
        f"DOSSIER:\n{_dossier_summary(dossier)}\n"
    )
    system = load_prompt("composer_system")

    last_err = ""
    for attempt in range(2):
        msg = user if not attempt else (
            user + f"\nYOUR PREVIOUS ATTEMPT FAILED VALIDATION:\n{last_err[:800]}\n"
            "Fix the structure and respond again with ONLY the JSON object."
        )
        try:
            raw = call_json(
                system=system,
                user=msg,
                # Generous cap: a 3-story issue with populated chart series
                # runs ~4-5k output tokens; truncation mid-JSON is unparseable
                # and a same-cap retry cannot fix it (seen on the first prod
                # run at 3000).
                max_tokens=8192,
                stats=stats,
                schema_hint=_DESIGN_SCHEMA_HINT,
            )
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            logger.warning("composer: design call failed (attempt %d): %s", attempt + 1, exc)
            continue
        if isinstance(raw, dict):
            return raw
        last_err = f"expected JSON object, got {type(raw).__name__}"
    return None


def _validate_rich_blocks(
    design: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate each rich block independently against the spec models.

    Returns json-ready block dicts (with internal placement keys preserved
    under "_after" / "_chart_id") and human-readable drop reasons.
    """
    kept: list[dict[str, Any]] = []
    dropped: list[str] = []

    kpis = design.get("kpis")
    if isinstance(kpis, dict):
        try:
            model = KpisBlock.model_validate({**_strip_internal(kpis), "kind": "kpis"})
            kept.append({**model.model_dump(exclude_none=True), "_after": kpis.get("after_block")})
        except ValidationError as exc:
            dropped.append(f"kpis: invalid ({_first_error(exc)})")

    for st in design.get("stats") or []:
        if not isinstance(st, dict):
            continue
        try:
            model = StatBlock.model_validate({**_strip_internal(st), "kind": "stat"})
            kept.append({**model.model_dump(exclude_none=True), "_after": st.get("after_block")})
        except ValidationError as exc:
            dropped.append(f"stat '{st.get('label', '?')}': invalid ({_first_error(exc)})")

    for fig in design.get("figures") or []:
        if not isinstance(fig, dict):
            continue
        payload = _strip_internal(fig)
        # Region maps may arrive without abbr/name; fill before validating.
        payload = _fill_region_identity(payload)
        try:
            model = FigureBlock.model_validate({**payload, "kind": "figure"})
            kept.append({
                **model.model_dump(exclude_none=True),
                "_after": fig.get("after_block"),
                "_chart_id": fig.get("chart_id"),
            })
        except ValidationError as exc:
            dropped.append(f"figure '{fig.get('title', '?')}': invalid ({_first_error(exc)})")
    return kept, dropped


def _strip_internal(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k not in ("after_block", "chart_id", "kind")}


def _first_error(exc: ValidationError) -> str:
    errs = exc.errors()
    if not errs:
        return "unknown"
    e = errs[0]
    return f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"


def _fill_region_identity(figure: dict[str, Any]) -> dict[str, Any]:
    """Fill abbr/name on region_map states from the FIPS lookup tables."""
    try:
        from backend.features.acreage_features import FIPS_TO_STATE
    except Exception:  # noqa: BLE001
        FIPS_TO_STATE = {}
    charts = figure.get("charts")
    if not isinstance(charts, list):
        return figure
    out_charts = []
    for chart in charts:
        if not isinstance(chart, dict) or chart.get("type") != "region_map":
            out_charts.append(chart)
            continue
        states = []
        for st in chart.get("states", []):
            if not isinstance(st, dict):
                continue
            fips = str(st.get("fips", "")).zfill(2)
            abbr = STATE_FIPS_TO_ABBREV.get(fips)
            if abbr is None:
                logger.info("composer: dropping unknown region_map fips %r", st.get("fips"))
                continue
            states.append({
                **st,
                "fips": fips,
                "abbr": st.get("abbr") or abbr,
                "name": st.get("name") or FIPS_TO_STATE.get(fips, abbr),
            })
        out_charts.append({**chart, "states": states})
    return {**figure, "charts": out_charts}


def _splice(
    prose: list[dict[str, Any]],
    rich: list[dict[str, Any]],
    anchor_pos: dict[str, int],
) -> list[dict[str, Any]]:
    """Insert rich blocks into the prose skeleton.

    Insert positions are indices into `prose`: a figure goes where its
    {{chart_N}} anchor stood; kpis go right after the dek; stats go after
    their `after_block`. Inserts are applied in descending position order so
    earlier indices stay valid.
    """
    n = len(prose)
    dek_idx = next((i for i, b in enumerate(prose) if b["kind"] == "dek"), None)
    title_idx = next((i for i, b in enumerate(prose) if b["kind"] == "title"), None)

    placements: list[tuple[int, int, dict[str, Any]]] = []
    for order, block in enumerate(rich):
        after = block.pop("_after", None)
        chart_id = block.pop("_chart_id", None)
        kind = block["kind"]
        if kind == "kpis":
            if dek_idx is not None:
                pos = dek_idx + 1
            elif title_idx is not None:
                pos = title_idx + 1
            else:
                pos = 0
        elif kind == "figure" and chart_id in anchor_pos:
            pos = anchor_pos[chart_id]
        elif isinstance(after, int):
            pos = min(max(after + 1, 0), n)
        else:
            pos = n  # unplaceable: append at the end
        placements.append((pos, order, block))

    out = list(prose)
    for pos, _, block in sorted(placements, key=lambda t: (t[0], t[1]), reverse=True):
        out.insert(pos, block)
    return out


def _scrub_spec_strings(obj: Any) -> Any:
    """Recursively scrub em dashes from every string in the spec payload."""
    if isinstance(obj, str):
        return _scrub_em_dashes(obj)
    if isinstance(obj, list):
        return [_scrub_spec_strings(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _scrub_spec_strings(v) for k, v in obj.items()}
    return obj
