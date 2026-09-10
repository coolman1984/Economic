"""Human decision rules and the approval gate."""

import pytest

from economic.domain import decisions


def test_decision_values_are_normalized():
    assert decisions.normalize_decision("approve") == "APPROVE"
    assert decisions.normalize_decision(" Hold ") == "HOLD"


def test_unknown_decision_is_rejected():
    with pytest.raises(decisions.DecisionError):
        decisions.normalize_decision("MAYBE")


def test_each_decision_maps_to_a_run_state():
    assert decisions.state_for("APPROVE") == decisions.HUMAN_APPROVED
    assert decisions.state_for("REJECT") == decisions.HUMAN_REJECTED
    assert decisions.state_for("HOLD") == decisions.HUMAN_HELD
    assert decisions.state_for("MODIFY") == decisions.HUMAN_MODIFIED


def test_approval_never_creates_a_transaction():
    for decision in decisions.HUMAN_DECISIONS:
        assert decisions.decision_creates_transaction(decision) is False


def test_a_decision_requires_the_run_to_have_reached_the_gate():
    decisions.require_ready_for_human(decisions.READY_FOR_HUMAN)
    with pytest.raises(decisions.DecisionError):
        decisions.require_ready_for_human(decisions.INDEPENDENT_ANALYSIS)
    with pytest.raises(decisions.DecisionError):
        decisions.require_ready_for_human(decisions.FAILED)


def test_a_decided_run_may_be_decided_again_for_the_record():
    decisions.require_ready_for_human(decisions.HUMAN_APPROVED)


def test_recommendation_actions_are_validated():
    assert decisions.normalize_action("no action") == "NO_ACTION"
    with pytest.raises(decisions.DecisionError):
        decisions.normalize_action("SHORT")
