"""Human decision workflow — the approval gate.

Recording APPROVE never creates a transaction or a broker order (ADR-008). A
real execution is a separate, explicit act recorded through PortfolioService.
"""

from __future__ import annotations

from typing import Optional

from ..agents import artifacts as artifact_module
from ..domain import decisions as rules
from ..persistence import sqlite_db
from .context import AppContext


class DecisionService:
    def __init__(self, context: AppContext):
        self.context = context
        self.repos = context.repos

    def record(self, run_reference: str, decision: str, recommendation_id: Optional[int] = None,
               modified_action: Optional[str] = None, note: Optional[str] = None) -> dict:
        """Persist a human decision and move the run to its resulting state."""
        run = self.repos.research_runs.find(run_reference)
        decision = rules.normalize_decision(decision)
        rules.require_ready_for_human(run["status"])

        if decision == rules.MODIFY and not (modified_action or note):
            raise rules.DecisionError(
                "MODIFY requires --modified-action or --note describing the change"
            )
        if modified_action:
            modified_action = rules.normalize_action(modified_action)

        if recommendation_id is not None:
            recommendation = self.repos.recommendations.get(recommendation_id)
            if recommendation["research_run_id"] != run["id"]:
                raise rules.DecisionError(
                    f"recommendation {recommendation_id} belongs to run "
                    f"{recommendation['research_run_id']}, not {run['id']}"
                )

        new_status = rules.state_for(decision)
        with sqlite_db.transaction(self.context.connection):
            decision_id = self.repos.decisions.add(
                run["id"], decision, recommendation_id, modified_action, note
            )
            self.repos.research_runs.set_status(run["id"], new_status, completed=True)
            self.repos.audit.record(
                action="HUMAN_DECISION", entity_type="research_run", entity_id=run["id"],
                before={"status": run["status"]},
                after={"status": new_status, "decision": decision,
                       "recommendation_id": recommendation_id,
                       "modified_action": modified_action},
                reason=note,
            )
        artifacts = artifact_module.RunArtifacts(self.context.config.runs_dir, run["id"])
        artifacts.ensure()
        history = self.repos.decisions.list_for_run(run["id"])
        artifacts.write_json(artifact_module.HUMAN_DECISION, {
            "run_id": run["id"],
            "run_status": new_status,
            # "Why did we decide this?" must include what the decision rested on.
            "committee_mode": run.get("committee_mode"),
            "data_quality_score": run.get("data_quality_score"),
            "agreement_score": run.get("agreement_score"),
            "decisions": history,
            "note": (
                "Recording a decision never places a broker order. A real execution "
                "is recorded separately once the user has acted with their broker."
            ),
        })

        record = self.repos.decisions.get(decision_id)
        record["run_status"] = new_status
        # Carry the run's integrity forward so the caller can warn the human that
        # this decision rests on a degraded committee (ADR-021).
        record["committee_mode"] = run.get("committee_mode")
        record["committee_degraded"] = run.get("committee_mode") == "DEGRADED"
        record["restricted_recommendation"] = None
        if recommendation_id is not None:
            decided = self.repos.recommendations.get(recommendation_id)
            if decided.get("restricted"):
                record["restricted_recommendation"] = decided.get("proposed_action")
        # An approval is a recorded intention, never an execution.
        record["created_transaction"] = rules.decision_creates_transaction(decision)
        return record

    def list_for_run(self, run_reference: str) -> list:
        run = self.repos.research_runs.find(run_reference)
        return self.repos.decisions.list_for_run(run["id"])
