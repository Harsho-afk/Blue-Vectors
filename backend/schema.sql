-- ARIA Layer 1 — PostgreSQL schema
-- Run once: psql -d aria -f schema.sql

CREATE TABLE IF NOT EXISTS accounts (
    id                SERIAL PRIMARY KEY,
    platform          TEXT        NOT NULL,
    username          TEXT        NOT NULL,
    display_name      TEXT,
    bio               TEXT,
    location          TEXT,
    created_at        TIMESTAMPTZ,
    profile_image_url TEXT,
    UNIQUE (platform, username)
);

CREATE TABLE IF NOT EXISTS posts (
    id         SERIAL PRIMARY KEY,
    account_id INTEGER     NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    text       TEXT,
    timestamp  TIMESTAMPTZ NOT NULL,
    metadata   JSONB,
    UNIQUE (account_id, timestamp, text)
);

CREATE INDEX IF NOT EXISTS posts_account_id_idx ON posts(account_id);
CREATE INDEX IF NOT EXISTS posts_timestamp_idx  ON posts(timestamp);
