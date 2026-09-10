"""Runtime configuration and filesystem layout.

Config precedence (later wins):
    packaged defaults -> config/local_config.json (or ECONOMIC_CONFIG) -> env vars.
Secrets are never read from or written to the repository.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_CONFIG = {
    "data_dir": "data",
    "database": "data/economic.db",
    "runs_dir": "data/runs",
    "logs_dir": "logs",
    "backups_dir": "backups",
    "currency": "EGP",
    "stale_price_after_days": 5,
    # Deterministic floor: below this portfolio data-quality score no proposal
    # may stand as actionable, whatever a model recommends (ADR-020).
    "min_data_quality_for_action": 50,
    "agents": {
        "mock": False,
        "timeout_seconds": 300,
        "chair": "claude",
        "codex": {
            "command": ["codex", "exec", "--skip-git-repo-check", "-"],
            "enabled": True,
        },
        "claude": {
            "command": ["claude", "-p", "--output-format", "json"],
            "enabled": True,
        },
    },
    "portfolio_rules": {
        "min_cash": None,
        "max_position_weight_pct": None,
        "max_sector_weight_pct": None,
        "restricted_symbols": [],
    },
}

CONFIG_ENV_VAR = "ECONOMIC_CONFIG"
HOME_ENV_VAR = "ECONOMIC_HOME"
MOCK_ENV_VAR = "ECONOMIC_MOCK"


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@dataclass
class Config:
    """Resolved configuration plus the absolute paths derived from it."""

    home: Path
    values: dict = field(default_factory=dict)
    source: Optional[Path] = None

    def _path(self, key: str) -> Path:
        raw = Path(self.values[key])
        return raw if raw.is_absolute() else self.home / raw

    @property
    def database_path(self) -> Path:
        return self._path("database")

    @property
    def data_dir(self) -> Path:
        return self._path("data_dir")

    @property
    def runs_dir(self) -> Path:
        return self._path("runs_dir")

    @property
    def logs_dir(self) -> Path:
        return self._path("logs_dir")

    @property
    def backups_dir(self) -> Path:
        return self._path("backups_dir")

    @property
    def agents(self) -> dict:
        return self.values.get("agents", {})

    @property
    def mock_agents(self) -> bool:
        return bool(self.agents.get("mock", False))

    @property
    def timeout_seconds(self) -> int:
        return int(self.agents.get("timeout_seconds", 300))

    @property
    def chair(self) -> str:
        return str(self.agents.get("chair", "claude"))

    @property
    def stale_price_after_days(self) -> int:
        return int(self.values.get("stale_price_after_days", 5))

    @property
    def min_data_quality_for_action(self) -> int:
        """Data-quality floor enforced by the evidence gate."""
        return int(self.values.get("min_data_quality_for_action", 50))

    @property
    def portfolio_rules(self) -> dict:
        return self.values.get("portfolio_rules", {})

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.runs_dir, self.logs_dir, self.backups_dir):
            path.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict:
        return {
            "home": str(self.home),
            "source": str(self.source) if self.source else None,
            "database": str(self.database_path),
            "runs_dir": str(self.runs_dir),
            **self.values,
        }


def load(home: Optional[Path] = None, config_path: Optional[Path] = None,
         overrides: Optional[dict] = None) -> Config:
    """Load configuration for a project home directory."""
    home = Path(home or os.environ.get(HOME_ENV_VAR) or Path.cwd()).resolve()

    if config_path is None:
        env_path = os.environ.get(CONFIG_ENV_VAR)
        candidates = [Path(env_path)] if env_path else [home / "config" / "local_config.json"]
        config_path = next((c for c in candidates if c.exists()), None)

    values = dict(DEFAULT_CONFIG)
    source = None
    if config_path and Path(config_path).exists():
        source = Path(config_path)
        values = _deep_merge(values, json.loads(source.read_text(encoding="utf-8")))

    env_mock = os.environ.get(MOCK_ENV_VAR)
    if env_mock is not None:
        values = _deep_merge(values, {"agents": {"mock": env_mock.strip().lower() in ("1", "true", "yes")}})

    if overrides:
        values = _deep_merge(values, overrides)

    return Config(home=home, values=values, source=source)
