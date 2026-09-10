"""What-if simulation workflow.

The service reads the live ledger, hands a *copy* of the resulting state to the
deterministic engine, and stores the result. It never writes a transaction.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from ..domain import simulation
from ..persistence import sqlite_db
from .context import AppContext
from .portfolio_service import PortfolioService


class SimulationService:
    def __init__(self, context: AppContext):
        self.context = context
        self.repos = context.repos
        self.portfolio_service = PortfolioService(context)

    def simulate_trade(self, account_reference, action: str, symbol: str, qty, price,
                       commission="0", fees="0", as_of: Optional[str] = None,
                       persist: bool = True, research_run_id: Optional[str] = None):
        """Run one hypothetical trade and optionally record it for the audit trail."""
        as_of = as_of or date.today().isoformat()
        account = self.portfolio_service.resolve_account(account_reference)
        state = self.portfolio_service.state_for_account(account.id)
        marks = self.portfolio_service.marks_for(state, as_of)
        rules = self.portfolio_service.rules()

        result = simulation.simulate_trade(
            state, marks, action, symbol, qty, price,
            commission=commission, fees=fees, as_of=as_of,
            min_cash=rules.min_cash,
            max_position_weight_pct=rules.max_position_weight_pct,
        )

        if persist:
            payload = result.to_dict()
            with sqlite_db.transaction(self.context.connection):
                self.repos.simulations.add(
                    simulation_type="WHAT_IF_TRADE",
                    input_payload={
                        "account_id": account.id, "action": result.action,
                        "symbol": result.symbol, "quantity": payload["quantity"],
                        "price": payload["price"], "commission": payload["commission"],
                        "fees": payload["fees"], "as_of": as_of,
                    },
                    output_payload=payload,
                    engine_version=simulation.ENGINE_VERSION,
                    account_id=account.id,
                    research_run_id=research_run_id,
                )
        return result
