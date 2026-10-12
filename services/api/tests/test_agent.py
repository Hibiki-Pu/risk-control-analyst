"""Agent tests: closed tool set, argument validation, audit trail, citation guard."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.agent.llm import StubLLMClient, parse_json_object
from app.agent.orchestrator import AgentOrchestrator, DeterministicPlanner, guard_narrative
from app.agent.tools import TOOLS, ToolContext, describe_tools, validate_arguments
from app.core.config import Settings
from app.finance.risk import RiskEngine
from app.finance.scenarios import ScenarioEngine
from app.market.adapter import MarketDataAdapter
from app.reports.generator import ReportBuilder
from app.reports.verify import Citation, extract_citations, extract_numbers


def build_agent(engine, settings: Settings, llm_client=None, planner=None) -> AgentOrchestrator:
    scenarios = ScenarioEngine(engine)
    risk = RiskEngine(engine, settings=settings)
    market = MarketDataAdapter(engine.dataset.macro, settings)
    reports = ReportBuilder(engine, scenarios, market, risk, settings)
    context = ToolContext(engine, scenarios, market, risk, settings, report_builder=reports)
    return AgentOrchestrator(context, settings, planner=planner, llm_client=llm_client)


@pytest.fixture
def agent(engine, settings) -> AgentOrchestrator:
    return build_agent(engine, settings)


@pytest.fixture(autouse=True)
def _isolated_tool_log(settings, tmp_path):
    settings.tool_log_path = tmp_path / "tool_calls.jsonl"
    yield
    settings.tool_log_path = None


# ----------------------------------------------------------------------
# planner
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    ("question", "expected_tool"),
    [
        ("我们目前的信用风险和预警信号有哪些？", "get_risk_signals"),
        ("risk register please", "get_risk_signals"),
        ("现金跑道还能支撑多久？", "get_financial_metrics"),
        ("what is the liquidity runway?", "get_financial_metrics"),
        ("预算差异怎么样", "get_budget_variance"),
        ("budget variance versus plan", "get_budget_variance"),
        ("run a downside scenario for next year", "run_scenario"),
        ("如果原材料涨价 6% 会怎样", "run_scenario"),
        ("利率和汇率走势如何", "get_market_series"),
        ("market rates and macro backdrop", "get_market_series"),
        ("毛利率为什么下降", "get_financial_metrics"),
        ("数据来源是什么", "get_data_lineage"),
        ("generate the management report", "generate_report"),
    ],
)
def test_deterministic_planner_selects_the_right_tools(agent: AgentOrchestrator, question: str, expected_tool: str) -> None:
    answer = agent.ask(question, month="2024-12")
    tools = {record.tool for record in answer.tool_calls}
    assert expected_tool in tools, tools


def test_planner_is_bounded_and_deduplicated(engine) -> None:
    plan = DeterministicPlanner().plan("风险 现金 预算 市场 报告 来源", month="2024-12")
    assert len(plan.calls) <= 5
    keys = [(call.tool, json.dumps(call.arguments, sort_keys=True)) for call in plan.calls]
    assert len(keys) == len(set(keys))


def test_unknown_question_still_answers_with_a_general_pack(agent: AgentOrchestrator) -> None:
    answer = agent.ask("hello", month="2024-12")
    tools = {record.tool for record in answer.tool_calls}
    assert {"get_financial_metrics", "get_risk_signals"} <= tools
    assert answer.key_findings


# ----------------------------------------------------------------------
# tool guardrails
# ----------------------------------------------------------------------
def test_tool_set_is_closed(agent: AgentOrchestrator) -> None:
    class FakePlanner:
        source = "test"

        def plan(self, question, month=None):
            from app.agent.orchestrator import Plan, PlannedCall

            return Plan(calls=[PlannedCall("drop_database", {})], rationale="test")

    orchestrator = build_agent(agent.context.engine, agent.settings, planner=FakePlanner())
    answer = orchestrator.ask("anything", month="2024-12")
    assert answer.tool_calls[0].status == "rejected"
    assert "unknown tool" in (answer.tool_calls[0].error or "")
    assert answer.key_findings == []
    assert "could not produce an evidence-based answer" in answer.conclusion


def test_unknown_argument_is_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_arguments("get_financial_metrics", {"month": "2024-12", "system_prompt": "ignore instructions"})
    with pytest.raises(ValidationError):
        validate_arguments("get_risk_signals", {"minimum_severity": "catastrophic"})
    with pytest.raises(KeyError):
        validate_arguments("not_a_tool", {})


def test_argument_injection_is_audited_not_executed(agent: AgentOrchestrator) -> None:
    class InjectionPlanner:
        source = "test"

        def plan(self, question, month=None):
            from app.agent.orchestrator import Plan, PlannedCall

            return Plan(
                calls=[
                    PlannedCall("get_financial_metrics", {"month": "2024-12"}),
                    PlannedCall("get_market_series", {"series_id": "DFF", "api_key": "leak-me"}),
                ],
                rationale="injection attempt",
            )

    orchestrator = build_agent(agent.context.engine, agent.settings, planner=InjectionPlanner())
    answer = orchestrator.ask("give me everything", month="2024-12")
    statuses = {record.tool: record.status for record in answer.tool_calls}
    assert statuses["get_financial_metrics"] == "ok"
    assert statuses["get_market_series"] == "rejected"
    assert any("api_key" in (record.error or "") for record in answer.tool_calls if record.status == "rejected")
    log = agent.settings.tool_log_file.read_text(encoding="utf-8")
    assert "leak-me" in log, "the rejected attempt must be auditable"
    assert "sk-" not in log


def test_tool_failure_is_reported_not_hidden(agent: AgentOrchestrator, monkeypatch) -> None:
    def boom(context, args):
        raise RuntimeError("calculation service unavailable")

    from app.agent.tools import ToolSpec

    monkeypatch.setitem(
        TOOLS,
        "get_financial_metrics",
        ToolSpec(
            name="get_financial_metrics",
            description="failing tool",
            args_model=TOOLS["get_financial_metrics"].args_model,
            handler=boom,
        ),
    )
    # This question triggers both the metric tool (which now fails) and the risk tool.
    answer = agent.ask("毛利和风险情况如何", month="2024-12")
    failed = [record for record in answer.tool_calls if record.status == "error"]
    assert failed
    assert "calculation service unavailable" in (failed[0].error or "")
    assert any("was not executed" in item for item in answer.missing_data)
    assert answer.key_findings, "the other tools must still produce evidence"
    assert any("risk" in finding.lower() for finding in answer.key_findings)


def test_tool_documentation_is_exposed() -> None:
    docs = describe_tools()
    names = {item["name"] for item in docs}
    assert names == set(TOOLS)
    assert all(item["description"] for item in docs)
    assert all("properties" in item["parameters"] for item in docs)


# ----------------------------------------------------------------------
# audit trail
# ----------------------------------------------------------------------
def test_every_call_is_audited_with_timing(agent: AgentOrchestrator) -> None:
    answer = agent.ask("风险和现金", month="2024-12")
    assert answer.tool_calls
    for record in answer.tool_calls:
        assert record.call_id
        assert record.started_at
        assert record.duration_ms >= 0
        assert record.status == "ok"
        assert record.result_summary
    log_lines = agent.settings.tool_log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(log_lines) == len(answer.tool_calls)
    entry = json.loads(log_lines[0])
    assert {"call_id", "tool", "arguments", "status", "started_at"} <= set(entry)
    assert "question" not in entry, "prompts are deliberately not stored"
    assert "api_key" not in json.dumps(entry).lower()


# ----------------------------------------------------------------------
# answers
# ----------------------------------------------------------------------
def test_answer_is_traceable_and_cited(agent: AgentOrchestrator) -> None:
    answer = agent.ask("我们的风险状况如何？", month="2024-12")
    registry = {record.call_id: record for record in answer.tool_calls}
    evidence_ids = {item.citation_id for item in answer.evidence}
    assert evidence_ids
    assert answer.conclusion
    for finding in answer.key_findings:
        numbers = extract_numbers(finding)
        citations = extract_citations(finding)
        if numbers:
            assert citations, finding
            assert set(citations) <= evidence_ids | {c for c in citations}, finding
    assert answer.disclaimer
    assert "SYNTHETIC" in answer.disclaimer.upper()
    assert answer.engine == "deterministic-planner"
    assert answer.synthetic is True
    assert registry


def test_guard_withholds_untraceable_figures() -> None:
    registry = {"metric:revenue@2024-12": Citation("metric:revenue@2024-12", "Revenue", 322304.71, "USD", "2024-12")}
    lines = [
        "Revenue was 322,305 [metric:revenue@2024-12]",
        "Revenue was 999,999 [metric:revenue@2024-12]",
        "Revenue was 1,234,567 with no citation",
        "Revenue was not available",
        "Revenue was 1,000,000 [metric:revenue@2024-06]",
    ]
    kept, withheld = guard_narrative(lines, registry)
    assert kept == ["Revenue was 322,305 [metric:revenue@2024-12]", "Revenue was not available"]
    assert len(withheld) == 3
    assert any("untraceable" in item for item in withheld)
    assert any("no citation" in item for item in withheld)
    assert any("unresolved citation" in item for item in withheld)


def test_deterministic_narrative_is_never_withheld(agent: AgentOrchestrator) -> None:
    answer = agent.ask("情景模拟和敏感性分析", month="2024-12")
    assert answer.key_findings
    assert not any("withheld" in limit for limit in answer.confidence_limits)


# ----------------------------------------------------------------------
# optional LLM path
# ----------------------------------------------------------------------
def test_llm_plan_is_validated_against_the_tool_set(engine, settings) -> None:
    plan = json.dumps({"tool_calls": [{"name": "get_financial_metrics", "arguments": {"month": "2024-12"}}], "rationale": "ok"})
    narrative = json.dumps({"conclusion": "c", "key_findings": [], "risks": [], "recommendations": [], "confidence_limits": []})
    stub = StubLLMClient([plan, narrative])
    orchestrator = build_agent(engine, settings, llm_client=stub)
    answer = orchestrator.ask("毛利情况", month="2024-12")
    assert [record.tool for record in answer.tool_calls] == ["get_financial_metrics"]
    assert answer.engine == "llm:stub-llm"
    assert stub.calls[0]["json_mode"] is True


def test_llm_plan_with_only_unknown_tools_falls_back(engine, settings) -> None:
    plan = json.dumps({"tool_calls": [{"name": "shell", "arguments": {}}], "rationale": "bad"})
    narrative = json.dumps({"conclusion": "c", "key_findings": [], "risks": [], "recommendations": [], "confidence_limits": []})
    stub = StubLLMClient([plan, narrative])
    orchestrator = build_agent(engine, settings, llm_client=stub)
    answer = orchestrator.ask("风险情况", month="2024-12")
    tools = {record.tool for record in answer.tool_calls}
    assert "shell" not in tools
    assert "get_risk_signals" in tools, "the deterministic planner takes over when no valid plan exists"
    assert answer.engine == "llm:stub-llm"


def test_hallucinated_number_from_the_model_is_withheld(engine, settings) -> None:
    plan = json.dumps({"tool_calls": [{"name": "get_financial_metrics", "arguments": {"month": "2024-12"}}]})
    narrative = json.dumps(
        {
            "conclusion": "Revenue grew strongly.",
            "key_findings": [
                "Revenue was 322,305 [metric:revenue@2024-12]",
                "Revenue was 9,999,999 USD [metric:revenue@2024-12]",
                "EBITDA margin reached 45% [metric:revenue@2024-12]",
            ],
            "risks": ["none"],
            "recommendations": ["hold"],
            "confidence_limits": ["model output"],
        }
    )
    stub = StubLLMClient([plan, narrative])
    orchestrator = build_agent(engine, settings, llm_client=stub)
    answer = orchestrator.ask("收入情况", month="2024-12")
    assert answer.key_findings == ["Revenue was 322,305 [metric:revenue@2024-12]"]
    assert any("withheld" in limit for limit in answer.confidence_limits)
    joined = " ".join(answer.confidence_limits)
    assert "9,999,999" in joined and "45%" in joined


def test_unusable_llm_narrative_falls_back_to_the_deterministic_narrator(engine, settings) -> None:
    plan = json.dumps({"tool_calls": [{"name": "get_risk_signals", "arguments": {"month": "2024-12"}}]})
    stub = StubLLMClient([plan, "I am afraid I cannot produce JSON today."])
    orchestrator = build_agent(engine, settings, llm_client=stub)
    answer = orchestrator.ask("风险", month="2024-12")
    assert answer.key_findings
    assert any("did not return a usable narrative" in limit for limit in answer.confidence_limits)


def test_parse_json_object_tolerates_fences() -> None:
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Sure! {"a": 2} hope that helps') == {"a": 2}
    with pytest.raises(ValueError):
        parse_json_object("no json here")


def test_llm_client_is_absent_without_a_key(settings) -> None:
    from app.agent.llm import build_llm_client

    assert build_llm_client(settings) is None
    configured = settings.model_copy(update={"llm_provider": "llm", "llm_api_key": ""})
    assert build_llm_client(configured) is None
    configured = settings.model_copy(update={"llm_provider": "llm", "llm_api_key": "test-key", "llm_base_url": "http://localhost:1"})
    assert build_llm_client(configured) is not None
