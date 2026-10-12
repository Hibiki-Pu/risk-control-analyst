"""Pytest fixtures shared by the suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.core.config import Settings  # noqa: E402
from app.data.store import DatasetStore  # noqa: E402
from app.data.synthetic import generate_dataset, load_dataset  # noqa: E402
from app.finance.engine import FinancialEngine  # noqa: E402
from app.finance.risk import RiskEngine, Thresholds  # noqa: E402
from app.finance.scenarios import ScenarioEngine  # noqa: E402
from app.market.adapter import MarketDataAdapter  # noqa: E402
from app.reports.generator import ReportBuilder  # noqa: E402
from app.services import Services, reset_services  # noqa: E402
from tests.helpers import build_tiny_dataset, with_macro, build_long_macro  # noqa: E402


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """Settings pointed at the shipped seed data with an isolated runtime dir."""
    runtime = tmp_path_factory.mktemp("runtime")
    return Settings(runtime_dir=runtime, llm_provider="deterministic", llm_api_key="", fred_api_key="")


@pytest.fixture(scope="session")
def seed_dataset():
    data_dir = REPO_ROOT / "data" / "synthetic"
    if not (data_dir / "monthly_financials.csv").exists():
        pytest.skip("seed data missing; run: python data/synthetic/generate.py --write")
    return load_dataset(data_dir)


@pytest.fixture(scope="session")
def engine(seed_dataset) -> FinancialEngine:
    return FinancialEngine(seed_dataset)


@pytest.fixture(scope="session")
def scenario_engine(engine) -> ScenarioEngine:
    return ScenarioEngine(engine)


@pytest.fixture(scope="session")
def risk_engine(engine) -> RiskEngine:
    return RiskEngine(engine)


@pytest.fixture(scope="session")
def market_adapter(seed_dataset) -> MarketDataAdapter:
    return MarketDataAdapter(seed_dataset.macro, Settings(fred_api_key=""))


@pytest.fixture(scope="session")
def report_builder(engine, scenario_engine, market_adapter, risk_engine, settings) -> ReportBuilder:
    return ReportBuilder(engine, scenario_engine, market_adapter, risk_engine, settings)


@pytest.fixture(scope="session")
def tiny_dataset():
    return with_macro(build_tiny_dataset(), build_long_macro())


@pytest.fixture(scope="session")
def tiny_engine(tiny_dataset) -> FinancialEngine:
    return FinancialEngine(tiny_dataset, dataset_id="tiny-test")


@pytest.fixture
def static_thresholds() -> Thresholds:
    return Thresholds()


@pytest.fixture
def services(tmp_path, monkeypatch) -> Services:
    """A Services container with an isolated runtime directory."""
    monkeypatch.setenv("RCA_RUNTIME_DIR", str(tmp_path / "runtime"))
    from app.core.config import get_settings

    get_settings.cache_clear()
    reset_services()
    container = Services(get_settings())
    yield container
    reset_services()
    get_settings.cache_clear()


@pytest.fixture
def client(services):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def fresh_generated_dataset():
    """A second, independent generation with the same seed (determinism check)."""
    return generate_dataset()


@pytest.fixture(scope="session")
def store(settings, tmp_path_factory) -> DatasetStore:
    store = DatasetStore(settings)
    store.ensure_seed()
    return store
