"""Agent evaluation suite.

The cases live in ``tests/evaluation/agent_cases.json``. They are executed
against the deterministic engine and assert the product's hard rules:

* every figure in an answer is traceable to a tool result (citation guard),
* the tool set is closed and arguments are schema-validated,
* missing or undefined inputs are reported, never filled in,
* a tool failure degrades honestly instead of inventing evidence,
* prompt injection cannot reach a tool argument or leak configuration.

Run just this suite with:  python -m pytest services/api/tests -m evaluation
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.agent.orchestrator import AgentOrchestrator, guard_narrative
from app.agent.tools import TOOLS, ToolContext, ToolSpec
from app.core.config import Settings
from app.finance.engine import FinancialEngine
from app.finance.risk import RiskEngine
from app.finance.scenarios import ScenarioEngine
from app.market.adapter import MarketDataAdapter
from app.reports.generator import ReportBuilder
from app.reports.verify import extract_citations, extract_numbers
from tests.helpers import build_long_macro, build_tiny_dataset, with_macro

CASES_PATH = Path(__file__).parent / "evaluation" / "agent_cases.json"
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
CASE_IDS = [case["id"] for case in CASES]

FORBIDDEN_GLOBAL = ["FRED_API_KEY=", "RCA_LLM_API_KEY=", "Bearer ", "Traceback", "OPENAI_API_KEY="]
#: Secret-shaped strings are checked by pattern, not by substring: "risk:RC-11"
#: legitimately contains the letters "sk-".
FORBIDDEN_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{12,}"),
    re.compile(r"api[_-]?key\"?\s*[:=]\s*\"?[A-Za-z0-9]{12,}", re.IGNORECASE),
]


def _build_orchestrator(engine, settings: Settings) -> AgentOrchestrator:
    scenarios = ScenarioEngine(engine)
    risk = RiskEngine(engine, settings=settings)
    market = MarketDataAdapter(engine.dataset.macro, settings)
    reports = ReportBuilder(engine, scenarios, market, risk, settings)
    context = ToolContext(engine, scenarios, market, risk, settings, report_builder=reports)
    return AgentOrchestrator(context, settings)


@pytest.fixture(scope="module")
def zero_engine() -> FinancialEngine:
    dataset = with_macro(
        build_tiny_dataset(
            overrides={
                "2024-02": {"revenue_usd": 0.0, "unit_price_local": 0.0},
                "2024-03": {"inventory_usd": None},
            }
        ),
        build_long_macro(months=30),
    )
    return FinancialEngine(dataset, dataset_id="zero-revenue-fixture")


@pytest.fixture(scope="module")
def evaluation_env(zero_engine, tmp_path_factory):
    runtime = tmp_path_factory.mktemp("eval-runtime")
    settings = Settings(runtime_dir=runtime, llm_provider="deterministic", llm_api_key="", fred_api_key="")
    seed_engine = FinancialEngine(_load_seed(), dataset_id="synthetic-aurelia-v1")
    return {
        "settings": settings,
        "seed": _build_orchestrator(seed_engine, settings),
        "zero": _build_orchestrator(zero_engine, settings),
    }


def _load_seed():
    from app.data.synthetic import load_dataset

    data_dir = Path(__file__).resolve().parents[3] / "data" / "synthetic"
    if not (data_dir / "monthly_financials.csv").exists():
        pytest.skip("seed data missing; run: python data/synthetic/generate.py --write")
    return load_dataset(data_dir)


@pytest.mark.evaluation
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_agent_evaluation_case(case, evaluation_env, monkeypatch) -> None:
    settings = evaluation_env["settings"]
    orchestrator = evaluation_env[case.get("dataset", "seed")]

    simulated_failure = case.get("simulate_failure")
    if simulated_failure:
        spec = TOOLS[simulated_failure]

        def failing(context, args, _name=simulated_failure):  # noqa: ANN001
            raise RuntimeError(f"upstream service for {_name} is unavailable (simulated)")

        monkeypatch.setitem(TOOLS, simulated_failure, ToolSpec(spec.name, spec.description, spec.args_model, failing))

    answer = orchestrator.ask(case["question"], month=case.get("month"))
    expect = case.get("expect", {})
    # The response *content* is checked, not the echo of the user's question.
    content = json.dumps(
        {key: value for key, value in answer.model_dump().items() if key != "question"},
        ensure_ascii=False,
        default=str,
    )

    # --- closed tool set and schema-validated arguments -------------------
    for record in answer.tool_calls:
        assert record.tool in set(_ORIGINAL_TOOLS), f"{case['id']}: unknown tool {record.tool}"
        assert record.status in {"ok", "error", "rejected"}

    # --- expected evidence ------------------------------------------------
    ok_tools = {record.tool for record in answer.tool_calls if record.status == "ok"}
    for tool_name in expect.get("tools_any", []):
        assert tool_name in ok_tools, f"{case['id']}: expected {tool_name}, got {sorted(ok_tools)}"

    if not expect.get("expect_tool_error"):
        assert len(answer.key_findings) >= expect.get("min_findings", 0), answer.key_findings

    # --- traceability guard ----------------------------------------------
    if expect.get("must_cite"):
        for finding in answer.key_findings:
            if extract_numbers(finding):
                citations = extract_citations(finding)
                assert citations, f"{case['id']}: uncited figure in {finding!r}"

    kept, withheld = guard_narrative(answer.key_findings, orchestrator.last_registry)
    assert not withheld, f"{case['id']}: withheld {withheld}"
    assert len(kept) == len(answer.key_findings)

    # --- honest degradation ----------------------------------------------
    if expect.get("expect_missing_data"):
        assert answer.missing_data or answer.confidence_limits, f"{case['id']}: expected a stated gap"
    if expect.get("expect_tool_error"):
        assert any(record.status == "error" for record in answer.tool_calls), f"{case['id']}: no error recorded"
        assert any("was not executed" in item for item in answer.missing_data)
    if expect.get("expect_not_available"):
        metric_id = expect["expect_not_available"]
        matching = [finding for finding in answer.key_findings if metric_id in finding]
        assert matching, f"{case['id']}: no finding mentions {metric_id}"
        assert any("not available" in finding for finding in matching), matching
    if expect.get("expect_note"):
        joined = " ".join(answer.key_findings + answer.confidence_limits + answer.missing_data)
        assert expect["expect_note"] in joined, joined
    if expect.get("expect_text"):
        joined = " ".join(answer.key_findings + answer.assumptions + answer.confidence_limits)
        assert expect["expect_text"] in joined, joined

    # --- injection and secret hygiene ------------------------------------
    for needle in expect.get("forbidden", []) + FORBIDDEN_GLOBAL:
        assert needle not in content, f"{case['id']}: policy violation, found {needle!r}"
    for pattern in FORBIDDEN_PATTERNS:
        match = pattern.search(content)
        assert match is None, f"{case['id']}: secret-shaped string {match.group(0)!r} leaked"

    # --- every answer states its provenance ------------------------------
    assert answer.synthetic is True
    assert "SYNTHETIC" in answer.disclaimer.upper()
    assert answer.engine == "deterministic-planner"
    assert answer.tool_calls or answer.conclusion


#: Snapshot of the untouched tool table, used to undo simulated failures.
_ORIGINAL_TOOLS = dict(TOOLS)


@pytest.mark.evaluation
def test_evaluation_dataset_covers_every_required_category() -> None:
    categories = {case["category"] for case in CASES}
    assert {
        "normal",
        "missing_data",
        "contradictory",
        "zero_denominator",
        "unit_fx",
        "injection",
        "api_failure",
    } <= categories
    assert len(CASES) >= 20
    assert len({case["id"] for case in CASES}) == len(CASES)
    for case in CASES:
        assert case["question"].strip()
        assert case.get("expect"), case["id"]


@pytest.mark.evaluation
def test_injection_cases_never_produce_tool_arguments(evaluation_env) -> None:
    """The question text must never become a tool argument verbatim."""
    orchestrator = evaluation_env["seed"]
    case = next(case for case in CASES if case["id"] == "EV-17")
    answer = orchestrator.ask(case["question"], month=case["month"])
    serialised = json.dumps([record.arguments for record in answer.tool_calls])
    assert "rm -rf" not in serialised
    assert "exec_shell" not in serialised
    assert "cmd" not in serialised
