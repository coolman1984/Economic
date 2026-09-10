"""The deterministic evidence gate (ADR-020).

These tests exist because prompt instructions are not enforcement: a model can
ignore them. Every restriction below must hold in code, whatever the model says.
"""

import pytest

from economic.domain import risk


def gate(**overrides):
    snapshot = {
        "data_quality_score": 100,
        "prices_as_of": {"COMI": "2026-01-10", "HRHO": "2026-01-10"},
        "missing_prices": [],
        "stale_prices": [],
    }
    snapshot.update(overrides.pop("snapshot", {}))
    return risk.build_evidence_gate(snapshot, **overrides)


def action(symbol="COMI", act="BUY", confidence=90, rank=1):
    return {"rank": rank, "symbol": symbol, "action": act, "confidence": confidence}


def test_good_evidence_lets_an_actionable_proposal_stand():
    result = risk.gate_actions([action()], gate())[0]
    assert result.action == "BUY"
    assert not result.restricted
    assert result.confidence == 90
    assert result.reasons == []


@pytest.mark.parametrize("act", sorted(risk.ACTIONABLE_ACTIONS))
def test_every_actionable_action_is_restricted_when_the_price_is_missing(act):
    evidence = gate(snapshot={"missing_prices": ["GHOST"], "data_quality_score": 60})
    result = risk.gate_actions([action(symbol="GHOST", act=act)], evidence)[0]
    assert result.restricted
    assert result.action == risk.RESTRICTED_ACTION
    assert result.proposed_action == act
    assert any("no price snapshot" in reason for reason in result.reasons)


def test_a_stale_price_restricts_an_actionable_action():
    evidence = gate(snapshot={"stale_prices": ["COMI"]})
    result = risk.gate_actions([action(act="SELL")], evidence)[0]
    assert result.restricted
    assert result.action == "WATCH"
    assert any("stale price" in reason for reason in result.reasons)


def test_a_security_with_no_price_evidence_at_all_is_restricted():
    result = risk.gate_actions([action(symbol="NEWCO")], gate())[0]
    assert result.restricted
    assert any("no price evidence" in reason for reason in result.reasons)


def test_low_portfolio_data_quality_restricts_every_actionable_action():
    evidence = gate(snapshot={"data_quality_score": 30}, min_data_quality=50)
    results = risk.gate_actions(
        [action(symbol="COMI"), action(symbol="HRHO", act="SELL", rank=2)], evidence)
    assert all(entry.restricted for entry in results)
    assert all(any("below the 50/100" in reason for reason in entry.reasons)
               for entry in results)


def test_the_data_quality_floor_is_configurable():
    forgiving = gate(snapshot={"data_quality_score": 30}, min_data_quality=10)
    assert not risk.gate_actions([action()], forgiving)[0].restricted


@pytest.mark.parametrize("act", ["HOLD", "WATCH", "NO_ACTION"])
def test_non_actionable_actions_are_never_downgraded(act):
    evidence = gate(snapshot={"data_quality_score": 5, "missing_prices": ["COMI"]})
    result = risk.gate_actions([action(act=act)], evidence)[0]
    assert result.action == act
    assert not result.restricted


def test_confidence_is_capped_at_the_data_quality_score_on_thin_evidence():
    evidence = gate(snapshot={"data_quality_score": 40, "missing_prices": ["COMI"]})
    result = risk.gate_actions([action(confidence=95)], evidence)[0]
    assert result.confidence == 40
    assert result.proposed_confidence == 95
    assert result.confidence_was_capped


def test_confidence_is_not_touched_when_no_reason_applies():
    result = risk.gate_actions([action(confidence=88)], gate())[0]
    assert result.confidence == 88
    assert not result.confidence_was_capped


def test_a_degraded_committee_restricts_actions_even_on_perfect_data():
    evidence = gate(committee_degraded=True, committee_reasons=["only 1 of 2 analyses"])
    result = risk.gate_actions([action(confidence=95)], evidence)[0]
    assert result.restricted
    assert result.action == "WATCH"
    assert any("committee was degraded" in reason for reason in result.reasons)


def test_a_degraded_committee_caps_confidence_independently_of_data_quality():
    """Perfect prices must not buy back the confidence a missing reviewer costs."""
    evidence = gate(committee_degraded=True, committee_reasons=["only 1 of 2 analyses"])
    result = risk.gate_actions([action(confidence=99)], evidence)[0]
    assert result.confidence == risk.DEGRADED_COMMITTEE_CONFIDENCE_CEILING


def test_duplicate_ranks_are_normalized_so_persistence_cannot_break():
    evidence = gate()
    results = risk.gate_actions(
        [action(symbol="COMI", rank=1), action(symbol="HRHO", rank=1),
         action(symbol="COMI", act="HOLD", rank=1)], evidence)
    assert [entry.rank for entry in results] == [1, 2, 3]


def test_rank_order_follows_the_chair_then_original_order():
    evidence = gate()
    results = risk.gate_actions(
        [action(symbol="HRHO", rank=5), action(symbol="COMI", rank=2)], evidence)
    assert [entry.symbol for entry in results] == ["COMI", "HRHO"]
    assert [entry.rank for entry in results] == [1, 2]


def test_the_proposed_action_is_always_preserved_for_audit():
    evidence = gate(snapshot={"missing_prices": ["COMI"], "data_quality_score": 20})
    result = risk.gate_actions([action(act="SELL", confidence=80)], evidence)[0]
    payload = result.to_dict()
    assert payload["proposed_action"] == "SELL"
    assert payload["proposed_confidence"] == 80
    assert payload["action"] == "WATCH"
    assert payload["restricted"] is True
    assert payload["reasons"]


def test_an_empty_action_list_is_handled():
    assert risk.gate_actions([], gate()) == []


def test_gate_is_built_from_the_snapshot_not_from_model_output():
    built = risk.build_evidence_gate(
        {"data_quality_score": 42, "missing_prices": ["A"], "stale_prices": ["B"],
         "prices_as_of": {"B": "2026-01-01"}})
    assert built.data_quality_score == 42
    assert built.missing_prices == frozenset({"A"})
    assert built.stale_prices == frozenset({"B"})
    assert not built.portfolio_data_is_sufficient
