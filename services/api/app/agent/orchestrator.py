"""Deterministic and LLM-backed orchestration.

One orchestrator, one closed tool set. The LLM never computes a number: it plans
tool calls and then narrates evidence that the deterministic engine produced.
Every narrative line is passed through :func:`guard_narrative`, which drops any
line whose figures cannot be traced to the citations on that same line.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.agent.llm import LLMClient, build_llm_client, parse_json_object
from app.agent.tools import TOOLS, ToolContext, ToolResult, validate_arguments
from app.core.config import Settings, get_settings
from app.reports.verify import Citation, extract_citations, extract_numbers
from app.schemas import AgentAnswer, Evidence, ToolCallRecord

MAX_TOOL_CALLS = 5

EVIDENCE_KIND = {
    "metric": "metric",
    "budget": "metric",
    "risk": "risk_signal",
    "scenario": "scenario",
    "series": "market_series",
    "lineage": "lineage",
}

DISCLAIMER = (
    "Demo output produced from SYNTHETIC data. Not investment advice, not a credit opinion, and not a "
    "substitute for professional judgement."
)

INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "scenario": ("情景", "模拟", "假设", "如果", "敏感性", "压力测试", "scenario", "simulate", "what-if", "what if", "sensitivity", "downside", "upside"),
    "risk": ("风险", "预警", "红旗", "风控", "敞口", "risk", "red flag", "early warning", "exposure", "register"),
    "cash": ("现金", "流动性", "跑道", "资金", "liquidity", "cash", "runway", "burn"),
    "budget": ("预算", "差异", "计划达成", "budget", "variance", "plan"),
    "market": ("市场", "宏观", "利率", "汇率", "政策利率", "market", "macro", "interest rate", "fed", "fx", "currency"),
    "margin": ("毛利", "毛利率", "利润", "盈利", "成本", "margin", "profit", "profitability", "cost"),
    "report": ("报告", "管理层", "汇报", "report", "board pack", "memo"),
    "source": ("来源", "出处", "数据来源", "可信", "lineage", "source", "provenance", "synthetic", "数据字典"),
}


@dataclass
class PlannedCall:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    calls: list[PlannedCall]
    rationale: str
    source: str = "deterministic-planner"


# ----------------------------------------------------------------------
# planners
# ----------------------------------------------------------------------
class DeterministicPlanner:
    """Keyword planner. Zero keys, fully reproducible, used by default."""

    source = "deterministic-planner"

    def plan(self, question: str, month: str | None = None) -> Plan:
        text = question.lower()
        matched = [intent for intent, words in INTENT_KEYWORDS.items() if any(word.lower() in text for word in words)]
        calls: list[PlannedCall] = []

        if not matched:
            # Nothing specific was asked: answer with the general financial + risk pack.
            calls.append(PlannedCall("get_financial_metrics", {"month": month}))
            calls.append(PlannedCall("get_risk_signals", {"month": month, "minimum_severity": "low"}))
            rationale = (
                "No specific intent keyword matched, so the general financial metrics and the risk register "
                "were requested."
            )
            return Plan(calls=calls[:MAX_TOOL_CALLS], rationale=rationale, source=self.source)

        if "report" in matched:
            calls.append(PlannedCall("generate_report", {"month": month}))
        if "scenario" in matched:
            calls.append(PlannedCall("run_scenario", {"horizon_months": 12}))
        if "risk" in matched:
            calls.append(PlannedCall("get_risk_signals", {"month": month, "minimum_severity": "low"}))
        if "cash" in matched:
            # Liquidity questions are answered with both the numbers and the
            # liquidity rules, otherwise the answer cannot contradict a
            # "we are very liquid" premise with evidence.
            calls.append(PlannedCall("get_risk_signals", {"month": month, "minimum_severity": "low"}))
            calls.append(
                PlannedCall(
                    "get_financial_metrics",
                    {
                        "month": month,
                        "metric_ids": [
                            "revenue",
                            "ebit",
                            "operating_cash_flow",
                            "free_cash_flow",
                            "cash",
                            "dso_days",
                            "cash_conversion_cycle_days",
                            "interest_coverage",
                        ],
                    },
                )
            )
        if "budget" in matched:
            calls.append(PlannedCall("get_budget_variance", {"month": month}))
        if "market" in matched:
            calls.append(PlannedCall("get_market_series", {"series_id": "DFF", "allow_live": True}))
            calls.append(PlannedCall("get_market_series", {"series_id": "PPIACO", "allow_live": True}))
        if "margin" in matched:
            calls.append(
                PlannedCall(
                    "get_financial_metrics",
                    {
                        "month": month,
                        "metric_ids": [
                            "revenue",
                            "gross_margin",
                            "operating_margin",
                            "ebit",
                            "net_margin",
                            "interest_coverage",
                        ],
                    },
                )
            )
        if "source" in matched:
            calls.append(PlannedCall("get_data_lineage", {}))

        if not calls:
            calls.append(PlannedCall("get_financial_metrics", {"month": month}))
            calls.append(PlannedCall("get_risk_signals", {"month": month}))
        deduped: list[PlannedCall] = []
        seen: set[tuple[str, str]] = set()
        for call in calls:
            key = (call.tool, json.dumps(call.arguments, sort_keys=True, default=str))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(call)

        rationale = (
            f"Matched intents: {', '.join(matched) if matched else 'none (general financial + risk overview)'}. "
            f"Planned {len(deduped[:MAX_TOOL_CALLS])} tool call(s) from the closed tool set."
        )
        return Plan(calls=deduped[:MAX_TOOL_CALLS], rationale=rationale, source=self.source)


class LLMPlanner:
    """Asks the model only for a *plan*; execution stays deterministic."""

    def __init__(self, client: LLMClient, fallback: DeterministicPlanner | None = None):
        self.client = client
        self.fallback = fallback or DeterministicPlanner()

    def plan(self, question: str, month: str | None = None) -> Plan:
        tool_docs = [
            {"name": spec.name, "description": spec.description, "parameters": spec.args_model.model_json_schema()}
            for spec in TOOLS.values()
        ]
        system = (
            "You are the planning component of a financial risk-control analyst. You may only choose from the "
            "provided tools. Never compute or invent numbers. Reply with JSON: "
            '{"tool_calls":[{"name":"<tool>","arguments":{...}}],"rationale":"..."} '
            f"Use at most {MAX_TOOL_CALLS} calls."
        )
        user = json.dumps({"question": question, "month": month, "tools": tool_docs}, ensure_ascii=False)
        response = self.client.complete(system, user, json_mode=True)
        payload = parse_json_object(response.text)
        calls: list[PlannedCall] = []
        for item in payload.get("tool_calls", []):
            name = item.get("name")
            if name not in TOOLS:
                continue
            calls.append(PlannedCall(name, item.get("arguments") or {}))
        if not calls:
            return self.fallback.plan(question, month)
        return Plan(calls=calls[:MAX_TOOL_CALLS], rationale=payload.get("rationale", ""), source=f"llm:{self.client.model_name}")


# ----------------------------------------------------------------------
# narrative guard
# ----------------------------------------------------------------------
def guard_narrative(lines: list[str], registry: dict[str, Citation]) -> tuple[list[str], list[str]]:
    """Keep only lines whose numbers are traceable to the citations on that line."""
    from app.reports.verify import CITATION_PATTERN

    kept: list[str] = []
    withheld: list[str] = []
    for line in lines:
        citation_ids = extract_citations(line)
        if not citation_ids:
            if extract_numbers(line):
                withheld.append(f"no citation: {line}")
                continue
            kept.append(line)
            continue
        acceptable: set[str] = set()
        unresolved = False
        for citation_id in citation_ids:
            citation = registry.get(citation_id)
            if citation is None:
                unresolved = True
                continue
            acceptable |= {option.replace(" ", "") for option in citation.formats()}
        if unresolved:
            withheld.append(f"unresolved citation: {line}")
            continue
        stripped = CITATION_PATTERN.sub(" ", line)
        bad = [token for token in extract_numbers(stripped) if token.replace(" ", "") not in acceptable]
        if bad:
            withheld.append(f"untraceable figure(s) {bad}: {line}")
            continue
        kept.append(line)
    return kept, withheld


# ----------------------------------------------------------------------
# orchestrator
# ----------------------------------------------------------------------
class AgentOrchestrator:
    def __init__(
        self,
        context: ToolContext,
        settings: Settings | None = None,
        planner=None,
        llm_client: LLMClient | None = None,
    ):
        self.context = context
        self.settings = settings or get_settings()
        self.llm_client = llm_client if llm_client is not None else build_llm_client(self.settings)
        self.planner = planner or (
            LLMPlanner(self.llm_client) if self.llm_client is not None else DeterministicPlanner()
        )
        self.audit: list[ToolCallRecord] = []
        #: Citation registry of the most recent answer (id -> value), exposed for
        #: verification and for the evaluation suite.
        self.last_registry: dict[str, Citation] = {}

    # ------------------------------------------------------------------
    @property
    def engine_label(self) -> str:
        return getattr(self.planner, "source", "deterministic-planner") if self.llm_client is not None else "deterministic-planner"

    def _record(self, record: ToolCallRecord) -> None:
        self.audit.append(record)
        try:
            self.settings.ensure_runtime_dir()
            with self.settings.tool_log_file.open("a", encoding="utf-8") as handle:
                handle.write(record.model_dump_json() + "\n")
        except OSError:
            # Auditing must never break a user request; the in-memory log remains.
            pass

    def _execute(self, call: PlannedCall) -> tuple[ToolResult | None, ToolCallRecord]:
        call_id = uuid.uuid4().hex[:12]
        started_at = datetime.now(timezone.utc)
        started = time.perf_counter()
        spec = TOOLS.get(call.tool)
        if spec is None:
            record = ToolCallRecord(
                call_id=call_id,
                tool=call.tool,
                arguments=call.arguments,
                status="rejected",
                error=f"unknown tool '{call.tool}' (the tool set is closed)",
                started_at=started_at,
            )
            self._record(record)
            return None, record
        try:
            arguments = validate_arguments(call.tool, call.arguments)
        except Exception as exc:  # noqa: BLE001 - validation failure is data, not a crash
            record = ToolCallRecord(
                call_id=call_id,
                tool=call.tool,
                arguments=call.arguments,
                status="rejected",
                error=f"argument validation failed: {exc}",
                started_at=started_at,
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
            self._record(record)
            return None, record
        try:
            result = spec.handler(self.context, arguments)
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller
            record = ToolCallRecord(
                call_id=call_id,
                tool=call.tool,
                arguments=call.arguments,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
                started_at=started_at,
                duration_ms=(time.perf_counter() - started) * 1000.0,
            )
            self._record(record)
            return None, record
        record = ToolCallRecord(
            call_id=call_id,
            tool=call.tool,
            arguments=arguments.model_dump(exclude_none=True),
            status="ok",
            duration_ms=(time.perf_counter() - started) * 1000.0,
            result_summary=result.summary,
            started_at=started_at,
            citations=sorted(result.citations.keys()),
        )
        self._record(record)
        return result, record

    # ------------------------------------------------------------------
    def ask(self, question: str, month: str | None = None) -> AgentAnswer:
        plan = self.planner.plan(question, month)
        results: list[ToolResult] = []
        records: list[ToolCallRecord] = []
        registry: dict[str, Citation] = {}
        missing: list[str] = []

        for call in plan.calls:
            result, record = self._execute(call)
            records.append(record)
            if result is None:
                missing.append(f"{call.tool} was not executed: {record.error}")
                continue
            results.append(result)
            registry.update(result.citations)
            missing.extend(result.missing_data)

        conclusion, findings, risks, recommendations, limits, used = self._compose(question, results, registry, plan)

        if self.llm_client is not None and results:
            narrated = self._llm_narrate(question, registry)
            if narrated is None:
                limits.append(
                    "The configured language model did not return a usable narrative, so the deterministic "
                    "narrator was used instead."
                )
            else:
                conclusion = narrated.get("conclusion") or conclusion
                findings = list(narrated.get("key_findings") or [])
                risks = list(narrated.get("risks") or risks)
                recommendations = list(narrated.get("recommendations") or recommendations)
                limits.extend(narrated.get("confidence_limits") or [])

        kept, withheld = guard_narrative(findings, registry)
        if withheld:
            limits.append(
                f"{len(withheld)} narrative line(s) were withheld because a figure could not be traced to a tool "
                "result: " + "; ".join(withheld[:3])
            )
        evidence = [
            Evidence(
                citation_id=citation_id,
                kind=EVIDENCE_KIND.get(citation_id.split(":", 1)[0], "metric"),  # type: ignore[arg-type]
                label=registry[citation_id].label,
                value=registry[citation_id].value,
                unit=registry[citation_id].unit,
                period=registry[citation_id].period,
                source_ids=registry[citation_id].source_ids,
            )
            for citation_id in used
            if citation_id in registry
        ]

        engine_used = "deterministic-planner" if self.llm_client is None else f"llm:{self.llm_client.model_name}"
        self.last_registry = registry
        if not results:
            conclusion = (
                "I could not produce an evidence-based answer: every planned tool call failed, so there is no "
                "computed figure to report."
            )
            limits.append("No tool call succeeded; no numbers were produced.")
            kept = []

        return AgentAnswer(
            question=question,
            engine=engine_used,
            as_of=self.context.engine.as_of,
            synthetic=self.context.engine.synthetic,
            conclusion=conclusion,
            key_findings=kept,
            evidence=evidence,
            assumptions=[
                plan.rationale,
                "Deterministic engine: metrics are computed by app.finance.engine; scenarios by "
                "app.finance.scenarios (driver-based, no machine learning).",
                "The language model, when enabled, may only select tools and narrate returned evidence.",
            ],
            risks=risks,
            recommendations=recommendations,
            confidence_limits=limits,
            missing_data=missing,
            tool_calls=records,
            disclaimer=DISCLAIMER,
        )

    # ------------------------------------------------------------------
    def _llm_narrate(self, question: str, registry: dict[str, Citation]) -> dict[str, Any] | None:
        """Optional narration step. Returns None when the model is unusable."""
        system = (
            "You are the narrative component of a financial risk-control analyst. You write in the language of the "
            "question. HARD RULES: (1) only use numbers that appear in the EVIDENCE list; (2) every bullet must end "
            "with the citation ids it uses, written like [metric:gross_margin@2024-12]; (3) never invent a value, a "
            "source or a date; (4) if the evidence is insufficient, say so instead of estimating. Reply with JSON: "
            '{"conclusion": str, "key_findings": [str], "risks": [str], "recommendations": [str], '
            '"confidence_limits": [str]}'
        )
        evidence = [
            {
                "citation_id": citation_id,
                "label": citation.label,
                "value": citation.value,
                "unit": citation.unit,
                "period": citation.period,
            }
            for citation_id, citation in registry.items()
        ]
        user = json.dumps({"question": question, "evidence": evidence}, ensure_ascii=False, default=str)
        try:
            response = self.llm_client.complete(system, user, json_mode=True)
            payload = parse_json_object(response.text)
        except Exception:  # noqa: BLE001 - any failure falls back to the deterministic narrator
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    # ------------------------------------------------------------------
    def _compose(self, question: str, results: list[ToolResult], registry: dict[str, Citation], plan: Plan):
        findings: list[str] = []
        risks: list[str] = []
        recommendations: list[str] = []
        limits: list[str] = []
        used: list[str] = []

        def cite(citation_id: str) -> str:
            if citation_id in registry:
                if citation_id not in used:
                    used.append(citation_id)
                return f"[{citation_id}]"
            return ""

        def fmt(value: float | None, unit: str) -> str:
            if value is None:
                return "not available"
            if unit == "pct":
                return f"{value * 100:.1f}%"
            if unit == "percent_points":
                return f"{value:.2f}%"
            if unit == "days":
                return f"{value:.1f} days"
            if unit == "x":
                return f"{value:.2f} x"
            if unit == "months":
                return f"{value:.1f} months"
            if unit == "pp":
                return f"{value:+.1f}pp"
            return f"{value:,.0f}"

        for result in results:
            if result.tool == "get_financial_metrics":
                period = result.payload.get("period", "")
                for metric_id, value in result.payload.get("metrics", {}).items():
                    unit = result.payload.get("units", {}).get(metric_id, "USD")
                    status = result.payload.get("status", {}).get(metric_id, "ok")
                    note = result.payload.get("notes", {}).get(metric_id)
                    citation = cite(f"metric:{metric_id}@{period}")
                    if status != "ok":
                        findings.append(
                            f"{metric_id} for {period} is not available ({status})"
                            + (f": {note}" if note else "")
                            + f" {citation}".rstrip()
                        )
                        continue
                    suffix = f" — {note}" if note else ""
                    findings.append(f"{metric_id} for {period}: {fmt(value, unit)} {citation}{suffix}".strip())
            elif result.tool == "get_budget_variance":
                period = result.payload.get("period", "")
                for metric_id, value in result.payload.get("variances", {}).items():
                    unit = result.payload.get("units", {}).get(metric_id, "USD")
                    status = result.payload.get("status", {}).get(metric_id, "ok")
                    citation = cite(f"budget:{metric_id}@{period}")
                    if status != "ok":
                        findings.append(f"plan variance {metric_id} ({period}) is not available ({status}) {citation}".strip())
                        continue
                    findings.append(f"plan variance {metric_id} ({period}): {fmt(value, unit)} {citation}".strip())
            elif result.tool == "get_risk_signals":
                register = result.payload.get("register", {})
                findings.append(
                    f"risk register level {register.get('overall_level')} with score "
                    f"{float(register.get('score', 0.0)):.1f} {cite('risk:register.score')}".strip()
                )
                for signal in register.get("signals", []):
                    citation = cite(f"risk:{signal['signal_id']}@{signal['period']}")
                    threshold = cite(f"risk:{signal['signal_id']}.threshold@{signal['period']}")
                    line = (
                        f"[{signal['severity']}] {signal['signal_id']} {signal['title']}: observed "
                        f"{fmt(signal.get('observed_value'), signal.get('unit', 'USD'))} {citation} against threshold "
                        f"{fmt(signal.get('threshold'), signal.get('threshold_unit', 'USD'))} {threshold}"
                    )
                    findings.append(line.strip())
                    if signal["severity"] in {"critical", "high"}:
                        risks.append(f"{signal['signal_id']} — {signal['detail']}")
                    if signal.get("recommended_check"):
                        recommendations.append(f"{signal['signal_id']} — {signal['recommended_check']}")
                for gap in register.get("data_gaps", []):
                    limits.append(f"data gap: {gap}")
            elif result.tool == "get_market_series":
                series = result.payload.get("series", {})
                if series.get("latest_value") is not None and series.get("latest_observation_date"):
                    citation = cite(f"series:{series['series_id']}@{series['latest_observation_date']}")
                    unit = "percent_points" if "Percent" in series.get("units", "") else "raw"
                    origin = "local demo fixture" if series.get("is_fixture") else "live FRED observation"
                    findings.append(
                        f"{series['series_id']} ({series.get('units')}) latest "
                        f"{fmt(series['latest_value'], unit)} on {series['latest_observation_date']} {citation} — {origin}"
                    )
                    if series.get("is_fixture"):
                        limits.append(
                            f"{series['series_id']}: values are DEMO fixtures, not live market data."
                        )
                elif series.get("error"):
                    limits.append(f"{series.get('series_id')}: {series['error']}")
            elif result.tool in {"run_scenario", "compare_scenarios"}:
                for summary in result.payload.get("scenarios", []):
                    scenario_id = summary["scenario_id"]
                    findings.append(
                        f"scenario {scenario_id}: EBIT {fmt(summary['ebit_usd'], 'USD')} "
                        f"{cite(f'scenario:{scenario_id}.ebit_usd')}, change vs run-rate "
                        f"{fmt(summary['ebit_delta_usd'], 'USD')} {cite(f'scenario:{scenario_id}.ebit_delta_usd')}, "
                        f"ending cash {fmt(summary['ending_cash_usd'], 'USD')} {cite(f'scenario:{scenario_id}.ending_cash_usd')}"
                    )
                for item in result.payload.get("sensitivities", [])[:4]:
                    swing_citation = cite(f"scenario:sensitivity.{item['driver']}.swing")
                    findings.append(
                        f"sensitivity: {item['label']} swing {fmt(item['ebit_swing_usd'], 'USD')} {swing_citation}"
                    )
                if result.payload.get("model_note"):
                    limits.append(result.payload["model_note"])
            elif result.tool == "get_data_lineage":
                for item in result.payload.get("lineage", []):
                    findings.append(
                        f"dataset {item['name']} ({item['kind']}, rows {item['rows']}, synthetic={item['synthetic']})"
                    )
            elif result.tool == "generate_report":
                status = result.payload.get("verification_status")
                findings.append(
                    f"management report {result.payload.get('report_id')} built with pre-export verification "
                    f"status {status}"
                )
                for item in result.payload.get("verification", []):
                    if item["status"] != "pass":
                        limits.append(f"verification {item['check_id']} {item['status']}: {item['detail']}")

        conclusion = self._conclusion(question, results, registry, cite)
        if not recommendations:
            recommendations.append("No rule fired with an action; keep the current monitoring cadence.")
        return conclusion, findings, risks, recommendations, limits, used

    # ------------------------------------------------------------------
    def _conclusion(self, question: str, results: list[ToolResult], registry: dict[str, Citation], cite) -> str:
        risk_result = next((result for result in results if result.tool == "get_risk_signals"), None)
        scenario_result = next((result for result in results if result.tool == "run_scenario"), None)
        parts: list[str] = []
        if risk_result is not None:
            register = risk_result.payload.get("register", {})
            count = len(register.get("signals", []))
            parts.append(
                f"The risk register reads {str(register.get('overall_level', 'n/a')).upper()} with score "
                f"{float(register.get('score', 0.0)):.1f} {cite('risk:register.score')} across {count} fired signal(s)."
            )
        if scenario_result is not None:
            downside = next(
                (item for item in scenario_result.payload.get("scenarios", []) if item["scenario_id"] == "downside"),
                None,
            )
            if downside is not None:
                parts.append(
                    f"In the downside scenario EBIT changes by {downside['ebit_delta_usd']:,.0f} USD "
                    f"{cite('scenario:downside.ebit_delta_usd')} versus the run-rate."
                )
        if not parts:
            parts.append(
                "Answered from the deterministic calculation service only; every figure below is traceable to a tool "
                "result."
            )
        parts.append(
            "All figures are computed by the deterministic engine (no LLM arithmetic) and are based on SYNTHETIC "
            "demo data."
        )
        return " ".join(parts)
