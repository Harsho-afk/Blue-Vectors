-- ARIA Migration 001: Case-centric Database Schema
-- Run order: users -> cases -> case_identifiers -> osint_lookups -> ALTER accounts -> ALTER posts -> linkage_results

-- 1. users
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name     TEXT,
    role          TEXT NOT NULL DEFAULT 'investigator',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. cases
CREATE TABLE IF NOT EXISTS cases (
    id              SERIAL PRIMARY KEY,
    investigator_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS cases_investigator_id_idx ON cases(investigator_id);

-- 3. case_identifiers
CREATE TABLE IF NOT EXISTS case_identifiers (
    id              SERIAL PRIMARY KEY,
    case_id         INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    identifier_type TEXT NOT NULL CHECK (identifier_type IN ('username', 'email', 'phone', 'profile_url')),
    value           TEXT NOT NULL,
    platform_hint   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS case_identifiers_case_id_idx ON case_identifiers(case_id);

-- 4. osint_lookups
CREATE TABLE IF NOT EXISTS osint_lookups (
    id          SERIAL PRIMARY KEY,
    case_id     INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    lookup_type TEXT NOT NULL CHECK (lookup_type IN ('sherlock', 'hibp', 'profile_url_scrape')),
    input_value TEXT NOT NULL,
    result_json JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS osint_lookups_case_id_idx ON osint_lookups(case_id);

-- 5. ALTER accounts
ALTER TABLE accounts ADD COLUMN case_id INTEGER REFERENCES cases(id) ON DELETE CASCADE;

-- Drop the old UNIQUE constraint on (platform, username)
-- Use IF EXISTS for safer execution if constraint names vary
ALTER TABLE accounts DROP CONSTRAINT IF EXISTS accounts_platform_username_key;

-- Add the new UNIQUE constraint on (case_id, platform, username)
ALTER TABLE accounts ADD CONSTRAINT accounts_case_platform_username_key UNIQUE (case_id, platform, username);

CREATE INDEX IF NOT EXISTS accounts_case_id_idx ON accounts(case_id);

-- 6. ALTER posts
ALTER TABLE posts ADD COLUMN spike_flag BOOLEAN NOT NULL DEFAULT false;

-- 7. linkage_results
CREATE TABLE IF NOT EXISTS linkage_results (
    id           SERIAL PRIMARY KEY,
    case_id      INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    account_a_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    account_b_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    confidence   NUMERIC(5,2) NOT NULL,
    shap_json    JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT linkage_results_ordered_accounts CHECK (account_a_id < account_b_id)
);

CREATE INDEX IF NOT EXISTS linkage_results_case_id_idx ON linkage_results(case_id);
