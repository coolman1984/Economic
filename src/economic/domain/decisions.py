"""Decision state rules.

Owns the human-decision vocabulary and the research-run state machine. It holds
no AI reasoning and never triggers an execution (ADR-008).
"""

from __future__ import annotations

APPROVE = "APPROVE"
REJECT = "REJECT"
HOLD = "HOLD"
MODIFY = "MODIFY"

HUMAN_DECISIONS = (APPROVE, REJECT, HOLD, MODIFY)

# Recommendation actions an agent may propose (INVESTMENT_RULES §5).
RECOMMENDATION_ACTIONS = (
    "BUY", "ADD", "HOLD", "WATCH", "REDUCE", "SELL", "NO_ACTION",
)

# Research-run states (ARCHITECTURE §7).
CREATED = "CREATED"
COLLECTING_DATA = "COLLECTING_DATA"
DATA_VALIDATED = "DATA_VALIDATED"
INDEPENDENT_ANALYSIS = "INDEPENDENT_ANALYSIS"
CROSS_REVIEW = "CROSS_REVIEW"
DISAGREEMENT_CHECK = "DISAGREEMENT_CHECK"
SIMULATION = "SIMULATION"
RISK_REVIEW = "RISK_REVIEW"
READY_FOR_SYNTHESIS = "READY_FOR_SYNTHESIS"
READY_FOR_HUMAN = "READY_FOR_HUMAN"
HUMAN_APPROVED = "HUMAN_APPROVED"
HUMAN_REJECTED = "HUMAN_REJECTED"
HUMAN_HELD = "HUMAN_HELD"
HUMAN_MODIFIED = "HUMAN_MODIFIED"
OUTCOME_MONITORING = "OUTCOME_MONITORING"
CLOSED = "CLOSED"
FAILED = "FAILED"

RUN_STATES = (
    CREATED, COLLECTING_DATA, DATA_VALIDATED, INDEPENDENT_ANALYSIS, CROSS_REVIEW,
    DISAGREEMENT_CHECK, SIMULATION, RISK_REVIEW, READY_FOR_SYNTHESIS,
    READY_FOR_HUMAN, HUMAN_APPROVED, HUMAN_REJECTED, HUMAN_HELD, HUMAN_MODIFIED,
    OUTCOME_MONITORING, CLOSED, FAILED,
)

DECISION_TO_STATE = {
    APPROVE: HUMAN_APPROVED,
    REJECT: HUMAN_REJECTED,
    HOLD: HUMAN_HELD,
    MODIFY: HUMAN_MODIFIED,
}

TERMINAL_HUMAN_STATES = frozenset(DECISION_TO_STATE.values())


class DecisionError(ValueError):
    """An invalid decision or state transition was requested."""


def normalize_decision(decision: str) -> str:
    """Validate a human decision value."""
    if not isinstance(decision, str):
        raise DecisionError("decision must be a string")
    value = decision.strip().upper()
    if value not in HUMAN_DECISIONS:
        raise DecisionError(
            f"invalid decision {decision!r}; expected one of {', '.join(HUMAN_DECISIONS)}"
        )
    return value


def normalize_action(action: str) -> str:
    """Validate a recommendation action value."""
    value = (action or "").strip().upper().replace(" ", "_")
    if value not in RECOMMENDATION_ACTIONS:
        raise DecisionError(
            f"invalid action {action!r}; expected one of "
            f"{', '.join(RECOMMENDATION_ACTIONS)}"
        )
    return value


def require_ready_for_human(run_state: str) -> None:
    """A human decision may only be recorded on a run that reached the gate."""
    if run_state in TERMINAL_HUMAN_STATES:
        return  # re-deciding is allowed; history keeps every decision record
    if run_state != READY_FOR_HUMAN:
        raise DecisionError(
            f"run is in state {run_state}; a human decision requires {READY_FOR_HUMAN}"
        )


def state_for(decision: str) -> str:
    """Map a validated human decision to the resulting run state."""
    return DECISION_TO_STATE[normalize_decision(decision)]


def decision_creates_transaction(decision: str) -> bool:
    """Always False: approving a recommendation never books a trade (ADR-008)."""
    normalize_decision(decision)
    return False
