"""Shared fixtures. Every test runs against a throwaway project home."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, str(SRC))

from economic.application.context import AppContext  # noqa: E402
from economic.application.decision_service import DecisionService  # noqa: E402
from economic.application.portfolio_service import PortfolioService  # noqa: E402
from economic.application.research_service import ResearchService  # noqa: E402
from economic.application.simulation_service import SimulationService  # noqa: E402


@pytest.fixture
def home(tmp_path) -> Path:
    return tmp_path / "project"


@pytest.fixture
def context(home):
    with AppContext.open(home=home, overrides={"agents": {"mock": True}}) as ctx:
        yield ctx


@pytest.fixture
def portfolio_service(context) -> PortfolioService:
    return PortfolioService(context)


@pytest.fixture
def simulation_service(context) -> SimulationService:
    return SimulationService(context)


@pytest.fixture
def research_service(context) -> ResearchService:
    return ResearchService(context)


@pytest.fixture
def decision_service(context) -> DecisionService:
    return DecisionService(context)


@pytest.fixture
def account(portfolio_service):
    return portfolio_service.add_account("Test Account", broker="Test Broker")
