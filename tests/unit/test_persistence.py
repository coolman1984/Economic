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
