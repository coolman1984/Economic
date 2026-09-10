"""Portfolio rules and risk-limit evaluation.

Phase 1 implements the deterministic limits the simulation and committee need:
minimum cash, maximum single-position weight, and unpriced-holding visibility.
Sector, liquidity, and drawdown limits belong to Phase 3 (see ROADMAP.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from .money import ZERO, to_decimal, to_text
from .portfolio import Valuation


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
