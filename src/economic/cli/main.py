"""Economic command-line interface.

The CLI parses arguments, calls application services, and prints results. It
contains no SQL, no accounting arithmetic, and never invokes an AI CLI directly
(PROJECT_MAP.md dependency rules).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional

from .. import __version__
from ..agents import artifacts as artifact_module
from ..application.context import AppContext
from ..application.decision_service import DecisionService
from ..application.market_data_service import MarketDataService
from ..application.portfolio_service import PortfolioService
from ..application.research_service import ResearchService
from ..application.simulation_service import SimulationService
from ..data_providers.base import ProviderError
from ..domain import decisions as decision_rules
from ..domain import ledger, portfolio, risk
from ..domain.money import AmountError, display, to_text
from ..persistence import sqlite_db
from ..persistence.repositories import DuplicateTransactionError, NotFoundError
from . import demo, formatting

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

HUMAN_GATE_NOTICE = (
    "This system never places broker orders. Recording a decision stores your "
    "intention only; a real execution is recorded separately."
)


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------

def _global_options() -> argparse.ArgumentParser:
    """Options accepted either before or after the subcommand.

    ``SUPPRESS`` keeps the unused copy from overwriting a value the user gave on
    the other side of the subcommand; ``_apply_global_defaults`` fills in the
    value when neither side supplied one.
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--home", type=Path, default=argparse.SUPPRESS,
                        help="project home directory (default: current directory)")
    common.add_argument("--config", type=Path, default=argparse.SUPPRESS,
                        help="path to a config JSON file")
    common.add_argument("--json", action="store_true", dest="as_json",
                        default=argparse.SUPPRESS,
                        help="print machine-readable JSON instead of a table")
    return common


COMMON = _global_options()


def _leaf(subparsers, name: str, **kwargs) -> argparse.ArgumentParser:
    """Add a runnable subcommand that also accepts the global options."""
    kwargs.setdefault("parents", [COMMON])
    return subparsers.add_parser(name, **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="economic",
        description="Local-first personal AI investment office for the Egyptian Exchange.",
        parents=[COMMON],
    )
    parser.add_argument("--version", action="version", version=f"economic {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    _leaf(sub, "init", help="create the database and runtime folders")
    doctor = _leaf(sub, "doctor", help="check database and agent CLI availability")
    doctor.add_argument("--mock", action="store_true", help="report the mock adapters instead")

    # account
    account = sub.add_parser("account", help="manage brokerage accounts").add_subparsers(
        dest="subcommand", required=True)
    account_add = _leaf(account, "add", help="add an account")
    account_add.add_argument("--name", required=True)
    account_add.add_argument("--broker")
    account_add.add_argument("--currency")
    _leaf(account, "list", help="list accounts")

    # instrument
    instrument = sub.add_parser("instrument", help="manage instruments").add_subparsers(
        dest="subcommand", required=True)
    instrument_add = _leaf(instrument, "add", help="add or update an instrument")
    instrument_add.add_argument("--symbol", required=True)
    instrument_add.add_argument("--name")
    instrument_add.add_argument("--sector")
    instrument_add.add_argument("--industry")
    _leaf(instrument, "list", help="list instruments")

    # cash
    cash = sub.add_parser("cash", help="record deposits and withdrawals").add_subparsers(
        dest="subcommand", required=True)
    for name, help_text in (("deposit", "record a cash deposit"),
                            ("withdraw", "record a cash withdrawal")):
        cash_cmd = _leaf(cash, name, help=help_text)
        cash_cmd.add_argument("--account", required=True, help="account id or name")
        cash_cmd.add_argument("--amount", required=True)
        cash_cmd.add_argument("--date")
        cash_cmd.add_argument("--fees", default="0")
        cash_cmd.add_argument("--note")
        cash_cmd.add_argument("--allow-duplicate", action="store_true",
                              help="record an identical repeat entry on purpose")

    # trade
    trade = sub.add_parser("trade", help="record buys and sells").add_subparsers(
        dest="subcommand", required=True)
    for name, help_text in (("buy", "record a purchase"), ("sell", "record a sale")):
        trade_cmd = _leaf(trade, name, help=help_text)
        trade_cmd.add_argument("--account", required=True, help="account id or name")
        trade_cmd.add_argument("--symbol", required=True)
        trade_cmd.add_argument("--qty", required=True)
        trade_cmd.add_argument("--price", required=True)
        trade_cmd.add_argument("--commission", default="0")
        trade_cmd.add_argument("--fees", default="0")
        trade_cmd.add_argument("--date")
        trade_cmd.add_argument("--sector")
        trade_cmd.add_argument("--note")
        trade_cmd.add_argument("--allow-duplicate", action="store_true",
                               help="record an identical repeat trade on purpose")

    # price
    price = sub.add_parser("price", help="manage manual price snapshots").add_subparsers(
        dest="subcommand", required=True)
    price_set = _leaf(price, "set", help="record a closing price")
    price_set.add_argument("--symbol", required=True)
    price_set.add_argument("--price", required=True)
    price_set.add_argument("--date")
    price_set.add_argument("--source", default="manual")
    price_set.add_argument("--source-url")
    price_show = _leaf(price, "show", help="show recent price snapshots")
    price_show.add_argument("--symbol", required=True)
    price_show.add_argument("--limit", type=int, default=10)

    # portfolio
    portfolio_cmd = sub.add_parser("portfolio", help="view portfolio state").add_subparsers(
        dest="subcommand", required=True)
    portfolio_show = _leaf(portfolio_cmd, "show", help="show holdings and equity")
    portfolio_show.add_argument("--account", help="account id or name; omit for all accounts")
    portfolio_show.add_argument("--as-of", help="valuation date (YYYY-MM-DD)")
    portfolio_ledger = _leaf(portfolio_cmd, "ledger", help="list recorded transactions")
    portfolio_ledger.add_argument("--account", required=True)
    portfolio_ledger.add_argument("--limit", type=int, default=50)

    # simulate
    simulate = _leaf(sub, "simulate", help="run a what-if trade without changing anything")
    simulate.add_argument("--account", required=True)
    simulate.add_argument("--action", required=True, choices=["BUY", "SELL", "buy", "sell"])
    simulate.add_argument("--symbol", required=True)
    simulate.add_argument("--qty", required=True)
    simulate.add_argument("--price", required=True)
    simulate.add_argument("--commission", default="0")
    simulate.add_argument("--fees", default="0")
    simulate.add_argument("--as-of")
    simulate.add_argument("--no-save", action="store_true",
                          help="do not store the simulation in history")

    # committee
    committee = _leaf(sub, "committee", help="run the investment committee")
    committee.add_argument("--question", required=True)
    committee.add_argument("--account", help="account id or name; omit for all accounts")
    committee.add_argument("--mock", action="store_true", help="run with offline mock agents")
    committee.add_argument("--live", action="store_true", help="force real provider CLIs")
    committee.add_argument("--chair", choices=["codex", "claude"], help="final synthesis provider")
    committee.add_argument("--as-of")

    # decide
    decide = _leaf(sub, "decide", help="record your decision on a run")
    decide.add_argument("--run", required=True, help="run id or unique prefix")
    decide.add_argument("--decision", required=True,
                        choices=[d.lower() for d in decision_rules.HUMAN_DECISIONS]
                        + list(decision_rules.HUMAN_DECISIONS))
    decide.add_argument("--recommendation", type=int, help="recommendation id being decided")
    decide.add_argument("--modified-action", help="the action you chose instead (for MODIFY)")
    decide.add_argument("--note")

    # execution
    execution = sub.add_parser("execution", help="link a real broker transaction to a decision")
    execution_sub = execution.add_subparsers(dest="subcommand", required=True)
    execution_record = _leaf(execution_sub, "record", help="record an actual execution")
    execution_record.add_argument("--transaction", type=int, required=True,
                                  help="id of the already-recorded transaction")
    execution_record.add_argument("--decision", type=int, help="human decision id")
    execution_record.add_argument("--note")

    # history / run
    history = _leaf(sub, "history", help="list past research runs")
    history.add_argument("--limit", type=int, default=20)
    history.add_argument("--account")

    run_cmd = sub.add_parser("run", help="inspect one research run").add_subparsers(
        dest="subcommand", required=True)
    run_show = _leaf(run_cmd, "show", help="show a full run from history")
    run_show.add_argument("run_id")
    run_show.add_argument("--full", action="store_true",
                          help="include full agent outputs and critiques")

    # audit
    audit = _leaf(sub, "audit", help="show the audit log")
    audit.add_argument("--limit", type=int, default=30)
    audit.add_argument("--entity-type")

    # demo
    demo_cmd = sub.add_parser("demo", help="load fictional demo data").add_subparsers(
        dest="subcommand", required=True)
    demo_seed = _leaf(demo_cmd, "seed", help="create a fictional demo account")
    demo_seed.add_argument("--account", default=demo.DEMO_ACCOUNT)

    # market (Phase 2 — market-truth layer)
    market = sub.add_parser(
        "market", help="import instruments, prices, disclosures, and financial facts"
    ).add_subparsers(dest="subcommand", required=True)

    market_instruments = _leaf(market, "import-instruments",
                               help="bulk-import an instrument master CSV")
    market_instruments.add_argument("--file", required=True, type=Path)

    market_prices = _leaf(market, "import-prices", help="bulk-import an EOD price CSV")
    market_prices.add_argument("--file", required=True, type=Path)

    market_disclosures = _leaf(market, "import-disclosures",
                               help="import official documents from a manifest CSV")
    market_disclosures.add_argument("--manifest", required=True, type=Path)
    market_disclosures.add_argument("--docs-dir", type=Path,
                                    help="directory the manifest's file paths are relative to"
                                    " (default: the manifest's own directory)")

    market_financials = _leaf(market, "import-financials",
                              help="import normalized financial-statement facts CSV")
    market_financials.add_argument("--file", required=True, type=Path)

    market_trace = _leaf(market, "trace",
                         help="show every stored fact for a symbol and its source")
    market_trace.add_argument("--symbol", required=True)

    market_history = _leaf(market, "history", help="list past ingestion runs")
    market_history.add_argument("--limit", type=int, default=20)
    market_history.add_argument("--kind",
                                choices=["instruments", "prices", "disclosures",
                                        "financial_facts"])

    return parser


# ---------------------------------------------------------------------------
# command handlers
# ---------------------------------------------------------------------------

def _print(payload, args, render) -> None:
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        render()


def cmd_init(context: AppContext, args) -> int:
    config = context.config
    payload = {
        "database": str(config.database_path),
        "schema_version": sqlite_db.schema_version(context.connection),
        "runs_dir": str(config.runs_dir),
        "config_source": str(config.source) if config.source else None,
        "accounts": len(context.repos.accounts.list()),
    }

    def render():
        print(formatting.heading("Economic initialized"))
        print(f"database        {payload['database']}")
        print(f"schema version  {payload['schema_version']}")
        print(f"run artifacts   {payload['runs_dir']}")
        print(f"config          {payload['config_source'] or 'built-in defaults'}")
        print(f"accounts        {payload['accounts']}")
        print("\nNext: economic account add --name \"My Broker Account\"")

    _print(payload, args, render)
    return EXIT_OK


def cmd_doctor(context: AppContext, args) -> int:
    research = ResearchService(context)
    adapters = research.doctor(mock=True if args.mock else None)
    integrity = sqlite_db.integrity_check(context.connection)
    payload = {
        "version": __version__,
        "database": {
            "path": str(context.config.database_path),
            "exists": context.config.database_path.exists(),
            "schema_version": sqlite_db.schema_version(context.connection),
            "integrity": integrity or "ok",
            "accounts": len(context.repos.accounts.list()),
            "transactions": len(context.repos.transactions.list_all()),
        },
        "mock_mode": context.config.mock_agents or bool(args.mock),
        "chair": context.config.chair,
        "min_data_quality_for_action": context.config.min_data_quality_for_action,
        "available_providers": [a["provider"] for a in adapters if a["available"]],
        "committee_would_be_degraded": len([a for a in adapters if a["available"]]) < 2,
        "agents": adapters,
    }

    def render():
        print(formatting.heading("Doctor"))
        database = payload["database"]
        print(f"economic        {payload['version']}")
        print(f"database        {database['path']} (schema v{database['schema_version']}, "
              f"integrity {database['integrity']})")
        print(f"records         {database['accounts']} account(s), "
              f"{database['transactions']} transaction(s)")
        print(f"mock mode       {'on' if payload['mock_mode'] else 'off'}")
        print(f"chair provider  {payload['chair']}")
        print(formatting.heading("Agent CLIs"))
        print(formatting.table(
            ["provider", "available", "path", "version"],
            [[a["provider"], "yes" if a["available"] else "no",
              a["path"] or "not found", a["version"] or "-"] for a in adapters],
        ))
        available = [a for a in adapters if a["available"]]
        if not available:
            print("\nNo provider CLI was found. Use --mock to run the committee offline.")
        elif len(available) < 2:
            print(f"\nOnly one provider is available ({available[0]['provider']}). Any "
                  "committee run will be recorded as DEGRADED: there is no second agent "
                  "to cross-review, so actionable proposals will be restricted.")

    _print(payload, args, render)
    return EXIT_OK


def cmd_account(context: AppContext, args) -> int:
    service = PortfolioService(context)
    if args.subcommand == "add":
        account = service.add_account(args.name, args.broker, args.currency)
        payload = vars(account)
        _print(payload, args, lambda: print(
            f"Account {account.id} created: {account.name} "
            f"({account.broker or 'no broker'}, {account.currency})"))
        return EXIT_OK

    accounts = service.list_accounts()
    payload = [vars(account) for account in accounts]

    def render():
        if not accounts:
            print("No accounts yet. Add one with: economic account add --name \"...\"")
            return
        print(formatting.table(
            ["id", "name", "broker", "currency", "status"],
            [[a.id, a.name, a.broker or "-", a.currency, a.status] for a in accounts],
        ))

    _print(payload, args, render)
    return EXIT_OK


def cmd_instrument(context: AppContext, args) -> int:
    service = PortfolioService(context)
    if args.subcommand == "add":
        instrument = service.add_instrument(args.symbol, args.name, args.sector, args.industry)
        payload = vars(instrument)
        _print(payload, args, lambda: print(
            f"Instrument {instrument.symbol} saved "
            f"({instrument.name or 'no name'}, sector {instrument.sector or '-'})"))
        return EXIT_OK

    instruments = service.list_instruments()
    payload = [vars(instrument) for instrument in instruments]
    _print(payload, args, lambda: print(formatting.table(
        ["symbol", "name", "sector", "exchange", "currency"],
        [[i.symbol, i.name or "-", i.sector or "-", i.exchange, i.currency] for i in instruments],
    )) if instruments else print("No instruments recorded yet."))
    return EXIT_OK


def cmd_cash(context: AppContext, args) -> int:
    service = PortfolioService(context)
    transaction_type = ledger.DEPOSIT if args.subcommand == "deposit" else ledger.WITHDRAW
    transaction = service.record_cash(
        args.account, transaction_type, args.amount, transaction_date=args.date,
        fees=args.fees, note=args.note, allow_duplicate=args.allow_duplicate,
    )
    state = service.state_for_account(transaction.account_id)
    payload = {"transaction_id": transaction.id, "type": transaction.transaction_type,
               "cash_amount": to_text(transaction.cash_amount),
               "date": transaction.transaction_date, "cash_after": to_text(state.cash)}
    _print(payload, args, lambda: print(
        f"{transaction.transaction_type} recorded (id {transaction.id}) on "
        f"{transaction.transaction_date}: {display(transaction.cash_amount)}. "
        f"Cash is now {display(state.cash)}."))
    return EXIT_OK


def cmd_trade(context: AppContext, args) -> int:
    service = PortfolioService(context)
    transaction_type = ledger.BUY if args.subcommand == "buy" else ledger.SELL
    transaction = service.record_trade(
        args.account, transaction_type, args.symbol, args.qty, args.price,
        transaction_date=args.date, commission=args.commission, fees=args.fees,
        note=args.note, allow_duplicate=args.allow_duplicate, sector=args.sector,
    )
    state = service.state_for_account(transaction.account_id)
    position = state.positions.get(transaction.symbol)
    payload = {
        "transaction_id": transaction.id,
        "type": transaction.transaction_type,
        "symbol": transaction.symbol,
        "quantity": to_text(transaction.quantity),
        "unit_price": to_text(transaction.unit_price),
        "cash_amount": to_text(transaction.cash_amount),
        "date": transaction.transaction_date,
        "cash_after": to_text(state.cash),
        "quantity_after": to_text(position.quantity) if position else "0",
        "average_cost_after": to_text(position.average_cost)
        if position and position.average_cost is not None else None,
        "realized_pnl_total": to_text(position.realized_pnl) if position else "0",
    }

    def render():
        print(f"{transaction.transaction_type} recorded (id {transaction.id}) on "
              f"{transaction.transaction_date}: {to_text(transaction.quantity)} "
              f"{transaction.symbol} @ {display(transaction.unit_price)} "
              f"(cash {display(transaction.cash_amount)})")
        if position:
            average = ("-" if position.average_cost is None
                       else display(position.average_cost))
            print(f"  position: {to_text(position.quantity)} {transaction.symbol}, "
                  f"average cost {average}, realized P&L "
                  f"{display(position.realized_pnl)}")
        print(f"  cash: {display(state.cash)}")

    _print(payload, args, render)
    return EXIT_OK


def cmd_price(context: AppContext, args) -> int:
    service = PortfolioService(context)
    if args.subcommand == "set":
        mark = service.set_price(args.symbol, args.price, args.date, args.source,
                                 args.source_url)
        payload = {"symbol": mark.symbol, "price": to_text(mark.price),
                   "price_date": mark.price_date, "source": mark.source}
        _print(payload, args, lambda: print(
            f"Price recorded: {mark.symbol} = {display(mark.price)} on {mark.price_date} "
            f"(source: {mark.source})"))
        return EXIT_OK

    marks = service.price_history(args.symbol, args.limit)
    payload = [{"symbol": m.symbol, "price": to_text(m.price), "price_date": m.price_date,
                "source": m.source, "retrieved_at": m.retrieved_at} for m in marks]
    _print(payload, args, lambda: print(formatting.table(
        ["date", "price", "source", "retrieved"],
        [[m.price_date, display(m.price), m.source, m.retrieved_at or "-"] for m in marks],
        align_right=[1],
    )) if marks else print(f"No price snapshots recorded for {args.symbol.upper()}."))
    return EXIT_OK


def _render_valuation(valuation: portfolio.Valuation, rules: risk.PortfolioRules,
                      title: str) -> None:
    print(formatting.heading(title))
    print(f"as of {valuation.as_of}")
    if valuation.positions:
        rows = []
        for valued in valuation.positions:
            position = valued.position
            rows.append([
                valued.symbol,
                to_text(position.quantity),
                formatting.money_cell(position.average_cost),
                formatting.money_cell(valued.mark.price) if valued.mark else "no price",
                valued.mark.price_date if valued.mark else "-",
                formatting.money_cell(valued.market_value),
                formatting.money_cell(valued.unrealized_pnl),
                formatting.money_cell(position.realized_pnl),
                (f"{display(valuation.weight_of(valued.symbol))}%" if valued.is_priced else "-"),
                "STALE" if valued.is_stale else ("UNPRICED" if not valued.is_priced else ""),
            ])
        print(formatting.table(
            ["symbol", "qty", "avg cost", "price", "price date", "market value",
             "unrealized", "realized", "weight", "flag"],
            rows, align_right=[1, 2, 3, 5, 6, 7, 8],
        ))
    else:
        print("No open positions.")

    print()
    print(f"cash            {display(valuation.cash)}")
    print(f"market value    {display(valuation.market_value)}")
    print(f"total equity    {display(valuation.total_equity)}")
    print(f"unrealized P&L  {display(valuation.unrealized_pnl)}")
    print(f"realized P&L    {display(valuation.realized_pnl)}")
    print(f"data quality    {risk.data_quality_score(valuation)}/100")

    if valuation.unpriced_positions:
        print("\nUnpriced holdings are EXCLUDED from market value and equity:")
        for line in formatting.bullets(
                [f"{v.symbol}: record a price with "
                 f"'economic price set --symbol {v.symbol} --price ...'"
                 for v in valuation.unpriced_positions]):
            print(line)

    violations = risk.evaluate(valuation, rules)
    actionable = [v for v in violations if v.severity != "data_quality"]
    if actionable:
        print("\nPortfolio rule warnings:")
        for line in formatting.bullets([v.detail for v in actionable]):
            print(line)


def cmd_portfolio(context: AppContext, args) -> int:
    service = PortfolioService(context)
    if args.subcommand == "ledger":
        account = service.resolve_account(args.account)
        transactions = service.repos.transactions.list_for_account(account.id)[-args.limit:]
        payload = [{
            "id": t.id, "date": t.transaction_date, "type": t.transaction_type,
            "symbol": t.symbol, "quantity": to_text(t.quantity),
            "unit_price": to_text(t.unit_price), "cash_amount": to_text(t.cash_amount),
            "commission": to_text(t.commission), "fees": to_text(t.fees), "note": t.note,
        } for t in transactions]
        _print(payload, args, lambda: print(formatting.table(
            ["id", "date", "type", "symbol", "qty", "price", "cash", "fees", "note"],
            [[t.id, t.transaction_date, t.transaction_type, t.symbol or "-",
              to_text(t.quantity) if t.is_trade else "-",
              display(t.unit_price) if t.is_trade else "-",
              display(t.cash_amount), display(t.total_charges), t.note or ""]
             for t in transactions],
            align_right=[0, 4, 5, 6, 7],
        )) if transactions else print(f"No transactions recorded for {account.name}."))
        return EXIT_OK

    valuation = service.valuation(args.account, args.as_of)
    rules = service.rules()
    snapshot = service.snapshot(args.account, args.as_of)
    title = ("Portfolio — all accounts" if args.account is None
             else f"Portfolio — {service.resolve_account(args.account).name}")
    _print(snapshot, args, lambda: _render_valuation(valuation, rules, title))
    return EXIT_OK


def cmd_simulate(context: AppContext, args) -> int:
    service = SimulationService(context)
    result = service.simulate_trade(
        args.account, args.action, args.symbol, args.qty, args.price,
        commission=args.commission, fees=args.fees, as_of=args.as_of,
        persist=not args.no_save,
    )
    payload = result.to_dict()

    def render():
        print(formatting.heading(
            f"Simulation — {result.action} {to_text(result.quantity)} {result.symbol} "
            f"@ {display(result.price)}"))
        print("This is a what-if only. Nothing was recorded in the ledger.\n")
        if not result.ok:
            print("Not possible:")
            for line in formatting.bullets(result.errors):
                print(line)
            return
        rows = [
            ["cash", result.before["cash"], result.after["cash"]],
            ["quantity", result.before["quantity"], result.after["quantity"]],
            ["average cost", result.before["average_cost"] or "-",
             result.after["average_cost"] or "-"],
            ["position weight", f"{result.before['weight_pct']}%",
             f"{result.after['weight_pct']}%"],
            ["total equity", result.before["total_equity"], result.after["total_equity"]],
            ["realized P&L", result.before["realized_pnl"], result.after["realized_pnl"]],
        ]
        print(formatting.table(["measure", "before", "after"], rows, align_right=[1, 2]))
        print(f"\ncash effect     {result.cash_effect}")
        if result.realized_pnl_effect != 0:
            print(f"realized P&L    {result.realized_pnl_effect}")
        if result.warnings:
            print("\nWarnings:")
            for line in formatting.bullets(result.warnings):
                print(line)

    _print(payload, args, render)
    return EXIT_OK if result.ok else EXIT_ERROR


def _stage_reporter(quiet: bool):
    def report(stage: str, provider: str, status: str) -> None:
        if quiet:
            return
        if status == "started":
            print(f"  [{stage}] {provider} ... ", end="", flush=True)
        else:
            print(status)
    return report


def cmd_committee(context: AppContext, args) -> int:
    service = ResearchService(context)
    mock = True if args.mock else (False if args.live else None)
    if not args.as_json:
        print(formatting.heading("Investment committee"))
    result = service.run_committee(
        question=args.question, account_reference=args.account, mock=mock,
        chair=args.chair, as_of=args.as_of, on_stage=_stage_reporter(args.as_json),
    )
    _print(result, args, lambda: _render_run(result, full=False))
    return EXIT_OK if result["run"]["status"] == decision_rules.READY_FOR_HUMAN else EXIT_ERROR


def _render_committee_banner(run: dict, integrity: Optional[dict]) -> None:
    """State plainly whether this was a real dual-agent committee."""
    if not integrity:
        return
    if integrity.get("degraded"):
        print()
        print("!" * 72)
        print("DEGRADED COMMITTEE — this was NOT a full dual-agent review.")
        for reason in integrity.get("reasons", []):
            print(f"  - {reason}")
        print(f"  analyses: {integrity.get('analyst_count')}   "
              f"cross-reviews: {integrity.get('critique_count')}")
        print("Actionable proposals were restricted and confidence was capped.")
        print("!" * 72)
    else:
        print(f"committee   FULL ({integrity.get('analyst_count')} independent analyses, "
              f"{integrity.get('critique_count')} cross-reviews)")


def _render_run(payload: dict, full: bool = False) -> None:
    run = payload["run"]
    integrity = payload.get("committee_integrity")
    print(formatting.heading(f"Run {run['id']}"))
    print(f"question    {run['question']}")
    print(f"status      {run['status']}")
    print(f"mode        {run['mode']}   chair: {run['chair_provider'] or '-'}")
    print(f"created     {run['created_at']}")
    print(f"artifacts   {payload['artifact_dir']}")
    _render_committee_banner(run, integrity)

    snapshot = run.get("portfolio_snapshot") or {}
    if snapshot:
        print(f"\nportfolio at run time: cash {snapshot.get('cash')}, equity "
              f"{snapshot.get('total_equity')}, data quality "
              f"{snapshot.get('data_quality_score')}/100")
        if snapshot.get("missing_prices"):
            print(f"  missing prices: {', '.join(snapshot['missing_prices'])}")

    agent_runs = payload.get("agent_runs", [])
    if agent_runs:
        print(formatting.heading("Agent stages"))
        print(formatting.table(
            ["provider", "role", "stage", "status", "detail"],
            [[a["agent_provider"], a["agent_role"], a["stage"], a["status"],
              a["failure_kind"] or "-"] for a in agent_runs],
        ))

    synthesis = payload.get("synthesis")
    if synthesis:
        print(formatting.heading("Chair synthesis"))
        print(synthesis.get("summary", ""))
        agreement = run.get("agreement_score")
        agreement_text = (
            f"{agreement}/100" if agreement is not None
            else "not measurable (fewer than two analyses)"
        )
        print(f"\ndata quality {run.get('data_quality_score')}/100    "
              f"agreement {agreement_text}")
        if synthesis.get("data_quality_score") != run.get("data_quality_score"):
            print(f"  (the chair reported {synthesis.get('data_quality_score')}/100; the "
                  "score above is the one the software calculated)")
        for recommendation in payload.get("recommendations", []):
            print(f"\n  #{recommendation['rank']} {recommendation['action']} "
                  f"{recommendation['symbol'] or '(portfolio-level)'}  "
                  f"confidence {recommendation['confidence']}  "
                  f"[recommendation id {recommendation['id']}]")
            if recommendation.get("restricted"):
                print(f"     RESTRICTED: the chair proposed "
                      f"{recommendation['proposed_action']} at confidence "
                      f"{recommendation['proposed_confidence']}. The evidence gate "
                      f"downgraded it because:")
                for reason in recommendation.get("restriction_reasons") or []:
                    print(f"       - {reason}")
            if recommendation.get("thesis_summary"):
                print(f"     why: {recommendation['thesis_summary']}")
            if recommendation.get("counterargument"):
                print(f"     strongest counterargument: {recommendation['counterargument']}")
            for invalidator in (recommendation.get("invalidators") or [])[:3]:
                print(f"     invalidator: {invalidator}")
        if synthesis.get("unresolved_questions"):
            print("\nUnresolved questions:")
            for line in formatting.bullets(synthesis["unresolved_questions"]):
                print(line)
    else:
        print("\nNo validated synthesis was produced.")

    if payload.get("disagreements"):
        print(formatting.heading("Material disagreements"))
        for item in payload["disagreements"]:
            print(f"  - {item['topic']} (materiality: {item['materiality']})")
            if item.get("codex_position"):
                print(f"      codex:  {item['codex_position']}")
            if item.get("claude_position"):
                print(f"      claude: {item['claude_position']}")

    if payload.get("failures"):
        print(formatting.heading("Failures"))
        for failure in payload["failures"]:
            print(f"  - {failure['provider']} / {failure['stage']}: {failure['detail']}")

    if payload.get("stopped_because"):
        print("\nStopping conditions:")
        for line in formatting.bullets(payload["stopped_because"]):
            print(line)

    decisions = payload.get("decisions", [])
    if decisions:
        print(formatting.heading("Human decisions"))
        print(formatting.table(
            ["id", "decision", "recommendation", "modified action", "note", "recorded"],
            [[d["id"], d["decision"], d["recommendation_id"] or "-",
              d["modified_action"] or "-", d["note"] or "", d["created_at"]] for d in decisions],
        ))
    elif run["status"] == decision_rules.READY_FOR_HUMAN:
        print(f"\n{HUMAN_GATE_NOTICE}")
        print(f"Record yours: economic decide --run {run['id'][:18]} --decision APPROVE|REJECT|HOLD|MODIFY")

    if full:
        print(formatting.heading("Full agent output"))
        for agent_run in agent_runs:
            print(f"\n--- {agent_run['agent_provider']} / {agent_run['stage']} ---")
            print(json.dumps(agent_run.get("parsed_output") or
                             {"validation_errors": agent_run.get("validation_errors")},
                             ensure_ascii=False, indent=2))


def cmd_decide(context: AppContext, args) -> int:
    service = DecisionService(context)
    record = service.record(args.run, args.decision, args.recommendation,
                            args.modified_action, args.note)

    def render():
        # The human must be reminded what they are deciding on, at the moment
        # they decide it, not only when they first read the run.
        if record.get("committee_mode") == "DEGRADED":
            print("Note: this decision is recorded against a DEGRADED committee "
                  "(no full dual-agent cross-review).")
        if record.get("restricted_recommendation"):
            print("Note: the recommendation you decided on was restricted by the "
                  "evidence gate; the chair had proposed "
                  f"{record['restricted_recommendation']}.")
        print(f"Decision recorded: {record['decision']} (id {record['id']})")
        print(f"Run status is now {record['run_status']}.")
        print(HUMAN_GATE_NOTICE)
        if record["decision"] == decision_rules.APPROVE:
            print("If you act with your broker, record the real trade with "
                  "'economic trade buy|sell ...' and link it using "
                  f"'economic execution record --transaction <id> --decision {record['id']}'.")

    _print(record, args, render)
    return EXIT_OK


def cmd_execution(context: AppContext, args) -> int:
    service = PortfolioService(context)
    execution_id = service.record_execution(args.transaction, args.decision, args.note)
    payload = {"execution_id": execution_id, "transaction_id": args.transaction,
               "human_decision_id": args.decision}
    _print(payload, args, lambda: print(
        f"Execution {execution_id} recorded for transaction {args.transaction}"
        + (f", linked to decision {args.decision}." if args.decision else ".")))
    return EXIT_OK


def cmd_history(context: AppContext, args) -> int:
    service = ResearchService(context)
    runs = service.list_runs(limit=args.limit, account_reference=args.account)
    payload = [{k: v for k, v in run.items() if k != "portfolio_snapshot"} for run in runs]

    def render():
        if not runs:
            print("No research runs yet. Start one with: "
                  "economic committee --question \"...\" --mock")
            return
        print(formatting.table(
            ["run id", "created", "mode", "committee", "status", "question"],
            [[run["id"], run["created_at"], run["mode"], run.get("committee_mode", "UNKNOWN"),
              run["status"],
              (run["question"][:48] + "...") if len(run["question"]) > 48 else run["question"]]
             for run in runs],
        ))

    _print(payload, args, render)
    return EXIT_OK


def cmd_run(context: AppContext, args) -> int:
    service = ResearchService(context)
    payload = service.get_run(args.run_id)
    _print(payload, args, lambda: _render_run(payload, full=args.full))
    return EXIT_OK


def cmd_audit(context: AppContext, args) -> int:
    entries = context.repos.audit.list(limit=args.limit, entity_type=args.entity_type)
    _print(entries, args, lambda: print(formatting.table(
        ["id", "when", "actor", "action", "entity", "reference"],
        [[e["id"], e["created_at"], e["actor_type"], e["action"], e["entity_type"],
          e["entity_id"] or "-"] for e in entries],
    )) if entries else print("Audit log is empty."))
    return EXIT_OK


def _render_ingestion_report(report) -> None:
    verb = "OK" if report.ok else "FAILED"
    print(formatting.heading(f"Ingestion {verb} — {report.kind}"))
    print(f"source      {report.source}")
    if not report.ok:
        print(f"failure     {report.failure_kind}")
        print(f"error       {report.error}")
        return
    print(f"read        {report.read}")
    print(f"inserted    {report.inserted}")
    print(f"updated     {report.updated}")
    print(f"duplicate   {report.duplicate}")
    print(f"rejected    {report.rejected_count}")
    if report.rejected:
        print("\nRejected rows:")
        for item in formatting.bullets(
                [f"row {r.index}: {r.reason}" for r in report.rejected]):
            print(item)


def cmd_market(context: AppContext, args) -> int:
    service = MarketDataService(context)

    if args.subcommand == "import-instruments":
        report = service.import_instruments(args.file)
    elif args.subcommand == "import-prices":
        report = service.import_prices(args.file)
    elif args.subcommand == "import-disclosures":
        report = service.import_disclosures(args.manifest, docs_dir=args.docs_dir)
    elif args.subcommand == "import-financials":
        report = service.import_financial_facts(args.file)
    elif args.subcommand == "trace":
        trace = service.trace_symbol(args.symbol)

        def render():
            print(formatting.heading(f"Traceability — {trace['symbol']}"))
            instrument = trace["instrument"]
            print(f"{instrument['symbol']}  {instrument.get('name') or '(no name on file)'}")
            print(f"sector: {instrument.get('sector') or '-'}   "
                  f"isin: {instrument.get('isin') or '-'}")

            print(formatting.heading("Prices"))
            if trace["prices"]:
                print(formatting.table(
                    ["date", "close", "source", "retrieved"],
                    [[p["price_date"], p["close"], p["source"], p["retrieved_at"]]
                     for p in trace["prices"]],
                ))
            else:
                print("No price history recorded.")

            print(formatting.heading("Disclosures"))
            if trace["documents"]:
                for doc in trace["documents"]:
                    print(f"\n  [{doc['document_type']}] {doc['title']}")
                    print(f"    published: {doc.get('published_at') or 'unknown'}   "
                          f"source: {doc['source_name']} ({doc['source_tier']})")
                    print(f"    url: {doc.get('source_url') or '-'}")
                    print(f"    content sha256: {doc['content_hash']}")
            else:
                print("No disclosures on file.")

            print(formatting.heading("Financial facts"))
            if trace["financial_facts"]:
                print(formatting.table(
                    ["period end", "type", "metric", "value", "source", "linked doc"],
                    [[f["period_end"], f["period_type"], f["metric"], f["value"],
                      f["source_name"], f["source_document_id"] or "-"]
                     for f in trace["financial_facts"]],
                ))
            else:
                print("No financial facts on file.")

        _print(trace, args, render)
        return EXIT_OK
    elif args.subcommand == "history":
        runs = service.list_ingestion_runs(limit=args.limit, kind=args.kind)

        def render():
            if not runs:
                print("No ingestion runs yet.")
                return
            print(formatting.table(
                ["id", "kind", "ok", "inserted", "updated", "rejected", "started"],
                [[r["id"], r["kind"], "yes" if r["ok"] else "no", r["inserted_count"],
                  r["updated_count"], r["rejected_count"], r["started_at"]] for r in runs],
            ))

        _print(runs, args, render)
        return EXIT_OK
    else:  # pragma: no cover - argparse guarantees a valid subcommand
        raise ValueError(f"unknown market subcommand: {args.subcommand}")

    _print(report.to_dict(), args, lambda: _render_ingestion_report(report))
    return EXIT_OK if report.ok else EXIT_ERROR


def cmd_demo(context: AppContext, args) -> int:
    summary = demo.seed(context, account_name=args.account)

    def render():
        print(formatting.heading("Demo data loaded"))
        print("All symbols and prices below are FICTIONAL and exist only to test the software.")
        print(f"\naccount        {summary['account']}")
        print(f"transactions   {summary['transactions']}")
        print(f"prices         {summary['prices']}")
        print("\nTry next:")
        for line in summary["next_steps"]:
            print(f"  {line}")

    _print(summary, args, render)
    return EXIT_OK


HANDLERS = {
    "init": cmd_init,
    "doctor": cmd_doctor,
    "account": cmd_account,
    "instrument": cmd_instrument,
    "cash": cmd_cash,
    "trade": cmd_trade,
    "price": cmd_price,
    "portfolio": cmd_portfolio,
    "simulate": cmd_simulate,
    "committee": cmd_committee,
    "decide": cmd_decide,
    "execution": cmd_execution,
    "history": cmd_history,
    "run": cmd_run,
    "audit": cmd_audit,
    "demo": cmd_demo,
    "market": cmd_market,
}

KNOWN_ERRORS = (
    ledger.LedgerError,
    portfolio.PortfolioError,
    decision_rules.DecisionError,
    DuplicateTransactionError,
    NotFoundError,
    AmountError,
    sqlite_db.DatabaseError,
    sqlite3.DatabaseError,
    ProviderError,
    ValueError,
)


GLOBAL_DEFAULTS = {"home": None, "config": None, "as_json": False}


def _apply_global_defaults(args: argparse.Namespace) -> argparse.Namespace:
    """Fill in options the user gave on neither side of the subcommand."""
    for name, default in GLOBAL_DEFAULTS.items():
        if not hasattr(args, name):
            setattr(args, name, default)
    return args


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = _apply_global_defaults(parser.parse_args(argv))
    try:
        with AppContext.open(home=args.home, config_path=args.config) as context:
            return HANDLERS[args.command](context, args)
    except KNOWN_ERRORS as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        print("\nCancelled.", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
