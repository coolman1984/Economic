"""The human approval gate and the separation of decision from execution."""

import pytest

from economic.application.decision_service import DecisionService
from economic.domain import decisions as decision_rules


@pytest.fixture
def ready_run(portfolio_service, research_service):
    account = portfolio_service.add_account("Gate Account")
    portfolio_service.record_cash(account.id, "DEPOSIT", "100000",
                                  transaction_date="2026-01-01")
    portfolio_service.record_trade(account.id, "BUY", "COMI", "100", "50",
                                   transaction_date="2026-01-02")
    portfolio_service.set_price("COMI", "60", price_date="2026-01-10")
    payload = research_service.run_committee(
        question="Should I add to COMI?", account_reference=account.id,
        mock=True, as_of="2026-01-10")
    return account, payload


@pytest.mark.parametrize("decision,expected_state", [
    ("APPROVE", decision_rules.HUMAN_APPROVED),
    ("REJECT", decision_rules.HUMAN_REJECTED),
    ("HOLD", decision_rules.HUMAN_HELD),
])
def test_each_decision_is_recorded_and_moves_the_run(
        decision_service, ready_run, decision, expected_state):
    _, payload = ready_run
    record = decision_service.record(payload["run"]["id"], decision)
    assert record["decision"] == decision
    assert record["run_status"] == expected_state


def test_modify_requires_a_described_change(decision_service, ready_run):
    _, payload = ready_run
    with pytest.raises(decision_rules.DecisionError):
        decision_service.record(payload["run"]["id"], "MODIFY")
    record = decision_service.record(payload["run"]["id"], "MODIFY",
                                     modified_action="REDUCE", note="half only")
    assert record["modified_action"] == "REDUCE"


def test_approval_creates_no_transaction_and_no_position_change(
        decision_service, portfolio_service, ready_run):
    account, payload = ready_run
    before = portfolio_service.snapshot(account.id, "2026-01-10")
    transactions_before = len(
        portfolio_service.repos.transactions.list_for_account(account.id))

    record = decision_service.record(payload["run"]["id"], "APPROVE",
                                     recommendation_id=payload["recommendations"][0]["id"])

    assert record["created_transaction"] is False
    assert portfolio_service.snapshot(account.id, "2026-01-10") == before
    assert len(portfolio_service.repos.transactions.list_for_account(account.id)) == \
        transactions_before


def test_an_execution_is_a_separate_explicit_record(
        decision_service, portfolio_service, ready_run, context):
    account, payload = ready_run
    record = decision_service.record(payload["run"]["id"], "APPROVE")

    # The user acts at the broker, then records the real trade themselves.
    transaction = portfolio_service.record_trade(
        account.id, "BUY", "COMI", "50", "61", transaction_date="2026-01-11")
    execution_id = portfolio_service.record_execution(
        transaction.id, record["id"], note="filled at open")

    executions = context.repos.executions.list_for_decision(record["id"])
    assert [e["id"] for e in executions] == [execution_id]
    assert executions[0]["transaction_id"] == transaction.id


def test_a_decision_cannot_be_recorded_before_the_gate(decision_service, context):
    context.repos.research_runs.create(
        "run-2026-01-01-deadbeef", "premature?", decision_rules.INDEPENDENT_ANALYSIS, "1.0")
    with pytest.raises(decision_rules.DecisionError):
        decision_service.record("run-2026-01-01-deadbeef", "APPROVE")


def test_a_recommendation_from_another_run_is_rejected(
        decision_service, portfolio_service, research_service, ready_run):
    _, payload = ready_run
    other = research_service.run_committee(
        question="A different question", mock=True, as_of="2026-01-10")
    with pytest.raises(decision_rules.DecisionError, match="belongs to run"):
        decision_service.record(payload["run"]["id"], "APPROVE",
                                recommendation_id=other["recommendations"][0]["id"])


def test_every_decision_stays_in_history(decision_service, ready_run):
    _, payload = ready_run
    run_id = payload["run"]["id"]
    decision_service.record(run_id, "HOLD", note="waiting for results")
    decision_service.record(run_id, "APPROVE", note="results were fine")
    history = decision_service.list_for_run(run_id)
    assert [entry["decision"] for entry in history] == ["HOLD", "APPROVE"]
