"""What-if simulation: correctness and the non-mutation invariant."""

from decimal import Decimal

from economic.domain import ledger, portfolio, simulation
from economic.domain.portfolio import PriceMark


def base_state():
    transactions = []
    for index, transaction in enumerate([
        ledger.build_cash_transaction(ledger.DEPOSIT, 1, "100000"),
        ledger.build_trade_transaction(ledger.BUY, 1, "COMI", "100", "50", commission="10"),
    ]):
        object.__setattr__(transaction, "sequence", index)
        transactions.append(transaction)
    return portfolio.rebuild(transactions, account_id=1)


MARKS = {"COMI": PriceMark("COMI", Decimal("60"), "2026-01-10")}


def test_buy_simulation_reports_post_trade_cash_and_quantity():
    result = simulation.simulate_trade(
        base_state(), MARKS, "BUY", "COMI", "100", "60", commission="15", as_of="2026-01-10")
    assert result.ok
    assert result.after["cash"] == "88975"      # 94990 - (6000 + 15)
    assert result.after["quantity"] == "200"
    assert result.cash_effect == Decimal("-6015")


def test_sell_simulation_validates_available_quantity():
    result = simulation.simulate_trade(
        base_state(), MARKS, "SELL", "COMI", "500", "60", as_of="2026-01-10")
    assert not result.ok
    assert "only 100 held" in result.errors[0]


def test_simulation_reports_resulting_position_weight():
    result = simulation.simulate_trade(
        base_state(), MARKS, "BUY", "COMI", "100", "60", as_of="2026-01-10")
    assert Decimal(result.after["weight_pct"]) > Decimal(result.before["weight_pct"])
    assert Decimal(result.after["weight_pct"]) == Decimal("11.8824")  # 12000 / 100990


def test_simulation_never_mutates_the_state_it_was_given():
    state = base_state()
    before = (state.cash, state.positions["COMI"].quantity,
              state.positions["COMI"].cost_basis, state.transaction_count)
    simulation.simulate_trade(state, MARKS, "BUY", "COMI", "100", "60", as_of="2026-01-10")
    simulation.simulate_trade(state, MARKS, "SELL", "COMI", "50", "60", as_of="2026-01-10")
    after = (state.cash, state.positions["COMI"].quantity,
             state.positions["COMI"].cost_basis, state.transaction_count)
    assert before == after


def test_simulation_is_deterministic_for_identical_inputs():
    first = simulation.simulate_trade(
        base_state(), MARKS, "BUY", "COMI", "100", "60", as_of="2026-01-10")
    second = simulation.simulate_trade(
        base_state(), MARKS, "BUY", "COMI", "100", "60", as_of="2026-01-10")
    assert first.to_dict() == second.to_dict()


def test_warnings_flag_rule_breaches_without_blocking_the_answer():
    result = simulation.simulate_trade(
        base_state(), MARKS, "BUY", "COMI", "1000", "60", as_of="2026-01-10",
        min_cash=Decimal("50000"), max_position_weight_pct=Decimal("20"))
    assert result.ok
    joined = " ".join(result.warnings)
    assert "minimum cash" in joined and "maximum position weight" in joined


def test_invalid_input_is_reported_not_raised():
    result = simulation.simulate_trade(
        base_state(), MARKS, "BUY", "COMI", "-5", "60", as_of="2026-01-10")
    assert not result.ok and result.errors
