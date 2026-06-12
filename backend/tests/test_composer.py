"""Tests for backend/agent/composer.py.

Parser fidelity is checked against a committed snapshot of a real dry-run
draft (fixtures/draft_fixture.md) so the Python port stays honest to the
TSX renderer it mirrors (web_app/src/components/insights/IssueRenderer.tsx).
The live artifact (backend/agent/data/last_draft.md) is gitignored and
mutates on every run, so it cannot be the fixture.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from backend.agent.composer import (
    ComposedIssue,
    _fill_region_identity,
    _guard_rich_blocks,
    _looks_like_watch,
    _splice,
    _split_trailing_watch_sentence,
    compose_issue,
    parse_markdown_blocks,
)
from backend.agent.issue_spec import IssueSpec
from backend.agent.researcher import FullDossier, StoryDossier
from backend.agent.writer import WrittenDraft

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "draft_fixture.md"


@pytest.fixture(scope="module")
def draft_md() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def parsed(draft_md: str) -> list[dict]:
    return parse_markdown_blocks(draft_md)


# ---------------------------------------------------------------------------
# Parser fidelity.
# ---------------------------------------------------------------------------


def test_one_title_dek_first(parsed):
    assert sum(1 for b in parsed if b["kind"] == "title") == 1
    # The fixture has a second italic line (the closing signature); the TSX
    # renderer also styles it as a dek, so the parser keeps both. The real
    # dek must sit before the first section.
    dek_idxs = [i for i, b in enumerate(parsed) if b["kind"] == "dek"]
    first_section = next(i for i, b in enumerate(parsed) if b["kind"] == "section")
    assert dek_idxs and dek_idxs[0] < first_section


def test_lead_section_flag(parsed):
    leads = [b for b in parsed if b["kind"] == "section" and b.get("lead")]
    assert len(leads) == 1
    assert not leads[0]["text"].lower().startswith("lead")


def test_chart_anchors_preserved(parsed):
    anchors = [b["id"] for b in parsed if b["kind"] == "chart_anchor"]
    assert anchors == ["chart_1"]


def test_watch_blocks_detected(parsed):
    watches = [b for b in parsed if b["kind"] == "watch"]
    assert watches, "expected at least one watch block in the fixture draft"
    # The lead's forward-looking closer (a standalone last paragraph).
    assert any(w["text"].startswith("Watch whether USDA revises") for w in watches)
    # A single-paragraph brief whose trailing watch sentence must be split off.
    assert any(
        w["text"].startswith("Watch whether updated June model vintages")
        for w in watches
    )


def test_prose_byte_fidelity(draft_md: str, parsed):
    """Every prose line of the source must appear verbatim in the block
    stream (paragraph lines are joined with single spaces, splits rejoin)."""
    combined = " ".join(b.get("text", "") for b in parsed)
    for raw in draft_md.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line or line == "---" or line.startswith("#"):
            continue
        if line.startswith("{{") or line.startswith("!["):
            continue
        if line.startswith("*") and line.endswith("*"):
            line = line[1:-1]  # dek loses its asterisks
        assert line in combined, f"prose line lost by parser: {line[:80]}"


def test_first_paragraph_tagging(parsed):
    section_idxs = [i for i, b in enumerate(parsed) if b["kind"] in ("section", "brief")]
    first_section = section_idxs[0]
    following_p = next(
        b for b in parsed[first_section + 1:] if b["kind"] in ("p", "watch")
    )
    assert following_p["kind"] == "p" and following_p.get("first") is True


# ---------------------------------------------------------------------------
# Watch heuristics.
# ---------------------------------------------------------------------------


def test_looks_like_watch():
    assert _looks_like_watch("Watch USDA's Crop Progress report for planting pace.")
    assert _looks_like_watch("Track the next WASDE release for ending stocks.")
    assert _looks_like_watch("If planted acres run ahead of average, the gap closes.")
    assert not _looks_like_watch("North Dakota planted 5.0M acres in 2025.")
    assert not _looks_like_watch("Monitor your blood pressure regularly.")


def test_split_trailing_watch_sentence():
    body = "A" * 100 + "."
    watch = "Watch USDA's June Acreage report for the first hard read."
    res = _split_trailing_watch_sentence(f"{body} {watch}")
    assert res == (body, watch)
    # Body too short: no split.
    assert _split_trailing_watch_sentence(f"Short body. {watch}") is None
    # Tail too short: no split.
    assert _split_trailing_watch_sentence(body + " Watch the USDA fast.") is None
    # Abbreviation boundary must not split ("U.S. corn" interior dot).
    text = "B" * 90 + ". the U.S. corn balance sheet tightened. Watch USDA's WASDE for the next read on stocks."
    res = _split_trailing_watch_sentence(text)
    assert res is not None
    assert res[1].startswith("Watch USDA's WASDE")


# ---------------------------------------------------------------------------
# Numeric guard.
# ---------------------------------------------------------------------------


def _dossier(**tool_output) -> FullDossier:
    story = StoryDossier(
        role="lead",
        signal_id="sig-1",
        headline="ND wheat acreage gap",
        editorial_angle="model vs USDA",
        claims=[
            "The model projected 6,236,516 planted acres for 2025.",
            "USDA's Prospective Plantings put the figure at 5,050,000 acres.",
        ],
        peer_context=["The 4-year mean was 6,683,750 acres."],
        what_to_watch="Watch Crop Progress.",
        tool_log=[{"name": "sql", "input": {}, "output": tool_output or {"forecast_2026": 5162101}}],
    )
    return FullDossier(lead=story, briefs=[])


def test_guard_keeps_grounded_figure():
    fig = {
        "kind": "figure", "title": "ND wheat forecast", "charts": [{
            "type": "bars", "data": [
                {"label": "Model", "value": 6.24},      # 6,236,516 scaled
                {"label": "USDA", "value": 5.05},        # 5,050,000 scaled
            ],
        }],
    }
    kept, dropped = _guard_rich_blocks([fig], _dossier())
    assert kept and not dropped


def test_guard_drops_invented_figure():
    fig = {
        "kind": "figure", "title": "Made up", "charts": [{
            "type": "bars", "data": [{"label": "X", "value": 9.99}],
        }],
    }
    kept, dropped = _guard_rich_blocks([fig], _dossier())
    assert not kept and dropped


def test_guard_drops_kpi_item_then_strip():
    strip = {
        "kind": "kpis", "items": [
            {"value": "6.24M", "label": "MODEL FORECAST"},
            {"value": "77.7M", "label": "INVENTED"},
        ],
    }
    kept, dropped = _guard_rich_blocks([strip], _dossier())
    # One item dies -> fewer than 2 remain -> whole strip dies.
    assert not kept
    assert any("INVENTED" in d for d in dropped)
    assert any("fewer than 2" in d for d in dropped)


def test_guard_allows_derived_percent():
    # 23.5% ~ (6236516 - 5050000) / 5050000 — a valid analyst derivation.
    stat = {"kind": "stat", "value": "+23.5%", "label": "model vs USDA gap"}
    kept, dropped = _guard_rich_blocks([stat], _dossier())
    assert kept and not dropped


# ---------------------------------------------------------------------------
# Region map identity fill.
# ---------------------------------------------------------------------------


def test_fill_region_identity():
    fig = {
        "title": "Belt map",
        "charts": [{
            "type": "region_map", "metricLabel": "x",
            "states": [
                {"fips": "38", "forecast": 5.16, "baseline": 6.68},
                {"fips": "6", "forecast": 1.0, "baseline": 1.1},
                {"fips": "99", "forecast": 2.0, "baseline": 2.1},
            ],
        }],
    }
    out = _fill_region_identity(fig)
    states = out["charts"][0]["states"]
    assert [s["fips"] for s in states] == ["38", "06"]
    assert states[0]["abbr"] == "ND" and states[0]["name"] == "North Dakota"
    assert states[1]["abbr"] == "CA"


# ---------------------------------------------------------------------------
# Splicing.
# ---------------------------------------------------------------------------


def test_splice_positions():
    prose = [
        {"kind": "title", "text": "T"},
        {"kind": "dek", "text": "D"},
        {"kind": "section", "text": "S", "lead": True},
        {"kind": "p", "text": "P1", "first": True},
        {"kind": "p", "text": "P2"},
    ]
    anchor_pos = {"chart_1": 5}  # anchor stood after P2
    rich = [
        {"kind": "kpis", "items": [{"value": "1", "label": "A"}, {"value": "2", "label": "B"}],
         "_after": 99, "_chart_id": None},
        {"kind": "figure", "title": "F", "charts": [], "_after": None, "_chart_id": "chart_1"},
        {"kind": "stat", "value": "+1%", "label": "L", "_after": 3, "_chart_id": None},
    ]
    out = _splice(prose, rich, anchor_pos)
    kinds = [b["kind"] for b in out]
    assert kinds == ["title", "dek", "kpis", "section", "p", "stat", "p", "figure"]
    assert all("_after" not in b and "_chart_id" not in b for b in out)


# ---------------------------------------------------------------------------
# End-to-end assembly with a mocked designer call.
# ---------------------------------------------------------------------------


def test_compose_issue_end_to_end(monkeypatch, draft_md: str):
    design = {
        "kpis": {
            "after_block": 1,
            "title": "THE WEEK AT A GLANCE",
            "items": [
                {"value": "6.24M", "unit": "ac", "label": "MODEL 2025 FORECAST", "tone": "harvest"},
                {"value": "5.05M", "unit": "ac", "label": "USDA PROSPECTIVE", "tone": "default"},
            ],
        },
        "stats": [],
        "figures": [{
            "chart_id": "chart_1",
            "title": "Model vs USDA, North Dakota Spring Wheat",
            "source": "FieldPulse model; NASS",
            "charts": [{
                "type": "bars",
                "data": [
                    {"label": "Model", "value": 6.24},
                    {"label": "USDA", "value": 5.05},
                ],
                "unit": "M acres",
            }],
        }],
    }
    monkeypatch.setattr(
        "backend.agent.composer._call_designer", lambda *a, **k: design
    )
    draft = WrittenDraft(markdown=draft_md, chart_specs=[{"id": "chart_1", "kind": "bars"}])
    composed = compose_issue(
        draft, dossier=_dossier(), as_of_date=date(2026, 6, 7)
    )
    assert isinstance(composed, ComposedIssue)
    spec = IssueSpec.model_validate(composed.spec)
    kinds = [type(b).__name__ for b in spec.blocks]
    assert "KpisBlock" in kinds and "FigureBlock" in kinds
    assert spec.meta.run_date == "2026-06-07"
    # No em dashes anywhere in the serialized spec.
    assert "—" not in json.dumps(composed.spec)


def test_compose_falls_back_when_designer_fails(monkeypatch, draft_md: str):
    monkeypatch.setattr(
        "backend.agent.composer._call_designer", lambda *a, **k: None
    )
    draft = WrittenDraft(markdown=draft_md, chart_specs=[])
    assert compose_issue(draft, dossier=_dossier(), as_of_date=date(2026, 6, 7)) is None


def test_compose_falls_back_when_charts_lost(monkeypatch, draft_md: str):
    # Designer returns no figures but the draft HAS chart specs: prefer the
    # markdown + PNG path so charts aren't silently lost.
    monkeypatch.setattr(
        "backend.agent.composer._call_designer",
        lambda *a, **k: {"kpis": None, "stats": [], "figures": []},
    )
    draft = WrittenDraft(markdown=draft_md, chart_specs=[{"id": "chart_1", "kind": "bar"}])
    assert compose_issue(draft, dossier=_dossier(), as_of_date=date(2026, 6, 7)) is None
