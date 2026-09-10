-- Migration 001 — initial Phase 1 schema (see DATA_MODEL.md).
-- Money and quantity values are stored as exact decimal TEXT, never REAL.

CREATE TABLE accounts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    broker          TEXT,
    currency        TEXT    NOT NULL DEFAULT 'EGP',
    status          TEXT    NOT NULL DEFAULT 'ACTIVE',
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE TABLE portfolios (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id        INTEGER NOT NULL REFERENCES accounts(id),
    name              TEXT    NOT NULL,
    objective         TEXT,
    risk_profile      TEXT,
    target_rules_json TEXT,
    created_at        TEXT    NOT NULL,
    updated_at        TEXT    NOT NULL,
    UNIQUE (account_id, name)
);

CREATE TABLE instruments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol         TEXT    NOT NULL UNIQUE,
    name           TEXT,
    exchange       TEXT    NOT NULL DEFAULT 'EGX',
    sector         TEXT,
    industry       TEXT,
    currency       TEXT    NOT NULL DEFAULT 'EGP',
    trading_status TEXT    NOT NULL DEFAULT 'ACTIVE',
    isin           TEXT,
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL
);

CREATE TABLE transactions (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id                  INTEGER NOT NULL REFERENCES accounts(id),
    portfolio_id                INTEGER REFERENCES portfolios(id),
    transaction_type            TEXT    NOT NULL
        CHECK (transaction_type IN ('BUY', 'SELL', 'DEPOSIT', 'WITHDRAW')),
    instrument_id               INTEGER REFERENCES instruments(id),
    symbol                      TEXT,
    quantity                    TEXT    NOT NULL DEFAULT '0',
    unit_price                  TEXT    NOT NULL DEFAULT '0',
    cash_amount                 TEXT    NOT NULL,
    commission                  TEXT    NOT NULL DEFAULT '0',
    fees                        TEXT    NOT NULL DEFAULT '0',
    transaction_date            TEXT    NOT NULL,
    external_reference          TEXT,
    source                      TEXT    NOT NULL DEFAULT 'manual',
    note                        TEXT,
    fingerprint                 TEXT    NOT NULL,
    sequence                    INTEGER NOT NULL,
    supersedes_transaction_id   INTEGER REFERENCES transactions(id),
    superseded_by_transaction_id INTEGER REFERENCES transactions(id),
    created_at                  TEXT    NOT NULL
);

CREATE INDEX idx_transactions_account ON transactions(account_id, transaction_date, sequence);
CREATE UNIQUE INDEX idx_transactions_fingerprint ON transactions(fingerprint);

CREATE TABLE price_snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument_id INTEGER NOT NULL REFERENCES instruments(id),
    symbol       TEXT    NOT NULL,
    price_date   TEXT    NOT NULL,
    close_price  TEXT    NOT NULL,
    open_price   TEXT,
    high_price   TEXT,
    low_price    TEXT,
    volume       TEXT,
    source       TEXT    NOT NULL DEFAULT 'manual',
    source_url   TEXT,
    retrieved_at TEXT    NOT NULL,
    UNIQUE (instrument_id, price_date, source)
);

CREATE INDEX idx_prices_symbol_date ON price_snapshots(symbol, price_date);

CREATE TABLE research_runs (
    id                      TEXT PRIMARY KEY,
    created_at              TEXT NOT NULL,
    question                TEXT NOT NULL,
    scope_type              TEXT NOT NULL DEFAULT 'ACCOUNT',
    scope_reference         TEXT,
    account_id              INTEGER REFERENCES accounts(id),
    status                  TEXT NOT NULL,
    mode                    TEXT NOT NULL DEFAULT 'live',
    chair_provider          TEXT,
    portfolio_snapshot_json TEXT,
    market_context_reference TEXT,
    contract_version        TEXT NOT NULL,
    artifact_dir            TEXT,
    completed_at            TEXT,
    error                   TEXT
);

CREATE INDEX idx_runs_created ON research_runs(created_at);

CREATE TABLE agent_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    research_run_id   TEXT NOT NULL REFERENCES research_runs(id),
    agent_provider    TEXT NOT NULL,
    agent_role        TEXT NOT NULL,
    stage             TEXT NOT NULL,
    session_reference TEXT,
    started_at        TEXT NOT NULL,
    completed_at      TEXT,
    duration_seconds  TEXT,
    status            TEXT NOT NULL,
    failure_kind      TEXT,
    input_hash        TEXT NOT NULL,
    raw_output_path   TEXT,
    parsed_output_json TEXT,
    validation_errors TEXT,
    exit_code         INTEGER,
    stderr_excerpt    TEXT,
    cost              TEXT,
    token_usage       TEXT
);

CREATE INDEX idx_agent_runs_run ON agent_runs(research_run_id);

CREATE TABLE disagreements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    research_run_id TEXT NOT NULL REFERENCES research_runs(id),
    topic           TEXT NOT NULL,
    codex_position  TEXT,
    claude_position TEXT,
    materiality     TEXT NOT NULL DEFAULT 'unknown',
    resolution_status TEXT NOT NULL DEFAULT 'OPEN',
    resolution_summary TEXT,
    evidence_json   TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE simulations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    research_run_id TEXT REFERENCES research_runs(id),
    account_id      INTEGER REFERENCES accounts(id),
    simulation_type TEXT NOT NULL,
    input_json      TEXT NOT NULL,
    output_json     TEXT NOT NULL,
    engine_version  TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE recommendations (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    research_run_id      TEXT NOT NULL REFERENCES research_runs(id),
    rank                 INTEGER NOT NULL,
    instrument_id        INTEGER REFERENCES instruments(id),
    symbol               TEXT,
    action               TEXT NOT NULL,
    confidence           INTEGER,
    data_quality_score   INTEGER,
    current_weight_pct   TEXT,
    suggested_weight_pct TEXT,
    thesis_summary       TEXT,
    counterargument      TEXT,
    invalidators_json    TEXT,
    risks_json           TEXT,
    portfolio_effect_json TEXT,
    evidence_json        TEXT,
    created_at           TEXT NOT NULL,
    UNIQUE (research_run_id, rank)
);

CREATE TABLE human_decisions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    research_run_id   TEXT NOT NULL REFERENCES research_runs(id),
    recommendation_id INTEGER REFERENCES recommendations(id),
    decision          TEXT NOT NULL
        CHECK (decision IN ('APPROVE', 'REJECT', 'HOLD', 'MODIFY')),
    modified_action   TEXT,
    note              TEXT,
    created_at        TEXT NOT NULL
);

CREATE INDEX idx_decisions_run ON human_decisions(research_run_id);

CREATE TABLE executions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    human_decision_id INTEGER REFERENCES human_decisions(id),
    transaction_id   INTEGER NOT NULL REFERENCES transactions(id),
    recorded_at      TEXT NOT NULL,
    note             TEXT,
    UNIQUE (transaction_id)
);

CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT NOT NULL,
    actor_type      TEXT NOT NULL,
    actor_reference TEXT,
    action          TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    entity_id       TEXT,
    before_json     TEXT,
    after_json      TEXT,
    reason          TEXT
);

CREATE INDEX idx_audit_entity ON audit_log(entity_type, entity_id);
