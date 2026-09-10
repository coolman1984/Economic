"""Ledger arithmetic and validation rules."""

from decimal import Decimal

import pytest

from economic.domain import ledger
from economic.domain.money import AmountError


def test_deposit_credits_the_exact_amount():
    transaction = ledger.build_cash_transaction(ledger.DEPOSIT, 1, "1000.50")
    assert transaction.cash_amount == Decimal("1000.50")


def test_deposit_fee_is_deducted():
    transaction = ledger.build_cash_transaction(ledger.DEPOSIT, 1, "1000", fees="25")
    assert transaction.cash_amount == Decimal("975")


def test_withdrawal_debits_amount_plus_fee():
    transaction = ledger.build_cash_transaction(ledger.WITHDRAW, 1, "1000", fees="25")
    assert transaction.cash_amount == Decimal("-1025")


def test_buy_cash_effect_includes_commission_and_fees():
    transaction = ledger.build_trade_transaction(
        ledger.BUY, 1, "COMI", "100", "52.50", commission="10", fees="2.5")
    assert transaction.cash_amount == Decimal("-5262.50")


def test_sell_cash_effect_subtracts_charges():
    transaction = ledger.build_trade_transaction(
        ledger.SELL, 1, "COMI", "100", "52.50", commission="10", fees="2.5")
    assert transaction.cash_amount == Decimal("5237.50")


@pytest.mark.parametrize("qty,price", [("0", "10"), ("-5", "10"), ("10", "0"), ("10", "-1")])
def test_trades_reject_non_positive_quantity_or_price(qty, price):
    with pytest.raises(ledger.LedgerError):
        ledger.build_trade_transaction(ledger.BUY, 1, "COMI", qty, price)


def test_negative_fees_are_rejected():
    with pytest.raises(ledger.LedgerError):
        ledger.build_trade_transaction(ledger.BUY, 1, "COMI", "1", "1", fees="-1")


def test_zero_or_negative_cash_amount_is_rejected():
    with pytest.raises(ledger.LedgerError):
        ledger.build_cash_transaction(ledger.DEPOSIT, 1, "0")


def test_symbols_are_normalized_and_validated():
    transaction = ledger.build_trade_transaction(ledger.BUY, 1, " comi ", "1", "1")
    assert transaction.symbol == "COMI"
    with pytest.raises(ledger.LedgerError):
        ledger.build_trade_transaction(ledger.BUY, 1, "bad symbol!", "1", "1")


def test_float_amounts_are_rejected_to_protect_precision():
    with pytest.raises(AmountError):
        ledger.build_cash_transaction(ledger.DEPOSIT, 1, 1000.10)


def test_invalid_date_is_rejected():
    with pytest.raises(ledger.LedgerError):
        ledger.build_cash_transaction(ledger.DEPOSIT, 1, "100", transaction_date="not-a-date")


def test_fingerprint_uses_external_reference_when_present():
    common = dict(transaction_type=ledger.BUY, account_id=1, symbol="COMI", qty="10",
                  price="5", transaction_date="2026-01-01")
    first = ledger.build_trade_transaction(**common, external_reference="BROKER-1")
    second = ledger.build_trade_transaction(**common, external_reference="BROKER-1")
    third = ledger.build_trade_transaction(**common, external_reference="BROKER-2")
    assert first.fingerprint() == second.fingerprint()
    assert first.fingerprint() != third.fingerprint()


def test_ordering_is_deterministic_by_date_then_sequence():
    late = ledger.build_cash_transaction(ledger.DEPOSIT, 1, "1", transaction_date="2026-02-01")
    early = ledger.build_cash_transaction(ledger.DEPOSIT, 1, "2", transaction_date="2026-01-01")
    ordered = ledger.ordered([late, early])
    assert [t.transaction_date for t in ordered] == ["2026-01-01", "2026-02-01"]


def test_superseded_transactions_are_excluded_from_replay():
    original = ledger.build_cash_transaction(ledger.DEPOSIT, 1, "100")
    object.__setattr__(original, "superseded_by_transaction_id", 99)
    correction = ledger.build_cash_transaction(ledger.DEPOSIT, 1, "150")
    assert ledger.ordered([original, correction]) == [correction]
