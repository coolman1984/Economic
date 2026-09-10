"""Persistence and reproducibility across restarts."""

from economic.application.context import AppContext
from economic.application.decision_service import DecisionService
from economic.application.portfolio_service import PortfolioService
from economic.application.research_service import ResearchService
from economic.domain import decisions as decision_rules


def reopen(home):
    return AppContext.open(home=home, overrides={"agents": {"mock": True}})


def test_accounts_and_transactions_survive_a_restart(home):
    with reopen(home) as context:
        service = PortfolioService(context)
        account = service.add_account("Persistent")
        service.record_cash(account.id, "DEPOSIT", "100000", transaction_date="2026-01-01")
        service.record_trade(account.id, "BUY", "COMI", "100", "50",
                             commission="10", transaction_date="2026-01-02")
        service.set_price("COMI", "60", price_date="2026-01-10")
        original = service.snapshot(account.id, "2026-01-10")

    with reopen(home) as context:
        service = PortfolioService(context)
        reloaded = service.snapshot(service.resolve_account("Persistent").id, "2026-01-10")

    assert reloaded == original
    assert reloaded["cash"] == "94990"
    assert reloaded["total_equity"] == "100990"


def test_rebuilding_from_sqlite_reproduces_the_same_portfolio(home):
    with reopen(home) as context:
        service = PortfolioService(context)
        account = service.add_account("Rebuild")
        service.record_cash(account.id, "DEPOSIT", "50000", transaction_date="2026-01-01")
        for index, (qty, price, date) in enumerate(
                [("100", "50", "2026-01-02"), ("50", "55", "2026-01-05"),
                 ("25", "58", "2026-01-08")]):
            service.record_trade(account.id, "BUY", "COMI", qty, price, transaction_date=date)
        service.record_trade(account.id, "SELL", "COMI", "60", "62",
                             transaction_date="2026-01-09")
        first = service.state_for_account(account.id)

    with reopen(home) as context:
        service = PortfolioService(context)
        second = service.state_for_account(service.resolve_account("Rebuild").id)

    assert first.cash == second.cash
    assert first.positions["COMI"].quantity == second.positions["COMI"].quantity
    assert first.positions["COMI"].cost_basis == second.positions["COMI"].cost_basis
    assert first.positions["COMI"].realized_pnl == second.positions["COMI"].realized_pnl


def test_a_complete_decision_run_reloads_from_history(home):
    with reopen(home) as context:
        portfolio_service = PortfolioService(context)
        account = portfolio_service.add_account("History")
        portfolio_service.record_cash(account.id, "DEPOSIT", "100000",
                                      transaction_date="2026-01-01")
        portfolio_service.record_trade(account.id, "BUY", "COMI", "100", "50",
                                       transaction_date="2026-01-02")
        portfolio_service.set_price("COMI", "60", price_date="2026-01-10")

        payload = ResearchService(context).run_committee(
            question="Should I trim COMI?", account_reference=account.id,
            mock=True, as_of="2026-01-10")
        run_id = payload["run"]["id"]
        recommendation_id = payload["recommendations"][0]["id"]
        DecisionService(context).record(
            run_id, "MODIFY", recommendation_id=recommendation_id,
            modified_action="REDUCE", note="Trimming half instead of holding.")

    with reopen(home) as context:
        reloaded = ResearchService(context).get_run(run_id)

    assert reloaded["run"]["status"] == decision_rules.HUMAN_MODIFIED
    assert reloaded["run"]["question"] == "Should I trim COMI?"
    assert reloaded["run"]["portfolio_snapshot"]["cash"] == "95000"
    assert reloaded["synthesis"]["human_decision_required"] is True
    assert len(reloaded["agent_runs"]) == 5      # 2 analyses + 2 critiques + 1 synthesis
    assert reloaded["recommendations"]
    decision = reloaded["decisions"][0]
    assert decision["decision"] == "MODIFY"
    assert decision["modified_action"] == "REDUCE"
    assert decision["recommendation_id"] == recommendation_id


def test_history_does_not_change_when_the_portfolio_changes_later(home):
    with reopen(home) as context:
        portfolio_service = PortfolioService(context)
        account = portfolio_service.add_account("Frozen")
        portfolio_service.record_cash(account.id, "DEPOSIT", "100000",
                                      transaction_date="2026-01-01")
        payload = ResearchService(context).run_committee(
            question="Anything to do?", account_reference=account.id,
            mock=True, as_of="2026-01-10")
        run_id = payload["run"]["id"]
        snapshot_then = payload["run"]["portfolio_snapshot"]

        # The portfolio moves on afterwards.
        portfolio_service.record_trade(account.id, "BUY", "COMI", "500", "40",
                                       transaction_date="2026-02-01")
        reloaded = ResearchService(context).get_run(run_id)

    assert reloaded["run"]["portfolio_snapshot"] == snapshot_then
    assert reloaded["run"]["portfolio_snapshot"]["cash"] == "100000"
