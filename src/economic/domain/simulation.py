"""Deterministic what-if simulation.

Critical invariant (BUILD_GUIDE Step 6): a simulation never mutates the live
ledger. This module operates only on a *copy* of a ``PortfolioState`` and
returns a plain result object; it has no access to persistence at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from . import ledger, portfolio
from .money import ZERO, money, pct, to_text

ENGINE_VERSION = "simulation/1.0"


@dataclass
class SimulationResult:
    """Before/after view of one hypothetical trade."""

    action: str
    symbol: str
    quantity: Decimal
    price: Decimal
    commission: Decimal
    fees: Decimal
    as_of: str
    ok: bool
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    before: Dict = field(default_factory=dict)
    after: Dict = field(default_factory=dict)
    cash_effect: Decimal = ZERO
    realized_pnl_effect: Decimal = ZERO
    engine_version: str = ENGINE_VERSION

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "symbol": self.symbol,
            "quantity": to_text(self.quantity),
            "price": to_text(self.price),
            "commission": to_text(self.commission),
            "fees": to_text(self.fees),
            "as_of": self.as_of,
            "ok": self.ok,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "before": self.before,
            "after": self.after,
            "cash_effect": to_text(self.cash_effect),
            "realized_pnl_effect": to_text(self.realized_pnl_effect),
            "engine_version": self.engine_version,
        }


def _view(state: portfolio.PortfolioState, marks, symbol: str, as_of: str) -> dict:
    valuation = portfolio.value(state, marks, as_of=as_of)
    position = state.positions.get(symbol)
    average_cost = position.average_cost if position else None
    return {
        "cash": to_text(state.cash),
        "quantity": to_text(position.quantity if position else ZERO),
        "average_cost": to_text(average_cost) if average_cost is not None else None,
        "position_market_value": next(
            (to_text(v.market_value) for v in valuation.priced_positions if v.symbol == symbol),
            None,
        ),
        "market_value": to_text(valuation.market_value),
        "total_equity": to_text(valuation.total_equity),
        "weight_pct": to_text(valuation.weight_of(symbol)),
        "realized_pnl": to_text(state.realized_pnl),
        "missing_prices": [v.symbol for v in valuation.unpriced_positions],
    }


def simulate_trade(
    state: portfolio.PortfolioState,
    marks: Dict[str, portfolio.PriceMark],
    action: str,
    symbol: str,
    qty,
    price,
    commission="0",
    fees="0",
    as_of: Optional[str] = None,
    min_cash: Optional[Decimal] = None,
    max_position_weight_pct: Optional[Decimal] = None,
) -> SimulationResult:
    """Simulate a hypothetical BUY or SELL against a copy of ``state``.

    ``state`` and ``marks`` are never modified. The trade is priced at the
    supplied ``price``, and the resulting position is marked at that same price
    so the post-trade weight reflects the trade the user is considering.
    """
    as_of = as_of or date.today().isoformat()
    action = (action or "").strip().upper()
    symbol = ledger.normalize_symbol(symbol)

    result = SimulationResult(
        action=action,
        symbol=symbol,
        quantity=ZERO,
        price=ZERO,
        commission=ZERO,
        fees=ZERO,
        as_of=as_of,
        ok=False,
    )

    try:
        transaction = ledger.build_trade_transaction(
            action, state.account_id or 0, symbol, qty, price,
            transaction_date=as_of, commission=commission, fees=fees, source="simulation",
        )
    except ledger.LedgerError as exc:
        result.errors.append(str(exc))
        return result

    result.quantity = transaction.quantity
    result.price = transaction.unit_price
    result.commission = transaction.commission
    result.fees = transaction.fees

    # Mark the traded symbol at the simulated price; leave other marks untouched.
    sim_marks = dict(marks)
    sim_marks[symbol] = portfolio.PriceMark(
        symbol=symbol, price=transaction.unit_price, price_date=as_of, source="simulation"
    )

    result.before = _view(state, sim_marks, symbol, as_of)

    working = state.copy()
    try:
        portfolio.apply_transaction(working, transaction)
    except portfolio.PortfolioError as exc:
        result.errors.append(str(exc))
        result.after = dict(result.before)
        return result

    result.after = _view(working, sim_marks, symbol, as_of)
    result.cash_effect = money(working.cash - state.cash, "cash_effect")
    result.realized_pnl_effect = money(
        working.realized_pnl - state.realized_pnl, "realized_pnl_effect"
    )
    result.ok = True

    if working.cash < 0:
        result.warnings.append(
            f"cash would go negative: {to_text(working.cash)}"
        )
    if min_cash is not None and working.cash < min_cash:
        result.warnings.append(
            f"cash {to_text(working.cash)} would fall below the minimum cash rule "
            f"{to_text(min_cash)}"
        )
    if max_position_weight_pct is not None:
        after_weight = Decimal(result.after["weight_pct"])
        if after_weight > max_position_weight_pct:
            result.warnings.append(
                f"resulting weight {to_text(after_weight)}% would exceed the maximum "
                f"position weight rule {to_text(max_position_weight_pct)}%"
            )
    if result.before["missing_prices"]:
        result.warnings.append(
            "portfolio has unpriced positions; weights and equity are partial: "
            + ", ".join(result.before["missing_prices"])
        )
    return result
