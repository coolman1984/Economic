"""Deterministic mock adapter for end-to-end testing without live model calls.

The mock produces *fictional* analysis text and then feeds it through exactly the
same normalization and contract validation as a real provider, so a mock run
exercises the whole pipeline. Every output is labelled ``MOCK`` so it can never
be mistaken for a real recommendation (BUILD_GUIDE Step 16).
"""

from __future__ import annotations

import hashlib
import json
from typing import List, Optional

from . import contracts
from .base_adapter import AgentAdapter, ProcessResult
from .prompts import templates

MOCK_NOTICE = "MOCK OUTPUT — fictional analysis generated locally for testing. Not investment advice."


def _stable_int(seed: str, low: int, high: int) -> int:
    """Deterministic pseudo-value in [low, high] derived from ``seed``."""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    span = high - low + 1
    return low + (int(digest[:8], 16) % span)


class MockAdapter(AgentAdapter):
    """Offline stand-in for a provider CLI.

    ``failure_kind`` forces a specific normalized failure, and ``raw_override``
    injects arbitrary raw output — both used by tests for the failure paths.
    """

    provider = "mock"

    def __init__(self, provider_name: str = "mock", failure_kind: Optional[str] = None,
                 raw_override: Optional[str] = None, timeout_seconds: int = 300,
                 enabled: bool = True, **kwargs):
        super().__init__(command=["mock"], timeout_seconds=timeout_seconds, enabled=enabled)
        self.provider = provider_name
        self.failure_kind = failure_kind
        self.raw_override = raw_override
        self._contract = contracts.INDEPENDENT_ANALYSIS

    @classmethod
    def default_command(cls) -> List[str]:
        return ["mock"]

    def executable_path(self) -> Optional[str]:
        return "<built-in mock>"

    def is_available(self) -> bool:
        return self.enabled

    def version(self) -> Optional[str]:
        return "mock/1.0 (offline deterministic adapter)"

    def doctor(self) -> dict:
        report = super().doctor()
        report.update({"path": "<built-in mock>", "available": self.enabled,
                       "version": self.version(), "mode": "mock"})
        return report

    def run(self, prompt: str, contract: str, role: str, stage: str,
            timeout_seconds: Optional[int] = None):
        self._contract = contract
        return super().run(prompt, contract, role, stage, timeout_seconds)

    def _execute(self, prompt: str, timeout_seconds: Optional[int] = None) -> ProcessResult:
        if self.failure_kind:
            return ProcessResult("", f"mock forced failure: {self.failure_kind}", None,
                                 self.failure_kind)
        if self.raw_override is not None:
            return ProcessResult(self.raw_override, "", 0, None)
        payload = self._build_payload(prompt)
        # Wrap in prose + a fenced block so the extraction path is exercised too.
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        return ProcessResult(f"{MOCK_NOTICE}\n\n```json\n{body}\n```\n", "", 0, None)

    # ---- deterministic fictional content --------------------------------

    def _build_payload(self, prompt: str) -> dict:
        context = templates.parse_context(prompt) or {}
        snapshot = context.get("portfolio", {})
        positions = snapshot.get("positions") or []
        symbols = [p.get("symbol") for p in positions if p.get("symbol")]
        missing = snapshot.get("missing_prices") or []
        seed = f"{self.provider}:{self._contract}:{','.join(symbols)}"

        if self._contract == contracts.CRITIQUE:
            return self._critique_payload(context, symbols, missing, seed)
        if self._contract == contracts.CHAIR_SYNTHESIS:
            return self._chair_payload(context, symbols, missing, seed)
        return self._analysis_payload(context, positions, symbols, missing, seed)

    def _analysis_payload(self, context, positions, symbols, missing, seed) -> dict:
        recommendations = []
        for index, position in enumerate(positions[:5]):
            symbol = position.get("symbol")
            weight = position.get("weight_pct")
            unpriced = symbol in missing
            action = "WATCH" if unpriced else ("REDUCE" if _stable_int(seed + symbol, 0, 1) else "HOLD")
            recommendations.append({
                "symbol": symbol,
                "action": action,
                "priority": index + 1,
                "confidence": 30 if unpriced else _stable_int(seed + symbol, 45, 70),
                "suggested_weight_pct": None,
                "thesis": (
                    f"[{MOCK_NOTICE}] {symbol} is held at an average cost of "
                    f"{position.get('average_cost')} with a current weight of "
                    f"{weight if weight is not None else 'unknown (unpriced)'}."
                ),
                "bull_case": [f"[MOCK] {symbol} keeps its current earnings trajectory."],
                "bear_case": [f"[MOCK] {symbol} margins compress and the weight becomes a concentration risk."],
                "invalidators": [f"[MOCK] {symbol} reports a material deterioration in its next filing."],
                "risks": (["price snapshot is missing, so the weight is unknown"] if unpriced
                          else ["single-name concentration", "EGX liquidity"]),
            })
        if not recommendations:
            recommendations.append({
                "symbol": None,
                "action": "NO_ACTION",
                "priority": 1,
                "confidence": 40,
                "thesis": f"[{MOCK_NOTICE}] The portfolio holds no open positions, so there is nothing to act on.",
                "bull_case": [], "bear_case": [],
                "invalidators": ["a position is opened"],
                "risks": ["cash held idle loses purchasing power"],
            })
        return {
            "status": "partial" if missing else "complete",
            "scope": context.get("question", "portfolio review"),
            "market_view": f"[{MOCK_NOTICE}] No live market data was retrieved in mock mode.",
            "portfolio_view": (
                f"[{MOCK_NOTICE}] Cash {context.get('portfolio', {}).get('cash')} against "
                f"{len(symbols)} open position(s); total equity "
                f"{context.get('portfolio', {}).get('total_equity')}."
            ),
            "recommendations": recommendations,
            "facts": [],
            "missing_data": (
                [f"no price snapshot for {symbol}" for symbol in missing]
                + ["no live EGX prices, filings, or news are available in mock mode"]
            ),
            "disagreements_or_uncertainty": ["mock output carries no researched conviction"],
            "next_checks": ["record current prices", "review the latest disclosures"],
            "confidence": 35 if missing else 50,
        }

    def _critique_payload(self, context, symbols, missing, seed) -> dict:
        reviewed = context.get("reviewed_provider", "the other analyst")
        return {
            "status": "complete",
            "reviewed_provider": reviewed,
            "unsupported_claims": [
                f"[{MOCK_NOTICE}] {reviewed} states a market view without citing a dated source."
            ],
            "stale_or_missing_evidence": (
                [f"no price evidence for {symbol}" for symbol in missing] or
                ["no filing or disclosure was cited for any holding"]
            ),
            "missed_risks": ["EGX single-name liquidity risk on exit", "currency risk on the cash balance"],
            "portfolio_fit_errors": [],
            "useful_insights_missed": ["the concentration point is fair and worth keeping"],
            "agreements": ["no action is warranted without verified current data"],
            "disagreements": [{
                "topic": "how much weight to give unpriced holdings",
                "my_position": "an unpriced holding must lower overall confidence",
                "their_position": "the holding can still be assessed qualitatively",
                "materiality": "medium" if missing else "low",
                "required_evidence": ["a current price snapshot from an official source"],
            }],
            "overall_assessment": (
                f"[{MOCK_NOTICE}] Structurally sound but evidence-light; treat conclusions as provisional."
            ),
            "confidence": _stable_int(seed, 40, 60),
        }

    def _chair_payload(self, context, symbols, missing, seed) -> dict:
        quality = context.get("data_quality_score")
        if not isinstance(quality, int):
            quality = 40 if missing else 70
        ranked = []
        for index, symbol in enumerate(symbols[:3]):
            ranked.append({
                "rank": index + 1,
                "symbol": symbol,
                "action": "WATCH" if symbol in missing else "HOLD",
                "confidence": _stable_int(seed + symbol, 35, 60),
                "suggested_weight_pct": None,
                "why": [
                    f"[{MOCK_NOTICE}] Both analysts stopped short of a conviction call on {symbol}.",
                    "No verified current evidence was available in mock mode.",
                ],
                "strongest_counterargument": (
                    f"Holding {symbol} by default is still an active decision to keep the exposure."
                ),
                "invalidators": [f"{symbol} publishes results that break the current thesis"],
                "portfolio_effect": "No change to cash or weights while the action is HOLD/WATCH.",
                "evidence_urls": [],
            })
        if not ranked:
            ranked.append({
                "rank": 1, "symbol": None, "action": "NO_ACTION", "confidence": 40,
                "why": [f"[{MOCK_NOTICE}] There are no open positions to act on."],
                "strongest_counterargument": "Holding only cash is itself an allocation choice.",
                "invalidators": [], "portfolio_effect": "None.", "evidence_urls": [],
            })
        return {
            "status": "partial" if missing else "complete",
            "summary": (
                f"[{MOCK_NOTICE}] The committee ran end to end but produced no researched "
                "conviction. Use this run to verify the workflow, not to decide."
            ),
            "data_quality_score": quality,
            "agreement_score": _stable_int(seed, 55, 80),
            "ranked_actions": ranked,
            "rejected_ideas": ["adding new positions without verified prices or filings"],
            "unresolved_questions": (
                [f"what is the current price of {symbol}?" for symbol in missing]
                + ["what do the latest disclosures say?"]
            ),
            "human_decision_required": True,
        }
