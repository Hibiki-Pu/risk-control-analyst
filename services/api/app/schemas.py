"""Pydantic API/data contracts.

Every number that leaves this service travels as a :class:`CitedValue`, which
carries its unit, period, formula and source ids. That is what makes the AI
report auditable: the LLM may only quote values that already exist here.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Status = Literal["ok", "missing", "undefined"]
Basis = Literal["actual", "budget", "variance", "forecast", "market"]

MONEY = "USD"
PCT = "pct"
DAYS = "days"
RATIO = "x"
COUNT = "units"


class CitedValue(BaseModel):
    """A single auditable number."""

    metric_id: str
    label: str
    value: float | None = None
    unit: str = MONEY
    period: str = Field(description="Reporting period, e.g. '2024-12' or '2024-01..2024-12'.")
    basis: Basis = "actual"
    formula: str = ""
    source_ids: list[str] = Field(default_factory=list)
    status: Status = "ok"
    note: str | None = None
    synthetic: bool = True

    model_config = {
        "json_schema_extra": {
            "example": {
                "metric_id": "gross_margin",
                "label": "Gross margin",
                "value": 0.3521,
                "unit": "pct",
                "period": "2024-12",
                "basis": "actual",
                "formula": "gross_profit / revenue",
                "source_ids": ["actual:monthly_financials@2024-12"],
                "status": "ok",
                "synthetic": True,
            }
        }
    }


class MetricSet(BaseModel):
    as_of: str
    period: str
    scope: dict[str, Any] = Field(default_factory=dict)
    currency: str = MONEY
    synthetic: bool = True
    values: dict[str, CitedValue] = Field(default_factory=dict)
    lineage: list[str] = Field(default_factory=list)


class MonthlyPoint(BaseModel):
    month: str
    revenue_usd: float | None = None
    cogs_usd: float | None = None
    gross_profit_usd: float | None = None
    gross_margin_pct: float | None = None
    ebit_usd: float | None = None
    operating_margin_pct: float | None = None
    interest_expense_usd: float | None = None
    net_income_usd: float | None = None
    operating_cash_flow_usd: float | None = None
    free_cash_flow_usd: float | None = None
    dso_days: float | None = None
    cash_usd: float | None = None
    budget_revenue_usd: float | None = None
    revenue_variance_usd: float | None = None
    revenue_variance_pct: float | None = None
    ebit_variance_usd: float | None = None
    mom_revenue_pct: float | None = None
    yoy_revenue_pct: float | None = None


class PeriodSeries(BaseModel):
    as_of: str
    granularity: Literal["month"] = "month"
    currency: str = MONEY
    synthetic: bool = True
    scope: dict[str, Any] = Field(default_factory=dict)
    points: list[MonthlyPoint] = Field(default_factory=list)
    lineage: list[str] = Field(default_factory=list)


class SupportingValue(BaseModel):
    """An extra auditable number quoted by a risk narrative."""

    key: str
    label: str
    value: float | None = None
    unit: str = MONEY


class RiskSignal(BaseModel):
    signal_id: str
    category: Literal[
        "profitability",
        "liquidity",
        "leverage",
        "working_capital",
        "budget_control",
        "market",
        "data_quality",
    ]
    severity: Literal["info", "low", "medium", "high", "critical"]
    title: str
    detail: str
    period: str
    observed_value: float | None = None
    unit: str = MONEY
    threshold: float | None = None
    threshold_unit: str = MONEY
    direction: Literal["above", "below", "change"] = "below"
    metric_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    supporting: list[SupportingValue] = Field(default_factory=list)
    recommended_check: str = ""
    synthetic: bool = True


class RiskRegister(BaseModel):
    as_of: str
    period: str
    synthetic: bool = True
    overall_level: Literal["low", "medium", "high", "critical"] = "low"
    score: float = 0.0
    signals: list[RiskSignal] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    lineage: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------
class ScenarioAssumptions(BaseModel):
    """Driver-based what-if inputs. Units are explicit and validated."""

    model_config = ConfigDict(extra="forbid")

    horizon_months: int = Field(default=12, ge=1, le=36)
    volume_growth_pct: float = Field(default=0.0, ge=-0.9, le=3.0, description="Annualised volume growth, decimal.")
    price_change_pct: float = Field(default=0.0, ge=-0.9, le=3.0, description="Selling price change vs base, decimal.")
    material_cost_change_pct: float = Field(default=0.0, ge=-0.9, le=3.0)
    labor_cost_change_pct: float = Field(default=0.0, ge=-0.9, le=3.0)
    overhead_cost_change_pct: float = Field(default=0.0, ge=-0.9, le=3.0)
    opex_change_pct: float = Field(default=0.0, ge=-0.9, le=3.0)
    interest_rate_delta_pp: float = Field(default=0.0, ge=-10.0, le=20.0, description="Change in annual rate, percentage points.")
    fx_change_pct: float = Field(default=0.0, ge=-0.9, le=3.0, description="USD per local currency; +5% = local currency stronger.")
    dso_days_delta: float = Field(default=0.0, ge=-60.0, le=120.0)
    capex_change_pct: float = Field(default=0.0, ge=-0.9, le=3.0)


class ScenarioDefinition(BaseModel):
    scenario_id: Literal["base", "upside", "downside"]
    label: str
    description: str
    assumptions: ScenarioAssumptions


class ScenarioMonth(BaseModel):
    month: str
    revenue_usd: float
    cogs_usd: float
    gross_profit_usd: float
    gross_margin_pct: float | None = None
    ebit_usd: float
    operating_margin_pct: float | None = None
    interest_expense_usd: float
    net_income_usd: float
    operating_cash_flow_usd: float
    free_cash_flow_usd: float
    cash_usd: float
    dso_days: float | None = None


class ScenarioSummary(BaseModel):
    scenario_id: str
    label: str
    currency: str = MONEY
    horizon_months: int
    revenue_usd: float
    gross_profit_usd: float
    gross_margin_pct: float | None = None
    ebit_usd: float
    operating_margin_pct: float | None = None
    interest_expense_usd: float
    net_income_usd: float
    operating_cash_flow_usd: float
    free_cash_flow_usd: float
    ending_cash_usd: float
    minimum_cash_usd: float
    revenue_delta_usd: float = 0.0
    ebit_delta_usd: float = 0.0
    ebit_delta_pct: float | None = None
    fcf_delta_usd: float = 0.0
    cash_runway_months: float | None = None
    months_with_negative_cash: int = 0


class SensitivityItem(BaseModel):
    driver: str
    label: str
    shock: str
    ebit_impact_usd_low: float
    ebit_impact_usd_high: float
    ebit_swing_usd: float


class ScenarioResult(BaseModel):
    as_of: str
    base_period: str
    horizon_months: int
    currency: str = MONEY
    synthetic: bool = True
    baseline: ScenarioSummary
    scenarios: list[ScenarioSummary] = Field(default_factory=list)
    monthly: dict[str, list[ScenarioMonth]] = Field(default_factory=dict)
    sensitivities: list[SensitivityItem] = Field(default_factory=list)
    assumptions: dict[str, ScenarioAssumptions] = Field(default_factory=dict)
    model_note: str = ""
    lineage: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Market data
# --------------------------------------------------------------------------
class MarketObservation(BaseModel):
    date: date
    value: float | None = None


class MarketSeries(BaseModel):
    series_id: str
    title: str
    units: str
    frequency: Literal["daily", "weekly", "monthly", "quarterly", "annual", "unknown"] = "unknown"
    country: str = "US"
    source_name: str = "FRED (Federal Reserve Bank of St. Louis)"
    source_url: str = ""
    fetched_at: datetime
    latest_observation_date: date | None = None
    latest_value: float | None = None
    previous_value: float | None = None
    change: float | None = None
    observations: list[MarketObservation] = Field(default_factory=list)
    is_fixture: bool = False
    is_stale: bool = False
    stale_after_days: int = 120
    alignment_note: str = ""
    license_note: str = ""
    error: str | None = None


class MarketCatalogItem(BaseModel):
    series_id: str
    title: str
    units: str
    frequency: str
    country: str
    rationale: str
    source_url: str
    available: bool = True


# --------------------------------------------------------------------------
# Agent
# --------------------------------------------------------------------------
class ToolCallRecord(BaseModel):
    call_id: str
    tool: str
    arguments: dict[str, Any]
    status: Literal["ok", "rejected", "error"] = "ok"
    error: str | None = None
    duration_ms: float = 0.0
    result_summary: str = ""
    started_at: datetime
    citations: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    citation_id: str
    kind: Literal["metric", "risk_signal", "scenario", "market_series", "lineage"]
    label: str
    value: float | None = None
    unit: str = MONEY
    period: str = ""
    source_ids: list[str] = Field(default_factory=list)


class AgentAnswer(BaseModel):
    question: str
    engine: str
    as_of: str
    synthetic: bool = True
    conclusion: str
    key_findings: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    confidence_limits: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    disclaimer: str = (
        "Demo output produced from SYNTHETIC data. Not investment advice and not a "
        "substitute for professional judgement."
    )


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------
class VerificationItem(BaseModel):
    check_id: str
    description: str
    status: Literal["pass", "warn", "fail"]
    detail: str = ""


class ReportDocument(BaseModel):
    report_id: str
    title: str
    as_of: str
    generated_at: datetime
    period: str
    currency: str = MONEY
    synthetic: bool = True
    markdown: str
    html: str
    citations: list[str] = Field(default_factory=list)
    verification: list[VerificationItem] = Field(default_factory=list)
    verification_status: Literal["pass", "warn", "fail"] = "pass"
    engine: str = "deterministic-report-builder"


class DataLineage(BaseModel):
    dataset_id: str
    name: str
    kind: Literal["synthetic_seed", "uploaded_file", "market_fixture", "market_live"]
    origin: str
    as_of: str
    rows: int = 0
    synthetic: bool = True
    columns: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
