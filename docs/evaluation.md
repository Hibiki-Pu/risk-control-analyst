# Evaluation & test evidence

All numbers below were produced by commands actually executed in this checkout
(Windows, Python 3.10.2, Node 24.11.1). Nothing here is projected.

## 1. Backend suite — `pytest`

```bash
cd services/api
python -m pytest tests -q --cov=app --cov-report=term
```

| Suite | Tests | What it pins down |
| --- | --- | --- |
| `test_agent.py` | 30 | Planner intents (zh/en), closed tool set, argument rejection, tool failure handling, audit trail, citation guard, optional LLM path with a stub client |
| `test_agent_evaluation.py` | 24 | The 22-case evaluation dataset (below) plus two dataset-design checks |
| `test_api.py` | 22 | Every endpoint, request validation, upload happy path/sad path, error hygiene |
| `test_engine.py` | 21 | Hand-calculated metric values, stock-vs-flow handling, working-capital formulas, zero denominators, missing values |
| `test_formulas.py` | 10 | Safe division, percentage change, missing-cell counting, calendar helpers |
| `test_market.py` | 13 | Fixture provenance, live fetch, cache TTL, retry, failure fallback, staleness |
| `test_reports.py` | 17 | Report sections, all seven verification checks, tamper detection, HTML escaping |
| `test_risk.py` | 14 | Each rule's trigger and severity boundary, data gaps, score arithmetic |
| `test_scenarios.py` | 22 | Run-rate identity, driver direction, DSO/capex isolation, tornado ranking, determinism |
| `test_synthetic.py` | 18 | Seed determinism, revenue identity, declared gap, round-trip write/load |
| **Total** | **191** | **All passing** |

Coverage: **96%** of statements (`2835` statements, `111` missed).

| Module | Cover | Module | Cover |
| --- | --- | --- | --- |
| `finance/engine.py` | 99% | `reports/verify.py` | 99% |
| `finance/formulas.py` | 100% | `finance/scenarios.py` | 98% |
| `schemas.py` | 100% | `market/adapter.py` | 98% |
| `core/config.py` | 100% | `agent/orchestrator.py` | 96% |
| `services.py` | 100% | `data/synthetic.py` | 96% |
| `agent/tools.py` | 95% | `reports/generator.py` | 94% |
| `data/store.py` | 95% | `api/routes.py` | 94% |
| `finance/risk.py` | 93% | `data/ingest.py` | 89% |
| `main.py` | 88% | `agent/llm.py` | 79% (live HTTP path) |

## 2. Frontend suite — `vitest`

```bash
cd apps/web
npm run typecheck     # tsc --noEmit, clean
npm test              # 6 files, 55 tests, all passing
npm run build         # 608 modules, dist/assets/index-*.js 797.40 kB (gzip 265.92 kB), CSS 19.49 kB (gzip 4.40 kB)
```

| Suite | Tests | What it pins down |
| --- | --- | --- |
| `lib/format.test.ts` | 30 | Every unit renderer, and that a missing value is `不可用` + note and never `0` |
| `components/KpiCard.test.tsx` | 7 | Value, delta, missing state, `data-state="missing"` |
| `components/Feedback.test.tsx` | 3 | Loading skeleton, empty state, error state with the API's own message |
| `pages/PnlAnalysis.test.ts` | 7 | Variance sign convention per cost/revenue line |
| `pages/Overview.test.tsx` | 6 | Skeleton → loaded transition, endpoint URLs, honest rendering |
| `pages/Overview.live.test.tsx` | 2 | **Live integration** against a running FastAPI service |

The live test is skipped unless the suite is started with the backend URL:

```bash
# terminal 1
cd services/api && python -m uvicorn app.main:app --port 8000
# terminal 2
cd apps/web && VITE_API_BASE=http://127.0.0.1:8000/api/v1 npm test
```

When it runs it asserts that the browser shows the engine's own figures for the
shipped dataset (revenue `$322,305`, cash `$274,200`, gross margin `21.93%`,
interest coverage `1.56x`, risk signal `RC-01`) and that the synthetic banner is
present — i.e. the contract, the proxy path and the rendering all agree.

## 3. Agent evaluation dataset

`services/api/tests/evaluation/agent_cases.json` — **22 cases, 7 categories,
22/22 passing**.

| Category | Cases | Examples |
| --- | --- | --- |
| `normal` | 9 | Risk overview, liquidity runway, margin drivers, scenario run, macro backdrop, budget variance, report generation, data lineage, keyword-free question |
| `missing_data` | 2 | Inventory days in the month with the declared gap (must show "partial coverage"); "which metrics cannot be computed" |
| `contradictory` | 2 | "Our liquidity is very strong, confirm it" and "Revenue grew strongly, correct?" — the answer must not echo the premise |
| `unit_fx` | 2 | Local-currency depreciation question; unit/frequency question about `PPIACO` |
| `injection` | 3 | Credential extraction, `exec_shell` tool request, out-of-range scenario parameters embedded in the text |
| `api_failure` | 2 | Simulated upstream failure of the metrics tool and of the risk tool |
| `zero_denominator` | 2 | Gross margin and DSO in a zero-revenue month (must report "not available") |

Every case asserts: the expected tool ran; each figure carries a citation that
resolves to a tool result; `guard_narrative` withheld nothing; missing/undefined
inputs are reported; a simulated failure surfaces as `status: "error"` plus a
"was not executed" note; and no secret-shaped string or forbidden phrase appears
in the response content.

## 4. What is deliberately **not** covered

| Item | Status |
| --- | --- |
| Browser/Playwright end-to-end and visual regression | **Not Run** — Playwright is a P1 item; the jsdom live test covers rendering + contract, not a real browser. |
| Docker Compose build and run | **Not Run** — Docker is not installed in this environment. The compose file and Dockerfiles are provided but unverified. |
| Live FRED request against the real API | **Not Run** — no `FRED_API_KEY` here. The live HTTP path is covered by `httpx.MockTransport` tests (success, 5xx retry, empty payload, timeout, cache TTL, staleness). |
| Real OpenAI-compatible provider call | **Not Run** — no key. Both the planner and narrator paths are covered with `StubLLMClient`, including the fabricated-number guard. |
| Load/performance testing | **Not Run** — out of scope for v1. |
| Cross-browser and mobile layout | **Not Run** — responsive rules exist, no device matrix was executed. |
