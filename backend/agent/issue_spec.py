"""Typed IssueSpec contract for chart-enabled FieldPulse issues.

Python mirror of web_app/src/components/insights/model/types.ts — the JSON
emitted here is consumed directly by the frontend ModelIssue renderer, so
field names keep the TS camelCase (valueFormat, metricLabel, refValue, ...).
Keep the two files in sync when the contract changes.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator

Tone = Literal["default", "positive", "negative", "harvest"]


class KpiItem(BaseModel):
    value: str
    unit: str | None = None
    label: str
    caption: str | None = None
    tone: Tone | None = None


# ---------------------------------------------------------------------------
# Charts.
# ---------------------------------------------------------------------------


class BarDatum(BaseModel):
    label: str
    value: float
    color: str | None = None


class BarsChart(BaseModel):
    type: Literal["bars"]
    data: list[BarDatum] = Field(min_length=1)
    valueFormat: Literal["abs", "signed_pct"] | None = None
    unit: str | None = None
    decimals: int | None = None
    height: int | None = None
    domain: tuple[float, float] | None = None
    caption: str | None = None


class TrendPoint(BaseModel):
    year: int
    value: float


class TrendForecast(BaseModel):
    year: int
    p50: float
    p10: float
    p90: float


class TrendForecastChart(BaseModel):
    type: Literal["trend_forecast"]
    actuals: list[TrendPoint] = Field(min_length=2)
    forecast: TrendForecast
    refValue: float | None = None
    refLabel: str | None = None
    unit: str | None = None
    height: int | None = None
    yDomain: tuple[float, float] | None = None
    caption: str | None = None


class RegionMapState(BaseModel):
    fips: str = Field(pattern=r"^\d{2}$")
    abbr: str
    name: str
    forecast: float | None = None
    baseline: float | None = None
    note: str | None = None


class RegionMapChart(BaseModel):
    type: Literal["region_map"]
    states: list[RegionMapState] = Field(min_length=2)
    metricLabel: str
    unit: str | None = None
    height: int | None = None
    caption: str | None = None


ChartSpec = Annotated[
    Union[BarsChart, TrendForecastChart, RegionMapChart],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Blocks.
# ---------------------------------------------------------------------------


class TitleBlock(BaseModel):
    kind: Literal["title"]
    text: str


class DekBlock(BaseModel):
    kind: Literal["dek"]
    text: str


class SectionBlock(BaseModel):
    kind: Literal["section"]
    text: str
    lead: bool | None = None


class BriefBlock(BaseModel):
    kind: Literal["brief"]
    text: str


class PBlock(BaseModel):
    kind: Literal["p"]
    text: str
    first: bool | None = None


class WatchBlock(BaseModel):
    kind: Literal["watch"]
    text: str


class KpisBlock(BaseModel):
    kind: Literal["kpis"]
    title: str | None = None
    items: list[KpiItem] = Field(min_length=2)


class StatBlock(BaseModel):
    kind: Literal["stat"]
    value: str
    label: str
    detail: str | None = None


class FigureBlock(BaseModel):
    kind: Literal["figure"]
    title: str
    subtitle: str | None = None
    source: str | None = None
    charts: list[ChartSpec]

    @field_validator("charts")
    @classmethod
    def _one_or_two_charts(cls, v: list) -> list:
        if not 1 <= len(v) <= 2:
            raise ValueError("figure must hold 1 or 2 charts")
        return v


class HrBlock(BaseModel):
    kind: Literal["hr"]


Block = Annotated[
    Union[
        TitleBlock, DekBlock, SectionBlock, BriefBlock, PBlock,
        WatchBlock, KpisBlock, StatBlock, FigureBlock, HrBlock,
    ],
    Field(discriminator="kind"),
]


class IssueMetaSpec(BaseModel):
    run_date: str
    cost_usd: float | None = None
    duration_sec: int | None = None
    n_tool_calls: int | None = None
    n_signals_scanned: int | None = None
    approved_by: str | None = None


class IssueSpec(BaseModel):
    blocks: list[Block]
    meta: IssueMetaSpec
