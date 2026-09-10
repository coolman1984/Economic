"""Deterministic portfolio engine: cost, P&L, valuation, and invariants."""

from decimal import Decimal

import pytest

from economic.domain import ledger, portfolio, risk
from economic.domain.portfolio import PriceMark


def _tx(index, transaction):
    object.__setattr__(transaction, "sequence", index)
    return transaction


def build(*transactions):
    return portfolio.rebuild(
        [_tx(index, transaction) for index, transaction in enumerate(transactions)],
        account_id=1,
    )


def deposit(amount, date="2026-01-01"):
    return ledger.build_cash_transaction(ledger.DEPOSIT, 1, amount, transaction_date=date)


def buy(symbol, qty, price, commission="0", date="2026-01-02"):
    return ledger.build_trade_transaction(
        ledger.BUY, 1, symbol, qty, price, commission=commission, transaction_date=date)


def sell(symbol, qty, price, commission="0", date="2026-01-03"):
    return ledger.build_trade_transaction(
        ledger.SELL, 1, symbol, qty, price, commission=commission, transaction_date=date)


def test_cash_math_for_deposit_and_withdrawal():
    state = build(deposit("1000"),
                  ledger.build_cash_transaction(ledger.WITHDRAW, 1, "250"))
    assert state.cash == Decimal("750")


def test_multiple_buys_use_weighted_average_cost_including_charges():
    state = build(deposit("100000"),
                  buy("COMI", "100", "50", commission="10"),
                  buy("COMI", "100", "60", commission="10"))
    position = state.positions["COMI"]
    assert position.quantity == Decimal("200")
    assert position.cost_basis == Decimal("11020")
    assert position.average_cost == Decimal("55.10")
    assert state.cash == Decimal("88980")


def test_partial_sell_realizes_pnl_against_average_cost():
    state = build(deposit("100000"),
                  buy("COMI", "100", "50", commission="10"),
                  buy("COMI", "100", "60", commission="10"),
                  sell("COMI", "100", "70", commission="10"))
    position = state.positions["COMI"]
    # proceeds 6990, released cost 5510 -> realized 1480
    assert position.realized_pnl == Decimal("1480")
    assert position.quantity == Decimal("100")
    assert position.cost_basis == Decimal("5510")
    assert state.cash == Decimal("95970")


def test_closing_a_position_leaves_zero_quantity_and_zero_basis():
    state = build(deposit("100000"), buy("COMI", "100", "50"), sell("COMI", "100", "60"))
    position = state.positions["COMI"]
    assert position.quantity == Decimal("0")
    assert position.cost_basis == Decimal("0")
    assert position.average_cost is None
    assert position.realized_pnl == Decimal("1000")
    assert state.open_positions() == []


def test_selling_more_than_held_is_rejected():
    state = build(deposit("100000"), buy("COMI", "100", "50"))
    with pytest.raises(portfolio.PortfolioError, match="only 100 held"):
        portfolio.apply_transaction(state, sell("COMI", "101", "60"))


def test_selling_an_unheld_symbol_is_rejected():
    state = build(deposit("100000"))
    with pytest.raises(portfolio.PortfolioError, match="no open position"):
        portfolio.apply_transaction(state, sell("HRHO", "1", "60"))


def test_rebuilding_from_stored_transactions_is_reproducible():
    transactions = [_tx(index, transaction) for index, transaction in enumerate(
        [deposit("100000"), buy("COMI", "100", "50"), buy("COMI", "50", "55"),
         sell("COMI", "30", "60")])]
    first = portfolio.rebuild(transactions, account_id=1)
    second = portfolio.rebuild(list(reversed(transactions)), account_id=1)
    assert first.cash == second.cash
    assert first.positions["COMI"].cost_basis == second.positions["COMI"].cost_basis
    assert first.positions["COMI"].realized_pnl == second.positions["COMI"].realized_pnl


def test_valuation_uses_the_latest_mark_and_computes_equity():
    state = build(deposit("100000"), buy("COMI", "100", "50"))
    marks = {"COMI": PriceMark("COMI", Decimal("60"), "2026-01-10")}
    valuation = portfolio.value(state, marks, as_of="2026-01-10")
    assert valuation.market_value == Decimal("6000")
    assert valuation.unrealized_pnl == Decimal("1000")
    assert valuation.total_equity == Decimal("101000")
    assert valuation.weight_of("COMI") == Decimal("5.9406")
    assert valuation.is_complete


def test_missing_price_is_visible_and_never_guessed():
    state = build(deposit("100000"), buy("COMI", "100", "50"))
    valuation = portfolio.value(state, {}, as_of="2026-01-10")
    assert valuation.market_value == Decimal("0")
    assert valuation.total_equity == Decimal("95000")
    assert [p.symbol for p in valuation.unpriced_positions] == ["COMI"]
    assert not valuation.is_complete
    assert valuation.data_quality()["missing_prices"] == ["COMI"]


def test_stale_price_is_flagged_but_still_used():
    state = build(deposit("100000"), buy("COMI", "100", "50"))
    marks = {"COMI": PriceMark("COMI", Decimal("60"), "2026-01-01")}
    valuation = portfolio.value(state, marks, as_of="2026-01-30", stale_after_days=5)
    valued = valuation.positions[0]
    assert valued.is_stale and valued.price_age_days == 29
    assert valuation.market_value == Decimal("6000")


def test_accounts_stay_separated_and_consolidate_by_sum():
    first = build(deposit("50000"), buy("COMI", "100", "50"))
    second_transactions = [
        _tx(0, ledger.build_cash_transaction(ledger.DEPOSIT, 2, "20000")),
        _tx(1, ledger.build_trade_transaction(ledger.BUY, 2, "COMI", "50", "52")),
    ]
    second = portfolio.rebuild(second_transactions, account_id=2)
    assert first.quantity_of("COMI") == Decimal("100")
    assert second.quantity_of("COMI") == Decimal("50")

    combined = portfolio.merge([first, second])
    assert combined.cash == first.cash + second.cash
    assert combined.quantity_of("COMI") == Decimal("150")
    assert combined.positions["COMI"].cost_basis == (
        first.positions["COMI"].cost_basis + second.positions["COMI"].cost_basis)


def test_data_quality_score_reflects_pricing_completeness():
    state = build(deposit("100000"), buy("COMI", "100", "50"), buy("HRHO", "10", "20"))
    complete = portfolio.value(state, {
        "COMI": PriceMark("COMI", Decimal("60"), "2026-01-10"),
        "HRHO": PriceMark("HRHO", Decimal("21"), "2026-01-10"),
    }, as_of="2026-01-10")
    partial = portfolio.value(state, {
        "COMI": PriceMark("COMI", Decimal("60"), "2026-01-10")}, as_of="2026-01-10")
    assert risk.data_quality_score(complete) == 100
    assert risk.data_quality_score(partial) == 50


def test_snapshot_records_prices_and_gaps():
    state = build(deposit("100000"), buy("COMI", "100", "50"), buy("HRHO", "10", "20"))
    valuation = portfolio.value(
        state, {"COMI": PriceMark("COMI", Decimal("60"), "2026-01-10")}, as_of="2026-01-10")
    snapshot = portfolio.snapshot(valuation, state)
    assert snapshot["missing_prices"] == ["HRHO"]
    assert snapshot["prices_as_of"] == {"COMI": "2026-01-10"}
    assert snapshot["cash"] == "94800"
