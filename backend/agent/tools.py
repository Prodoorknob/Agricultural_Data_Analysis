"""Researcher tools (§7.1 of analyst-agent-tech-spec.md).

Five read-only tools the researcher LLM can call. Every tool takes an
implicit `as_of_date` injected by the runtime — the LLM does not control
it. SQL is guarded by sqlglot AST traversal: SELECT-only, no DDL/DML.

Public API:
    build_tool_specs() -> list[dict]      # for Anthropic tools= parameter
    build_tool_handlers(as_of) -> dict    # name -> bound callable

The handlers all return JSON-serializable structures (lists of dicts,
plain dicts, scalars) for direct insertion as tool_result content.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Callable, Literal

import sqlglot
import sqlglot.expressions as exp
from sqlalchemy import text

from backend.agent.signals._fips_label import county_label, state_label
from backend.etl.common import get_sync_session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQL guard: parse the LLM's query, reject anything not a single SELECT,
# and inject as_of constraints on tables that have time columns.
# ---------------------------------------------------------------------------


# Map of table_name -> column to constrain by `<= :as_of`.
_AS_OF_TABLE_COLUMNS: dict[str, str] = {
    "yield_forecasts": "created_at",
    "yield_accuracy": "updated_at",
    "acreage_forecasts": "created_at",
    "acreage_accuracy": "updated_at",
    "price_forecasts": "created_at",
    "wasde_releases": "release_date",
    "futures_daily": "trade_date",
    "dxy_daily": "trade_date",
    "drought_index": None,            # year-only, no row-level timestamp
    "export_commitments": "as_of_date",
    "ers_production_costs": None,     # annual, no timestamp
    "ers_fertilizer_prices": None,
    "feature_weekly": "ingest_ts",
    "soil_features": None,
}

_ALLOWED_TABLES = set(_AS_OF_TABLE_COLUMNS.keys())


class SqlValidationError(ValueError):
    pass


def validate_and_rewrite_sql(sql: str, as_of: date) -> str:
    """Parse SQL, reject non-SELECT, inject `<col> <= '<as_of>'` predicates.

    Strategy:
      1. parse with sqlglot
      2. require exactly one statement, of type Select
      3. walk every Table reference; reject unknown table names
      4. for each known table with an as_of column, append
         `AND <table>.<col> <= 'YYYY-MM-DD'` to the SELECT's WHERE clause
    """
    try:
        parsed = sqlglot.parse(sql, dialect="postgres")
    except sqlglot.errors.ParseError as exc:
        raise SqlValidationError(f"sql parse error: {exc}")

    if len(parsed) != 1:
        raise SqlValidationError("only single SELECT allowed")
    stmt = parsed[0]
    if stmt is None or not isinstance(stmt, exp.Select):
        raise SqlValidationError(
            f"only SELECT allowed; got {stmt.key if stmt else 'None'}"
        )

    # Reject any DML/DDL hidden in subqueries by walking for those classes.
    forbidden_classes = (
        exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
        exp.Alter, exp.TruncateTable,
    )
    for node in stmt.walk():
        if isinstance(node, forbidden_classes):
            raise SqlValidationError(
                f"{type(node).__name__} is forbidden, read-only access"
            )

    # Collect referenced tables; reject unknown ones.
    referenced: list[tuple[exp.Table, str]] = []  # (node, name_lower)
    for tbl in stmt.find_all(exp.Table):
        name = (tbl.name or "").lower()
        if not name:
            continue
        if name not in _ALLOWED_TABLES:
            raise SqlValidationError(
                f"table {name!r} not allowed; pick from {sorted(_ALLOWED_TABLES)}"
            )
        referenced.append((tbl, name))

    # Inject as_of constraints. We attach them via a single AND-chain to the
    # outermost SELECT's WHERE, qualified by table alias if present.
    extras: list[exp.Expression] = []
    as_of_str = as_of.isoformat()
    for tbl, name in referenced:
        col_name = _AS_OF_TABLE_COLUMNS.get(name)
        if not col_name:
            continue
        # Use alias if set, else table name.
        alias = tbl.alias or name
        col_ref = exp.Column(this=exp.Identifier(this=col_name), table=exp.Identifier(this=alias))
        extras.append(
            exp.LTE(
                this=col_ref,
                expression=exp.Literal.string(as_of_str),
            )
        )

    if extras:
        # Combine with AND.
        new_filter = extras[0]
        for e in extras[1:]:
            new_filter = exp.And(this=new_filter, expression=e)
        existing = stmt.args.get("where")
        if existing is not None:
            stmt.set(
                "where",
                exp.Where(this=exp.And(this=existing.this, expression=new_filter)),
            )
        else:
            stmt.set("where", exp.Where(this=new_filter))

    return stmt.sql(dialect="postgres")


# ---------------------------------------------------------------------------
# Tool implementations.
# ---------------------------------------------------------------------------


_RESULT_ROW_LIMIT = 200


def _query_sql(sql: str, *, as_of_date: date) -> dict[str, Any]:
    """Validate, rewrite, and execute. Truncates result rows."""
    rewritten = validate_and_rewrite_sql(sql, as_of_date)
    with get_sync_session() as s:
        rows = s.execute(text(rewritten)).mappings().all()
    truncated = len(rows) > _RESULT_ROW_LIMIT
    rows = rows[:_RESULT_ROW_LIMIT]
    out_rows = [{k: _coerce(v) for k, v in r.items()} for r in rows]
    return {
        "rewritten_sql": rewritten,
        "row_count": len(out_rows),
        "truncated": truncated,
        "rows": out_rows,
    }


def _coerce(v: Any) -> Any:
    """Cast Decimal / date / datetime to JSON-friendly types."""
    from datetime import datetime
    from decimal import Decimal

    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _get_forecast(
    *,
    commodity: str,
    kind: Literal["yield", "acreage", "price"],
    scope: str,
    horizon: int | None = None,
    as_of_date: date,
) -> dict[str, Any]:
    """Read a single forecast from the right forecast table.

    `scope` semantics:
      - kind=price:    'national' (only national supported)
      - kind=acreage:  'national' or 'state:NN'
      - kind=yield:    'county:NNNNN'
    """
    if kind == "price":
        sql = text(
            """
            SELECT *
            FROM price_forecasts
            WHERE commodity = :c
              AND created_at <= :as_of
              AND (:horizon IS NULL OR horizon_month = :horizon_str)
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        import pandas as pd

        horizon_str = (
            (pd.Timestamp(as_of_date) + pd.DateOffset(months=horizon)).strftime("%Y-%m")
            if horizon is not None
            else None
        )
        with get_sync_session() as s:
            row = s.execute(
                sql,
                {"c": commodity, "as_of": as_of_date, "horizon": horizon, "horizon_str": horizon_str},
            ).mappings().first()
        return {"row": dict(row) if row else None} if row else {"row": None}

    if kind == "acreage":
        if scope == "national":
            target_fips = "00"
        elif scope.startswith("state:"):
            target_fips = scope.split(":", 1)[1]
        else:
            return {"error": f"acreage scope must be 'national' or 'state:NN', got {scope}"}
        with get_sync_session() as s:
            row = s.execute(
                text(
                    """
                    SELECT * FROM acreage_forecasts
                    WHERE commodity = :c AND state_fips = :f
                      AND created_at <= :as_of
                    ORDER BY created_at DESC LIMIT 1
                    """
                ),
                {"c": commodity, "f": target_fips, "as_of": as_of_date},
            ).mappings().first()
        return {"row": {k: _coerce(v) for k, v in dict(row).items()} if row else None}

    if kind == "yield":
        if not scope.startswith("county:"):
            return {"error": f"yield scope must be 'county:NNNNN', got {scope}"}
        fips = scope.split(":", 1)[1]
        with get_sync_session() as s:
            row = s.execute(
                text(
                    """
                    SELECT * FROM yield_forecasts
                    WHERE crop = :c AND fips = :f AND created_at <= :as_of
                    ORDER BY week DESC, created_at DESC LIMIT 1
                    """
                ),
                {"c": commodity, "f": fips, "as_of": as_of_date},
            ).mappings().first()
        return {"row": {k: _coerce(v) for k, v in dict(row).items()} if row else None}

    return {"error": f"unknown kind: {kind}"}


def _get_history(
    *,
    commodity: str,
    scope: str,
    metric: str,
    start_year: int,
    end_year: int,
    as_of_date: date,
) -> dict[str, Any]:
    """Pull a long-history series from yield_accuracy or acreage_accuracy.

    metric ∈ {'yield', 'acres'}. Yield uses yield_accuracy.actual_yield;
    acres uses acreage_accuracy.usda_june_actual.
    """
    end_year = min(end_year, as_of_date.year)
    if metric == "yield":
        if not scope.startswith("county:"):
            return {"error": "yield history needs scope='county:NNNNN'"}
        fips = scope.split(":", 1)[1]
        sql = text(
            """
            SELECT forecast_year, AVG(actual_yield) AS actual_yield
            FROM yield_accuracy
            WHERE crop = :c AND fips = :f
              AND forecast_year BETWEEN :y0 AND :y1
              AND actual_yield IS NOT NULL
              AND updated_at <= :as_of
            GROUP BY forecast_year
            ORDER BY forecast_year
            """
        )
        params = {
            "c": commodity, "f": fips,
            "y0": start_year, "y1": end_year, "as_of": as_of_date,
        }
    elif metric == "acres":
        if scope == "national":
            target = "00"
        elif scope.startswith("state:"):
            target = scope.split(":", 1)[1]
        else:
            return {"error": "acres history needs scope='national' or 'state:NN'"}
        sql = text(
            """
            SELECT forecast_year, AVG(usda_june_actual) AS acres
            FROM acreage_accuracy
            WHERE commodity = :c AND state_fips = :f
              AND forecast_year BETWEEN :y0 AND :y1
              AND usda_june_actual IS NOT NULL
              AND updated_at <= :as_of
            GROUP BY forecast_year
            ORDER BY forecast_year
            """
        )
        params = {
            "c": commodity, "f": target,
            "y0": start_year, "y1": end_year, "as_of": as_of_date,
        }
    else:
        return {"error": f"unknown metric: {metric}"}

    with get_sync_session() as s:
        rows = s.execute(sql, params).mappings().all()
    return {"series": [{k: _coerce(v) for k, v in r.items()} for r in rows]}


def _get_weather(
    *, fips: str, start: str, end: str, as_of_date: date
) -> dict[str, Any]:
    """County weekly weather features over a date range, capped at as_of_date.

    Returns aggregated weekly rows from feature_weekly.
    """
    try:
        d_start = date.fromisoformat(start)
        d_end = date.fromisoformat(end)
    except ValueError:
        return {"error": "start/end must be YYYY-MM-DD"}
    d_end = min(d_end, as_of_date)

    sql = text(
        """
        SELECT crop_year, week, crop, gdd_ytd, cci_cumul, precip_deficit,
               vpd_stress_days, drought_d3d4_pct
        FROM feature_weekly
        WHERE fips = :f
          AND ingest_ts <= :as_of
          AND crop_year BETWEEN :y0 AND :y1
        ORDER BY crop_year, week, crop
        LIMIT 200
        """
    )
    params = {
        "f": fips, "as_of": as_of_date,
        "y0": d_start.year, "y1": d_end.year,
    }
    with get_sync_session() as s:
        rows = s.execute(sql, params).mappings().all()
    return {
        "fips": fips,
        "label": county_label(fips),
        "weeks": [{k: _coerce(v) for k, v in r.items()} for r in rows],
    }


def _compare_peers(
    *, scope: str, metric: str, n: int = 5, as_of_date: date
) -> dict[str, Any]:
    """Top/bottom-N peers by a metric.

    For now: yield rank by latest year's actual_yield among counties in the
    same state. Future expansion: acreage by state, etc.
    """
    if metric != "yield" or not scope.startswith("county:"):
        return {"error": "v1 supports only metric='yield' and scope='county:NNNNN'"}
    fips = scope.split(":", 1)[1]
    state_fips = fips[:2]
    sql = text(
        """
        WITH latest AS (
            SELECT MAX(forecast_year) AS yr FROM yield_accuracy
            WHERE actual_yield IS NOT NULL AND updated_at <= :as_of
        )
        SELECT fips, crop, actual_yield, forecast_year
        FROM yield_accuracy
        WHERE actual_yield IS NOT NULL
          AND forecast_year = (SELECT yr FROM latest)
          AND updated_at <= :as_of
          AND SUBSTRING(fips, 1, 2) = :sf
        ORDER BY actual_yield DESC
        LIMIT :limit
        """
    )
    n = max(1, min(20, int(n)))
    with get_sync_session() as s:
        top = s.execute(sql, {"as_of": as_of_date, "sf": state_fips, "limit": n}).mappings().all()
        bot_sql = text(
            """
            WITH latest AS (
                SELECT MAX(forecast_year) AS yr FROM yield_accuracy
                WHERE actual_yield IS NOT NULL AND updated_at <= :as_of
            )
            SELECT fips, crop, actual_yield, forecast_year
            FROM yield_accuracy
            WHERE actual_yield IS NOT NULL
              AND forecast_year = (SELECT yr FROM latest)
              AND updated_at <= :as_of
              AND SUBSTRING(fips, 1, 2) = :sf
            ORDER BY actual_yield ASC
            LIMIT :limit
            """
        )
        bot = s.execute(bot_sql, {"as_of": as_of_date, "sf": state_fips, "limit": n}).mappings().all()
    return {
        "scope": scope,
        "state": state_label(state_fips),
        "top": [
            {**{k: _coerce(v) for k, v in dict(r).items()}, "label": county_label(r["fips"])}
            for r in top
        ],
        "bottom": [
            {**{k: _coerce(v) for k, v in dict(r).items()}, "label": county_label(r["fips"])}
            for r in bot
        ],
    }


# ---------------------------------------------------------------------------
# Anthropic tool specs (the part shipped to the LLM).
# ---------------------------------------------------------------------------


def build_tool_specs() -> list[dict[str, Any]]:
    """JSON schemas for the LLM. as_of_date is intentionally NOT exposed."""
    return [
        {
            "name": "query_sql",
            "description": (
                "Read-only SELECT against the analytics tables. "
                f"Allowed tables: {sorted(_ALLOWED_TABLES)}. "
                "INSERT/UPDATE/DELETE/DDL are rejected. "
                "Time-bound tables get an implicit `<= as_of` filter so the "
                "query returns only data that was knowable on the run date. "
                "Returns at most 200 rows."
            ),
            "input_schema": {
                "type": "object",
                "required": ["sql"],
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "A single Postgres SELECT statement.",
                    }
                },
            },
        },
        {
            "name": "get_forecast",
            "description": (
                "Fetch a single forecast row. kind='price' returns national price "
                "forecast; 'acreage' returns national or state acreage; 'yield' "
                "returns county yield. scope is 'national' | 'state:NN' | "
                "'county:NNNNN' depending on kind."
            ),
            "input_schema": {
                "type": "object",
                "required": ["commodity", "kind", "scope"],
                "properties": {
                    "commodity": {"type": "string", "enum": ["corn", "soybean", "wheat"]},
                    "kind": {"type": "string", "enum": ["yield", "acreage", "price"]},
                    "scope": {"type": "string"},
                    "horizon": {
                        "type": "integer",
                        "description": "Months out (price kind only). Optional.",
                    },
                },
            },
        },
        {
            "name": "get_history",
            "description": (
                "Long-history annual series. metric='yield' uses observed county "
                "yields; 'acres' uses USDA June actual planted acres."
            ),
            "input_schema": {
                "type": "object",
                "required": ["commodity", "scope", "metric", "start_year", "end_year"],
                "properties": {
                    "commodity": {"type": "string", "enum": ["corn", "soybean", "wheat"]},
                    "scope": {"type": "string"},
                    "metric": {"type": "string", "enum": ["yield", "acres"]},
                    "start_year": {"type": "integer"},
                    "end_year": {"type": "integer"},
                },
            },
        },
        {
            "name": "get_weather",
            "description": (
                "County weekly weather features (GDD, CCI, precip deficit, VPD "
                "stress days, drought %) over a date range."
            ),
            "input_schema": {
                "type": "object",
                "required": ["fips", "start", "end"],
                "properties": {
                    "fips": {"type": "string", "description": "5-digit county FIPS"},
                    "start": {"type": "string", "description": "YYYY-MM-DD"},
                    "end": {"type": "string", "description": "YYYY-MM-DD"},
                },
            },
        },
        {
            "name": "compare_peers",
            "description": (
                "Top-N and bottom-N peer counties (in the same state) by a metric. "
                "Currently supports metric='yield' for scope='county:NNNNN'."
            ),
            "input_schema": {
                "type": "object",
                "required": ["scope", "metric"],
                "properties": {
                    "scope": {"type": "string"},
                    "metric": {"type": "string", "enum": ["yield"]},
                    "n": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                },
            },
        },
    ]


# ---------------------------------------------------------------------------
# Handler factory — closes over as_of_date so the LLM can't override it.
# ---------------------------------------------------------------------------


def build_tool_handlers(as_of_date: date) -> dict[str, Callable[..., Any]]:
    """Return {tool_name: handler} with as_of_date bound by partial application."""
    def query_sql(*, sql: str, **kwargs) -> dict[str, Any]:
        return _query_sql(sql, as_of_date=as_of_date)

    def get_forecast(*, commodity, kind, scope, horizon=None, **kwargs) -> dict[str, Any]:
        return _get_forecast(
            commodity=commodity, kind=kind, scope=scope,
            horizon=horizon, as_of_date=as_of_date,
        )

    def get_history(*, commodity, scope, metric, start_year, end_year, **kwargs) -> dict[str, Any]:
        return _get_history(
            commodity=commodity, scope=scope, metric=metric,
            start_year=start_year, end_year=end_year, as_of_date=as_of_date,
        )

    def get_weather(*, fips, start, end, **kwargs) -> dict[str, Any]:
        return _get_weather(fips=fips, start=start, end=end, as_of_date=as_of_date)

    def compare_peers(*, scope, metric, n=5, **kwargs) -> dict[str, Any]:
        return _compare_peers(scope=scope, metric=metric, n=n, as_of_date=as_of_date)

    return {
        "query_sql": query_sql,
        "get_forecast": get_forecast,
        "get_history": get_history,
        "get_weather": get_weather,
        "compare_peers": compare_peers,
    }
