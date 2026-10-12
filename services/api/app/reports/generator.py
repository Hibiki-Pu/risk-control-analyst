"""Management report builder.

The report is assembled from deterministic results only. Every number is emitted
together with a citation token, and the citation registry is handed to the
pre-export verifier (``app.reports.verify``) so a wrong figure can never reach an
export unnoticed.
"""

from __future__ import annotations

import html as html_lib
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.core.config import Settings, get_settings
from app.finance.engine import TAX_RATE_USED, FinancialEngine
from app.finance.risk import RiskEngine
from app.finance.scenarios import ScenarioEngine
from app.market.adapter import MarketDataAdapter, provenance_summary
from app.reports.verify import Citation, overall_status, verify_report
from app.schemas import (
    MetricSet,
    ReportDocument,
    RiskRegister,
    ScenarioResult,
    VerificationItem,
)

DEFAULT_MARKET_SERIES = ("DFF", "PPIACO", "DEXTHUS", "DTWEXBGS")

SECTION_TITLES = (
    "Executive Summary",
    "KPI Performance",
    "Budget Performance",
    "External Market Signals",
    "Scenario Comparison",
    "Key Risks",
    "Recommended Actions",
    "Assumptions & Sources",
)


def money(value: float | None, currency: str = "USD") -> str:
    if value is None:
        return "n/a"
    return f"{value:,.0f}"


def pct(value: float | None, digits: int = 1, signed: bool = False) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:+.{digits}f}%" if signed else f"{value * 100:.{digits}f}%"


def ratio(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f} x"


def days(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f} days"


def percent_points(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.1f}pp"


class ReportBuilder:
    def __init__(
        self,
        engine: FinancialEngine,
        scenario_engine: ScenarioEngine,
        market: MarketDataAdapter,
        risk_engine: RiskEngine,
        settings: Settings | None = None,
    ):
        self.engine = engine
        self.scenarios = scenario_engine
        self.market = market
        self.risk = risk_engine
        self.settings = settings or get_settings()
        self.registry: dict[str, Citation] = {}

    # ------------------------------------------------------------------
    def _register(self, citation_id: str, citation: Citation) -> str:
        self.registry[citation_id] = citation
        return f"[{citation_id}]"

    def _register_metric(self, pack: MetricSet, metric_id: str) -> str:
        cited = pack.values.get(metric_id)
        if cited is None:
            return ""
        citation_id = f"metric:{metric_id}@{pack.period}"
        return self._register(
            citation_id,
            Citation(
                citation_id=citation_id,
                label=cited.label,
                value=cited.value,
                unit=cited.unit,
                period=pack.period,
                source_ids=cited.source_ids,
            ),
        )

    def _register_scenario(self, scenario_id: str, field: str, value: float | None, unit: str, label: str) -> str:
        citation_id = f"scenario:{scenario_id}.{field}"
        return self._register(
            citation_id,
            Citation(
                citation_id=citation_id,
                label=label,
                value=value,
                unit=unit,
                period="horizon",
                source_ids=["model:driver-based-forecast@v1"],
            ),
        )

    def _register_series(self, series_id: str, value: float | None, unit: str, period: str, source_ids: list[str]) -> str:
        citation_id = f"series:{series_id}@{period}"
        return self._register(
            citation_id,
            Citation(
                citation_id=citation_id,
                label=series_id,
                value=value,
                unit=unit,
                period=period,
                source_ids=source_ids,
            ),
        )

    # ------------------------------------------------------------------
    def build(
        self,
        month: str | None = None,
        scenario_ids: tuple[str, ...] = ("base", "upside", "downside"),
        market_series_ids: tuple[str, ...] = DEFAULT_MARKET_SERIES,
        horizon_months: int = 12,
    ) -> ReportDocument:
        month = month or self.engine.as_of
        self.registry = {}
        fy_months = [m for m in self.engine.months if m.startswith(month[:4])]
        monthly = self.engine.metrics(months=[month])
        ttm_months = self.engine.months[max(0, self.engine.months.index(month) - 11): self.engine.months.index(month) + 1]
        ttm = self.engine.metrics(months=ttm_months)
        fy = self.engine.metrics(months=fy_months)
        variance = self.engine.budget_variance(months=fy_months)
        register = self.risk.build(month=month)
        scenario_result = self._run_scenarios(scenario_ids, horizon_months)

        market_series = [self.market.get_series(series_id) for series_id in market_series_ids]
        market_notes = [provenance_summary(series) for series in market_series]

        sections: list[tuple[str, str]] = []
        sections.append(("Executive Summary", self._executive_summary(month, monthly, fy, register, scenario_result)))
        sections.append(("KPI Performance", self._kpi_section(month, monthly, ttm, fy)))
        sections.append(("Budget Performance", self._budget_section(fy, variance)))
        sections.append(("External Market Signals", self._market_section(market_series, month)))
        sections.append(("Scenario Comparison", self._scenario_section(scenario_result)))
        sections.append(("Key Risks", self._risk_section(register)))
        sections.append(("Recommended Actions", self._action_section(register)))
        sections.append(("Assumptions & Sources", self._sources_section(month, scenario_result, market_series)))

        header = self._header(month, register, scenario_result)
        body = "\n\n".join(f"## {index + 1}. {title}\n\n{content}" for index, (title, content) in enumerate(sections))
        markdown = f"{header}\n\n{body}\n"

        undefined = [
            metric_id
            for metric_id, cited in {**monthly.values, **fy.values}.items()
            if cited.status != "ok" and metric_id in markdown
        ]
        verification: list[VerificationItem] = verify_report(
            markdown,
            self.registry,
            synthetic=self.engine.synthetic,
            as_of=month,
            market_notes=market_notes,
            undefined_metrics=undefined,
        )
        status = overall_status(verification)

        report_id = f"RCA-{month.replace('-', '')}-{uuid.uuid4().hex[:6]}"
        document = ReportDocument(
            report_id=report_id,
            title=f"Risk Control & Financial Performance Report — {month}",
            as_of=month,
            generated_at=datetime.now(timezone.utc),
            period=f"{fy_months[0]}..{fy_months[-1]}",
            currency=self.engine.currency,
            synthetic=self.engine.synthetic,
            markdown=markdown,
            html=render_html(markdown, f"Risk Control Report — {month}"),
            citations=sorted(self.registry.keys()),
            verification=verification,
            verification_status=status,  # type: ignore[arg-type]
        )
        self._persist(document)
        return document

    # ------------------------------------------------------------------
    def _run_scenarios(self, scenario_ids: tuple[str, ...], horizon_months: int) -> ScenarioResult:
        """Run the preset scenarios (base / upside / downside) at the requested horizon."""
        del scenario_ids  # the presets define the scenario set; ids are validated by the API layer
        return self.scenarios.run(horizon_months=horizon_months)

    # ------------------------------------------------------------------
    def _header(self, month: str, register: RiskRegister, scenario_result: ScenarioResult) -> str:
        score_citation = self._register(
            "risk:register.score",
            Citation("risk:register.score", "Risk register score", register.score, "score", month, register.lineage),
        )
        horizon_citation = self._register_scenario(
            "base", "horizon_months", float(scenario_result.horizon_months), "months", "Scenario horizon"
        )
        return (
            f"# Risk Control & Financial Performance Report\n\n"
            f"**As-of date:** {month} | **Reporting currency:** {self.engine.currency} | "
            f"**Data classification:** SYNTHETIC DEMO DATA (fictional company)\n\n"
            f"**Overall risk level:** {register.overall_level.upper()} "
            f"(register score {register.score:.1f} {score_citation} across the live signal set) | "
            f"**Scenario horizon:** {scenario_result.horizon_months} months {horizon_citation} "
            f"from {scenario_result.as_of}\n\n"
            "All figures are computed deterministically by the calculation service. Every number below carries a "
            "citation of the form `metric:gross_margin@" + month + "`; the pre-export verifier re-computes each one "
            "before the report can be exported."
        )

    # ------------------------------------------------------------------
    def _executive_summary(
        self,
        month: str,
        monthly: MetricSet,
        fy: MetricSet,
        register: RiskRegister,
        scenario_result: ScenarioResult,
    ) -> str:
        lines: list[str] = []
        revenue = monthly.values["revenue"]
        ebit = monthly.values["ebit"]
        cash = monthly.values["cash"]
        coverage = monthly.values["interest_coverage"]
        gross_margin = monthly.values["gross_margin"]
        fy_revenue = fy.values["revenue"]

        lines.append(
            f"- **Revenue** in {month} was {money(revenue.value)} {self.engine.currency} {self._register_metric(monthly, 'revenue')}, "
            f"taking {fy.period} revenue to {money(fy_revenue.value)} {self.engine.currency} {self._register_metric(fy, 'revenue')}."
        )
        lines.append(
            f"- **Profitability:** EBIT of {money(ebit.value)} {self.engine.currency} {self._register_metric(monthly, 'ebit')} "
            f"on a gross margin of {pct(gross_margin.value)} {self._register_metric(monthly, 'gross_margin')}."
        )
        lines.append(
            f"- **Debt service:** interest cover of {ratio(coverage.value)} {self._register_metric(monthly, 'interest_coverage')} "
            f"against a policy floor of {ratio(self.risk.thresholds.interest_coverage_min)} "
            f"{self._register('risk:policy.interest_coverage', Citation('risk:policy.interest_coverage', 'Interest coverage floor', self.risk.thresholds.interest_coverage_min, 'x', month, ['policy:risk-thresholds@v1']))}."
        )
        lines.append(
            f"- **Liquidity:** closing cash of {money(cash.value)} {self.engine.currency} {self._register_metric(monthly, 'cash')} "
            f"with operating cash flow of {money(monthly.values['operating_cash_flow'].value)} {self.engine.currency} "
            f"{self._register_metric(monthly, 'operating_cash_flow')} and free cash flow of "
            f"{money(monthly.values['free_cash_flow'].value)} {self.engine.currency} {self._register_metric(monthly, 'free_cash_flow')}."
        )
        lines.append(
            f"- **Risk register:** overall level **{register.overall_level.upper()}** with score "
            f"{register.score:.1f} {self._register('risk:register.score', Citation('risk:register.score', 'Risk register score', register.score, 'score', month, register.lineage))} "
            f"across {len(register.signals)} fired signals ({len(register.data_gaps)} known data gaps)."
        )
        worst = next((signal for signal in register.signals if signal.severity in {"critical", "high"}), None)
        if worst is not None:
            lines.append(
                f"- **Headline exposure:** {worst.title} — {worst.detail.splitlines()[0]} "
                f"{self._register('risk:' + worst.signal_id + '@' + worst.period, Citation('risk:' + worst.signal_id + '@' + worst.period, worst.title, worst.observed_value, worst.unit, worst.period, worst.source_ids))}"
            )
        downside = next(
            (summary for summary in scenario_result.scenarios if summary.scenario_id == "downside"), None
        )
        if downside is not None:
            lines.append(
                f"- **Scenario view:** under the downside case EBIT reaches {money(downside.ebit_usd)} {self.engine.currency} "
                f"{self._register_scenario('downside', 'ebit_usd', downside.ebit_usd, self.engine.currency, 'Downside EBIT')}, "
                f"a change of {money(downside.ebit_delta_usd)} {self.engine.currency} "
                f"{self._register_scenario('downside', 'ebit_delta_usd', downside.ebit_delta_usd, self.engine.currency, 'Downside EBIT delta')} "
                f"versus the run-rate, with ending cash of {money(downside.ending_cash_usd)} {self.engine.currency} "
                f"{self._register_scenario('downside', 'ending_cash_usd', downside.ending_cash_usd, self.engine.currency, 'Downside ending cash')}."
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    def _kpi_section(self, month: str, monthly: MetricSet, ttm: MetricSet, fy: MetricSet) -> str:
        rows = [
            ("Revenue", "revenue", money),
            ("Gross margin", "gross_margin", pct),
            ("EBIT", "ebit", money),
            ("Operating margin", "operating_margin", pct),
            ("Net income (proxy)", "net_income", money),
            ("Operating cash flow (proxy)", "operating_cash_flow", money),
            ("Free cash flow (proxy)", "free_cash_flow", money),
            ("DSO (average receivables)", "dso_days", days),
            ("Cash conversion cycle", "cash_conversion_cycle_days", days),
            ("Interest coverage", "interest_coverage", ratio),
            ("Net debt / EBITDA (annualised)", "net_leverage", ratio),
            ("Closing cash", "cash", money),
        ]
        out = [f"Latest month {month}; trailing twelve months = {ttm.period}.", "", "| Metric | Latest month | Trailing 12M | Source citation |", "| --- | --- | --- | --- |"]
        for label, metric_id, formatter in rows:
            current = monthly.values.get(metric_id)
            trailing = ttm.values.get(metric_id)
            if current is None:
                continue
            citation = self._register_metric(monthly, metric_id)
            trailing_citation = self._register_metric(ttm, metric_id)
            if current.status != "ok":
                out.append(
                    f"| {label} | not available ({current.note}) | "
                    f"{formatter(trailing.value) if trailing else 'n/a'} {trailing_citation} | {citation} |"
                )
                continue
            out.append(
                f"| {label} | {formatter(current.value)} {citation} | "
                f"{formatter(trailing.value) if trailing else 'n/a'} {trailing_citation} | {citation} |"
            )
        variance_note = (
            f"Period note: {ttm.values['revenue'].note}" if ttm.values.get("revenue") and ttm.values["revenue"].note else ""
        )
        if variance_note:
            out.append("")
            out.append(f"{variance_note} {self._register_metric(ttm, 'revenue')}")
        return "\n".join(out)

    # ------------------------------------------------------------------
    def _budget_section(self, fy: MetricSet, variance: MetricSet) -> str:
        out = [
            f"Plan comparison for {variance.period}. Positive revenue variance is favourable; for a cost line a "
            "positive variance is unfavourable.",
            "",
            "| Metric | Actual | Plan | Variance | Variance % | Citation |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        pairs = [
            ("Revenue", "revenue", "budget_revenue", "revenue_variance", "revenue_variance_pct"),
            ("Cost of goods sold", "cogs", "budget_cogs", "cogs_variance", "cogs_variance_pct"),
            ("Operating expenses", "opex", "budget_opex", "opex_variance", "opex_variance_pct"),
            ("EBIT", "ebit", "budget_ebit", "ebit_variance", "ebit_variance_pct"),
        ]
        budget_index = self.engine.budget_series_index()
        year = variance.period[:4]
        months = [month for month in self.engine.months if month.startswith(year)]
        available = [month for month in months if month in budget_index.index]
        if not available:
            # No plan in the dataset: say so instead of comparing against nothing.
            note = next(
                (cited.note for cited in variance.values.values() if cited.note),
                "No budget layer is available for this dataset.",
            )
            out.append("")
            out.append(f"Plan comparison is not available: {note}")
            return "\n".join(out)
        for label, metric_id, plan_column, variance_id, variance_pct_id in pairs:
            actual = fy.values.get(metric_id)
            var = variance.values.get(variance_id)
            var_pct = variance.values.get(variance_pct_id)
            if actual is None or var is None:
                continue
            planned = None
            if available and plan_column in budget_index.columns:
                planned_value = budget_index.loc[available, plan_column].sum(min_count=1)
                planned = None if pd.isna(planned_value) else float(planned_value)
            plan_citation = self._register(
                f"budget:{metric_id}_plan@{variance.period}",
                Citation(
                    f"budget:{metric_id}_plan@{variance.period}",
                    f"{label} plan",
                    planned,
                    self.engine.currency,
                    variance.period,
                    [f"budget:monthly_budget@{month}" for month in available],
                ),
            ) if planned is not None else ""
            variance_citation = self._register(
                f"budget:{variance_id}@{variance.period}",
                Citation(
                    f"budget:{variance_id}@{variance.period}",
                    label + " variance",
                    var.value,
                    self.engine.currency,
                    variance.period,
                    var.source_ids,
                ),
            )
            pct_citation = ""
            if var_pct is not None and var_pct.status == "ok" and var_pct.value is not None:
                pct_citation = self._register(
                    f"budget:{variance_pct_id}@{variance.period}",
                    Citation(
                        f"budget:{variance_pct_id}@{variance.period}",
                        label + " variance %",
                        var_pct.value,
                        "pct",
                        variance.period,
                        var_pct.source_ids,
                    ),
                )
            out.append(
                f"| {label} | {money(actual.value)} {self._register_metric(fy, metric_id)} | "
                f"{money(planned)} {plan_citation} | {money(var.value)} {variance_citation} | "
                f"{pct(var_pct.value, signed=True) if var_pct and var_pct.value is not None else 'n/a'} {pct_citation} | "
                f"{variance_citation} |"
            )
        if not budget_index.empty and "budget_note" in budget_index.columns:
            plan_note = str(budget_index["budget_note"].iloc[0])
            out.append("")
            out.append(f"Plan basis: {plan_note} Months covered: {len(available)}.")
        return "\n".join(out)

    # ------------------------------------------------------------------
    def _market_section(self, series_list, month: str) -> str:
        out = [
            "Market inputs are read through the Market Data Adapter. Fixtures are never presented as live observations.",
            "",
            "| Series | Latest value | Observation date | Frequency | Provenance | Citation |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for series in series_list:
            if series.latest_value is None or series.latest_observation_date is None:
                out.append(
                    f"| {series.series_id} | not available | n/a | {series.frequency} | "
                    f"{'local demo fixture' if series.is_fixture else 'live'} | n/a |"
                )
                continue
            unit = "percent_points" if ("Percent" in series.units or "Rate" in series.title) else "raw"
            citation = self._register_series(
                series.series_id,
                series.latest_value,
                unit,
                series.latest_observation_date.isoformat(),
                [f"market:{series.series_id}@{series.latest_observation_date.isoformat()}"],
            )
            rendered = (
                f"{series.latest_value:.2f}%"
                if unit == "percent_points"
                else f"{series.latest_value:,.2f}"
            )
            provenance = (
                "local demo fixture (NOT live)" if series.is_fixture else "FRED live observation"
            )
            if series.error:
                provenance += f"; {series.error}"
            out.append(
                f"| {series.series_id} | {rendered} | {series.latest_observation_date.isoformat()} | "
                f"{series.frequency} | {provenance} | {citation} |"
            )
        out.append("")
        out.append(
            "Alignment policy: series keep their native frequency and are never forward-filled across "
            "frequencies; consumers must select the observation date they need."
        )
        return "\n".join(out)

    # ------------------------------------------------------------------
    def _tax_rate_citation(self) -> str:
        """Model parameter used by the projection: stated and cited explicitly."""
        return self._register(
            "model:tax_rate@v1",
            Citation(
                citation_id="model:tax_rate@v1",
                label="Assumed tax rate",
                value=TAX_RATE_USED,
                unit="pct",
                period="model",
                source_ids=["model:driver-based-forecast@v1"],
            ),
        )

    def _scenario_section(self, result: ScenarioResult) -> str:
        model_citation = self._tax_rate_citation()
        out = [
            f"Driver-based projection over {result.horizon_months} months from {result.as_of}. "
            f"Baseline run-rate window: {result.base_period}.",
            "",
            f"Model note: {result.model_note} {model_citation}",
            "",
            "| Scenario | Revenue | EBIT | EBIT vs base | FCF | Ending cash | Minimum cash |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for summary in result.scenarios:
            cells = []
            for field, value, unit, label in (
                ("revenue_usd", summary.revenue_usd, self.engine.currency, "Revenue"),
                ("ebit_usd", summary.ebit_usd, self.engine.currency, "EBIT"),
                ("ebit_delta_usd", summary.ebit_delta_usd, self.engine.currency, "EBIT delta"),
                ("free_cash_flow_usd", summary.free_cash_flow_usd, self.engine.currency, "FCF"),
                ("ending_cash_usd", summary.ending_cash_usd, self.engine.currency, "Ending cash"),
                ("minimum_cash_usd", summary.minimum_cash_usd, self.engine.currency, "Minimum cash"),
            ):
                citation = self._register_scenario(summary.scenario_id, field, value, unit, f"{summary.label} {label}")
                cells.append(f"{money(value)} {citation}")
            out.append(f"| {summary.label} | " + " | ".join(cells) + " |")

        if result.sensitivities:
            out.append("")
            out.append("Sensitivity of horizon EBIT to a single-driver shock (tornado, largest swing first):")
            out.append("")
            out.append("| Driver | Shock | EBIT impact down | EBIT impact up | Swing | Citation |")
            out.append("| --- | --- | --- | --- | --- | --- |")
            for item in result.sensitivities[:5]:
                low = self._register_scenario("sensitivity", f"{item.driver}.low", item.ebit_impact_usd_low, self.engine.currency, item.label)
                high = self._register_scenario("sensitivity", f"{item.driver}.high", item.ebit_impact_usd_high, self.engine.currency, item.label)
                swing = self._register_scenario("sensitivity", f"{item.driver}.swing", item.ebit_swing_usd, self.engine.currency, item.label)
                out.append(
                    f"| {item.label} | {item.shock} | {money(item.ebit_impact_usd_low)} {low} | "
                    f"{money(item.ebit_impact_usd_high)} {high} | {money(item.ebit_swing_usd)} {swing} | {swing} |"
                )
        return "\n".join(out)

    # ------------------------------------------------------------------
    def _risk_section(self, register: RiskRegister) -> str:
        if not register.signals:
            return (
                f"No risk rule fired in {register.period}. The register score is {register.score:.1f} "
                f"{self._register('risk:register.score', Citation('risk:register.score', 'Risk register score', register.score, 'score', register.period, register.lineage))}."
            )
        out: list[str] = []
        for signal in register.signals:
            observed = self._register(
                f"risk:{signal.signal_id}@{signal.period}",
                Citation(f"risk:{signal.signal_id}@{signal.period}", signal.title, signal.observed_value, signal.unit, signal.period, signal.source_ids),
            )
            threshold_citation = ""
            if signal.threshold is not None:
                threshold_citation = " " + self._register(
                    f"risk:{signal.signal_id}.threshold@{signal.period}",
                    Citation(f"risk:{signal.signal_id}.threshold@{signal.period}", signal.title + " threshold", signal.threshold, signal.threshold_unit, signal.period, ["policy:risk-thresholds@v1"]),
                )
            supporting_citations = ""
            for item in signal.supporting:
                supporting_citations += " " + self._register(
                    f"risk:{signal.signal_id}.{item.key}@{signal.period}",
                    Citation(
                        f"risk:{signal.signal_id}.{item.key}@{signal.period}",
                        item.label,
                        item.value,
                        item.unit,
                        signal.period,
                        signal.source_ids,
                    ),
                )
            observed_text = self._format_signal_value(signal.observed_value, signal.unit)
            threshold_text = self._format_signal_value(signal.threshold, signal.threshold_unit)
            out.append(
                f"- **[{signal.severity.upper()}] {signal.signal_id} — {signal.title}** "
                f"({signal.category.replace('_', ' ')}). Observed {observed_text} {observed}{threshold_citation}"
                f"{supporting_citations} against a threshold of {threshold_text}. {signal.detail} "
                f"Check: {signal.recommended_check}"
            )
        if register.data_gaps:
            out.append("")
            out.append("Known data gaps (not measurable with the shipped dataset):")
            out.extend(f"- {gap}" for gap in register.data_gaps)
        return "\n".join(out)

    @staticmethod
    def _format_signal_value(value: float | None, unit: str) -> str:
        if value is None:
            return "n/a"
        if unit == "pct":
            return pct(value)
        if unit == "days":
            return days(value)
        if unit == "x":
            return ratio(value)
        if unit == "pp":
            return percent_points(value)
        if unit == "months":
            return f"{value:.1f} months"
        if unit == "cells":
            return f"{value:.0f} cells"
        if unit == "score":
            return f"{value:.1f}"
        return money(value)

    # ------------------------------------------------------------------
    def _action_section(self, register: RiskRegister) -> str:
        out = [
            "Actions are derived from the fired risk rules. They are operational checks, not investment advice.",
            "",
        ]
        seen: set[str] = set()
        for signal in register.signals:
            if signal.recommended_check and signal.recommended_check not in seen:
                seen.add(signal.recommended_check)
                out.append(f"- **{signal.signal_id}** {signal.recommended_check}")
        if not seen:
            out.append("- No rule fired; maintain the current monitoring cadence.")
        out.append("")
        out.append(
            "Nothing in this report is a buy/sell recommendation, a credit rating or an audit opinion."
        )
        return "\n".join(out)

    # ------------------------------------------------------------------
    def _sources_section(self, month: str, result: ScenarioResult, series_list) -> str:
        lineage = self.engine.lineage()
        out = [
            f"- **As-of date:** {month}; **currency:** {self.engine.currency}; **period covered:** "
            f"{result.base_period} (run-rate) plus {result.horizon_months} projected months.",
            f"- **Data classification:** SYNTHETIC DEMO DATA. The company is fictional, the seeded dataset is "
            f"generated with a fixed seed, and the market values in fixture mode are hand-built demo values.",
            f"- **Model assumptions:** {result.model_note} {self._tax_rate_citation()}",
            "- **Methodology:** `docs/financial-methodology.md` (formulas, units, period conventions, "
            "zero-denominator and missing-data policy).",
            "- **Risk rules:** `docs/risk-rules.md` (thresholds, severities and scoring).",
            "",
            "| Dataset | Kind | Origin | Rows | Synthetic |",
            "| --- | --- | --- | --- | --- |",
        ]
        for item in lineage:
            out.append(
                f"| {item.name} | {item.kind} | {item.origin} | {item.rows} | {'yes' if item.synthetic else 'no'} |"
            )
        out.append("")
        out.append("Market data provenance:")
        out.extend(f"- {provenance_summary(series)}" for series in series_list)
        out.append("")
        out.append(
            "Recomputation: every figure above can be regenerated with "
            "`python data/synthetic/generate.py --write` followed by "
            "`python -m pytest services/api/tests`."
        )
        return "\n".join(out)

    # ------------------------------------------------------------------
    def _persist(self, document: ReportDocument) -> None:
        target = self.settings.runtime_dir / "reports"
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{document.report_id}.md").write_text(document.markdown, encoding="utf-8")
        (target / f"{document.report_id}.html").write_text(document.html, encoding="utf-8")
        (target / f"{document.report_id}.verification.json").write_text(
            document.model_dump_json(indent=2), encoding="utf-8"
        )


# ----------------------------------------------------------------------
# Minimal markdown -> HTML renderer for the subset this builder emits.
# ----------------------------------------------------------------------
_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _inline(text: str) -> str:
    escaped = html_lib.escape(text, quote=False)
    escaped = _INLINE_CODE.sub(r"<code>\1</code>", escaped)
    escaped = _BOLD.sub(r"<strong>\1</strong>", escaped)
    escaped = _LINK.sub(r'<a href="\2">\1</a>', escaped)
    return escaped


def render_html(markdown: str, title: str) -> str:
    lines = markdown.splitlines()
    parts: list[str] = []
    in_list = False
    in_table = False
    for line in lines:
        stripped = line.strip()
        if in_table and not stripped.startswith("|"):
            parts.append("</tbody></table>")
            in_table = False
        if in_list and not stripped.startswith("- "):
            parts.append("</ul>")
            in_list = False
        if not stripped:
            continue
        if stripped.startswith("| "):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if set("".join(cells)) <= {"-", " ", ":"}:
                continue
            if not in_table:
                parts.append("<table><thead><tr>" + "".join(f"<th>{_inline(cell)}</th>" for cell in cells) + "</tr></thead><tbody>")
                in_table = True
                continue
            parts.append("<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in cells) + "</tr>")
            continue
        if stripped.startswith("- "):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{_inline(stripped[2:])}</li>")
            continue
        if stripped.startswith("### "):
            parts.append(f"<h3>{_inline(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            parts.append(f"<h2>{_inline(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            parts.append(f"<h1>{_inline(stripped[2:])}</h1>")
        else:
            parts.append(f"<p>{_inline(stripped)}</p>")
    if in_table:
        parts.append("</tbody></table>")
    if in_list:
        parts.append("</ul>")
    body = "\n".join(parts)
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{html_lib.escape(title)}</title>\n"
        "<style>body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:1040px;"
        "margin:32px auto;padding:0 20px;line-height:1.55;color:#0f172a}h1{font-size:26px}h2{font-size:19px;"
        "margin-top:28px;border-bottom:1px solid #e2e8f0;padding-bottom:6px}table{border-collapse:collapse;"
        "width:100%;margin:12px 0;font-size:14px}th,td{border:1px solid #e2e8f0;padding:6px 8px;text-align:left}"
        "th{background:#f8fafc}code{background:#f1f5f9;padding:1px 4px;border-radius:3px;font-size:12px}"
        "li{margin:4px 0}</style>\n</head>\n<body>\n"
        f"{body}\n</body>\n</html>\n"
    )
