-- Migration 003 — Phase 2 market-truth layer (ADR-022, ADR-023, ADR-024).
--
-- Creates the two tables DATA_MODEL.md documented from the start but Phase 1
-- deliberately scoped out (external_documents, financial_facts), plus adds
-- provenance/freshness columns to price_snapshots so a price import carries
-- the same audit trail as a document or financial fact.
--
-- Additive only: no existing column is altered or dropped. Rollback drops the
-- two new tables and the new price_snapshots columns; no existing personal
-- data (accounts, transactions, existing price rows) is affected.

ALTER TABLE price_snapshots ADD COLUMN source_tier TEXT NOT NULL DEFAULT 'IMPORT';
ALTER TABLE price_snapshots ADD COLUMN published_at TEXT;

CREATE TABLE external_documents (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument_id  INTEGER REFERENCES instruments(id),
    symbol         TEXT,
    document_type  TEXT    NOT NULL,
    title          TEXT    NOT NULL,
    published_at   TEXT,
    source_name    TEXT    NOT NULL,
    source_tier    TEXT    NOT NULL DEFAULT 'IMPORT',
    source_url     TEXT,
    external_id    TEXT,
    content_hash   TEXT    NOT NULL,
    local_path     TEXT,
    retrieved_at   TEXT    NOT NULL,
    fingerprint    TEXT    NOT NULL
);

-- Duplicate protection (ADR-016 extended to documents): the same file content
-- re-imported is a no-op; a different file sharing a source+external_id is
-- also treated as the same logical document (a corrected re-upload updates it).
CREATE UNIQUE INDEX idx_documents_fingerprint ON external_documents(fingerprint);
CREATE INDEX idx_documents_symbol ON external_documents(symbol, document_type);
CREATE INDEX idx_documents_external_id ON external_documents(external_id);

CREATE TABLE financial_facts (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument_id           INTEGER NOT NULL REFERENCES instruments(id),
    symbol                  TEXT    NOT NULL,
    period_start            TEXT,
    period_end              TEXT    NOT NULL,
    period_type             TEXT    NOT NULL,
    metric                  TEXT    NOT NULL,
    value                   TEXT    NOT NULL,
    currency                TEXT    NOT NULL DEFAULT 'EGP',
    source_document_id      INTEGER REFERENCES external_documents(id),
    source_name             TEXT    NOT NULL,
    source_tier             TEXT    NOT NULL DEFAULT 'IMPORT',
    source_url              TEXT,
    published_at            TEXT,
    retrieved_at            TEXT    NOT NULL,
    fingerprint             TEXT    NOT NULL,
    created_at              TEXT    NOT NULL
);

CREATE UNIQUE INDEX idx_financial_facts_fingerprint ON financial_facts(fingerprint);
CREATE INDEX idx_financial_facts_symbol ON financial_facts(symbol, period_end, metric);

CREATE TABLE ingestion_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT    NOT NULL,
    provider        TEXT    NOT NULL,
    source          TEXT,
    ok              INTEGER NOT NULL,
    failure_kind    TEXT,
    error           TEXT,
    read_count      INTEGER NOT NULL DEFAULT 0,
    inserted_count  INTEGER NOT NULL DEFAULT 0,
    updated_count   INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    rejected_count  INTEGER NOT NULL DEFAULT 0,
    rejected_json   TEXT,
    started_at      TEXT    NOT NULL,
    completed_at    TEXT
);

CREATE INDEX idx_ingestion_runs_kind ON ingestion_runs(kind, started_at);
