"""Versioned, machine-checkable contracts for AI output.

An agent's answer is only usable after it validates against one of these
contracts. Malformed output becomes an explicit failure and is never partially
trusted (AGENTS.md §7, BUILD_GUIDE Step 7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..domain.decisions import RECOMMENDATION_ACTIONS

CONTRACT_VERSION = "1.0"

INDEPENDENT_ANALYSIS = "independent_analysis"
CRITIQUE = "critique"
CHAIR_SYNTHESIS = "chair_synthesis"

CONTRACT_NAMES = (INDEPENDENT_ANALYSIS, CRITIQUE, CHAIR_SYNTHESIS)

VALID_STATUSES = ("complete", "partial", "insufficient_data")
MATERIALITY_LEVELS = ("high", "medium", "low", "unknown")


class ContractError(ValueError):
    """The output does not satisfy its contract."""


@dataclass
class ValidationResult:
    """Outcome of validating one agent output against a contract."""

    contract: str
    ok: bool
    data: Optional[dict] = None
    errors: List[str] = field(default_factory=list)

    def raise_if_invalid(self) -> dict:
        if not self.ok:
            raise ContractError(
                f"{self.contract} contract validation failed: " + "; ".join(self.errors)
            )
        return self.data


class _Checker:
    """Small dependency-free structural validator."""

    def __init__(self, payload: Any, contract: str):
        self.payload = payload
        self.contract = contract
        self.errors: List[str] = []
        self.data: Dict[str, Any] = {}

    def fail(self, message: str) -> None:
        self.errors.append(message)

    def is_object(self) -> bool:
        if not isinstance(self.payload, dict):
            self.fail(f"expected a JSON object, got {type(self.payload).__name__}")
            return False
        return True

    def string(self, key: str, required: bool = True, default: str = "",
               choices: Optional[tuple] = None, max_length: int = 20000,
               path: Optional[str] = None, source: Optional[dict] = None) -> str:
        source = self.payload if source is None else source
        label = path or key
        value = source.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            if required:
                self.fail(f"{label} is required")
            return default
        if not isinstance(value, str):
            self.fail(f"{label} must be a string")
            return default
        value = value.strip()[:max_length]
        if choices is not None:
            normalized = value.upper() if choices and choices[0].isupper() else value.lower()
            if normalized not in choices:
                self.fail(f"{label} must be one of {', '.join(choices)}, got {value!r}")
                return default
            return normalized
        return value

    def integer(self, key: str, required: bool = False, default: Optional[int] = None,
                minimum: Optional[int] = None, maximum: Optional[int] = None,
                path: Optional[str] = None, source: Optional[dict] = None) -> Optional[int]:
        source = self.payload if source is None else source
        label = path or key
        value = source.get(key)
        if value is None:
            if required:
                self.fail(f"{label} is required")
            return default
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            if isinstance(value, str):
                try:
                    value = int(float(value.strip().rstrip("%")))
                except ValueError:
                    self.fail(f"{label} must be a number")
                    return default
            else:
                self.fail(f"{label} must be a number")
                return default
        value = int(value)
        if minimum is not None and value < minimum:
            self.fail(f"{label} must be >= {minimum}")
            return default
        if maximum is not None and value > maximum:
            self.fail(f"{label} must be <= {maximum}")
            return default
        return value

    def string_list(self, key: str, required: bool = False, max_items: int = 50,
                    path: Optional[str] = None, source: Optional[dict] = None) -> List[str]:
        source = self.payload if source is None else source
        label = path or key
        value = source.get(key)
        if value is None:
            if required:
                self.fail(f"{label} is required")
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            self.fail(f"{label} must be a list of strings")
            return []
        items = []
        for index, item in enumerate(value[:max_items]):
            if isinstance(item, str) and item.strip():
                items.append(item.strip())
            elif isinstance(item, dict):
                # Tolerate {"text": "..."} shapes without accepting arbitrary junk.
                text = item.get("text") or item.get("claim") or item.get("risk")
                if isinstance(text, str) and text.strip():
                    items.append(text.strip())
                else:
                    self.fail(f"{label}[{index}] is not a readable string")
            else:
                self.fail(f"{label}[{index}] must be a string")
        return items

    def object_list(self, key: str, required: bool = False, max_items: int = 50,
                    path: Optional[str] = None) -> List[dict]:
        label = path or key
        value = self.payload.get(key)
        if value is None:
            if required:
                self.fail(f"{label} is required")
            return []
        if not isinstance(value, list):
            self.fail(f"{label} must be a list")
            return []
        items = []
        for index, item in enumerate(value[:max_items]):
            if isinstance(item, dict):
                items.append(item)
            else:
                self.fail(f"{label}[{index}] must be an object")
        return items


def _validate_fact(checker: _Checker, fact: dict, label: str) -> dict:
    return {
        "fact": checker.string("fact", required=True, path=f"{label}.fact", source=fact),
        "source_name": checker.string("source_name", required=False, path=f"{label}.source_name", source=fact),
        "source_url": checker.string("source_url", required=False, path=f"{label}.source_url", source=fact),
        "source_date": checker.string("source_date", required=False, path=f"{label}.source_date", source=fact),
        "verified": bool(fact.get("verified", False)),
    }


def validate_independent_analysis(payload: Any) -> ValidationResult:
    """Validate an analyst's first-pass output (AGENT_ORCHESTRATION §9)."""
    checker = _Checker(payload, INDEPENDENT_ANALYSIS)
    if not checker.is_object():
        return ValidationResult(INDEPENDENT_ANALYSIS, False, None, checker.errors)

    data = {
        "contract": INDEPENDENT_ANALYSIS,
        "contract_version": CONTRACT_VERSION,
        "status": checker.string("status", required=True, choices=VALID_STATUSES),
        "scope": checker.string("scope", required=False),
        "market_view": checker.string("market_view", required=False),
        "portfolio_view": checker.string("portfolio_view", required=True),
        "missing_data": checker.string_list("missing_data"),
        "disagreements_or_uncertainty": checker.string_list("disagreements_or_uncertainty"),
        "next_checks": checker.string_list("next_checks"),
        "confidence": checker.integer("confidence", required=False, default=None, minimum=0, maximum=100),
    }

    recommendations = []
    for index, item in enumerate(checker.object_list("recommendations", required=True)):
        label = f"recommendations[{index}]"
        action = checker.string("action", required=True, choices=RECOMMENDATION_ACTIONS,
                                path=f"{label}.action", source=item)
        recommendations.append({
            "symbol": checker.string("symbol", required=False, path=f"{label}.symbol", source=item).upper() or None,
            "action": action,
            "priority": checker.integer("priority", required=False, default=index + 1,
                                        minimum=1, path=f"{label}.priority", source=item),
            "confidence": checker.integer("confidence", required=True, default=0, minimum=0,
                                          maximum=100, path=f"{label}.confidence", source=item),
            "suggested_weight_pct": checker.integer("suggested_weight_pct", required=False,
                                                    default=None, minimum=0, maximum=100,
                                                    path=f"{label}.suggested_weight_pct", source=item),
            "thesis": checker.string("thesis", required=True, path=f"{label}.thesis", source=item),
            "bull_case": checker.string_list("bull_case", path=f"{label}.bull_case", source=item),
            "bear_case": checker.string_list("bear_case", path=f"{label}.bear_case", source=item),
            "invalidators": checker.string_list("invalidators", path=f"{label}.invalidators", source=item),
            "risks": checker.string_list("risks", path=f"{label}.risks", source=item),
        })
    if not recommendations and not checker.errors:
        checker.fail("recommendations must contain at least one entry")
    data["recommendations"] = recommendations

    data["facts"] = [
        _validate_fact(checker, fact, f"facts[{index}]")
        for index, fact in enumerate(checker.object_list("facts"))
    ]

    return ValidationResult(INDEPENDENT_ANALYSIS, not checker.errors,
                            data if not checker.errors else None, checker.errors)


def validate_critique(payload: Any) -> ValidationResult:
    """Validate a cross-review output (AGENT_ORCHESTRATION §5)."""
    checker = _Checker(payload, CRITIQUE)
    if not checker.is_object():
        return ValidationResult(CRITIQUE, False, None, checker.errors)

    data = {
        "contract": CRITIQUE,
        "contract_version": CONTRACT_VERSION,
        "status": checker.string("status", required=True, choices=VALID_STATUSES),
        "reviewed_provider": checker.string("reviewed_provider", required=True),
        "unsupported_claims": checker.string_list("unsupported_claims"),
        "stale_or_missing_evidence": checker.string_list("stale_or_missing_evidence"),
        "missed_risks": checker.string_list("missed_risks"),
        "portfolio_fit_errors": checker.string_list("portfolio_fit_errors"),
        "useful_insights_missed": checker.string_list("useful_insights_missed"),
        "agreements": checker.string_list("agreements"),
        "overall_assessment": checker.string("overall_assessment", required=True),
        "confidence": checker.integer("confidence", required=False, default=None,
                                      minimum=0, maximum=100),
    }

    disagreements = []
    for index, item in enumerate(checker.object_list("disagreements")):
        label = f"disagreements[{index}]"
        disagreements.append({
            "topic": checker.string("topic", required=True, path=f"{label}.topic", source=item),
            "my_position": checker.string("my_position", required=True,
                                          path=f"{label}.my_position", source=item),
            "their_position": checker.string("their_position", required=True,
                                             path=f"{label}.their_position", source=item),
            "materiality": checker.string("materiality", required=False, default="unknown",
                                          choices=MATERIALITY_LEVELS,
                                          path=f"{label}.materiality", source=item),
            "required_evidence": checker.string_list("required_evidence",
                                                     path=f"{label}.required_evidence", source=item),
        })
    data["disagreements"] = disagreements

    return ValidationResult(CRITIQUE, not checker.errors,
                            data if not checker.errors else None, checker.errors)


def validate_chair_synthesis(payload: Any) -> ValidationResult:
    """Validate the final chair output (AGENT_ORCHESTRATION §10)."""
    checker = _Checker(payload, CHAIR_SYNTHESIS)
    if not checker.is_object():
        return ValidationResult(CHAIR_SYNTHESIS, False, None, checker.errors)

    data = {
        "contract": CHAIR_SYNTHESIS,
        "contract_version": CONTRACT_VERSION,
        "status": checker.string("status", required=True, choices=VALID_STATUSES),
        "summary": checker.string("summary", required=True),
        "data_quality_score": checker.integer("data_quality_score", required=True, default=0,
                                              minimum=0, maximum=100),
        "agreement_score": checker.integer("agreement_score", required=True, default=0,
                                           minimum=0, maximum=100),
        "rejected_ideas": checker.string_list("rejected_ideas"),
        "unresolved_questions": checker.string_list("unresolved_questions"),
    }

    ranked = []
    for index, item in enumerate(checker.object_list("ranked_actions", required=True)):
        label = f"ranked_actions[{index}]"
        ranked.append({
            "rank": checker.integer("rank", required=False, default=index + 1, minimum=1,
                                    path=f"{label}.rank", source=item),
            "symbol": checker.string("symbol", required=False, path=f"{label}.symbol", source=item).upper() or None,
            "action": checker.string("action", required=True, choices=RECOMMENDATION_ACTIONS,
                                     path=f"{label}.action", source=item),
            "confidence": checker.integer("confidence", required=True, default=0, minimum=0,
                                          maximum=100, path=f"{label}.confidence", source=item),
            "suggested_weight_pct": checker.integer("suggested_weight_pct", required=False,
                                                    default=None, minimum=0, maximum=100,
                                                    path=f"{label}.suggested_weight_pct", source=item),
            "why": checker.string_list("why", required=True, path=f"{label}.why", source=item),
            "strongest_counterargument": checker.string(
                "strongest_counterargument", required=True,
                path=f"{label}.strongest_counterargument", source=item),
            "invalidators": checker.string_list("invalidators", path=f"{label}.invalidators", source=item),
            "portfolio_effect": checker.string("portfolio_effect", required=False,
                                               path=f"{label}.portfolio_effect", source=item),
            "evidence_urls": checker.string_list("evidence_urls", path=f"{label}.evidence_urls", source=item),
        })
    if not ranked and not checker.errors:
        checker.fail("ranked_actions must contain at least one entry")
    data["ranked_actions"] = ranked

    # The human gate is a property of the system, not a field the model may switch off.
    if payload.get("human_decision_required") is False:
        checker.fail("human_decision_required must be true; the human gate cannot be waived")
    data["human_decision_required"] = True

    return ValidationResult(CHAIR_SYNTHESIS, not checker.errors,
                            data if not checker.errors else None, checker.errors)


VALIDATORS = {
    INDEPENDENT_ANALYSIS: validate_independent_analysis,
    CRITIQUE: validate_critique,
    CHAIR_SYNTHESIS: validate_chair_synthesis,
}


def validate(contract: str, payload: Any) -> ValidationResult:
    """Validate ``payload`` against the named contract."""
    if contract not in VALIDATORS:
        raise ContractError(f"unknown contract: {contract}")
    return VALIDATORS[contract](payload)
