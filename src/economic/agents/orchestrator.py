"""The single owner of multi-agent workflow state.

Responsibilities (ARCHITECTURE §6): run identity, prompts, timeouts, stage
sequencing, output validation, persistence, stopping conditions, and the human
approval gate. No CLI or UI code ever calls an adapter directly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

from .. import CONTRACT_VERSION
from ..domain import decisions as decision_rules
from . import artifacts as artifact_module
from . import contracts
from .base_adapter import AgentAdapter, AgentResponse
from .prompts import templates

# Phase 1 runs exactly one cross-review round (ADR-007).
MAX_REVIEW_ROUNDS = 1

STAGE_INDEPENDENT = "INDEPENDENT_ANALYSIS"
STAGE_CROSS_REVIEW = "CROSS_REVIEW"
STAGE_SYNTHESIS = "SYNTHESIS"


class OrchestratorError(RuntimeError):
    """The workflow cannot continue."""


def new_run_id(today: Optional[str] = None) -> str:
    """Human-sortable run identifier, e.g. ``run-2026-09-10-a1b2c3d4``."""
    stamp = today or date.today().isoformat()
    return f"run-{stamp}-{uuid.uuid4().hex[:8]}"


@dataclass
class CommitteeResult:
    """Everything one committee run produced."""

    run_id: str
    status: str
    question: str
    mode: str
    chair_provider: str
    context: dict
    analyses: Dict[str, dict] = field(default_factory=dict)
    critiques: Dict[str, dict] = field(default_factory=dict)
    synthesis: Optional[dict] = None
    disagreements: List[dict] = field(default_factory=list)
    failures: List[dict] = field(default_factory=list)
    agent_responses: List[AgentResponse] = field(default_factory=list)
    stopped_because: List[str] = field(default_factory=list)

    @property
    def ready_for_human(self) -> bool:
        return self.status == decision_rules.READY_FOR_HUMAN


class Orchestrator:
    """Drives one committee run from snapshot to the human gate."""

    def __init__(
        self,
        adapters: Dict[str, AgentAdapter],
        artifacts: artifact_module.RunArtifacts,
        chair: str = "claude",
        review_rounds: int = MAX_REVIEW_ROUNDS,
        timeout_seconds: Optional[int] = None,
        on_stage=None,
    ):
        if not adapters:
            raise OrchestratorError("at least one agent adapter is required")
        self.adapters = adapters
        self.artifacts = artifacts
        self.chair = chair if chair in adapters else next(iter(adapters))
        self.review_rounds = min(int(review_rounds), MAX_REVIEW_ROUNDS)
        self.timeout_seconds = timeout_seconds
        self.on_stage = on_stage or (lambda *_args, **_kwargs: None)

    # ---- stage helpers ---------------------------------------------------

    def _record(self, result: CommitteeResult, response: AgentResponse, filename: str) -> None:
        """Persist one agent response as artifacts, success or failure."""
        result.agent_responses.append(response)
        self.artifacts.write_raw(
            f"{response.provider}_{response.stage.lower()}.txt", response.raw_output
        )
        payload = {
            "provider": response.provider,
            "role": response.role,
            "stage": response.stage,
            "contract": response.contract,
            "status": response.status,
            "failure_kind": response.failure_kind,
            "validation_errors": response.validation_errors,
            "started_at": response.started_at,
            "completed_at": response.completed_at,
            "duration_seconds": response.duration_seconds,
            "input_hash": response.input_hash,
            "exit_code": response.exit_code,
            "stderr_excerpt": response.stderr_excerpt,
            "output": response.data,
        }
        self.artifacts.write_json(filename, payload)
        if not response.ok:
            result.failures.append({
                "provider": response.provider,
                "stage": response.stage,
                "failure_kind": response.failure_kind,
                "detail": response.error_message(),
            })

    def _run_stage(self, provider: str, prompt: str, contract: str, role: str,
                   stage: str) -> AgentResponse:
        adapter = self.adapters[provider]
        self.on_stage(stage, provider, "started")
        response = adapter.run(prompt, contract, role, stage,
                               timeout_seconds=self.timeout_seconds)
        self.on_stage(stage, provider, response.status)
        return response

    # ---- the workflow ----------------------------------------------------

    def run_committee(self, run_id: str, question: str, context: dict,
                      mode: str = "live") -> CommitteeResult:
        """Independent analysis -> one cross-review round -> chair synthesis.

        A provider failure is recorded and the run continues with whatever
        evidence exists; a missing result is never fabricated (AGENTS.md §3).
        """
        self.artifacts.ensure()
        result = CommitteeResult(
            run_id=run_id,
            status=decision_rules.INDEPENDENT_ANALYSIS,
            question=question,
            mode=mode,
            chair_provider=self.chair,
            context=context,
        )

        # Stage 1 — independent analysis. No agent sees the other's conclusion.
        for provider in self.adapters:
            prompt = templates.independent_analysis(question, context)
            response = self._run_stage(provider, prompt, contracts.INDEPENDENT_ANALYSIS,
                                       "analyst", STAGE_INDEPENDENT)
            self._record(result, response, f"{provider}_independent.json")
            if response.ok:
                result.analyses[provider] = response.data

        if not result.analyses:
            result.status = decision_rules.FAILED
            result.stopped_because.append(
                "no provider produced a valid independent analysis; nothing to synthesize"
            )
            self._write_final(result, None)
            return result

        # Stage 2 — cross-review. Exactly one round in Phase 1.
        result.status = decision_rules.CROSS_REVIEW
        if self.review_rounds >= 1 and len(result.analyses) >= 2:
            for reviewer in self.adapters:
                targets = [p for p in result.analyses if p != reviewer]
                if not targets:
                    continue
                reviewed = targets[0]
                review_context = dict(context)
                review_context["reviewed_provider"] = reviewed
                prompt = templates.critique(reviewer, reviewed, question, review_context,
                                            result.analyses[reviewed])
                response = self._run_stage(reviewer, prompt, contracts.CRITIQUE,
                                           "reviewer", STAGE_CROSS_REVIEW)
                self._record(result, response, f"{reviewer}_critique.json")
                if response.ok:
                    result.critiques[reviewer] = response.data
        else:
            result.stopped_because.append(
                "cross-review skipped: fewer than two valid independent analyses"
            )

        # Stage 3 — collect material disagreements for the record.
        result.status = decision_rules.DISAGREEMENT_CHECK
        result.disagreements = self._collect_disagreements(result)
        result.stopped_because.append(
            f"review-round limit reached ({self.review_rounds} of {MAX_REVIEW_ROUNDS})"
        )

        # Stage 4 — chair synthesis.
        result.status = decision_rules.READY_FOR_SYNTHESIS
        chair_provider = self.chair
        if chair_provider not in result.analyses:
            fallback = next(iter(result.analyses))
            result.stopped_because.append(
                f"chair {chair_provider} produced no valid analysis; {fallback} chaired instead"
            )
            chair_provider = fallback
        result.chair_provider = chair_provider

        prompt = templates.chair_synthesis(
            question, context, result.analyses, result.critiques,
            simulations=context.get("simulations"), risk_review=context.get("risk_review"),
        )
        response = self._run_stage(chair_provider, prompt, contracts.CHAIR_SYNTHESIS,
                                   "chair", STAGE_SYNTHESIS)
        self._record(result, response, f"{chair_provider}_synthesis.json")

        if response.ok:
            result.synthesis = response.data
            result.status = decision_rules.READY_FOR_HUMAN
        else:
            result.status = decision_rules.FAILED
            result.stopped_because.append("chair synthesis failed contract validation")

        self._write_final(result, result.synthesis)
        return result

    def _collect_disagreements(self, result: CommitteeResult) -> List[dict]:
        """Flatten reviewer-reported disagreements into explicit records."""
        collected: List[dict] = []
        for reviewer, critique in result.critiques.items():
            for item in critique.get("disagreements", []):
                collected.append({
                    "topic": item.get("topic"),
                    "raised_by": reviewer,
                    "reviewed_provider": critique.get("reviewed_provider"),
                    "reviewer_position": item.get("my_position"),
                    "reviewed_position": item.get("their_position"),
                    "materiality": item.get("materiality", "unknown"),
                    "required_evidence": item.get("required_evidence", []),
                })
        return collected

    def _write_final(self, result: CommitteeResult, synthesis: Optional[dict]) -> None:
        self.artifacts.write_json(artifact_module.FINAL_RECOMMENDATION, {
            "run_id": result.run_id,
            "status": result.status,
            "question": result.question,
            "mode": result.mode,
            "chair_provider": result.chair_provider,
            "contract_version": CONTRACT_VERSION,
            "synthesis": synthesis,
            "disagreements": result.disagreements,
            "failures": result.failures,
            "stopped_because": result.stopped_because,
            "human_decision_required": True,
        })
