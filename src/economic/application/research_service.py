"""Research workflow: build the snapshot, run the committee, persist everything.

This is the only place that constructs agent adapters. The CLI asks for a
committee run; it never learns which provider CLI was invoked or how.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from .. import CONTRACT_VERSION
from ..agents import artifacts as artifact_module
from ..agents.base_adapter import AgentAdapter
from ..agents.claude_adapter import ClaudeAdapter
from ..agents.codex_adapter import CodexAdapter
from ..agents.mock_adapter import MockAdapter
from ..agents.orchestrator import CommitteeResult, Orchestrator, new_run_id
from ..domain import decisions as decision_rules
from ..domain import risk
from ..persistence import sqlite_db
from .context import AppContext
from .portfolio_service import PortfolioService

PROVIDERS = ("codex", "claude")


def build_adapters(config, mock: Optional[bool] = None,
                   providers: Optional[List[str]] = None) -> Dict[str, AgentAdapter]:
    """Construct one adapter per enabled provider, honouring mock mode."""
    use_mock = config.mock_agents if mock is None else bool(mock)
    wanted = [p for p in (providers or PROVIDERS)]
    settings = config.agents
    adapters: Dict[str, AgentAdapter] = {}
    for provider in wanted:
        provider_config = settings.get(provider, {}) or {}
        if not provider_config.get("enabled", True):
            continue
        if use_mock:
            adapters[provider] = MockAdapter(
                provider_name=provider, timeout_seconds=config.timeout_seconds
            )
        else:
            adapter_class = CodexAdapter if provider == "codex" else ClaudeAdapter
            adapters[provider] = adapter_class(
                command=provider_config.get("command"),
                timeout_seconds=config.timeout_seconds,
                enabled=True,
            )
    return adapters


class ResearchService:
    def __init__(self, context: AppContext):
        self.context = context
        self.repos = context.repos
        self.config = context.config
        self.portfolio_service = PortfolioService(context)

    # ---- diagnostics -----------------------------------------------------

    def doctor(self, mock: Optional[bool] = None) -> List[dict]:
        return [adapter.doctor() for adapter in build_adapters(self.config, mock=mock).values()]

    # ---- committee -------------------------------------------------------

    def run_committee(self, question: str, account_reference=None, mock: Optional[bool] = None,
                      chair: Optional[str] = None, as_of: Optional[str] = None,
                      on_stage=None, simulations: Optional[List[dict]] = None) -> dict:
        """Run one full committee and leave the run at the human gate."""
        as_of = as_of or date.today().isoformat()
        use_mock = self.config.mock_agents if mock is None else bool(mock)
        adapters = build_adapters(self.config, mock=use_mock)
        if not adapters:
            raise RuntimeError("no agent providers are enabled; check config agents.*.enabled")

        account = (
            None if account_reference is None
            else self.portfolio_service.resolve_account(account_reference)
        )
        run_id = new_run_id(as_of)
        artifacts = artifact_module.RunArtifacts(self.config.runs_dir, run_id).ensure()
        chair_provider = chair or self.config.chair

        snapshot = self.portfolio_service.snapshot(account_reference, as_of)
        context_payload = self._build_context(question, snapshot, as_of, simulations)

        with sqlite_db.transaction(self.context.connection):
            self.repos.research_runs.create(
                run_id=run_id, question=question, status=decision_rules.COLLECTING_DATA,
                contract_version=CONTRACT_VERSION,
                account_id=account.id if account else None,
                scope_type="ACCOUNT" if account else "CONSOLIDATED",
                scope_reference=account.name if account else None,
                mode="mock" if use_mock else "live",
                chair_provider=chair_provider,
                artifact_dir=str(artifacts.directory),
            )
            self.repos.research_runs.set_snapshot(run_id, snapshot)
            self.repos.research_runs.set_status(run_id, decision_rules.DATA_VALIDATED)
            self.repos.audit.record(
                action="RESEARCH_RUN_CREATED", entity_type="research_run", entity_id=run_id,
                actor_type="system",
                after={"question": question, "mode": "mock" if use_mock else "live",
                       "account_id": account.id if account else None},
            )

        artifacts.write_json(artifact_module.PORTFOLIO_SNAPSHOT, snapshot)
        artifacts.write_json(artifact_module.MARKET_CONTEXT, {
            "as_of": as_of,
            "sources": [],
            "note": (
                "Phase 1 has no automated market-data ingestion. Prices come from "
                "manual snapshots recorded by the user."
            ),
        })
        artifacts.write_json(artifact_module.RUN_META, {
            "run_id": run_id, "created_for": question, "as_of": as_of,
            "mode": "mock" if use_mock else "live", "chair": chair_provider,
            "providers": sorted(adapters), "contract_version": CONTRACT_VERSION,
        })
        if simulations:
            artifacts.write_json(artifact_module.SIMULATIONS, simulations)
        artifacts.write_json(artifact_module.RISK_REVIEW, context_payload["risk_review"])

        orchestrator = Orchestrator(
            adapters=adapters, artifacts=artifacts, chair=chair_provider,
            timeout_seconds=self.config.timeout_seconds, on_stage=on_stage,
        )
        result = orchestrator.run_committee(run_id, question, context_payload,
                                            mode="mock" if use_mock else "live")

        self._persist_result(run_id, result)
        return self.get_run(run_id)

    def _build_context(self, question: str, snapshot: dict, as_of: str,
                       simulations: Optional[List[dict]]) -> dict:
        """Minimum context an agent needs — no account names, no credentials."""
        portfolio_context = {
            key: snapshot.get(key)
            for key in (
                "as_of", "cash", "market_value", "total_equity", "realized_pnl",
                "unrealized_pnl", "positions", "missing_prices", "stale_prices",
                "prices_as_of", "data_quality",
            )
        }
        return {
            "as_of": as_of,
            "currency": self.config.values.get("currency", "EGP"),
            "exchange": "EGX",
            "question": question,
            "portfolio": portfolio_context,
            "risk_limits": snapshot.get("risk_limits", {}),
            "risk_review": {
                "violations": snapshot.get("rule_violations", []),
                "data_quality_score": snapshot.get("data_quality_score"),
            },
            "data_quality_score": snapshot.get("data_quality_score"),
            "simulations": simulations or [],
            "contract_version": CONTRACT_VERSION,
            "constraints": [
                "No broker execution is possible from this system.",
                "The human user records the final decision.",
                "Phase 1 has no automated market data; only manually recorded prices exist.",
            ],
        }

    def _persist_result(self, run_id: str, result: CommitteeResult) -> None:
        """Store agent runs, disagreements, recommendations, and the final status."""
        raw_dir = self.config.runs_dir / run_id / "raw"
        with sqlite_db.transaction(self.context.connection):
            for response in result.agent_responses:
                raw_path = raw_dir / f"{response.provider}_{response.stage.lower()}.txt"
                self.repos.agent_runs.record(
                    research_run_id=run_id,
                    provider=response.provider,
                    role=response.role,
                    stage=response.stage,
                    status=response.status,
                    input_hash=response.input_hash,
                    started_at=response.started_at,
                    completed_at=response.completed_at,
                    duration_seconds=str(response.duration_seconds),
                    parsed_output=response.data,
                    validation_errors=response.validation_errors or None,
                    raw_output_path=str(raw_path),
                    exit_code=response.exit_code,
                    stderr_excerpt=response.stderr_excerpt or None,
                    failure_kind=response.failure_kind,
                )

            for item in result.disagreements:
                self.repos.disagreements.add(
                    research_run_id=run_id,
                    topic=item.get("topic") or "unspecified",
                    codex_position=self._position_for("codex", item),
                    claude_position=self._position_for("claude", item),
                    materiality=item.get("materiality", "unknown"),
                    evidence=item.get("required_evidence"),
                )

            if result.synthesis:
                for action in result.synthesis.get("ranked_actions", []):
                    self.repos.recommendations.add(
                        research_run_id=run_id,
                        rank=action.get("rank") or 1,
                        action=action.get("action"),
                        symbol=action.get("symbol"),
                        confidence=action.get("confidence"),
                        data_quality_score=result.synthesis.get("data_quality_score"),
                        suggested_weight_pct=(
                            None if action.get("suggested_weight_pct") is None
                            else str(action["suggested_weight_pct"])
                        ),
                        current_weight_pct=self._current_weight(result, action.get("symbol")),
                        thesis_summary=" ".join(action.get("why", [])) or None,
                        counterargument=action.get("strongest_counterargument"),
                        invalidators=action.get("invalidators"),
                        risks=result.synthesis.get("unresolved_questions"),
                        portfolio_effect={"description": action.get("portfolio_effect")},
                        evidence=action.get("evidence_urls"),
                    )

            error = None
            if result.status == decision_rules.FAILED:
                error = "; ".join(
                    f"{failure['provider']}/{failure['stage']}: {failure['detail']}"
                    for failure in result.failures
                ) or "committee did not reach a validated synthesis"

            self.repos.research_runs.set_status(
                run_id, result.status, error=error,
                completed=result.status == decision_rules.FAILED,
            )
            self.repos.audit.record(
                action="RESEARCH_RUN_COMPLETED", entity_type="research_run", entity_id=run_id,
                actor_type="system",
                after={"status": result.status,
                       "failures": [f["failure_kind"] for f in result.failures],
                       "chair": result.chair_provider},
            )

    @staticmethod
    def _position_for(provider: str, item: dict) -> Optional[str]:
        if item.get("raised_by") == provider:
            return item.get("reviewer_position")
        if item.get("reviewed_provider") == provider:
            return item.get("reviewed_position")
        return None

    @staticmethod
    def _current_weight(result: CommitteeResult, symbol: Optional[str]) -> Optional[str]:
        if not symbol:
            return None
        positions = result.context.get("portfolio", {}).get("positions", [])
        for position in positions:
            if position.get("symbol") == symbol:
                return position.get("weight_pct")
        return None

    # ---- history ---------------------------------------------------------

    def list_runs(self, limit: int = 20, account_reference=None) -> List[dict]:
        account_id = (
            None if account_reference is None
            else self.portfolio_service.resolve_account(account_reference).id
        )
        return self.repos.research_runs.list(limit=limit, account_id=account_id)

    def get_run(self, run_reference: str) -> dict:
        """Reload a complete historical run: snapshot, agents, decisions, artifacts."""
        run = self.repos.research_runs.find(run_reference)
        run_id = run["id"]
        artifacts = artifact_module.RunArtifacts(self.config.runs_dir, run_id)
        final = artifacts.read_json(artifact_module.FINAL_RECOMMENDATION) or {}
        return {
            "run": run,
            "agent_runs": self.repos.agent_runs.list_for_run(run_id),
            "disagreements": self.repos.disagreements.list_for_run(run_id),
            "recommendations": self.repos.recommendations.list_for_run(run_id),
            "decisions": self.repos.decisions.list_for_run(run_id),
            "simulations": self.repos.simulations.list_for_run(run_id),
            "synthesis": final.get("synthesis"),
            "failures": final.get("failures", []),
            "stopped_because": final.get("stopped_because", []),
            "artifact_dir": str(artifacts.directory),
            "artifact_files": artifacts.list_files(),
        }
