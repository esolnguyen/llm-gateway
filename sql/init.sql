-- Initial schema for llm-wrapper (providers + costs modules).
-- Apply with: psql "$DATABASE_URL" -f sql/init.sql
-- Replace with Alembic migrations before production.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
-- providers module: model credentials
-- ============================================================
CREATE TABLE IF NOT EXISTS model_credentials (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider       VARCHAR(50)  NOT NULL,
    model_name     VARCHAR(255) NOT NULL UNIQUE,
    api_key_enc    BYTEA        NOT NULL,
    api_endpoint   TEXT,
    api_version    VARCHAR(50),
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Example insert (encrypt the api_key at write time):
--   INSERT INTO model_credentials (provider, model_name, api_key_enc, api_endpoint, api_version)
--   VALUES (
--     'google',
--     'gemini-2.0-flash',
--     pgp_sym_encrypt('YOUR_API_KEY_HERE', 'YOUR_ENCRYPTION_KEY'),
--     NULL,
--     NULL
--   );

-- ============================================================
-- costs module: pricing and cost events
-- ============================================================
CREATE TABLE IF NOT EXISTS model_pricing (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name      VARCHAR(255)   NOT NULL,
    capability      VARCHAR(50)    NOT NULL,            -- 'chat' | 'ocr'
    unit_type       VARCHAR(50)    NOT NULL,            -- 'input_tokens' | 'output_tokens' | 'pages'
    price_per_unit  NUMERIC(20,10) NOT NULL,
    currency        CHAR(3)        NOT NULL DEFAULT 'USD',
    effective_from  TIMESTAMPTZ    NOT NULL,
    effective_to    TIMESTAMPTZ,
    CONSTRAINT uq_model_pricing_effective
        UNIQUE (model_name, capability, unit_type, effective_from)
);

CREATE TABLE IF NOT EXISTS cost_events (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    module_name       VARCHAR(100)   NOT NULL,
    service_name      VARCHAR(100)   NOT NULL,
    user_id           VARCHAR(100)   NOT NULL,
    organisation_id   VARCHAR(100)   NOT NULL,
    model_name        VARCHAR(255)   NOT NULL,
    capability        VARCHAR(50)    NOT NULL,
    units             JSONB          NOT NULL,
    cost_amount       NUMERIC(20,10) NOT NULL,
    currency          CHAR(3)        NOT NULL DEFAULT 'USD',
    external_ref_type VARCHAR(100),
    external_ref_id   VARCHAR(100),
    event_metadata    JSONB,
    created_at        TIMESTAMPTZ    NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cost_events_org
    ON cost_events (organisation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cost_events_user
    ON cost_events (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cost_events_model
    ON cost_events (model_name, created_at DESC);
