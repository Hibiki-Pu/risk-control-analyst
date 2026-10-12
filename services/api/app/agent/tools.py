"""Tools the AI Analyst is allowed to call.

Design rules
------------
* The tool list is closed. The model cannot reach the data any other way.
* Every argument model is ``extra="forbid"``: an unexpected key (the classic
  parameter-injection or prompt-injection route) is rejected, not ignored.
* Tools never mutate financial data. They read the deterministic engine.
* Every tool returns ``citations`` — ``id -> value`` pairs — so the narrative
  layer can only quote numbers it actually received.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings
from app.finance.engine import FinancialEngine
from app.finance.risk import RiskEngine
from app.finance.scenarios import ScenarioEngine
from app.market.adapter import MarketDataAdapter, provenance_summary
from app.reports.verify import Citation


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MetricsArgs(ToolArgs):
    month: str | None = Field(default=None, description="Single month, e.g. '2024-12'.")
    start: str | None = Field(default=None, description="Start month of a range.")
    end: str | None = Field(default=None, description="End month of a range.")
    regions: list[str] | None = Field(default=None, description="Subset of regions, e.g. ['SG','TH'].")
    metric_ids: list[str] | None = Field(default=None, description="Restrict the returned metrics.")


class BudgetArgs(ToolArgs):
    month: str | None = None
    start: str | None = None
    end: str | None = None


class RiskArgs(ToolArgs):
    month: str | None = None
    minimum_severity: str = Field(default="info", pattern="^(info|low|medium|high|critical)$")


class MarketArgs(ToolArgs):
    series_id: str = Field(default="DFF", max_length=32)
    allow_live: bool = True
    limit: int = Field(default=60, ge=1, le=1000)


class ScenarioArgs(ToolArgs):
    horizon_months: int = Field(default=12, ge=1, le=36)
    volume_growth_pct: float = Field(default=0.0, ge=-0.9, le=3.0)
    price_change_pct: float = Field(default=0.0, ge=-0.9, le=3.0)
    material_cost_change_pct: float = Field(default=0.0, ge=-0.9, le=3.0)
    labor_cost_change_pct: float = Field(default=0.0, ge=-0.9, le=3.0)
    overhead_cost_change_pct: float = Field(default=0.0, ge=-0.9, le=3.0)
    opex_change_pct: float = Field(default=0.0, ge=-0.9, le=3.0)
    interest_rate_delta_pp: float = Field(default=0.0, ge=-10.0, le=20.0)
    fx_change_pct: float = Field(default=0.0, ge=-0.9, le=3.0)
    dso_days_delta: float = Field(default=0.0, ge=-60.0, le=120.0)
    capex_change_pct: float = Field(default=0.0, ge=-0.9, le=3.0)


class CompareScenariosArgs(ToolArgs):
    horizon_months: int = Field(default=12, ge=1, le=36)


class ReportArgs(ToolArgs):
    month: str | None = None
    horizon_months: int = Field(default=12, ge=1, le=36)


class LineageArgs(ToolArgs):
    dataset_id: str | None = None


@dataclass
class ToolResult:
    tool: str
    arguments: dict[str, Any]
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    citations: dict[str, Citation] = field(default_factory=dict)
    missing_data: list[str] = field(default_factory=list)


@dataclass
class ToolSpec:
    name: str
    description: str
    args_model: type[ToolArgs]
    handler: Callable[[Any, ToolArgs], ToolResult]


class ToolContext:
    """Everything a tool is allowed to touch."""

    def __init__(
        self,
        engine: FinancialEngine,
        scenarios: ScenarioEngine,
        market: MarketDataAdapter,
        risk: RiskEngine,
        settings: Settings,
        report_builder=None,
    ):
        self.engine = engine
        self.scenarios = scenarios
        self.market = market
        self.risk = risk
        self.settings = settings
        self.report_builder = report_builder


# ----------------------------------------------------------------------
# handlers
# ----------------------------------------------------------------------
def _metric_citation(pack, metric_id: str) -> Citation | None:
    cited = pack.values.get(metric_id)
    if cited is None:
        return None
    return Citation(
        citation_id=f"metric:{metric_id}@{pack.period}",
        label=cited.label,
        value=cited.value,
        unit=cited.unit,
        period=pack.period,
        source_ids=cited.source_ids,
    )


def _resolve_months(context: ToolContext, args: MetricsArgs | BudgetArgs) -> list[str]:
    if args.month:
        return [args.month]
    return context.engine.select_months(args.start, args.end)


def tool_get_financial_metrics(context: ToolContext, args: MetricsArgs) -> ToolResult:
    months = _resolve_months(context, args)
    pack = context.engine.metrics(months=months, regions=args.regions)
    wanted = args.metric_ids
    citations: dict[str, Citation] = {}
    missing: list[str] = []
    for metric_id, cited in pack.values.items():
        if wanted and metric_id not in wanted:
            continue
        citation = _metric_citation(pack, metric_id)
        if citation is None:
            continue
        citations[citation.citation_id] = citation
        if cited.status != "ok":
            missing.append(f"{metric_id} ({cited.status}: {cited.note})")
    summary = f"{len(citations)} metric(s) for {pack.period} (regions={args.regions or 'ALL'})"
    return ToolResult(
        tool="get_financial_metrics",
        arguments=args.model_dump(exclude_none=True),
        summary=summary,
        payload={
            "period": pack.period,
            "metrics": {key: value.value for key, value in pack.values.items()},
            "units": {key: value.unit for key, value in pack.values.items()},
            "status": {key: value.status for key, value in pack.values.items()},
            "notes": {key: value.note for key, value in pack.values.items() if value.note},
        },
        citations=citations,
        missing_data=missing,
    )


def tool_get_budget_variance(context: ToolContext, args: BudgetArgs) -> ToolResult:
    months = _resolve_months(context, args)
    pack = context.engine.budget_variance(months=months)
    citations: dict[str, Citation] = {}
    missing: list[str] = []
    for metric_id, cited in pack.values.items():
        citation = Citation(
            citation_id=f"budget:{metric_id}@{pack.period}",
            label=cited.label,
            value=cited.value,
            unit=cited.unit,
            period=pack.period,
            source_ids=cited.source_ids,
        )
        citations[citation.citation_id] = citation
        if cited.status != "ok":
            missing.append(f"{metric_id} ({cited.status}: {cited.note})")
    return ToolResult(
        tool="get_budget_variance",
        arguments=args.model_dump(exclude_none=True),
        summary=f"{len(citations)} plan-variance metric(s) for {pack.period}",
        payload={
            "period": pack.period,
            "variances": {key: value.value for key, value in pack.values.items()},
            "units": {key: value.unit for key, value in pack.values.items()},
            "status": {key: value.status for key, value in pack.values.items()},
        },
        citations=citations,
        missing_data=missing,
    )


def tool_get_risk_signals(context: ToolContext, args: RiskArgs) -> ToolResult:
    register = context.risk.build(month=args.month)
    order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    threshold = order[args.minimum_severity]
    signals = [signal for signal in register.signals if order[signal.severity] >= threshold]
    citations: dict[str, Citation] = {
        "risk:register.score": Citation(
            citation_id="risk:register.score",
            label="Risk register score",
            value=register.score,
            unit="score",
            period=register.period,
            source_ids=register.lineage,
        )
    }
    for signal in signals:
        citations[f"risk:{signal.signal_id}@{signal.period}"] = Citation(
            citation_id=f"risk:{signal.signal_id}@{signal.period}",
            label=signal.title,
            value=signal.observed_value,
            unit=signal.unit,
            period=signal.period,
            source_ids=signal.source_ids,
        )
        if signal.threshold is not None:
            citations[f"risk:{signal.signal_id}.threshold@{signal.period}"] = Citation(
                citation_id=f"risk:{signal.signal_id}.threshold@{signal.period}",
                label=signal.title + " threshold",
                value=signal.threshold,
                unit=signal.threshold_unit,
                period=signal.period,
                source_ids=["policy:risk-thresholds@v1"],
            )
        for item in signal.supporting:
            citations[f"risk:{signal.signal_id}.{item.key}@{signal.period}"] = Citation(
                citation_id=f"risk:{signal.signal_id}.{item.key}@{signal.period}",
                label=item.label,
                value=item.value,
                unit=item.unit,
                period=signal.period,
                source_ids=signal.source_ids,
            )
    return ToolResult(
        tool="get_risk_signals",
        arguments=args.model_dump(exclude_none=True),
        summary=(
            f"risk level {register.overall_level} (score {register.score}) with {len(signals)} signal(s) "
            f"at or above '{args.minimum_severity}'"
        ),
        payload={"register": register.model_dump(mode="json")},
        citations=citations,
        missing_data=list(register.data_gaps),
    )


def tool_get_market_series(context: ToolContext, args: MarketArgs) -> ToolResult:
    series = context.market.get_series(args.series_id, allow_live=args.allow_live, limit=args.limit)
    citations: dict[str, Citation] = {}
    missing: list[str] = []
    if series.error:
        missing.append(series.error)
    if series.latest_value is not None and series.latest_observation_date is not None:
        unit = "percent_points" if ("Percent" in series.units or "Rate" in series.title) else "raw"
        citation_id = f"series:{series.series_id}@{series.latest_observation_date.isoformat()}"
        citations[citation_id] = Citation(
            citation_id=citation_id,
            label=series.title,
            value=series.latest_value,
            unit=unit,
            period=series.latest_observation_date.isoformat(),
            source_ids=[f"market:{series.series_id}@{series.latest_observation_date.isoformat()}"],
        )
    return ToolResult(
        tool="get_market_series",
        arguments=args.model_dump(exclude_none=True),
        summary=provenance_summary(series),
        payload={"series": series.model_dump(mode="json")},
        citations=citations,
        missing_data=missing,
    )


def tool_run_scenario(context: ToolContext, args: ScenarioArgs) -> ToolResult:
    from app.schemas import ScenarioAssumptions

    assumptions = ScenarioAssumptions.model_validate(args.model_dump())
    result = context.scenarios.run(
        assumptions=assumptions,
        scenario_id="custom",
        label="Custom scenario",
        include_presets=True,
    )
    citations = _scenario_citations(result)
    return ToolResult(
        tool="run_scenario",
        arguments=args.model_dump(exclude_none=True),
        summary=(
            f"ran base/upside/downside plus a custom case over {result.horizon_months} months; "
            f"custom EBIT delta {_first_custom(result):,.0f}"
        ),
        payload={"scenarios": [summary.model_dump(mode="json") for summary in result.scenarios], "monthly": {key: [m.model_dump(mode="json") for m in value] for key, value in result.monthly.items()}},
        citations=citations,
    )


def _first_custom(result) -> float:
    custom = next((summary for summary in result.scenarios if summary.scenario_id == "custom"), None)
    return custom.ebit_usd if custom else result.baseline.ebit_usd


def tool_compare_scenarios(context: ToolContext, args: CompareScenariosArgs) -> ToolResult:
    result = context.scenarios.run(horizon_months=args.horizon_months)
    citations = _scenario_citations(result)
    return ToolResult(
        tool="compare_scenarios",
        arguments=args.model_dump(exclude_none=True),
        summary=(
            " | ".join(
                f"{summary.label}: EBIT {summary.ebit_usd:,.0f} ({summary.ebit_delta_usd:+,.0f} vs base)"
                for summary in result.scenarios
            )
        ),
        payload={
            "scenarios": [summary.model_dump(mode="json") for summary in result.scenarios],
            "sensitivities": [item.model_dump(mode="json") for item in result.sensitivities],
            "model_note": result.model_note,
        },
        citations=citations,
    )


def _scenario_citations(result) -> dict[str, Citation]:
    citations: dict[str, Citation] = {}
    for summary in result.scenarios:
        for field_name, unit in (
            ("revenue_usd", "USD"),
            ("gross_profit_usd", "USD"),
            ("ebit_usd", "USD"),
            ("interest_expense_usd", "USD"),
            ("net_income_usd", "USD"),
            ("free_cash_flow_usd", "USD"),
            ("ending_cash_usd", "USD"),
            ("minimum_cash_usd", "USD"),
            ("ebit_delta_usd", "USD"),
            ("revenue_delta_usd", "USD"),
            ("fcf_delta_usd", "USD"),
            ("gross_margin_pct", "pct"),
            ("operating_margin_pct", "pct"),
            ("ebit_delta_pct", "pct"),
            ("cash_runway_months", "months"),
        ):
            value = getattr(summary, field_name)
            if value is None:
                continue
            citation_id = f"scenario:{summary.scenario_id}.{field_name}"
            citations[citation_id] = Citation(
                citation_id=citation_id,
                label=f"{summary.label} {field_name}",
                value=value,
                unit=unit,
                period=f"{result.horizon_months}m",
                source_ids=["model:driver-based-forecast@v1"],
            )
    for item in result.sensitivities:
        for suffix, value in (
            ("low", item.ebit_impact_usd_low),
            ("high", item.ebit_impact_usd_high),
            ("swing", item.ebit_swing_usd),
        ):
            citation_id = f"scenario:sensitivity.{item.driver}.{suffix}"
            citations[citation_id] = Citation(
                citation_id=citation_id,
                label=f"{item.label} EBIT impact ({suffix})",
                value=value,
                unit="USD",
                period=f"{result.horizon_months}m",
                source_ids=["model:driver-based-forecast@v1"],
            )
    return citations


def tool_get_data_lineage(context: ToolContext, args: LineageArgs) -> ToolResult:
    lineage = context.engine.lineage()
    if args.dataset_id:
        lineage = [item for item in lineage if item.dataset_id == args.dataset_id]
    return ToolResult(
        tool="get_data_lineage",
        arguments=args.model_dump(exclude_none=True),
        summary=f"{len(lineage)} dataset(s) in lineage",
        payload={"lineage": [item.model_dump(mode="json") for item in lineage]},
    )


def tool_generate_report(context: ToolContext, args: ReportArgs) -> ToolResult:
    if context.report_builder is None:
        raise RuntimeError("report builder is not wired into this agent context")
    document = context.report_builder.build(month=args.month, horizon_months=args.horizon_months)
    citations: dict[str, Citation] = dict(context.report_builder.registry)
    failed = [item for item in document.verification if item.status == "fail"]
    return ToolResult(
        tool="generate_report",
        arguments=args.model_dump(exclude_none=True),
        summary=(
            f"report {document.report_id} for {document.as_of}; pre-export verification "
            f"{document.verification_status} ({len(document.verification)} checks, {len(failed)} failed)"
        ),
        payload={
            "report_id": document.report_id,
            "verification_status": document.verification_status,
            "verification": [item.model_dump(mode="json") for item in document.verification],
            "markdown": document.markdown,
        },
        citations=citations,
        missing_data=[f"{item.check_id}: {item.detail}" for item in failed],
    )


TOOLS: dict[str, ToolSpec] = {
    "get_financial_metrics": ToolSpec(
        "get_financial_metrics",
        "Deterministic financial metrics (revenue, margins, EBIT, cash flow, DSO, coverage) for a month or range.",
        MetricsArgs,
        tool_get_financial_metrics,
    ),
    "get_budget_variance": ToolSpec(
        "get_budget_variance",
        "Actual versus plan variances with absolute and percentage values.",
        BudgetArgs,
        tool_get_budget_variance,
    ),
    "get_risk_signals": ToolSpec(
        "get_risk_signals",
        "Rule-based risk register with severities, observed values and thresholds.",
        RiskArgs,
        tool_get_risk_signals,
    ),
    "get_market_series": ToolSpec(
        "get_market_series",
        "Macro market series with provenance (live FRED observation or clearly-labelled local fixture).",
        MarketArgs,
        tool_get_market_series,
    ),
    "run_scenario": ToolSpec(
        "run_scenario",
        "Driver-based what-if projection: base, upside, downside plus a custom case.",
        ScenarioArgs,
        tool_run_scenario,
    ),
    "compare_scenarios": ToolSpec(
        "compare_scenarios",
        "Compare the preset scenarios and return the EBIT sensitivity ranking.",
        CompareScenariosArgs,
        tool_compare_scenarios,
    ),
    "generate_report": ToolSpec(
        "generate_report",
        "Build the management report and run the pre-export verification checks.",
        ReportArgs,
        tool_generate_report,
    ),
    "get_data_lineage": ToolSpec(
        "get_data_lineage",
        "Dataset lineage: origin, row counts, synthetic flags and data gaps.",
        LineageArgs,
        tool_get_data_lineage,
    ),
}


def describe_tools() -> list[dict[str, Any]]:
    """Tool documentation for the prompt and for ``GET /agent/tools``."""
    out: list[dict[str, Any]] = []
    for spec in TOOLS.values():
        out.append(
            {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.args_model.model_json_schema(),
            }
        )
    return out


def validate_arguments(tool_name: str, arguments: dict[str, Any]) -> ToolArgs:
    """Validate (and reject unknown keys in) tool arguments."""
    spec = TOOLS.get(tool_name)
    if spec is None:
        raise KeyError(f"unknown tool '{tool_name}'")
    return spec.args_model.model_validate(arguments)


__all__ = [
    "TOOLS",
    "ToolContext",
    "ToolResult",
    "ToolSpec",
    "ValidationError",
    "describe_tools",
    "validate_arguments",
    "pd",
]
