-- ARIA PostgreSQL schema
-- Run once to initialize the database: psql -d aria -f schema.sql

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
    status          TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'closed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS cases_investigator_id_idx
ON cases(investigator_id);

-- 3. case_identifiers
CREATE TABLE IF NOT EXISTS case_identifiers (
    id              SERIAL PRIMARY KEY,
    case_id         INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    identifier_type TEXT NOT NULL
                    CHECK (identifier_type IN ('username', 'email', 'phone', 'profile_url')),
    value           TEXT NOT NULL,
    platform_hint   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS case_identifiers_case_id_idx
ON case_identifiers(case_id);

-- 4. osint_lookups
CREATE TABLE IF NOT EXISTS osint_lookups (
    id          SERIAL PRIMARY KEY,
    case_id     INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    lookup_type TEXT NOT NULL
                CHECK (lookup_type IN ('maigret', 'sherlock', 'hibp', 'xposedornot', 'profile_url_scrape', 'phone', 'dorking', 'holehe')),
    input_value TEXT NOT NULL,
    result_json JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS osint_lookups_case_id_idx
ON osint_lookups(case_id);

-- 5. accounts
CREATE TABLE IF NOT EXISTS accounts (
    id                SERIAL PRIMARY KEY,
    case_id           INTEGER REFERENCES cases(id) ON DELETE CASCADE,
    platform          TEXT NOT NULL,
    username          TEXT NOT NULL,
    display_name      TEXT,
    bio               TEXT,
    location          TEXT,
    created_at        TIMESTAMPTZ,
    profile_image_url TEXT,
    image_embedding   JSONB,
    karma             INTEGER,
    follower_count    INTEGER,
    following_count   INTEGER,
    UNIQUE (case_id, platform, username)
);

CREATE INDEX IF NOT EXISTS accounts_case_id_idx
ON accounts(case_id);

-- 6. posts
CREATE TABLE IF NOT EXISTS posts (
    id           SERIAL PRIMARY KEY,
    account_id   INTEGER NOT NULL
                 REFERENCES accounts(id)
                 ON DELETE CASCADE,
    -- Platform-specific unique identifier
    -- Reddit: t1_xxx / t3_xxx
    -- Twitter/X: tweet ID
    external_id  TEXT NOT NULL,
    text         TEXT,
    timestamp    TIMESTAMPTZ NOT NULL,
    metadata     JSONB,
    spike_flag   BOOLEAN NOT NULL DEFAULT false,
    UNIQUE (account_id, external_id)
);

CREATE INDEX IF NOT EXISTS posts_account_id_idx
ON posts(account_id);

CREATE INDEX IF NOT EXISTS posts_timestamp_idx
ON posts(timestamp);

CREATE INDEX IF NOT EXISTS posts_external_id_idx
ON posts(external_id);

-- 7. linkage_results
CREATE TABLE IF NOT EXISTS linkage_results (
    id           SERIAL PRIMARY KEY,
    case_id      INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    account_a_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    account_b_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    confidence   NUMERIC(5,2) NOT NULL,
    shap_json    JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT linkage_results_ordered_accounts
    CHECK (account_a_id < account_b_id)
);

CREATE INDEX IF NOT EXISTS linkage_results_case_id_idx
ON linkage_results(case_id);

-- 8. insights (Stage 2A deterministic computation output)
CREATE TABLE IF NOT EXISTS insights (
    id          SERIAL PRIMARY KEY,
    case_id     INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    account_id  INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
    category    TEXT NOT NULL
                CHECK (category IN (
                    'geography', 'pattern_of_life', 'identity_consistency',
                    'coordination', 'risk', 'cross_reference', 'content'
                )),
    claim       TEXT NOT NULL,
    confidence  TEXT NOT NULL
                CHECK (confidence IN ('high', 'medium', 'low')),
    evidence    JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS insights_case_id_idx
ON insights(case_id);

CREATE INDEX IF NOT EXISTS insights_account_id_idx
ON insights(account_id);

-- 9. intelligence_reports (Stage 2B/2C Analyst LLM output)
CREATE TABLE IF NOT EXISTS intelligence_reports (
    id          SERIAL PRIMARY KEY,
    case_id     INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    narrative   TEXT NOT NULL,
    claims      JSONB NOT NULL,
    label       TEXT NOT NULL DEFAULT 'AI-synthesized, citation-linked',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS intelligence_reports_case_id_idx
ON intelligence_reports(case_id);

-- 10. socmint_reports (versioned investigation report snapshots)
CREATE TABLE IF NOT EXISTS socmint_reports (
    id                  SERIAL PRIMARY KEY,
    case_id             INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    version             INTEGER NOT NULL DEFAULT 1,
    status              TEXT NOT NULL DEFAULT 'generating'
                        CHECK (status IN ('generating', 'ready', 'failed')),
    report_json         JSONB,
    source_snapshot     JSONB,
    methodology_version TEXT NOT NULL DEFAULT '1.0',
    generated_by        INTEGER NOT NULL REFERENCES users(id),
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    content_hash        TEXT,
    error_message       TEXT,
    UNIQUE (case_id, version)
);

CREATE INDEX IF NOT EXISTS socmint_reports_case_id_idx
ON socmint_reports(case_id);

-- ═══════════════════════════════════════════════════════════════════════════════
-- MONITORING / WATCHLIST SYSTEM
-- ═══════════════════════════════════════════════════════════════════════════════

-- 11. monitor_targets — profiles placed under active monitoring
CREATE TABLE IF NOT EXISTS monitor_targets (
    id                SERIAL PRIMARY KEY,
    case_id           INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    created_by        INTEGER NOT NULL REFERENCES users(id),
    -- exactly one of these must be set
    account_id        INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
    identifier_id     INTEGER REFERENCES case_identifiers(id) ON DELETE CASCADE,
    status            TEXT NOT NULL DEFAULT 'pending_baseline'
                      CHECK (status IN (
                          'pending_baseline', 'active', 'paused',
                          'degraded', 'expired', 'revoked'
                      )),
    reason            TEXT NOT NULL,
    -- what sources to check
    permitted_sources JSONB NOT NULL DEFAULT '["platform_recollect", "maigret", "dorking", "breach"]',
    interval_seconds  INTEGER NOT NULL DEFAULT 3600,
    next_check_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_checked_at   TIMESTAMPTZ,
    expires_at        TIMESTAMPTZ NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT monitor_targets_one_target
        CHECK (
            (account_id IS NOT NULL AND identifier_id IS NULL) OR
            (account_id IS NULL AND identifier_id IS NOT NULL)
        )
);

CREATE INDEX IF NOT EXISTS monitor_targets_case_id_idx
ON monitor_targets(case_id);

CREATE INDEX IF NOT EXISTS monitor_targets_next_check_idx
ON monitor_targets(next_check_at)
WHERE status IN ('active', 'pending_baseline');

-- 12. monitor_snapshots — point-in-time state captures for diffing
CREATE TABLE IF NOT EXISTS monitor_snapshots (
    id            SERIAL PRIMARY KEY,
    target_id     INTEGER NOT NULL REFERENCES monitor_targets(id) ON DELETE CASCADE,
    source        TEXT NOT NULL,
    snapshot_json JSONB NOT NULL,
    content_hash  TEXT NOT NULL,
    is_baseline   BOOLEAN NOT NULL DEFAULT false,
    observed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS monitor_snapshots_target_id_idx
ON monitor_snapshots(target_id);

CREATE INDEX IF NOT EXISTS monitor_snapshots_baseline_idx
ON monitor_snapshots(target_id, source)
WHERE is_baseline = true;

-- 13. monitor_events — detected changes between snapshots
CREATE TABLE IF NOT EXISTS monitor_events (
    id                SERIAL PRIMARY KEY,
    target_id         INTEGER NOT NULL REFERENCES monitor_targets(id) ON DELETE CASCADE,
    event_type        TEXT NOT NULL
                      CHECK (event_type IN (
                          'profile_changed', 'new_posts', 'network_changed',
                          'account_discovered', 'account_disappeared',
                          'breach_detected', 'correlation_drift',
                          'new_web_mention', 'hard_link_found'
                      )),
    source            TEXT NOT NULL,
    title             TEXT NOT NULL,
    previous_json     JSONB,
    current_json      JSONB,
    evidence_json     JSONB,
    source_url        TEXT,
    confidence        TEXT CHECK (confidence IN ('high', 'medium', 'low')),
    priority          TEXT NOT NULL DEFAULT 'normal'
                      CHECK (priority IN ('low', 'normal', 'high', 'critical')),
    fingerprint       TEXT NOT NULL,
    observed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS monitor_events_target_id_idx
ON monitor_events(target_id);

CREATE UNIQUE INDEX IF NOT EXISTS monitor_events_dedup_idx
ON monitor_events(target_id, source, fingerprint);

-- 14. alerts — investigator-facing notifications
CREATE TABLE IF NOT EXISTS alerts (
    id               SERIAL PRIMARY KEY,
    case_id          INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    monitor_event_id INTEGER REFERENCES monitor_events(id) ON DELETE SET NULL,
    investigator_id  INTEGER NOT NULL REFERENCES users(id),
    status           TEXT NOT NULL DEFAULT 'unread'
                     CHECK (status IN ('unread', 'read', 'acknowledged', 'dismissed')),
    title            TEXT NOT NULL,
    message          TEXT NOT NULL,
    priority         TEXT NOT NULL DEFAULT 'normal'
                     CHECK (priority IN ('low', 'normal', 'high', 'critical')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at          TIMESTAMPTZ,
    acknowledged_at  TIMESTAMPTZ,
    dismissed_at     TIMESTAMPTZ,
    dismiss_reason   TEXT
);

CREATE INDEX IF NOT EXISTS alerts_investigator_status_idx
ON alerts(investigator_id, status);

CREATE INDEX IF NOT EXISTS alerts_case_id_idx
ON alerts(case_id);
