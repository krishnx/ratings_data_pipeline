-- ═══════════════════════════════════════════════════════════════
-- EXTENSIONS
-- ═══════════════════════════════════════════════════════════════
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- ═══════════════════════════════════════════════════════════════
-- dim_company
-- One row per legal entity. Natural key = entity_name (normalized).
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS dim_company (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_name TEXT    NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT  uq_company_name UNIQUE (entity_name)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_name_lower
    ON dim_company (LOWER(entity_name));

-- ═══════════════════════════════════════════════════════════════
-- upload_audit
-- One row per processed file. Metadata only — no raw bytes here.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS upload_audit (
    id                INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    filename          TEXT        NOT NULL,
    file_sha256       TEXT        NOT NULL,
    uploaded_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pipeline_run_id   TEXT        NOT NULL,
    byte_size         BIGINT,
    validation_status TEXT        NOT NULL
        CHECK (validation_status IN ('passed', 'passed_with_warnings', 'failed')),
    validation_report JSONB,
    CONSTRAINT uq_upload_sha256 UNIQUE (file_sha256)
);

CREATE INDEX IF NOT EXISTS idx_upload_uploaded_at
    ON upload_audit (uploaded_at DESC);

CREATE INDEX IF NOT EXISTS idx_upload_pipeline_run
    ON upload_audit (pipeline_run_id);

-- ═══════════════════════════════════════════════════════════════
-- upload_file_store
-- Isolated raw bytes — joined only when /uploads/{id}/file is called.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS upload_file_store (
    upload_id   INTEGER PRIMARY KEY REFERENCES upload_audit(id) ON DELETE CASCADE,
    raw_bytes   BYTEA NOT NULL
);

-- ═══════════════════════════════════════════════════════════════
-- fact_company_snapshot
-- One row per (company, upload). SCD Type 2: valid_to=NULL is current.
--
-- WHY NOT PARTITIONED:
-- The plan evaluated RANGE partitioning on valid_from (annual) but two
-- PostgreSQL constraints make it infeasible here:
--
--   1. GENERATED ALWAYS AS STORED columns (search_vector below) cannot
--      reference columns outside the partition in PostgreSQL 15; the
--      generated expression must be defined identically on the parent and
--      all child partitions, which creates DDL complexity and drift risk.
--
--   2. Foreign keys FROM fact_industry_segment and fact_credit_metric
--      reference fact_company_snapshot(id). On a partitioned table the
--      PRIMARY KEY must include the partition key, making it (id, valid_from).
--      PostgreSQL requires FK columns to form a unique constraint on the
--      referenced table; snapshot_id alone is not unique when the PK is
--      composite, so both child-table FKs would fail.
--
-- Compensation: the full index set below (covering, partial WHERE valid_to
-- IS NULL, BRIN, GIN) achieves equivalent query performance for the
-- current data volume. Partitioning can be re-evaluated if the table
-- grows to millions of rows — at that scale, removing the generated column
-- and replacing it with a trigger, or upgrading to PostgreSQL 17 (which
-- relaxes some of these restrictions), would unblock it.
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS fact_company_snapshot (
    id                          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id                  INTEGER     NOT NULL REFERENCES dim_company(id),
    upload_id                   INTEGER     NOT NULL REFERENCES upload_audit(id),
    version_number              INTEGER     NOT NULL,

    valid_from                  TIMESTAMPTZ NOT NULL,
    valid_to                    TIMESTAMPTZ,

    corporate_sector            TEXT,
    reporting_currency          TEXT,
    country_of_origin           TEXT,
    accounting_principles       TEXT,
    business_year_end_month     TEXT,
    segmentation_criteria       TEXT,

    business_risk_profile       TEXT,
    blended_industry_risk_profile TEXT,
    competitive_positioning     TEXT,
    market_share                TEXT,
    diversification             TEXT,
    operating_profitability     TEXT,
    sector_specific_factor_1    TEXT,
    sector_specific_factor_2    TEXT,
    financial_risk_profile      TEXT,
    leverage                    TEXT,
    interest_cover              TEXT,
    cash_flow_cover             TEXT,
    liquidity_adjustment        TEXT,

    rating_methodologies        TEXT[],
    raw_extras                  JSONB,

    search_vector               TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english',
            COALESCE(corporate_sector,             '') || ' ' ||
            COALESCE(country_of_origin,            '') || ' ' ||
            COALESCE(business_risk_profile,        '') || ' ' ||
            COALESCE(financial_risk_profile,       '') || ' ' ||
            COALESCE(blended_industry_risk_profile,'')
        )
    ) STORED
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshot_current_by_company
    ON fact_company_snapshot (company_id)
    WHERE valid_to IS NULL;

CREATE INDEX IF NOT EXISTS idx_snapshot_versions_covering
    ON fact_company_snapshot (company_id, valid_from DESC)
    INCLUDE (version_number, corporate_sector, reporting_currency,
             country_of_origin, business_risk_profile, financial_risk_profile,
             blended_industry_risk_profile, valid_to);

CREATE INDEX IF NOT EXISTS idx_snapshot_point_in_time
    ON fact_company_snapshot (company_id, valid_from, valid_to);

CREATE INDEX IF NOT EXISTS idx_snapshot_sector_current
    ON fact_company_snapshot (corporate_sector)
    WHERE valid_to IS NULL;

CREATE INDEX IF NOT EXISTS idx_snapshot_country_current
    ON fact_company_snapshot (country_of_origin)
    WHERE valid_to IS NULL;

CREATE INDEX IF NOT EXISTS idx_snapshot_currency_current
    ON fact_company_snapshot (reporting_currency)
    WHERE valid_to IS NULL;

CREATE INDEX IF NOT EXISTS idx_snapshot_valid_from_brin
    ON fact_company_snapshot USING BRIN (valid_from);

CREATE INDEX IF NOT EXISTS idx_snapshot_methodologies_gin
    ON fact_company_snapshot USING GIN (rating_methodologies);

CREATE INDEX IF NOT EXISTS idx_snapshot_search_fts
    ON fact_company_snapshot USING GIN (search_vector);

CREATE INDEX IF NOT EXISTS idx_snapshot_analytics_dimensions
    ON fact_company_snapshot (corporate_sector, reporting_currency, country_of_origin)
    INCLUDE (version_number, business_risk_profile, financial_risk_profile, valid_from)
    WHERE valid_to IS NULL;

-- ═══════════════════════════════════════════════════════════════
-- fact_industry_segment
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS fact_industry_segment (
    id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id     INTEGER     NOT NULL REFERENCES fact_company_snapshot(id) ON DELETE CASCADE,
    segment_index   SMALLINT    NOT NULL,
    industry_name   TEXT        NOT NULL,
    risk_score      TEXT        NOT NULL,
    weight          NUMERIC(6,4) NOT NULL,
    CONSTRAINT uq_segment_snapshot_idx UNIQUE (snapshot_id, segment_index)
);

-- ═══════════════════════════════════════════════════════════════
-- fact_credit_metric
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS fact_credit_metric (
    id                    INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id           INTEGER     NOT NULL REFERENCES fact_company_snapshot(id) ON DELETE CASCADE,
    metric_year           SMALLINT    NOT NULL,
    ebitda_interest_cover DOUBLE PRECISION,
    debt_ebitda           DOUBLE PRECISION,
    ffo_debt              DOUBLE PRECISION,
    loan_value            DOUBLE PRECISION,
    focf_debt             DOUBLE PRECISION,
    liquidity             DOUBLE PRECISION,
    CONSTRAINT uq_metric_snapshot_year UNIQUE (snapshot_id, metric_year)
);

CREATE INDEX IF NOT EXISTS idx_credit_metric_analytics
    ON fact_credit_metric (metric_year)
    INCLUDE (snapshot_id, ffo_debt, debt_ebitda, ebitda_interest_cover, focf_debt);

-- ═══════════════════════════════════════════════════════════════
-- data_lineage
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS data_lineage (
    id              INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lineage_id      TEXT        NOT NULL,
    stage           TEXT        NOT NULL
        CHECK (stage IN ('source', 'extracted', 'validated', 'loaded')),
    source_ref      TEXT        NOT NULL,
    target_ref      TEXT,
    stage_status    TEXT        NOT NULL
        CHECK (stage_status IN ('success', 'failed', 'skipped')),
    upload_id       INTEGER     REFERENCES upload_audit(id),
    snapshot_id     INTEGER,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata        JSONB
);

CREATE INDEX IF NOT EXISTS idx_lineage_lineage_id
    ON data_lineage (lineage_id);

CREATE INDEX IF NOT EXISTS idx_lineage_upload_id
    ON data_lineage (upload_id);

-- ═══════════════════════════════════════════════════════════════
-- pipeline_state
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS pipeline_state (
    id                INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id            TEXT    NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL,
    finished_at       TIMESTAMPTZ,
    status            TEXT    NOT NULL
        CHECK (status IN ('running', 'success', 'partial', 'failed')),
    files_found       INTEGER,
    files_processed   INTEGER,
    files_skipped     INTEGER,
    files_failed      INTEGER,
    total_duration_ms BIGINT,
    error_summary     JSONB,
    CONSTRAINT uq_pipeline_run_id UNIQUE (run_id)
);

-- ═══════════════════════════════════════════════════════════════
-- mv_current_snapshots (MATERIALIZED VIEW)
-- Pre-joined current state of every company.
-- ═══════════════════════════════════════════════════════════════
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_current_snapshots AS
    SELECT
        s.id                            AS snapshot_id,
        c.id                            AS company_id,
        c.entity_name,
        s.version_number,
        s.valid_from,
        s.corporate_sector,
        s.reporting_currency,
        s.country_of_origin,
        s.accounting_principles,
        s.business_year_end_month,
        s.business_risk_profile,
        s.blended_industry_risk_profile,
        s.financial_risk_profile,
        s.competitive_positioning,
        s.market_share,
        s.diversification,
        s.operating_profitability,
        s.leverage,
        s.interest_cover,
        s.cash_flow_cover,
        s.liquidity_adjustment,
        s.rating_methodologies,
        s.segmentation_criteria
    FROM fact_company_snapshot s
    JOIN dim_company c ON c.id = s.company_id
    WHERE s.valid_to IS NULL
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_current_company_id
    ON mv_current_snapshots (company_id);

CREATE INDEX IF NOT EXISTS idx_mv_current_sector
    ON mv_current_snapshots (corporate_sector);

CREATE INDEX IF NOT EXISTS idx_mv_current_country
    ON mv_current_snapshots (country_of_origin);

CREATE INDEX IF NOT EXISTS idx_mv_current_currency
    ON mv_current_snapshots (reporting_currency);

-- ═══════════════════════════════════════════════════════════════
-- mv_analytics_summary (MATERIALIZED VIEW)
-- ═══════════════════════════════════════════════════════════════
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_analytics_summary AS
    SELECT
        s.corporate_sector,
        s.reporting_currency,
        s.country_of_origin,
        COUNT(*)                          AS company_count,
        AVG(cm.ffo_debt)                  AS avg_ffo_debt,
        AVG(cm.debt_ebitda)               AS avg_debt_ebitda,
        AVG(cm.ebitda_interest_cover)     AS avg_ebitda_cover,
        MIN(cm.metric_year)               AS earliest_year,
        MAX(cm.metric_year)               AS latest_year
    FROM mv_current_snapshots s
    JOIN fact_credit_metric cm ON cm.snapshot_id = s.snapshot_id
    GROUP BY s.corporate_sector, s.reporting_currency, s.country_of_origin
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_analytics_dims
    ON mv_analytics_summary (corporate_sector, reporting_currency, country_of_origin);
