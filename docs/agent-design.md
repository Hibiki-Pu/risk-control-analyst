# AI analyst design and safety boundaries

**One orchestrator, a closed tool set, and a hard rule: the language model never
computes a number.**

```
question ──► planner ──► tool calls (validated, audited) ──► deterministic engine
                │                                                  │
                └──────────────► narrator ◄──── citation registry ─┘
                                    │
                          guard_narrative()  ──► withheld lines are dropped and reported
```

## Components

| Module | Responsibility |
| --- | --- |
| `app/agent/orchestrator.py` | `DeterministicPlanner`, `LLMPlanner`, `AgentOrchestrator.ask`, narrative guard and composer, tool-call audit. |
| `app/agent/tools.py` | The closed tool set with `extra="forbid"` argument models. |
| `app/agent/llm.py` | Optional OpenAI-compatible client plus `StubLLMClient` used by the evaluation suite. |
| `app/reports/verify.py` | `Citation`, `extract_citations`, `extract_numbers` and the same traceability logic the report verifier uses. |

## The tool set (closed)

| Tool | Arguments | Returns |
| --- | --- | --- |
| `get_financial_metrics` | `month` \| `start`/`end`, `regions[]`, `metric_ids[]` | Metric pack with units, statuses and notes |
| `get_budget_variance` | `month` \| `start`/`end` | Actual-vs-plan variances |
| `get_risk_signals` | `month`, `minimum_severity` | Risk register slice |
| `get_market_series` | `series_id`, `allow_live`, `limit` | One macro series with provenance |
| `run_scenario` | all `ScenarioAssumptions` fields | base/upside/downside + a custom case |
| `compare_scenarios` | `horizon_months` | Scenario comparison + sensitivity ranking |
| `generate_report` | `month`, `horizon_months` | Report id + pre-export verification result |
| `get_data_lineage` | `dataset_id` | Dataset provenance and known gaps |

`GET /api/v1/agent/tools` publishes exactly this list with JSON schemas.

## Guardrails

| Risk | Control |
| --- | --- |
| Arbitrary code execution / unknown capability | The tool list is closed. An unknown tool name is recorded as `status: "rejected"` and never executed. |
| Parameter injection (`api_key`, extra keys) | Every argument model is `extra="forbid"`; the rejected attempt is audited with the offending argument. |
| Prompt injection via the question | The question text is **never** parsed into tool arguments. The deterministic planner maps intents to fixed argument sets; the LLM planner's arguments are schema-validated before use. |
| Hallucinated figures | `guard_narrative` drops any line whose numbers cannot be reproduced from the citations on that same line, and the answer lists what was withheld. |
| Fabricated sources | Findings may only cite ids that a tool produced; an unresolved citation causes the line to be withheld. |
| Silent failure | A tool exception becomes `status: "error"` with the exception text, and the answer states that the tool was not executed. |
| Secret leakage | No prompt, key or file content is stored. `runtime/tool_calls.jsonl` holds call id, tool, arguments, status, duration and citation ids only. |
| Invented values in a projection | Scenario outputs are cited as `model:driver-based-forecast@v1` and the model note travels with them. |

## Two modes

**Deterministic (default, zero keys).** `RCA_LLM_PROVIDER=deterministic` (the
default) or simply no `RCA_LLM_API_KEY`. A keyword planner (Chinese and English
keywords → intents) selects up to five tool calls, and a deterministic composer
writes the answer. `answer.engine = "deterministic-planner"`. This is the mode the
tests and the demo run in, so the product is fully demonstrable offline.

**LLM-assisted (optional).** With a provider, base URL and key configured, the
model receives the tool catalogue and the question and returns a JSON plan. After
the tools run, the model receives only the evidence list (citation id, label,
value, unit, period) and must return JSON: `conclusion`, `key_findings`, `risks`,
`recommendations`, `confidence_limits`. Every finding line then passes through
`guard_narrative`. If the model returns unusable output, the deterministic
narrator takes over and the answer says so in `confidence_limits`
(`"The configured language model did not return a usable narrative…"`).
`answer.engine = "llm:<model>"`.

## Answer shape

`POST /api/v1/agent/ask` returns `AgentAnswer`:

| Field | Meaning |
| --- | --- |
| `conclusion` | Short, cited summary |
| `key_findings` | Figure-level statements, each with `[citation_id]` |
| `evidence` | Citation id → value, unit, period, source ids |
| `assumptions` | Planner rationale + engine/model statements |
| `risks` / `recommendations` | From the fired rules (never investment advice) |
| `confidence_limits` | Fixture warnings, model notes, withheld-line reports, data gaps |
| `missing_data` | Unavailable metrics and failed tool calls |
| `tool_calls` | Audit records with status, timing and citations |
| `disclaimer` | States that the output is synthetic demo material |

## Evaluation

`services/api/tests/evaluation/agent_cases.json` holds 22 cases across seven
categories: `normal`, `missing_data`, `contradictory`, `zero_denominator`,
`unit_fx`, `injection`, `api_failure`. The suite asserts, per case, that the
expected tool ran, that every figure carries a resolvable citation, that missing
or undefined inputs are reported rather than filled in, that a simulated upstream
failure is surfaced, and that no secret-shaped string or forbidden phrasing
appears. See `docs/evaluation.md` for the latest results.

## Deliberately out of scope

Multi-agent fan-out, autonomous loops, memory across sessions, write access to
financial data, and any action beyond reading the deterministic engine.
