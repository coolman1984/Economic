"""Append-oriented run artifacts on disk (ARCHITECTURE §9).

Database rows and run files cross-reference the same run ID. Artifacts are
written once as the run progresses and are never rewritten afterwards, so a
historical decision can be reproduced exactly as it was made.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

PORTFOLIO_SNAPSHOT = "portfolio_snapshot.json"
MARKET_CONTEXT = "market_context.json"
RUN_META = "run.json"
SIMULATIONS = "simulations.json"
RISK_REVIEW = "risk_review.json"
FINAL_RECOMMENDATION = "final_recommendation.json"
HUMAN_DECISION = "human_decision.json"


class RunArtifacts:
    """Filesystem home for one research run."""

    def __init__(self, root: Path, run_id: str):
        self.run_id = run_id
        self.directory = Path(root) / run_id
        self.raw_directory = self.directory / "raw"

    def ensure(self) -> "RunArtifacts":
        self.directory.mkdir(parents=True, exist_ok=True)
        self.raw_directory.mkdir(parents=True, exist_ok=True)
        return self

    def write_json(self, name: str, payload) -> Path:
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def read_json(self, name: str) -> Optional[dict]:
        path = self.directory / name
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write_raw(self, name: str, text: str) -> Path:
        """Store an agent's raw stdout for forensic inspection."""
        self.raw_directory.mkdir(parents=True, exist_ok=True)
        path = self.raw_directory / name
        path.write_text(text or "", encoding="utf-8")
        return path

    def stage_file(self, provider: str, stage: str) -> str:
        return f"{provider}_{stage.lower()}.json"

    def list_files(self) -> list:
        if not self.directory.exists():
            return []
        return sorted(
            str(path.relative_to(self.directory))
            for path in self.directory.rglob("*")
            if path.is_file()
        )
