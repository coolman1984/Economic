"""Full mock committee workflow, end to end."""

from decimal import Decimal

import pytest

from economic.agents import artifacts as artifact_module
from economic.agents import base_adapter, contracts
from economic.agents.mock_adapter import MockAdapter
from economic.application import research_service as research_module
from economic.domain import decisions as decision_rules


@pytest.fixture
def funded_account(portfolio_service):
    account = portfolio_service.add_account("Committee Account")
    portfolio_service.record_cash(account.id, "DEPOSIT", "200000", transaction_date="2026-01-01")
    portfolio_service.record_trade(account.id, "BUY", "COMI", "1000", "50",
                                   commission="100", transaction_date="2026-01-02")
    portfolio_service.record_trade(account.id, "BUY", "HRHO", "2000", "20",
                                   commission="80", transaction_date="2026-01-03")
    portfolio_service.set_price("COMI", "60", price_date="2026-01-10")
    # HRHO is intentionally left unpriced so the data-quality path is exercised.
    return account


def run_committee(research_service, account, **kwargs):
    return research_service.run_committee(
        question="What should I do with this portfolio?",
        account_reference=account.id, mock=True, as_of="2026-01-10", **kwargs)


def test_full_mock_committee_reaches_the_human_gate(research_service, funded_account):
    payload = run_committee(research_service, funded_account)
    run = payload["run"]
    assert run["status"] == decision_rules.READY_FOR_HUMAN
    assert run["id"].startswith("run-2026-01-10-")
    assert run["mode"] == "mock"
    assert payload["synthesis"]["human_decision_required"] is True
    assert payload["recommendations"]


def test_snapshot_is_saved_before_analysis_and_reflects_the_ledger(
        research_service, funded_account):
    payload = run_committee(research_service, funded_account)
    snapshot = payload["run"]["portfolio_snapshot"]
    assert snapshot["cash"] == "109820"          # 200000 - 50100 - 40080
    assert snapshot["missing_prices"] == ["HRHO"]
    assert snapshot["total_equity"] == "169820"  # cash + 60000 priced COMI


def test_both_providers_analyze_independently_before_cross_review(
        research_service, funded_account):
    payload = run_committee(research_service, funded_account)
    stages = [(a["agent_provider"], a["stage"], a["status"]) for a in payload["agent_runs"]]
    independent = [s for s in stages if s[1] == "INDEPENDENT_ANALYSIS"]
    review = [s for s in stages if s[1] == "CROSS_REVIEW"]
    assert {s[0] for s in independent} == {"codex", "claude"}
    assert {s[0] for s in review} == {"codex", "claude"}
    # every independent stage is recorded before any review stage
    assert max(stages.index(s) for s in independent) < min(stages.index(s) for s in review)


def test_exactly_one_cross_review_round_is_run(research_service, funded_account):
    payload = run_committee(research_service, funded_account)
    reviews = [a for a in payload["agent_runs"] if a["stage"] == "CROSS_REVIEW"]
    assert len(reviews) == 2  # one critique per provider = a single round
    assert any("review-round limit reached" in reason
               for reason in payload["stopped_because"])


def test_disagreements_are_recorded_not_hidden(research_service, funded_account):
    payload = run_committee(research_service, funded_account)
    assert payload["disagreements"]
    assert all(item["topic"] for item in payload["disagreements"])


def test_run_artifacts_are_written_to_disk(research_service, funded_account, context):
    payload = run_committee(research_service, funded_account)
    files = set(payload["artifact_files"])
    for expected in (artifact_module.PORTFOLIO_SNAPSHOT, artifact_module.FINAL_RECOMMENDATION,
                     artifact_module.RISK_REVIEW, artifact_module.RUN_META,
                     "codex_independent.json", "claude_independent.json",
                     "codex_critique.json", "claude_critique.json"):
        assert expected in files, expected
    assert any(name.startswith("raw/") for name in files)


def test_chair_is_configurable(research_service, funded_account):
    payload = run_committee(research_service, funded_account, chair="codex")
    assert payload["run"]["chair_provider"] == "codex"
    synthesis_runs = [a for a in payload["agent_runs"] if a["stage"] == "SYNTHESIS"]
    assert [a["agent_provider"] for a in synthesis_runs] == ["codex"]


def test_a_failed_provider_is_persisted_and_the_run_continues(
        research_service, funded_account, monkeypatch):
    """One provider times out; the run must record it and still reach the gate."""
    original = research_module.build_adapters

    def degraded(config, mock=None, providers=None):
        adapters = original(config, mock=True, providers=providers)
        adapters["codex"] = MockAdapter("codex", failure_kind=base_adapter.TIMEOUT)
        return adapters

    monkeypatch.setattr(research_module, "build_adapters", degraded)
    payload = run_committee(research_service, funded_account, chair="claude")

    codex_runs = [a for a in payload["agent_runs"] if a["agent_provider"] == "codex"]
    assert codex_runs and all(a["status"] == "FAILED" for a in codex_runs)
    assert all(a["failure_kind"] == base_adapter.TIMEOUT for a in codex_runs)
    assert payload["run"]["status"] == decision_rules.READY_FOR_HUMAN
    assert any(f["provider"] == "codex" for f in payload["failures"])
    # No fabricated replacement for the missing analysis.
    assert not any(a["agent_provider"] == "codex" and a["parsed_output"]
                   for a in payload["agent_runs"])


def test_cross_review_is_skipped_when_only_one_analysis_survives(
        research_service, funded_account, monkeypatch):
    original = research_module.build_adapters

    def degraded(config, mock=None, providers=None):
        adapters = original(config, mock=True, providers=providers)
        adapters["codex"] = MockAdapter("codex", failure_kind=base_adapter.NON_ZERO_EXIT)
        return adapters

    monkeypatch.setattr(research_module, "build_adapters", degraded)
    payload = run_committee(research_service, funded_account, chair="claude")
    assert not [a for a in payload["agent_runs"] if a["stage"] == "CROSS_REVIEW"]
    assert any("cross-review skipped" in reason for reason in payload["stopped_because"])


def test_a_malformed_chair_output_fails_the_run_without_a_recommendation(
        research_service, funded_account, monkeypatch):
    original = research_module.build_adapters

    def degraded(config, mock=None, providers=None):
        adapters = original(config, mock=True, providers=providers)
        adapters["claude"] = _ChairBreaks("claude")
        return adapters

    monkeypatch.setattr(research_module, "build_adapters", degraded)
    payload = run_committee(research_service, funded_account, chair="claude")
    assert payload["run"]["status"] == decision_rules.FAILED
    assert payload["run"]["error"]
    assert payload["recommendations"] == []
    assert payload["synthesis"] is None


class _ChairBreaks(MockAdapter):
    """Valid analyst and reviewer, but returns prose when asked to chair."""

    def run(self, prompt, contract, role, stage, timeout_seconds=None):
        if contract == contracts.CHAIR_SYNTHESIS:
            self.raw_override = "I cannot produce structured output right now."
        else:
            self.raw_override = None
        return super().run(prompt, contract, role, stage, timeout_seconds)


def test_a_failed_committee_never_changes_portfolio_state(
        research_service, portfolio_service, funded_account, monkeypatch):
    before = portfolio_service.snapshot(funded_account.id, "2026-01-10")

    def broken(config, mock=None, providers=None):
        return {"codex": MockAdapter("codex", failure_kind=base_adapter.TIMEOUT),
                "claude": MockAdapter("claude", failure_kind=base_adapter.TIMEOUT)}

    monkeypatch.setattr(research_module, "build_adapters", broken)
    payload = run_committee(research_service, funded_account)
    assert payload["run"]["status"] == decision_rules.FAILED
    assert portfolio_service.snapshot(funded_account.id, "2026-01-10") == before


def test_agents_receive_no_account_identity(research_service, funded_account, context):
    """Context minimization: symbols and numbers, never account or broker names."""
    payload = run_committee(research_service, funded_account)
    raw_dir = context.config.runs_dir / payload["run"]["id"] / "raw"
    prompts_and_output = "\n".join(
        path.read_text(encoding="utf-8") for path in raw_dir.glob("*.txt"))
    assert "Committee Account" not in prompts_and_output
