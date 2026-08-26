"""Tests for the researcher's generated TABLE SCHEMAS doc.

Regression for the w28-w34 query_sql failures: the LLM invented column names
(stocks_to_use_pct, settle_price, dxy_close, fips on drought_index, commodity
on yield_accuracy, ...) because the prompt never listed real columns. The doc
is generated from ORM metadata so it cannot drift from the schema.
"""

from backend.agent.llm import load_prompt
from backend.agent.tools import _ALLOWED_TABLES, build_schema_doc


def test_every_allowlisted_table_is_documented():
    doc = build_schema_doc()
    for name in _ALLOWED_TABLES:
        assert f"- {name}(" in doc, f"{name} missing from schema doc"


def test_real_columns_present_and_id_excluded():
    doc = build_schema_doc()
    # The columns the LLM kept guessing wrong, by their REAL names.
    for real in (
        "settlement",            # futures_daily (LLM guessed settle_price)
        "dxy",                   # dxy_daily (guessed dxy_close)
        "stocks_to_use",         # wasde_releases (guessed stocks_to_use_pct/_ratio)
        "total_domestic_use",    # wasde_releases
        "as_of_date",            # export_commitments (guessed week_ending)
        "net_sales_mt",          # export_commitments (guessed net_sales)
        "dsci_nov",              # drought_index (guessed fips/week/drought_pct)
    ):
        assert real in doc, f"column {real} missing from schema doc"
    # Surrogate PK is noise for the LLM.
    assert "(id," not in doc


def test_researcher_prompt_has_placeholder():
    prompt = load_prompt("researcher_system")
    assert "{{TABLE_SCHEMAS}}" in prompt
    substituted = prompt.replace("{{TABLE_SCHEMAS}}", build_schema_doc())
    assert "TABLE SCHEMAS" in substituted
    assert "{{TABLE_SCHEMAS}}" not in substituted
