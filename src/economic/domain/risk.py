"""Portfolio rules, risk-limit evaluation, and the evidence gate.

Phase 1 implements the deterministic limits the simulation and committee need:
minimum cash, maximum single-position weight, and unpriced-holding visibility.
Sector, liquidity, and drawdown limits belong to Phase 3 (see ROADMAP.md).

This module also owns the **evidence gate** (ADR-020): the deterministic rule
that decides whether a proposed action is allowed to stand as actionable. The
gate is code, not a prompt instruction, so a model cannot talk its way past it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from .money import ZERO, to_decimal, to_text
from .portfolio import Valuation

# Actions that would move money or change a position if the human acted on them.
ACTIONABLE_ACTIONS = frozenset({"BUY", "ADD", "REDUCE", "SELL"})

# What an actionable action is downgraded to when the evidence does not support it.
RESTRICTED_ACTION = "WATCH"

# Default floor for the deterministic data-quality score below which no action
# may stand as actionable, whatever the model proposed.
DEFAULT_MIN_DATA_QUALITY = 50

# A single unreviewed opinion cannot support high confidence, however sure the
# chair sounds and however complete the price data is. Degraded committees and
# thin evidence are separate axes, so each imposes its own ceiling.
DEGRADED_COMMITTEE_CONFIDENCE_CEILING = 50


@dataclass
class PortfolioRules:
    """Configurable portfolio constraints. Absent values are not enforced."""

    min_cash: Optional[Decimal] = None
    max_position_weight_pct: Optional[Decimal] = None
    max_sector_weight_pct: Optional[Decimal] = None
    restricted_symbols: List[str] = field(default_factory=list)

    @classmethod
    def from_config(cls, config: dict) -> "PortfolioRules":
        config = config or {}

        def optional(key):
            value = config.get(key)
            return None if value in (None, "") else to_decimal(value, key)

        return cls(
            min_cash=optional("min_cash"),
            max_position_weight_pct=optional("max_position_weight_pct"),
            max_sector_weight_pct=optional("max_sector_weight_pct"),
            restricted_symbols=[s.upper() for s in config.get("restricted_symbols", [])],
        )

    def to_dict(self) -> dict:
        return {
            "min_cash": to_text(self.min_cash) if self.min_cash is not None else None,
            "max_position_weight_pct": (
                to_text(self.max_position_weight_pct)
                if self.max_position_weight_pct is not None
                else None
            ),
            "max_sector_weight_pct": (
                to_text(self.max_sector_weight_pct)
                if self.max_sector_weight_pct is not None
                else None
            ),
            "restricted_symbols": list(self.restricted_symbols),
        }


@dataclass
class RuleViolation:
    rule: str
    severity: str
    detail: str
    subject: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "detail": self.detail,
            "subject": self.subject,
        }


def evaluate(valuation: Valuation, rules: PortfolioRules) -> List[RuleViolation]:
    """Check a priced valuation against the configured rules."""
    violations: List[RuleViolation] = []

    if rules.min_cash is not None and valuation.cash < rules.min_cash:
        violations.append(
            RuleViolation(
                rule="min_cash",
                severity="warning",
                detail=(
                    f"cash {to_text(valuation.cash)} is below the minimum "
                    f"{to_text(rules.min_cash)}"
                ),
            )
        )

    if rules.max_position_weight_pct is not None:
        for valued in valuation.priced_positions:
            weight = valuation.weight_of(valued.symbol)
            if weight > rules.max_position_weight_pct:
                violations.append(
                    RuleViolation(
                        rule="max_position_weight_pct",
                        severity="warning",
                        subject=valued.symbol,
                        detail=(
                            f"{valued.symbol} weight {to_text(weight)}% exceeds the maximum "
                            f"{to_text(rules.max_position_weight_pct)}%"
                        ),
                    )
                )

    for symbol in rules.restricted_symbols:
        if any(v.symbol == symbol for v in valuation.positions):
            violations.append(
                RuleViolation(
                    rule="restricted_symbol",
                    severity="warning",
                    subject=symbol,
                    detail=f"{symbol} is on the restricted list but is held",
                )
            )

    for valued in valuation.unpriced_positions:
        violations.append(
            RuleViolation(
                rule="missing_price",
                severity="data_quality",
                subject=valued.symbol,
                detail=f"{valued.symbol} has no price snapshot; it is excluded from equity",
            )
        )

    for valued in valuation.stale_positions:
        violations.append(
            RuleViolation(
                rule="stale_price",
                severity="data_quality",
                subject=valued.symbol,
                detail=(
                    f"{valued.symbol} price is {valued.price_age_days} days old "
                    f"({valued.mark.price_date})"
                ),
            )
        )

    return violations


def data_quality_score(valuation: Valuation) -> int:
    """A 0-100 score reflecting how completely the portfolio is priced.

    This is a deterministic input to the committee; agents may not overwrite it.
    """
    total = len(valuation.positions)
    if total == 0:
        return 100
    priced = len(valuation.priced_positions)
    fresh = priced - len(valuation.stale_positions)
    score = (Decimal(priced) * 70 + Decimal(max(fresh, 0)) * 30) / Decimal(total)
    return int(score.to_integral_value())


# ---------------------------------------------------------------------------
# Evidence gate (ADR-020)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceGate:
    """The deterministic facts an action is judged against.

    Built from the run's own portfolio snapshot and committee integrity, never
    from model output.
    """

    data_quality_score: int
    min_data_quality: int
    priced_symbols: frozenset
    missing_prices: frozenset
    stale_prices: frozenset
    committee_degraded: bool = False
    committee_reasons: tuple = ()

    @property
    def portfolio_data_is_sufficient(self) -> bool:
        return self.data_quality_score >= self.min_data_quality

    def to_dict(self) -> dict:
        return {
            "data_quality_score": self.data_quality_score,
            "min_data_quality": self.min_data_quality,
            "portfolio_data_is_sufficient": self.portfolio_data_is_sufficient,
            "missing_prices": sorted(self.missing_prices),
            "stale_prices": sorted(self.stale_prices),
            "committee_degraded": self.committee_degraded,
            "committee_reasons": list(self.committee_reasons),
        }


@dataclass
class GatedAction:
    """One proposed action after the evidence gate has been applied."""

    rank: int
    symbol: Optional[str]
    action: str
    proposed_action: str
    confidence: Optional[int]
    proposed_confidence: Optional[int]
    restricted: bool
    reasons: List[str] = field(default_factory=list)
    proposed_index: int = 0

    @property
    def confidence_was_capped(self) -> bool:
        return (
            self.proposed_confidence is not None
            and self.confidence is not None
            and self.confidence < self.proposed_confidence
        )

    def to_dict(self) -> dict:
        return {
            "rank": self.rank,
            "symbol": self.symbol,
            "action": self.action,
            "proposed_action": self.proposed_action,
            "confidence": self.confidence,
            "proposed_confidence": self.proposed_confidence,
            "restricted": self.restricted,
            "confidence_was_capped": self.confidence_was_capped,
            "reasons": list(self.reasons),
        }


def build_evidence_gate(snapshot: dict, min_data_quality: int = DEFAULT_MIN_DATA_QUALITY,
                        committee_degraded: bool = False,
                        committee_reasons: Optional[List[str]] = None) -> EvidenceGate:
    """Derive the gate from a run's deterministic portfolio snapshot."""
    snapshot = snapshot or {}
    score = snapshot.get("data_quality_score")
    return EvidenceGate(
        data_quality_score=int(score) if isinstance(score, int) else 0,
        min_data_quality=int(min_data_quality),
        priced_symbols=frozenset((snapshot.get("prices_as_of") or {}).keys()),
        missing_prices=frozenset(snapshot.get("missing_prices") or []),
        stale_prices=frozenset(snapshot.get("stale_prices") or []),
        committee_degraded=bool(committee_degraded),
        committee_reasons=tuple(committee_reasons or ()),
    )


def _reasons_for(symbol: Optional[str], gate: EvidenceGate) -> List[str]:
    """Every deterministic reason this action's evidence is inadequate."""
    reasons: List[str] = []

    if symbol:
        if symbol in gate.missing_prices:
            reasons.append(
                f"{symbol} has no price snapshot, so its weight and market value are unknown"
            )
        elif symbol not in gate.priced_symbols:
            reasons.append(
                f"{symbol} has no price evidence in this run's snapshot"
            )
        if symbol in gate.stale_prices:
            reasons.append(
                f"{symbol} is marked at a stale price"
            )

    if not gate.portfolio_data_is_sufficient:
        reasons.append(
            f"portfolio data quality {gate.data_quality_score}/100 is below the "
            f"{gate.min_data_quality}/100 required for an actionable recommendation"
        )

    if gate.committee_degraded:
        detail = "; ".join(gate.committee_reasons) or "committee did not complete"
        reasons.append(f"the committee was degraded ({detail})")

    return reasons


def _confidence_ceilings(symbol: Optional[str], gate: EvidenceGate) -> List[int]:
    """Every deterministic ceiling that applies to this action's confidence.

    Thin evidence caps confidence at the data-quality score; a degraded committee
    caps it independently, because a second agent never checked the work.
    """
    ceilings: List[int] = []
    thin_evidence = (
        (symbol and (symbol in gate.missing_prices
                     or symbol in gate.stale_prices
                     or symbol not in gate.priced_symbols))
        or not gate.portfolio_data_is_sufficient
    )
    if thin_evidence:
        ceilings.append(gate.data_quality_score)
    if gate.committee_degraded:
        ceilings.append(DEGRADED_COMMITTEE_CONFIDENCE_CEILING)
    return ceilings


def gate_actions(ranked_actions: List[dict], gate: EvidenceGate) -> List[GatedAction]:
    """Apply the evidence gate to the chair's ranked actions.

    An actionable proposal (BUY/ADD/REDUCE/SELL) whose evidence is inadequate is
    downgraded to WATCH and the reasons are recorded. Nothing is deleted: the
    proposed action is preserved so the human can see exactly what was proposed
    and why the system would not let it stand as actionable.

    Confidence is capped at the deterministic data-quality score whenever any
    reason applies, because a proposal cannot be more reliable than the data
    underneath it.
    """
    gated: List[GatedAction] = []
    for index, item in enumerate(ranked_actions or []):
        proposed_action = (item.get("action") or "").upper()
        symbol = item.get("symbol")
        proposed_confidence = item.get("confidence")
        reasons = _reasons_for(symbol, gate)

        is_actionable = proposed_action in ACTIONABLE_ACTIONS
        restricted = bool(reasons) and is_actionable
        action = RESTRICTED_ACTION if restricted else proposed_action

        confidence = proposed_confidence
        ceilings = _confidence_ceilings(symbol, gate)
        if ceilings and isinstance(proposed_confidence, int):
            confidence = min(proposed_confidence, *ceilings)

        gated.append(GatedAction(
            rank=item.get("rank") or index + 1,
            symbol=symbol,
            action=action,
            proposed_action=proposed_action,
            confidence=confidence,
            proposed_confidence=proposed_confidence,
            restricted=restricted,
            reasons=reasons,
            proposed_index=index,
        ))

    # Ranks must be unique and contiguous; the model's numbering is only a hint,
    # and duplicate ranks must not be able to break persistence.
    gated.sort(key=lambda entry: (entry.rank, entry.proposed_index))
    for position, entry in enumerate(gated, start=1):
        entry.rank = position
    return gated
