"""Database setup, migrations, duplicate protection, and audit trail."""

import pytest

from economic.domain import ledger
from economic.persistence import sqlite_db
from economic.persistence.repositories import (
    DuplicateTransactionError, NotFoundError, Repositories)


def test_database_initializes_from_empty_and_records_its_version(home):
    connection = sqlite_db.initialize(home / "data" / "test.db")
    assert sqlite_db.schema_version(connection) == len(sqlite_db.available_migrations())
    assert sqlite_db.integrity_check(connection) is None


def test_migrations_are_idempotent(home):
    connection = sqlite_db.initialize(home / "data" / "test.db")
    assert sqlite_db.migrate(connection) == []


def test_migration_002_upgrades_a_v1_database_without_losing_data(home, tmp_path):
    """Personal data must survive a schema change (DATA_MODEL §10)."""
    import shutil

    staging = tmp_path / "v1"
    staging.mkdir()
    shutil.copy(sqlite_db.MIGRATIONS_DIR / "001_initial.sql", staging / "001_initial.sql")
    real_dir = sqlite_db.MIGRATIONS_DIR
    database = home / "data" / "legacy.db"
    try:
        sqlite_db.MIGRATIONS_DIR = staging
        connection = sqlite_db.initialize(database)
        assert sqlite_db.schema_version(connection) == 1
        connection.execute(
            "INSERT INTO research_runs (id, created_at, question, scope_type, status, mode,"
            " contract_version) VALUES ('run-legacy', '2026-01-01', 'old question',"
            " 'ACCOUNT', 'READY_FOR_HUMAN', 'live', '1.0')")
        connection.execute(
            "INSERT INTO recommendations (research_run_id, rank, action, confidence,"
            " created_at) VALUES ('run-legacy', 1, 'BUY', 88, '2026-01-01')")
        connection.close()
    finally:
        sqlite_db.MIGRATIONS_DIR = real_dir

    upgraded = sqlite_db.initialize(database)
    assert sqlite_db.schema_version(upgraded) == len(sqlite_db.available_migrations())
    assert sqlite_db.integrity_check(upgraded) is None

    run = dict(upgraded.execute("SELECT * FROM research_runs").fetchone())
    assert run["question"] == "old question"
    # A run recorded before integrity was tracked must not be claimed as FULL.
    assert run["committee_mode"] == "UNKNOWN"

    recommendation = dict(upgraded.execute("SELECT * FROM recommendations").fetchone())
    assert recommendation["action"] == "BUY"
    assert recommendation["confidence"] == 88
    assert recommendation["restricted"] == 0


def test_migration_003_upgrades_a_v2_database_without_losing_data(home, tmp_path):
    """Phase 1 personal data must survive the Phase 2 schema change (ADR-022)."""
    import shutil

    staging = tmp_path / "v2"
    staging.mkdir()
    for name in ("001_initial.sql", "002_committee_integrity_and_gate.sql"):
        shutil.copy(sqlite_db.MIGRATIONS_DIR / name, staging / name)
    real_dir = sqlite_db.MIGRATIONS_DIR
    database = home / "data" / "legacy2.db"
    try:
        sqlite_db.MIGRATIONS_DIR = staging
        connection = sqlite_db.initialize(database)
        assert sqlite_db.schema_version(connection) == 2
        connection.execute(
            "INSERT INTO accounts (name, currency, status, created_at, updated_at)"
            " VALUES ('Main', 'EGP', 'ACTIVE', '2026-01-01', '2026-01-01')")
        connection.execute(
            "INSERT INTO instruments (symbol, exchange, currency, trading_status,"
            " created_at, updated_at) VALUES ('COMI', 'EGX', 'EGP', 'ACTIVE',"
            " '2026-01-01', '2026-01-01')")
        connection.execute(
            "INSERT INTO price_snapshots (instrument_id, symbol, price_date, close_price,"
            " source, retrieved_at) VALUES (1, 'COMI', '2026-01-01', '50', 'manual',"
            " '2026-01-01')")
        connection.close()
    finally:
        sqlite_db.MIGRATIONS_DIR = real_dir

    upgraded = sqlite_db.initialize(database)
    assert sqlite_db.schema_version(upgraded) == len(sqlite_db.available_migrations())
    assert sqlite_db.integrity_check(upgraded) is None

    price = dict(upgraded.execute("SELECT * FROM price_snapshots").fetchone())
    assert price["symbol"] == "COMI"
    assert price["close_price"] == "50"
    # New provenance columns exist with a safe default, not a guessed OFFICIAL tag.
    assert price["source_tier"] == "IMPORT"

    # The new Phase 2 tables exist and are queryable (empty, not missing).
    assert upgraded.execute("SELECT COUNT(*) FROM external_documents").fetchone()[0] == 0
    assert upgraded.execute("SELECT COUNT(*) FROM financial_facts").fetchone()[0] == 0
    assert upgraded.execute("SELECT COUNT(*) FROM ingestion_runs").fetchone()[0] == 0


def test_backup_produces_a_readable_copy(home):
    connection = sqlite_db.initialize(home / "data" / "test.db")
    Repositories(connection).accounts.add("Backed Up")
    target = sqlite_db.backup(connection, home / "backups" / "copy.db")
    restored = sqlite_db.connect(target)
    assert Repositories(restored).accounts.get_by_name("Backed Up").name == "Backed Up"


def test_duplicate_transactions_are_blocked_by_default(context, account):
    repos = context.repos
    transaction = ledger.build_cash_transaction(
        ledger.DEPOSIT, account.id, "1000", transaction_date="2026-01-01")
    repos.transactions.add(transaction)
    with pytest.raises(DuplicateTransactionError):
        repos.transactions.add(transaction)


def test_an_intentional_repeat_is_allowed_explicitly(context, account):
    repos = context.repos
    transaction = ledger.build_cash_transaction(
        ledger.DEPOSIT, account.id, "1000", transaction_date="2026-01-01")
    first = repos.transactions.add(transaction)
    second = repos.transactions.add(transaction, allow_duplicate=True)
    assert first.id != second.id
    assert len(repos.transactions.list_for_account(account.id)) == 2


def test_accounts_are_resolvable_by_id_or_name(context, account):
    repos = context.repos
    assert repos.accounts.resolve(account.id).id == account.id
    assert repos.accounts.resolve(account.name).id == account.id
    assert repos.accounts.resolve(str(account.id)).id == account.id
    with pytest.raises(NotFoundError):
        repos.accounts.resolve("No Such Account")


def test_price_lookup_uses_the_latest_snapshot_on_or_before_the_date(context):
    repos = context.repos
    instrument = repos.instruments.upsert("COMI")
    repos.prices.set_price(instrument.id, "COMI", "50", "2026-01-01")
    repos.prices.set_price(instrument.id, "COMI", "60", "2026-02-01")
    assert repos.prices.latest_mark("COMI", "2026-01-15").price_date == "2026-01-01"
    assert repos.prices.latest_mark("COMI", "2026-03-01").price_date == "2026-02-01"
    assert repos.prices.latest_mark("COMI", "2025-12-01") is None


def test_setting_the_same_price_date_twice_updates_rather_than_duplicates(context):
    repos = context.repos
    instrument = repos.instruments.upsert("COMI")
    repos.prices.set_price(instrument.id, "COMI", "50", "2026-01-01")
    repos.prices.set_price(instrument.id, "COMI", "55", "2026-01-01")
    assert len(repos.prices.history("COMI")) == 1
    assert str(repos.prices.latest_mark("COMI").price) == "55.0000"


def test_superseding_keeps_the_original_row(context, account):
    repos = context.repos
    original = repos.transactions.add(ledger.build_cash_transaction(
        ledger.DEPOSIT, account.id, "1000", transaction_date="2026-01-01"))
    correction = repos.transactions.add(ledger.build_cash_transaction(
        ledger.DEPOSIT, account.id, "1500", transaction_date="2026-01-01"))
    repos.transactions.mark_superseded(original.id, correction.id)
    active = repos.transactions.list_for_account(account.id)
    assert [t.id for t in active] == [correction.id]
    assert len(repos.transactions.list_for_account(account.id, include_superseded=True)) == 2


def test_financial_writes_are_audited(portfolio_service, context, account):
    portfolio_service.record_cash(account.id, "DEPOSIT", "1000")
    portfolio_service.record_trade(account.id, "BUY", "COMI", "10", "50")
    portfolio_service.set_price("COMI", "55")
    actions = [entry["action"] for entry in context.repos.audit.list()]
    assert "ACCOUNT_CREATED" in actions
    assert "TRANSACTION_DEPOSIT" in actions
    assert "TRANSACTION_BUY" in actions
    assert "PRICE_SET" in actions


def test_run_can_be_found_by_unique_prefix(context):
    repos = context.repos
    repos.research_runs.create("run-2026-01-01-abcdef01", "q", "CREATED", "1.0")
    assert repos.research_runs.find("run-2026-01-01-abc")["id"] == "run-2026-01-01-abcdef01"
    with pytest.raises(NotFoundError):
        repos.research_runs.find("run-nope")


# ---- Phase 2: documents, financial facts, ingestion runs -----------------

def test_document_repository_upserts_by_external_id_fingerprint(context):
    repos = context.repos
    instrument = repos.instruments.upsert("COMI")
    first = repos.documents.add(
        document_type="BOARD_DECISION", title="Original", source_name="EGX",
        content_hash="abc", symbol="COMI", instrument_id=instrument.id,
        external_id="EGX-1",
    )
    assert first["_was_new"] is True
    second = repos.documents.add(
        document_type="BOARD_DECISION", title="Corrected", source_name="EGX",
        content_hash="def", symbol="COMI", instrument_id=instrument.id,
        external_id="EGX-1",
    )
    assert second["_was_new"] is False
    assert second["id"] == first["id"]
    assert second["title"] == "Corrected"
    assert len(repos.documents.list_for_symbol("COMI")) == 1


def test_document_repository_without_external_id_dedupes_by_content_hash(context):
    repos = context.repos
    first = repos.documents.add(
        document_type="OTHER", title="A", source_name="manual", content_hash="samehash",
    )
    second = repos.documents.add(
        document_type="OTHER", title="A again", source_name="manual",
        content_hash="samehash",
    )
    assert first["id"] == second["id"]
    assert second["_was_new"] is False


def test_document_repository_find_by_external_id_ignores_source_name(context):
    """A financial fact and the document it cites are commonly attributed to
    different named sources; linking must not require them to match."""
    repos = context.repos
    doc = repos.documents.add(
        document_type="ANNUAL_REPORT", title="Report", source_name="EGX disclosures",
        content_hash="h1", external_id="EGX-COMI-2025-AR",
    )
    found = repos.documents.find_by_external_id("EGX-COMI-2025-AR")
    assert found["id"] == doc["id"]
    assert repos.documents.find_by_external_id("no-such-id") is None


def test_financial_fact_repository_upserts_by_fingerprint(context):
    repos = context.repos
    instrument = repos.instruments.upsert("COMI")
    first = repos.financial_facts.add(
        instrument_id=instrument.id, symbol="COMI", period_end="2025-12-31",
        period_type="ANNUAL", metric="revenue", value="100", source_name="src",
    )
    assert first["_was_new"] is True
    second = repos.financial_facts.add(
        instrument_id=instrument.id, symbol="COMI", period_end="2025-12-31",
        period_type="ANNUAL", metric="revenue", value="150", source_name="src",
    )
    assert second["_was_new"] is False
    assert second["id"] == first["id"]
    assert second["value"] == "150"
    assert len(repos.financial_facts.list_for_symbol("COMI")) == 1


def test_financial_fact_repository_different_metric_is_a_different_fact(context):
    repos = context.repos
    instrument = repos.instruments.upsert("COMI")
    repos.financial_facts.add(
        instrument_id=instrument.id, symbol="COMI", period_end="2025-12-31",
        period_type="ANNUAL", metric="revenue", value="100", source_name="src",
    )
    repos.financial_facts.add(
        instrument_id=instrument.id, symbol="COMI", period_end="2025-12-31",
        period_type="ANNUAL", metric="net_income", value="20", source_name="src",
    )
    assert len(repos.financial_facts.list_for_symbol("COMI")) == 2


def test_ingestion_run_repository_records_and_lists(context):
    from economic.data_providers.base import IngestionReport

    report = IngestionReport(provider="price_file", kind="prices", ok=True,
                             source="p.csv", read=2, inserted=2)
    report.completed_at = report.started_at
    context.repos.ingestion_runs.record(report)

    runs = context.repos.ingestion_runs.list()
    assert len(runs) == 1
    assert runs[0]["kind"] == "prices"
    assert runs[0]["inserted_count"] == 2

    filtered = context.repos.ingestion_runs.list(kind="disclosures")
    assert filtered == []


def test_instrument_isin_is_persisted_and_retrievable(context):
    repos = context.repos
    repos.instruments.upsert("COMI")
    repos.instruments.set_isin("COMI", "EGS60121C018")
    instrument = repos.instruments.get_by_symbol("COMI")
    assert instrument.isin == "EGS60121C018"


def test_official_source_is_preferred_over_a_lower_tier_for_the_same_date(context):
    """Phase 2 gate: official-source data is preferred when available."""
    repos = context.repos
    instrument = repos.instruments.upsert("COMI")
    repos.prices.set_price(instrument.id, "COMI", "60", "2026-09-08",
                           source="forum-tip", source_tier="COMMUNITY")
    repos.prices.set_price(instrument.id, "COMI", "74.25", "2026-09-08",
                           source="EGX prices page", source_tier="OFFICIAL")
    mark = repos.prices.latest_mark("COMI")
    assert mark.source == "EGX prices page"
    assert str(mark.price) == "74.2500"


def test_tier_preference_does_not_override_a_more_recent_date(context):
    """A stale official price never beats a fresher lower-tier one — freshness
    still wins first; tier only breaks a tie on the same date."""
    repos = context.repos
    instrument = repos.instruments.upsert("COMI")
    repos.prices.set_price(instrument.id, "COMI", "50", "2026-09-01",
                           source="EGX prices page", source_tier="OFFICIAL")
    repos.prices.set_price(instrument.id, "COMI", "60", "2026-09-08",
                           source="forum-tip", source_tier="COMMUNITY")
    mark = repos.prices.latest_mark("COMI")
    assert mark.price_date == "2026-09-08"
    assert mark.source == "forum-tip"


def test_pre_phase_2_rows_default_to_import_tier_and_break_ties_by_recency(context):
    """Existing behavior for same-tier rows (the only case Phase 1 ever had)
    must be unchanged: most recently written wins."""
    repos = context.repos
    instrument = repos.instruments.upsert("COMI")
    repos.prices.set_price(instrument.id, "COMI", "50", "2026-09-08", source="manual")
    repos.prices.set_price(instrument.id, "COMI", "55", "2026-09-08", source="manual-2")
    mark = repos.prices.latest_mark("COMI")
    assert str(mark.price) == "55.0000"
