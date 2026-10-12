"""Service container: wires the dataset store, engines, adapters, reports and agent."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.agent.orchestrator import AgentOrchestrator
from app.agent.tools import ToolContext
from app.core.config import Settings, get_settings
from app.data.store import DatasetStore
from app.finance.engine import FinancialEngine
from app.finance.risk import RiskEngine
from app.finance.scenarios import ScenarioEngine
from app.market.adapter import MarketDataAdapter
from app.reports.generator import ReportBuilder


@dataclass
class Bundle:
    dataset_id: str
    engine: FinancialEngine
    scenarios: ScenarioEngine
    risk: RiskEngine
    market: MarketDataAdapter
    reports: ReportBuilder
    agent: AgentOrchestrator
    synthetic: bool = True


@dataclass
class Services:
    settings: Settings = field(default_factory=get_settings)
    store: DatasetStore = field(init=False)
    _bundle: Bundle | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.store = DatasetStore(self.settings)
        self.store.ensure_seed()

    def bundle(self) -> Bundle:
        active = self.store.active()
        if self._bundle is None or self._bundle.dataset_id != active.dataset_id:
            engine = self.store.engine()
            scenarios = ScenarioEngine(engine)
            risk = RiskEngine(engine, settings=self.settings)
            market = MarketDataAdapter(active.dataset.macro, self.settings)
            reports = ReportBuilder(engine, scenarios, market, risk, self.settings)
            context = ToolContext(engine, scenarios, market, risk, self.settings, report_builder=reports)
            agent = AgentOrchestrator(context, self.settings)
            self._bundle = Bundle(
                dataset_id=active.dataset_id,
                engine=engine,
                scenarios=scenarios,
                risk=risk,
                market=market,
                reports=reports,
                agent=agent,
                synthetic=active.synthetic,
            )
        return self._bundle

    def invalidate(self) -> None:
        self._bundle = None


_SERVICES: Services | None = None


def get_services() -> Services:
    global _SERVICES  # noqa: PLW0603 - single process-wide container
    if _SERVICES is None:
        _SERVICES = Services()
    return _SERVICES


def reset_services() -> None:
    global _SERVICES  # noqa: PLW0603 - used by tests
    _SERVICES = None
