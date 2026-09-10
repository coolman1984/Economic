"""Phase 1 hardening regressions (ADR-020, ADR-021).

Each test here corresponds to a defect found in the hardening audit. They prove
the fix is enforced end to end — in the database and in what the human is told —
not merely requested in a prompt.
"""

import json

import pytest

from economic.agents import base_adapter, contracts
from economic.agents.mock_adapter import MockAdapter
from economic.application import research_service as research_module
from economic.domain import risk


def chair_saying(payload):
    """A provider that behaves normally except when asked to chair."""

    class Chair(MockAdapter):
        def run(self, prompt, contract, role, stage, timeout_seconds=None):
            self.raw_override = (
                json.dumps(payload) if contract == contracts.CHAIR_SYNTHESIS else None)
            return super().run(prompt, contract, role, stage, timeout_seconds)

    return Chair


def synthesis(actions, data_quality=100, agreement=95):
    return {
        "status": "complete", "summary": "committee summary",
        "data_quality_score": data_quality, "agreement_score": agreement,
        "ranked_actions": actions, "human_decision_required": True,
    }


def ranked(symbol, action, confidence=95, rank=1):
    return {"rank": rank, "symbol": symbol, "action": action, "confidence": confidence,
            "why": ["a reason"], "strongest_counterargument": "a counterargument",
            "invalidators": [], "portfolio_effect": "some effect"}


@pytest.fixture
def portfolio(portfolio_service):
    """One priced holding, one unpriced holding, plenty of cash."""
    account = portfolio_service.add_account("Hardening")
    portfolio_service.record_cash(account.id, "DEPOSIT", "200000",
                                  transaction_date="2026-01-01")
    portfolio_service.record_trade(account.id, "BUY", "COMI", "1000", "50",
                                   transaction_date="2026-01-02")
    portfolio_service.set_price("COMI", "60", price_date="2026-01-10")
    return account


@pytest.fixture
def fully_priced(portfolio_service):
    account = portfolio_service.add_account("Clean")
    portfolio_service.record_cash(account.id, "DEPOSIT", "200000",
                                  transaction_date="2026-01-01")
    portfolio_service.record_trade(account.id, "BUY", "COMI", "1000", "50",
                                   transaction_date="2026-01-02")
    portfolio_service.set_price("COMI", "60", price_date="2026-01-10")
    return account


@pytest.fixture
def adapters(monkeypatch):
    """Install a provider set for one run; restores itself afterwards."""
    original = research_module.build_adapters

    def install(**providers):
        def build(config, mock=None, providers_arg=None, **_kwargs):
            return dict(providers)
        monkeypatch.setattr(research_module, "build_adapters", build)

    yield install
    monkeypatch.setattr(research_module, "build_adapters", original)


def run(research_service, account, **kwargs):
    return research_service.run_committee(
        question="what should I do?", account_reference=account.id, mock=True,
        as_of="2026-01-10", chair="claude", **kwargs)


# --- F1: a single surviving agent is a degraded committee -------------------

def test_a_single_surviving_agent_is_recorded_as_degraded(
        research_service, portfolio, adapters):
    adapters(codex=MockAdapter("codex", failure_kind=base_adapter.TIMEOUT),
             claude=MockAdapter("claude"))
    payload = run(research_service, portfolio)

    assert payload["run"]["committee_mode"] == "DEGRADED"
    assert payload["run"]["degraded"] is True
    assert payload["run"]["analyst_count"] == 1
    assert payload["run"]["critique_count"] == 0
    assert payload["committee_integrity"]["reasons"]


def test_a_full_committee_is_recorded_as_full(research_service, portfolio, adapters):
    adapters(codex=MockAdapter("codex"), claude=MockAdapter("claude"))
    payload = run(research_service, portfolio)

    assert payload["run"]["committee_mode"] == "FULL"
    assert payload["run"]["degraded"] is False
    assert payload["run"]["analyst_count"] == 2
    assert payload["run"]["critique_count"] == 2


def test_a_fabricated_agreement_score_is_not_recorded_for_one_analyst(
        research_service, portfolio, adapters):
    """The chair claims 95% agreement while alone. The system records nothing."""
    adapters(codex=MockAdapter("codex", failure_kind=base_adapter.TIMEOUT),
             claude=chair_saying(synthesis([ranked("COMI", "HOLD")], agreement=95))("claude"))
    payload = run(research_service, portfolio)

    assert payload["run"]["agreement_score"] is None
    # The claim itself is still preserved verbatim for audit.
    assert payload["synthesis"]["agreement_score"] == 95


def test_agreement_is_recorded_when_two_analyses_exist(
        research_service, portfolio, adapters):
    adapters(codex=MockAdapter("codex"),
             claude=chair_saying(synthesis([ranked("COMI", "HOLD")], agreement=71))("claude"))
    payload = run(research_service, portfolio)
    assert payload["run"]["agreement_score"] == 71


def test_a_degraded_committee_cannot_emit_an_actionable_recommendation(
        research_service, fully_priced, adapters):
    """Perfect price data does not buy back a missing second agent."""
    adapters(codex=MockAdapter("codex", failure_kind=base_adapter.TIMEOUT),
             claude=chair_saying(synthesis([ranked("COMI", "BUY", 99)]))("claude"))
    payload = run(research_service, fully_priced)

    recommendation = payload["recommendations"][0]
    assert recommendation["action"] == "WATCH"
    assert recommendation["proposed_action"] == "BUY"
    assert recommendation["restricted"] is True
    assert recommendation["confidence"] == risk.DEGRADED_COMMITTEE_CONFIDENCE_CEILING
    assert recommendation["proposed_confidence"] == 99
    assert any("degraded" in reason for reason in recommendation["restriction_reasons"])


# --- F2: missing and stale data restrict actionable recommendations ---------

def test_a_buy_on_an_unpriced_security_is_restricted_in_the_database(
        research_service, portfolio_service, portfolio, adapters):
    portfolio_service.record_trade(portfolio.id, "BUY", "GHOST", "1000", "30",
                                   transaction_date="2026-01-02")
    adapters(codex=MockAdapter("codex"),
             claude=chair_saying(synthesis([ranked("GHOST", "BUY", 95)]))("claude"))
    payload = run(research_service, portfolio)

    recommendation = payload["recommendations"][0]
    assert recommendation["action"] == "WATCH"
    assert recommendation["proposed_action"] == "BUY"
    assert recommendation["restricted"] is True
    assert any("no price snapshot" in reason
               for reason in recommendation["restriction_reasons"])


def test_a_sell_on_a_stale_price_is_restricted(
        research_service, portfolio_service, adapters):
    account = portfolio_service.add_account("Stale")
    portfolio_service.record_cash(account.id, "DEPOSIT", "100000",
                                  transaction_date="2026-01-01")
    portfolio_service.record_trade(account.id, "BUY", "COMI", "100", "50",
                                   transaction_date="2026-01-02")
    portfolio_service.set_price("COMI", "60", price_date="2026-01-03")

    adapters(codex=MockAdapter("codex"),
             claude=chair_saying(synthesis([ranked("COMI", "SELL", 90)]))("claude"))
    payload = research_service.run_committee(
        question="sell?", account_reference=account.id, mock=True,
        as_of="2026-03-01", chair="claude")

    recommendation = payload["recommendations"][0]
    assert recommendation["restricted"] is True
    assert recommendation["action"] == "WATCH"
    assert any("stale price" in reason for reason in recommendation["restriction_reasons"])


def test_good_evidence_and_a_full_committee_leave_an_action_actionable(
        research_service, fully_priced, adapters):
    """The gate must restrict thin evidence, not block every recommendation."""
    adapters(codex=MockAdapter("codex"),
             claude=chair_saying(synthesis([ranked("COMI", "REDUCE", 80)]))("claude"))
    payload = run(research_service, fully_priced)

    recommendation = payload["recommendations"][0]
    assert recommendation["action"] == "REDUCE"
    assert recommendation["restricted"] is False
    assert recommendation["confidence"] == 80
    assert recommendation["restriction_reasons"] is None


def test_the_deterministic_data_quality_score_is_stored_not_the_chairs(
        research_service, portfolio_service, portfolio, adapters):
    portfolio_service.record_trade(portfolio.id, "BUY", "GHOST", "1000", "30",
                                   transaction_date="2026-01-02")
    adapters(codex=MockAdapter("codex"),
             claude=chair_saying(
                 synthesis([ranked("COMI", "HOLD")], data_quality=100))("claude"))
    payload = run(research_service, portfolio)

    deterministic = payload["run"]["portfolio_snapshot"]["data_quality_score"]
    assert deterministic < 100
    assert payload["run"]["data_quality_score"] == deterministic
    assert payload["recommendations"][0]["data_quality_score"] == deterministic
    assert payload["synthesis"]["data_quality_score"] == 100  # claim preserved


def test_the_evidence_gate_used_for_the_run_is_persisted(
        research_service, portfolio, adapters):
    adapters(codex=MockAdapter("codex"), claude=MockAdapter("claude"))
    payload = run(research_service, portfolio)
    gate = payload["evidence_gate"]
    assert gate["min_data_quality"] == 50
    assert "data_quality_score" in gate
    assert gate["committee_degraded"] is False


# --- F3: duplicate ranks must not break persistence -------------------------

def test_duplicate_ranks_from_the_chair_do_not_break_the_run(
        research_service, fully_priced, adapters):
    actions = [ranked("COMI", "HOLD", 60, rank=1), ranked("COMI", "WATCH", 50, rank=1),
               ranked("COMI", "NO_ACTION", 40, rank=1)]
    adapters(codex=MockAdapter("codex"),
             claude=chair_saying(synthesis(actions))("claude"))
    payload = run(research_service, fully_priced)

    assert payload["run"]["status"] == "READY_FOR_HUMAN"
    assert [r["rank"] for r in payload["recommendations"]] == [1, 2, 3]


# --- invariants the hardening must not have broken --------------------------

def test_a_restricted_recommendation_can_still_be_decided_by_the_human(
        research_service, decision_service, portfolio_service, fully_priced, adapters):
    """The gate restricts what the software asserts, never the human's authority."""
    adapters(codex=MockAdapter("codex", failure_kind=base_adapter.TIMEOUT),
             claude=chair_saying(synthesis([ranked("COMI", "BUY", 99)]))("claude"))
    payload = run(research_service, fully_priced)
    recommendation_id = payload["recommendations"][0]["id"]

    before = portfolio_service.snapshot(fully_priced.id, "2026-01-10")
    record = decision_service.record(payload["run"]["id"], "APPROVE",
                                     recommendation_id=recommendation_id,
                                     note="I accept the risk")

    assert record["decision"] == "APPROVE"
    assert record["created_transaction"] is False
    assert record["committee_degraded"] is True
    assert record["restricted_recommendation"] == "BUY"
    assert portfolio_service.snapshot(fully_priced.id, "2026-01-10") == before


def test_a_degraded_run_reloads_from_history_with_its_labels(
        research_service, portfolio, adapters):
    adapters(codex=MockAdapter("codex", failure_kind=base_adapter.TIMEOUT),
             claude=MockAdapter("claude"))
    run_id = run(research_service, portfolio)["run"]["id"]

    reloaded = research_service.get_run(run_id)
    assert reloaded["run"]["committee_mode"] == "DEGRADED"
    assert reloaded["committee_integrity"]["analyst_count"] == 1
    assert reloaded["evidence_gate"]["committee_degraded"] is True


def test_history_listing_exposes_the_committee_mode(
        research_service, portfolio, adapters):
    adapters(codex=MockAdapter("codex", failure_kind=base_adapter.TIMEOUT),
             claude=MockAdapter("claude"))
    run(research_service, portfolio)
    assert research_service.list_runs(limit=1)[0]["committee_mode"] == "DEGRADED"
