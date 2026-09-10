# Agent Orchestration Contract

## 1. Purpose

Codex CLI and Claude Code CLI must collaborate as independent analytical workers under one local orchestrator. Neither agent owns the final decision, portfolio truth, database, or workflow state.

## 2. Core Pattern

```text
Task
 -> deterministic portfolio/data snapshot
 -> Codex independent analysis
 -> Claude independent analysis
 -> cross-review
 -> material disagreement extraction
 -> targeted follow-up if justified
 -> deterministic simulation/risk checks
 -> final synthesis
 -> human decision
```

## 3. Independence Rule

The first analytical pass is blind to the other agent's conclusion.

Reason: avoid anchoring and consensus-by-imitation.

Only after both independent outputs are persisted may cross-review begin.

## 4. Delegation Rule

An agent may delegate narrow research tasks if its environment supports subagents, but the parent task must remain bounded.

Good delegation examples:

- verify a specific disclosure;
- compare two reporting periods;
- extract debt/cash metrics;
- investigate one material news claim;
- calculate a defined scenario.

Bad delegation examples:

- 'research everything';
- duplicate the full parent task;
- recursively ask subagents to create more committees without limits.

The orchestrator should eventually record delegated task identity and lineage.

## 5. Review Rule

Cross-review asks each agent to critique the other, not restart the whole analysis.

Review dimensions:

- unsupported facts;
- stale evidence;
- source quality;
- missing material risks;
- weak assumptions;
- portfolio-fit errors;
- invalid probability claims;
- useful insights the reviewer missed.

## 6. Disagreement Protocol

Material disagreements become explicit records.

Example:

```json
{
  "topic": "earnings growth sustainability",
  "codex_position": "likely sustainable",
  "claude_position": "not demonstrated",
  "materiality": "high",
  "required_evidence": ["revenue mix", "margin trend", "one-off items"]
}
```

The orchestrator may launch one targeted follow-up task focused only on the unresolved question.

## 7. Stop Conditions

Stop additional agent discussion when any of these are true:

- no material new evidence emerged in the previous round;
- all high-materiality factual disagreements are resolved;
- remaining disagreement is judgment rather than verifiable fact;
- the configured review-round limit is reached;
- required external data is unavailable;
- marginal research value is lower than time/cost.

No infinite debates.

## 8. Task Depth Levels

### Level 1 — Single Analyst

Use for low-impact summaries or classification.

### Level 2 — Analyst + Reviewer

Use for moderate-impact research.

### Level 3 — Dual Independent Analysts + Cross-Review

Default for meaningful portfolio decisions.

### Level 4 — Full Committee

Dual analysis + cross-review + targeted disagreement resolution + deterministic simulation + risk review + final chair.

Use only when decision materiality warrants the cost.

## 9. Standard Analyst Output

Agents return machine-validated structured output. Suggested contract:

```json
{
  "status": "complete",
  "scope": "...",
  "market_view": "...",
  "portfolio_view": "...",
  "recommendations": [
    {
      "symbol": "...",
      "action": "WATCH",
      "priority": 1,
      "confidence": 70,
      "suggested_weight_pct": null,
      "thesis": "...",
      "bull_case": [],
      "bear_case": [],
      "invalidators": [],
      "risks": []
    }
  ],
  "facts": [
    {
      "fact": "...",
      "source_url": "...",
      "source_name": "...",
      "source_date": "..."
    }
  ],
  "missing_data": [],
  "disagreements_or_uncertainty": [],
  "next_checks": []
}
```

## 10. Final Chair Output

```json
{
  "status": "complete",
  "summary": "...",
  "data_quality_score": 0,
  "agreement_score": 0,
  "ranked_actions": [
    {
      "rank": 1,
      "symbol": "...",
      "action": "HOLD",
      "confidence": 0,
      "suggested_weight_pct": null,
      "why": [],
      "strongest_counterargument": "...",
      "invalidators": [],
      "portfolio_effect": "...",
      "evidence_urls": []
    }
  ],
  "rejected_ideas": [],
  "unresolved_questions": [],
  "human_decision_required": true
}
```

## 11. Agent Adapters

Keep provider details isolated.

### Codex Adapter

Responsibilities:

- construct safe non-interactive command;
- send prompt through stdin where practical;
- enforce timeout;
- capture structured stream/output;
- normalize final assistant result;
- return process metadata/errors.

### Claude Adapter

Same responsibilities, using Claude Code's non-interactive interface and structured output.

No application service should depend on provider-specific CLI flags.

## 11a. Degraded Committees

A run is a FULL committee only when two independent analyses were produced and
both were cross-reviewed. Anything less is DEGRADED, and the difference is
recorded rather than glossed over (ADR-021).

Causes of degradation:

- a provider CLI is missing, unauthenticated, timed out, or returned invalid output;
- only one provider is enabled in configuration;
- the cross-review round did not complete.

Consequences, all enforced in code:

- `committee_mode` is stored as DEGRADED with the specific reasons;
- `agreement_score` is not recorded at all when fewer than two analyses exist,
  because there was no second position to agree with;
- every actionable proposal is downgraded to WATCH by the evidence gate;
- confidence is capped independently of data quality, since complete price data
  does not substitute for a missing reviewer;
- the degradation is shown in the run view, the history listing, and again when
  the human records a decision.

A degraded run still reaches the human. It simply never pretends to be a
committee.

## 11b. The Evidence Gate

Section 13 tells agents not to act on missing or stale data. That instruction is
kept, but it is not what enforces the rule. After the chair answers, a
deterministic gate (ADR-020) re-decides every ranked action:

- an actionable action (BUY, ADD, REDUCE, SELL) on a security with no price
  snapshot, no price evidence, or a stale price is downgraded to WATCH;
- if the deterministic data-quality score is below the configured floor, every
  actionable action is downgraded;
- if the committee is degraded, every actionable action is downgraded;
- confidence is capped at the data-quality score when evidence is thin.

The chair's proposal is preserved next to the restricted result so the human can
see what was asked for and why it was reduced.

## 12. Failure Handling

Possible states:

- executable missing;
- authentication failure;
- timeout;
- non-zero exit;
- malformed structured output;
- empty result;
- source retrieval unavailable;
- contract validation failure.

A failed agent does not automatically fail the whole system. The orchestrator decides whether to:

- retry once;
- continue with lower confidence;
- call the other agent only;
- stop and report insufficient evidence.

Never fabricate a missing agent result.

## 13. Prompt Safety During Investment Analysis

Default investment-analysis runs should not modify project files.

Prompts should explicitly state:

- human is final decision maker;
- no broker orders;
- no local code modifications;
- no invented facts/sources;
- separate facts from interpretation;
- lower confidence when data is stale/missing;
- evaluate portfolio fit, not company quality alone.

## 14. Cost and Performance Memory

Persist when available:

- duration;
- model/provider;
- token usage;
- cost;
- task type;
- validation failures;
- eventual quality score.

Later, routing may use measured performance to choose the cheapest sufficient workflow.

## 15. Human Gate

The final synthesis can only transition to:

`READY_FOR_HUMAN`

The human then explicitly records:

- APPROVE;
- REJECT;
- HOLD;
- MODIFY.

An approval is still not a broker execution. Real execution is recorded separately after the user performs it.
