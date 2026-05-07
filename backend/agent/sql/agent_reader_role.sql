-- agent_reader role + curated read-only views for FieldPulse Weekly.
--
-- Spec: §7.1 of research/analyst-agent-tech-spec.md.
--
-- This is run manually against the prod RDS instance (psql via the
-- ag_app master user). Not driven by alembic because:
--   * roles are out-of-scope for SQLAlchemy migrations
--   * the password should be set interactively, not committed
--
-- Usage:
--   psql "postgres://ag_app:<MASTER_PW>@ag-dashboard.cvuu6ce8odqc.us-east-2.rds.amazonaws.com:5432/ag_dashboard" \
--        -v ROLE_PW="$AGENT_READER_PW" -f backend/agent/sql/agent_reader_role.sql
--
-- After running:
--   * the agent process connects with DATABASE_URL_AGENT_READER, e.g.
--     postgresql+psycopg://agent_reader:<pw>@<host>:5432/ag_dashboard
--   * the SQL tool (§7.1) restricts queries to the `agent_*_v` views below.
--
-- IMPORTANT: every view filters by an `:as_of` parameter so the LLM cannot
-- see future data during the 12-week backfill. Views accept the parameter
-- via PostgreSQL session settings (`SET app.as_of = '2025-09-15'`) which
-- the runtime sets once per tool invocation.

\set ON_ERROR_STOP on

-- 1. Role
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_reader') THEN
        EXECUTE format('CREATE ROLE agent_reader LOGIN PASSWORD %L', :'ROLE_PW');
    END IF;
END$$;

REVOKE ALL ON SCHEMA public FROM agent_reader;
GRANT USAGE ON SCHEMA public TO agent_reader;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM agent_reader;

-- 2. Helper: parse the session-level as_of setting into a date.
CREATE OR REPLACE FUNCTION agent_as_of() RETURNS date
LANGUAGE plpgsql STABLE AS $$
DECLARE v_str text; v_dt date;
BEGIN
    BEGIN
        v_str := current_setting('app.as_of', true);
    EXCEPTION WHEN OTHERS THEN
        v_str := NULL;
    END;
    IF v_str IS NULL OR v_str = '' THEN
        RETURN current_date;
    END IF;
    BEGIN
        v_dt := v_str::date;
    EXCEPTION WHEN OTHERS THEN
        v_dt := current_date;
    END;
    RETURN v_dt;
END;
$$;
GRANT EXECUTE ON FUNCTION agent_as_of() TO agent_reader;

-- 3. Curated views: each one applies the as_of filter on the right column.

CREATE OR REPLACE VIEW agent_yield_forecasts_v AS
    SELECT *
    FROM yield_forecasts
    WHERE created_at <= agent_as_of();

CREATE OR REPLACE VIEW agent_acreage_forecasts_v AS
    SELECT *
    FROM acreage_forecasts
    WHERE created_at <= agent_as_of();

CREATE OR REPLACE VIEW agent_price_forecasts_v AS
    SELECT *
    FROM price_forecasts
    WHERE created_at <= agent_as_of();

CREATE OR REPLACE VIEW agent_wasde_releases_v AS
    SELECT *
    FROM wasde_releases
    WHERE release_date <= agent_as_of();

CREATE OR REPLACE VIEW agent_futures_daily_v AS
    SELECT *
    FROM futures_daily
    WHERE trade_date <= agent_as_of();

CREATE OR REPLACE VIEW agent_dxy_daily_v AS
    SELECT *
    FROM dxy_daily
    WHERE trade_date <= agent_as_of();

CREATE OR REPLACE VIEW agent_drought_index_v AS
    SELECT *
    FROM drought_index
    WHERE year < EXTRACT(YEAR FROM agent_as_of())::int
       OR (year = EXTRACT(YEAR FROM agent_as_of())::int);
-- drought_index is annualized; the year filter is a coarse approximation.

CREATE OR REPLACE VIEW agent_export_commitments_v AS
    SELECT *
    FROM export_commitments
    WHERE as_of_date <= agent_as_of();

CREATE OR REPLACE VIEW agent_yield_accuracy_v AS
    SELECT *
    FROM yield_accuracy
    WHERE updated_at <= agent_as_of();

CREATE OR REPLACE VIEW agent_acreage_accuracy_v AS
    SELECT *
    FROM acreage_accuracy
    WHERE updated_at <= agent_as_of();

-- 4. Grants.
GRANT SELECT ON
    agent_yield_forecasts_v,
    agent_acreage_forecasts_v,
    agent_price_forecasts_v,
    agent_wasde_releases_v,
    agent_futures_daily_v,
    agent_dxy_daily_v,
    agent_drought_index_v,
    agent_export_commitments_v,
    agent_yield_accuracy_v,
    agent_acreage_accuracy_v
TO agent_reader;
