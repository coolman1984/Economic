"""Agent output contracts: malformed output must never be trusted."""

import json

import pytest

from economic.agents import contracts, validators

VALID_ANALYSIS = {
    "status": "complete",
    "scope": "portfolio review",
    "market_view": "no live data",
    "portfolio_view": "concentrated in one name",
    "recommendations": [{
        "symbol": "comi", "action": "hold", "priority": 1, "confidence": 60,
        "thesis": "position is adequately sized", "bull_case": ["earnings"],
        "bear_case": ["rates"], "invalidators": ["margin collapse"], "risks": ["liquidity"],
    }],
    "facts": [{"fact": "cash is 1000", "source_name": "ledger", "source_date": "2026-01-01"}],
    "missing_data": ["current price"],
    "confidence": 55,
}

VALID_CRITIQUE = {
    "status": "complete",
    "reviewed_provider": "claude",
    "unsupported_claims": ["no source for the growth claim"],
    "overall_assessment": "reasonable but thin on evidence",
    "disagreements": [{
        "topic": "growth", "my_position": "not shown", "their_position": "sustainable",
        "materiality": "high", "required_evidence": ["revenue mix"],
    }],
}

VALID_SYNTHESIS = {
    "status": "complete",
    "summary": "hold and gather evidence",
    "data_quality_score": 50,
    "agreement_score": 70,
    "ranked_actions": [{
        "rank": 1, "symbol": "COMI", "action": "HOLD", "confidence": 55,
        "why": ["no new evidence"], "strongest_counterargument": "holding is still a choice",
        "invalidators": ["thesis break"], "portfolio_effect": "none",
    }],
    "human_decision_required": True,
}


def test_valid_analysis_is_accepted_and_normalized():
    result = contracts.validate(contracts.INDEPENDENT_ANALYSIS, VALID_ANALYSIS)
    assert result.ok, result.errors
    assert result.data["recommendations"][0]["symbol"] == "COMI"
    assert result.data["recommendations"][0]["action"] == "HOLD"


def test_analysis_missing_required_fields_is_rejected():
    result = contracts.validate(contracts.INDEPENDENT_ANALYSIS, {"status": "complete"})
    assert not result.ok
    assert "portfolio_view is required" in result.errors


def test_analysis_with_an_invented_action_is_rejected():
    payload = json.loads(json.dumps(VALID_ANALYSIS))
    payload["recommendations"][0]["action"] = "YOLO"
    result = contracts.validate(contracts.INDEPENDENT_ANALYSIS, payload)
    assert not result.ok
    assert any("action must be one of" in error for error in result.errors)


def test_out_of_range_confidence_is_rejected():
    payload = json.loads(json.dumps(VALID_ANALYSIS))
    payload["recommendations"][0]["confidence"] = 900
    result = contracts.validate(contracts.INDEPENDENT_ANALYSIS, payload)
    assert not result.ok


def test_non_object_output_is_rejected():
    result = contracts.validate(contracts.INDEPENDENT_ANALYSIS, ["not", "an", "object"])
    assert not result.ok


def test_critique_requires_an_assessment():
    payload = dict(VALID_CRITIQUE)
    payload.pop("overall_assessment")
    assert not contracts.validate(contracts.CRITIQUE, payload).ok
    assert contracts.validate(contracts.CRITIQUE, VALID_CRITIQUE).ok


def test_chair_cannot_waive_the_human_gate():
    payload = json.loads(json.dumps(VALID_SYNTHESIS))
    payload["human_decision_required"] = False
    result = contracts.validate(contracts.CHAIR_SYNTHESIS, payload)
    assert not result.ok
    assert any("human gate cannot be waived" in error for error in result.errors)


def test_chair_output_always_reports_the_human_gate_as_required():
    result = contracts.validate(contracts.CHAIR_SYNTHESIS, VALID_SYNTHESIS)
    assert result.ok and result.data["human_decision_required"] is True


def test_chair_requires_a_counterargument_for_every_action():
    payload = json.loads(json.dumps(VALID_SYNTHESIS))
    payload["ranked_actions"][0].pop("strongest_counterargument")
    assert not contracts.validate(contracts.CHAIR_SYNTHESIS, payload).ok


def test_raise_if_invalid_reports_every_problem():
    result = contracts.validate(contracts.INDEPENDENT_ANALYSIS, {})
    with pytest.raises(contracts.ContractError):
        result.raise_if_invalid()


# --- extraction from realistic provider output ---------------------------

def test_payload_is_recovered_from_a_fenced_code_block():
    raw = "Sure, here is my analysis:\n\n```json\n" + json.dumps(VALID_ANALYSIS) + "\n```\nDone."
    result = validators.parse_and_validate(raw, contracts.INDEPENDENT_ANALYSIS)
    assert result.ok, result.errors


def test_payload_is_recovered_from_a_provider_envelope():
    raw = json.dumps({"type": "result", "is_error": False,
                      "result": json.dumps(VALID_ANALYSIS)})
    result = validators.parse_and_validate(raw, contracts.INDEPENDENT_ANALYSIS)
    assert result.ok, result.errors


def test_payload_is_recovered_from_a_jsonl_event_stream():
    raw = "\n".join([
        json.dumps({"type": "task_started"}),
        json.dumps({"type": "agent_message", "text": json.dumps(VALID_ANALYSIS)}),
        json.dumps({"type": "task_complete"}),
    ])
    result = validators.parse_and_validate(raw, contracts.INDEPENDENT_ANALYSIS)
    assert result.ok, result.errors


def test_prose_without_json_is_rejected():
    result = validators.parse_and_validate(
        "I think you should probably buy the bank stock.", contracts.INDEPENDENT_ANALYSIS)
    assert not result.ok
    assert "no JSON object found" in result.errors[0]


def test_truncated_json_is_rejected():
    raw = json.dumps(VALID_ANALYSIS)[:80]
    result = validators.parse_and_validate(raw, contracts.INDEPENDENT_ANALYSIS)
    assert not result.ok


def test_empty_output_is_rejected():
    assert not validators.parse_and_validate("   ", contracts.INDEPENDENT_ANALYSIS).ok
