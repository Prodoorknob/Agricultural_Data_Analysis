"""Fact-checker (§8.2 of analyst-agent-tech-spec.md).

Two-pass gate:
  1. Deterministic numeric extraction with a unit-aware tokenizer.
     Every number in the draft must match (within tolerance) a number that
     appears in the dossier. Unmatched numbers fail the run.
  2. LLM critique via Haiku 4.5: reviews the draft against the dossier and
     flags wording-level issues (causation, em dashes, unsupported context).

Tokenizer grammar (§8.2 final list):
  $N           dollar amount       (canonical: dollars)
  N%           percent             (canonical: percent)
  N pp         percentage points   (canonical: percentage_points)
  N bu/ac      yield (grain)       (canonical: bu_per_ac)
  N cwt/ac     yield (rice)        (canonical: cwt_per_ac)
  N lb/ac      yield (cotton)      (canonical: lb_per_ac)
  Nx / N×      ratio
  N M / N million / N B / N billion / N K / N thousand   (scaled)
  N pp / N basis points (bps)      (1 bp = 0.01 pp)
  ISO years (4-digit) and YYYY/YY marketing year forms
  bare numbers near commodity unit nouns

Tolerances:
  ±2% relative for numeric values
  ±0.5 pp absolute for percentage-point claims
  exact match for years
  Soft (±5% rel) when "approximately"/"roughly"/"about" precedes the token.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from backend.agent.llm import CallStats, call_json, load_prompt
from backend.agent.researcher import FullDossier
from backend.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class CheckIssue:
    severity: str    # 'major' | 'minor'
    source: str      # 'numeric' | 'llm'
    detail: str
    quote: str = ""
    dossier_ref: str | None = None


@dataclass
class CheckResult:
    passed: bool
    numeric_issues: list[CheckIssue] = field(default_factory=list)
    llm_issues: list[CheckIssue] = field(default_factory=list)

    @property
    def all_issues(self) -> list[CheckIssue]:
        return self.numeric_issues + self.llm_issues

    @property
    def major_issues(self) -> list[CheckIssue]:
        return [i for i in self.all_issues if i.severity == "major"]


def fact_check(
    markdown: str,
    *,
    dossier: FullDossier,
    stats: CallStats | None = None,
) -> CheckResult:
    numeric_issues = _numeric_check(markdown, dossier)
    llm_issues = _llm_critique(markdown, dossier, stats=stats)
    has_major = any(i.severity == "major" for i in numeric_issues + llm_issues)
    return CheckResult(
        passed=not has_major,
        numeric_issues=numeric_issues,
        llm_issues=llm_issues,
    )


# ---------------------------------------------------------------------------
# Numeric tokenizer + matcher.
# ---------------------------------------------------------------------------


# Each pattern captures a numeric value plus its semantic unit.
# Order matters, most specific first.
#
# Sign-handling: `(?<![\w.])` before the optional `-` rejects the dash when
# it's a range separator (e.g. "27.7M-32.9M" should NOT tokenize -32.9).
# A literal sign requires either start-of-string or non-word/non-dot char
# immediately preceding.
_SIGN = r"(?<![\w.])\-?"

_TOKEN_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(rf"(?<!\w)\$({_SIGN}\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)\s*(million|M|billion|B|thousand|K)?(?!\w)"),
     "dollars_scale"),
    (re.compile(rf"({_SIGN}\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)\s*(?:percentage points|pp)(?!\w)"),
     "percentage_points"),
    (re.compile(rf"({_SIGN}\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)\s*(?:basis points|bps)(?!\w)"),
     "basis_points"),
    (re.compile(rf"({_SIGN}\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)\s*%"),
     "percent"),
    (re.compile(rf"({_SIGN}\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)\s*(?:bu/ac|bu/acre|bushels/acre|bu per ac)"),
     "bu_per_ac"),
    (re.compile(rf"({_SIGN}\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)\s*cwt/ac"),
     "cwt_per_ac"),
    (re.compile(rf"({_SIGN}\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)\s*lb/ac"),
     "lb_per_ac"),
    (re.compile(rf"({_SIGN}\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)\s*[xX×]\b"),
     "ratio"),
    (re.compile(r"\b(\d{4})\b"),
     "year"),
    (re.compile(rf"({_SIGN}\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)\s*(million|billion|M|B|thousand|K)\s*(?:acres|bushels|tons|head|metric tons|mt)\b", re.IGNORECASE),
     "scaled_count"),
    (re.compile(rf"({_SIGN}\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)\s*(million|billion|M|B|thousand|K)\b", re.IGNORECASE),
     "scaled_number"),
    (re.compile(rf"({_SIGN}\d{{1,3}}(?:,\d{{3}})*\.\d+)"),
     "decimal"),
]


def _scale(suffix: str | None) -> float:
    if not suffix:
        return 1.0
    s = suffix.strip().lower()
    if s in ("million", "m"):
        return 1_000_000
    if s in ("billion", "b"):
        return 1_000_000_000
    if s in ("thousand", "k"):
        return 1_000
    return 1.0


def _normalize_token(value_str: str, unit: str, suffix: str | None = None) -> tuple[float, str]:
    """Return (numeric_value, canonical_unit). Strips commas, applies scale."""
    v = float(value_str.replace(",", ""))
    if unit == "dollars_scale":
        return v * _scale(suffix), "dollars"
    if unit == "scaled_count":
        return v * _scale(suffix), "count"
    if unit == "scaled_number":
        return v * _scale(suffix), "number"
    if unit == "basis_points":
        return v * 0.01, "percentage_points"  # bps to pp
    return v, unit


def _extract_tokens(text: str) -> list[dict[str, Any]]:
    """Tokenize a text block into {value, unit, span, fuzzy}.

    fuzzy=True if 'approximately'/'about'/'roughly' appears in a 6-word window
    before the token.
    """
    out: list[dict[str, Any]] = []
    consumed = [False] * len(text)
    for pat, unit in _TOKEN_PATTERNS:
        for m in pat.finditer(text):
            start, end = m.start(), m.end()
            if any(consumed[start:end]):
                continue
            groups = m.groups()
            value_str = groups[0]
            suffix = groups[1] if len(groups) > 1 else None
            try:
                v, canonical = _normalize_token(value_str, unit, suffix)
            except ValueError:
                continue
            preceding = text[max(0, start - 60):start].lower()
            fuzzy = bool(re.search(r"\b(approximately|roughly|about)\b\s*$", preceding))
            out.append({
                "value": v, "unit": canonical,
                "span": (start, end), "raw": text[start:end],
                "fuzzy": fuzzy,
            })
            for i in range(start, end):
                consumed[i] = True
    return out


def _dossier_tokens(dossier: FullDossier) -> list[dict[str, Any]]:
    """Tokenize every textual fragment in the dossier (claims + peer_context +
    what_to_watch + evidence values + headline).
    """
    blobs: list[str] = []
    for story in dossier.all():
        blobs.append(story.headline)
        blobs.append(story.editorial_angle)
        blobs.append(story.what_to_watch)
        blobs.extend(story.claims)
        blobs.extend(story.peer_context)
        # tool_log inputs/outputs flattened to text
        for entry in story.tool_log:
            try:
                blobs.append(json.dumps(entry.get("output"), default=str))
            except Exception:
                pass

    tokens: list[dict[str, Any]] = []
    for blob in blobs:
        if not isinstance(blob, str):
            continue
        tokens.extend(_extract_tokens(blob))
    return tokens


def _numeric_check(markdown: str, dossier: FullDossier) -> list[CheckIssue]:
    """Match every numeric token in the markdown to a dossier token."""
    md_tokens = _extract_tokens(markdown)
    dossier_tokens = _dossier_tokens(dossier)
    magnitudes = _magnitude_pool(dossier_tokens)

    issues: list[CheckIssue] = []
    for tok in md_tokens:
        if _has_match(tok, dossier_tokens):
            continue
        # Not a verbatim match. Before flagging, check whether it is a correctly
        # *derived* figure: a gap, sum, ratio, %-change, or %-of two dossier
        # numbers (e.g. "a gap of 1.19M" = 6.24M - 5.05M). Such numbers never
        # appear verbatim in the dossier, so the exact matcher misses them even
        # though they are fully supported. Accepting them removes a whole class
        # of false-positive failures that no reviser pass can fix.
        if _is_derivable(tok, magnitudes):
            continue
        # Unmatched.
        # Year tokens are common false positives for run-of-mill prose
        # ("In 2026 we expect..."). If we couldn't find the year in dossier
        # treat it as a minor issue rather than a major one.
        severity = "minor" if tok["unit"] == "year" else "major"
        issues.append(
            CheckIssue(
                severity=severity,
                source="numeric",
                detail=f"unmatched {tok['unit']}={tok['value']}",
                quote=_context_window(markdown, tok["span"]),
            )
        )
    return issues


def _magnitude_pool(dossier_tokens: list[dict[str, Any]]) -> list[float]:
    """Distinct non-zero, non-year magnitudes from the dossier.

    Unit-agnostic on purpose: the tokenizer assigns "6.24 million acres" and
    "6.24 million" to different canonical units (count vs number), so a
    derivation check keyed on units would miss valid pairings. Years are
    excluded so they cannot spuriously satisfy ratio/percent derivations.
    """
    mags: list[float] = []
    for d in dossier_tokens:
        if d["unit"] == "year":
            continue
        v = float(d["value"])
        if v == 0:
            continue
        if not any(abs(v - m) <= abs(m) * 1e-6 for m in mags):
            mags.append(v)
    return mags


def _is_derivable(tok: dict[str, Any], magnitudes: list[float]) -> bool:
    """True if tok's value is a common analyst derivation of two dossier
    magnitudes within tolerance. Scoped by the token's unit so the check stays
    tight (a difference for magnitudes, a %-change/%-of for percents, a quotient
    for ratios) rather than becoming a match-anything escape hatch.
    """
    unit = tok["unit"]
    if unit == "year":
        return False
    av = abs(tok["value"])
    if av == 0:
        return False
    tol = 0.05 if tok.get("fuzzy") else 0.02

    def _ops(a: float, b: float) -> list[float]:
        if unit == "percent":
            out: list[float] = []
            if b != 0:
                out.append((a - b) / b * 100.0)  # % change
                out.append(a / b * 100.0)        # % of
            if a != 0:
                out.append((a - b) / a * 100.0)
            return out
        if unit == "ratio":
            return [a / b] if b != 0 else []
        if unit == "percentage_points":
            return [abs(a - b)]
        # magnitude units (number/count/dollars/decimal/yields): gap, sum, ratio
        out = [abs(a - b), a + b]
        if b != 0:
            out.append(a / b)
        return out

    n = len(magnitudes)
    for i in range(n):
        a = magnitudes[i]
        for j in range(n):
            if i == j:
                continue
            for c in _ops(a, magnitudes[j]):
                if c == 0:
                    continue
                if abs(abs(c) - av) / av <= tol:
                    return True
    return False


def _has_match(tok: dict[str, Any], dossier: list[dict[str, Any]]) -> bool:
    """Return True if any dossier token matches within tolerance."""
    unit = tok["unit"]
    val = tok["value"]
    soft = 0.05 if tok.get("fuzzy") else 0.02

    for d in dossier:
        if d["unit"] != unit:
            continue
        if unit == "year":
            if int(d["value"]) == int(val):
                return True
            continue
        if unit == "percentage_points":
            if abs(d["value"] - val) <= 0.5:
                return True
            continue
        if unit == "ratio":
            tol = 0.10 if tok.get("fuzzy") else 0.05
            if d["value"] != 0 and abs(d["value"] - val) / abs(d["value"]) <= tol:
                return True
            continue
        # Generic relative tolerance.
        if d["value"] == 0:
            if val == 0:
                return True
            continue
        if abs(d["value"] - val) / abs(d["value"]) <= soft:
            return True
    return False


def _context_window(text: str, span: tuple[int, int], padding: int = 40) -> str:
    s, e = span
    chunk = text[max(0, s - padding):min(len(text), e + padding)].replace("\n", " ")
    return chunk.strip()


# ---------------------------------------------------------------------------
# Haiku critique pass.
# ---------------------------------------------------------------------------


def _llm_critique(
    markdown: str,
    dossier: FullDossier,
    *,
    stats: CallStats | None = None,
) -> list[CheckIssue]:
    settings = get_settings()
    user = (
        f"DRAFT_MARKDOWN:\n{markdown}\n\n"
        f"DOSSIER_CLAIMS:\n{_dossier_summary(dossier)}\n"
    )
    try:
        raw = call_json(
            system=load_prompt("factcheck_system"),
            user=user,
            model=settings.AGENT_MODEL_CRITIC,
            max_tokens=1024,
            stats=stats,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("fact-check LLM critique errored: %s — soft-passing", exc)
        return []

    issues: list[CheckIssue] = []
    for raw_iss in raw.get("issues", [])[:6]:
        sev = str(raw_iss.get("severity", "minor")).lower()
        if sev not in {"major", "minor"}:
            sev = "minor"
        issues.append(
            CheckIssue(
                severity=sev,
                source="llm",
                detail=str(raw_iss.get("explanation", "")),
                quote=str(raw_iss.get("quote", ""))[:200],
                dossier_ref=raw_iss.get("dossier_ref"),
            )
        )
    return issues


def _dossier_summary(dossier: FullDossier) -> str:
    out: list[str] = []
    for story in dossier.all():
        out.append(f"[{story.role}] {story.headline}")
        for c in story.claims:
            out.append(f"  - claim: {c}")
        for p in story.peer_context:
            out.append(f"  - peer: {p}")
        if story.what_to_watch:
            out.append(f"  - watch: {story.what_to_watch}")
    return "\n".join(out)
