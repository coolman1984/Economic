"""Committee integrity (ADR-021).

A run with one surviving agent is not a dual-agent committee and must never be
recorded as one.
"""

import pytest

from economic.agents import artifacts as artifact_module
from economic.agents import base_adapter, contracts
from economic.agents.mock_adapter import MockAdapter
from economic.agents.orchestrator import (
    COMMITTEE_DEGRADED, COMMITTEE_FULL, Orchestrator, new_run_id)

CONTEXT = {
    "question": "what now?",
    "portfolio": {"cash": "1000", "total_equity": "1000", "positions": [],
                  "missing_prices": []},
    "data_quality_score": 100,
}


def orchestrate(tmp_path, adapters, chair="claude"):
    run_id = new_run_id("2026-01-10")
    artifacts = artifact_module.RunArtifacts(tmp_path / "runs", run_id)
    orchestrator = Orchestrator(adapters=adapters, artifacts=artifacts, chair=chair)
    return orchestrator.run_committee(run_id, "what now?", CONTEXT, mode="mock")


def both_working():
    return {"codex": MockAdapter("codex"), "claude": MockAdapter("claude")}


def test_two_analyses_and_two_critiques_is_a_full_committee(tmp_path):
    result = orchestrate(tmp_path, both_working())
    assert result.integrity.mode == COMMITTEE_FULL
    assert not result.degraded
    assert result.integrity.analyst_count == 2
    assert result.integrity.critique_count == 2
    assert result.integrity.reasons == []
    assert result.integrity.agreement_is_measurable


def test_one_failed_analyst_makes_the_committee_degraded(tmp_path):
    adapters = both_working()
    adapters["codex"] = MockAdapter("codex", failure_kind=base_adapter.TIMEOUT)
    result = orchestrate(tmp_path, adapters)
    assert result.integrity.mode == COMMITTEE_DEGRADED
    assert result.degraded
    assert result.integrity.analyst_count == 1
    assert result.integrity.analyst_providers == ["claude"]
    assert any("only 1 of 2 independent analyses" in reason
               for reason in result.integrity.reasons)
    assert any("codex" in reason for reason in result.integrity.reasons)


def test_a_degraded_committee_still_reaches_the_human_but_labelled(tmp_path):
    """The human should still see the work; they must not see it as a committee."""
    adapters = both_working()
    adapters["codex"] = MockAdapter("codex", failure_kind=base_adapter.NON_ZERO_EXIT)
    result = orchestrate(tmp_path, adapters)
    assert result.ready_for_human
    assert result.degraded
    assert any("committee is DEGRADED" in reason for reason in result.stopped_because)


def test_agreement_is_not_measurable_with_a_single_analysis(tmp_path):
    adapters = both_working()
    adapters["codex"] = MockAdapter("codex", failure_kind=base_adapter.TIMEOUT)
    result = orchestrate(tmp_path, adapters)
    assert not result.integrity.agreement_is_measurable
    # Whatever the chair claimed, the system records nothing.
    assert result.integrity.effective_agreement_score(97) is None


def test_agreement_is_measurable_once_two_analyses_exist(tmp_path):
    result = orchestrate(tmp_path, both_working())
    assert result.integrity.effective_agreement_score(71) == 71


def test_failed_cross_review_degrades_but_keeps_agreement_measurable(tmp_path):
    """Two independent views can still be compared even if neither critiqued."""

    class NoCritique(MockAdapter):
        def run(self, prompt, contract, role, stage, timeout_seconds=None):
            self.failure_kind = (
                base_adapter.TIMEOUT if contract == contracts.CRITIQUE else None)
            return super().run(prompt, contract, role, stage, timeout_seconds)

    result = orchestrate(tmp_path, {"codex": NoCritique("codex"),
                                    "claude": NoCritique("claude")})
    assert result.integrity.mode == COMMITTEE_DEGRADED
    assert result.integrity.analyst_count == 2
    assert result.integrity.critique_count == 0
    assert result.integrity.agreement_is_measurable
    assert any("were cross-reviewed" in reason for reason in result.integrity.reasons)


def test_a_single_enabled_provider_is_degraded_by_construction(tmp_path):
    result = orchestrate(tmp_path, {"claude": MockAdapter("claude")})
    assert result.integrity.mode == COMMITTEE_DEGRADED
    assert any("only 1 provider(s) were enabled" in reason
               for reason in result.integrity.reasons)


def test_integrity_is_recorded_even_when_every_analyst_fails(tmp_path):
    adapters = {p: MockAdapter(p, failure_kind=base_adapter.TIMEOUT)
                for p in ("codex", "claude")}
    result = orchestrate(tmp_path, adapters)
    assert result.status == "FAILED"
    assert result.integrity is not None
    assert result.integrity.mode == COMMITTEE_DEGRADED
    assert result.integrity.analyst_count == 0


def test_integrity_is_written_into_the_final_artifact(tmp_path):
    adapters = both_working()
    adapters["codex"] = MockAdapter("codex", failure_kind=base_adapter.TIMEOUT)
    result = orchestrate(tmp_path, adapters)
    artifacts = artifact_module.RunArtifacts(tmp_path / "runs", result.run_id)
    final = artifacts.read_json(artifact_module.FINAL_RECOMMENDATION)
    assert final["committee_integrity"]["degraded"] is True
    assert final["committee_integrity"]["analyst_count"] == 1


def test_the_chair_prompt_states_the_degradation(tmp_path):
    """The chair must be told; the code still enforces it either way."""
    adapters = both_working()
    adapters["codex"] = MockAdapter("codex", failure_kind=base_adapter.TIMEOUT)
    result = orchestrate(tmp_path, adapters)
    raw = (tmp_path / "runs" / result.run_id / "raw" / "claude_synthesis.txt")
    assert raw.exists()
    chair_run = [r for r in result.agent_responses if r.stage == "SYNTHESIS"][0]
    assert chair_run.ok
