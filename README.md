# RiskControl Analyst · 风险控制分析师

**A financial risk-control and FP&A decision-intelligence demo: import operating data → connect market
indicators → compute metrics deterministically → simulate scenarios → interpret with an evidence-bound AI
analyst → export a traceable management report.**

> ⚠️ **Every number in this repository is SYNTHETIC demo data.** The company ("Aurelia Consumer Goods
> Pte. Ltd.") is fictional. The macro values shipped as fixtures are hand-built demo values, not market
> observations. Nothing here is investment advice, a credit opinion or an audit opinion.

```
        ┌────────────┐   ┌──────────────┐   ┌───────────────┐   ┌──────────────┐
        │ 导入经营数据 │ → │  风险指标计算  │ → │  What-if 情景  │ → │  管理层报告   │
        │ seed / 上传 │   │ 14 条风控规则  │   │ 3 情景+敏感性  │   │ 逐条可追溯    │
        └────────────┘   └──────────────┘   └───────────────┘   └──────────────┘
```

---

## 1. The problem

SME finance teams can produce a P&L, but they cannot easily answer **"are we drifting into trouble, why,
and what happens if we do nothing?"** — and they cannot trust a chatbot to do the arithmetic:

| Pain | What this project does |
| --- | --- |
| Risk is spotted late, in a spreadsheet, after month-end | 14 documented risk rules run on every dataset and produce a scored register with observed value, threshold and a recommended check |
| Scenario work lives in undocumented spreadsheet copies | A driver-based what-if engine (base / upside / downside + a custom case) with a published model contract, monotonicity tests and a CSV export |
| AI answers cannot be audited | One orchestrator, a closed tool set, and a guard that **drops any sentence whose figures cannot be traced to a tool result** |
| Reports mix up EBITDA / EBIT / net income and hide missing data | A deterministic engine with per-metric formula, unit, period and source ids; missing inputs render as "not available", never as `0` |
| Macro context is bolted on without provenance | A Market Data Adapter that serves live FRED only when a key exists and otherwise says, loudly, that the values are fixtures |

## 2. Target users

* **FP&A analyst** — needs the numbers to reconcile and the drill-down to be honest about gaps.
* **Finance manager / controller** — needs the risk register, the budget variance and the scenario deltas.
* **Management / board reader** — needs one verified report with sources, assumptions and limits.

## 3. What it does

| Capability | Detail |
| --- | --- |
| Deterministic metric engine | 28 metric ids: P&L, cash flow, DSO/DIO/DPO, cash conversion cycle, coverage, net leverage, current ratio, MoM/YoY, budget variance |
| Risk register | 14 rules (`RC-01`…`RC-14`) with severity ladders, weighted score and explicit data gaps |
| Scenario simulator | 11 drivers (volume, price, material, labour, overhead, opex, rate Δpp, FX, DSO Δdays, capex, horizon) → month-by-month projection, three presets, tornado sensitivity, CSV export |
| Market intelligence | 7 curated FRED series with caching, retry, rate limiting, staleness flags and a live-vs-fixture provenance badge |
| SEC EDGAR | Interface **designed and deliberately not enabled** in v1: data contract, five endpoints, the SEC access policy and an explicit refusal, published at `GET /api/v1/market/edgar/status` so an unfinished integration can never look like data |
| AI analyst | Closed tool set, strict argument schemas, audited tool calls, citation-checked narrative; runs with **zero API keys** |
| Report centre | 8 sections, Markdown/HTML export, and a pre-export verification step (7 checks) that can fail the report |
| Data ingestion | CSV/XLSX upload with schema validation, identity checks and honest degradation when a plan is absent |
| Web UI | 7 pages in Simplified Chinese: Overview, P&L analysis, Risk control, Market intelligence, Scenario simulator, AI analyst, Report centre |
| Delivery gates | `scripts/check_secrets.py` privacy/secret scan (tested, exits non-zero on any finding) and a deterministic seed generator with a SHA-256 manifest |

## 4. Architecture

```
data/synthetic/generate.py (seed 20260101)
        │  monthly_financials.csv · monthly_budget.csv · macro_series.csv · manifest(sha256)
        ▼
services/api/app/data/store.py ──(upload)── ingest.py: validate → activate
        │
        ├─ finance/engine.py      deterministic metrics  → CitedValue(unit, period, formula, sources)
        ├─ finance/risk.py        14 rules              → RiskRegister(score, signals, data gaps)
        ├─ finance/scenarios.py   driver-based what-if  → ScenarioResult(monthly, summary, tornado)
        ├─ market/adapter.py      FRED ─┬─ live (key)   → MarketSeries(is_fixture, is_stale, provenance)
        │                               └─ fixtures
        ├─ reports/generator.py   8 sections + citations → ReportDocument
        │      └─ reports/verify.py  V-01…V-08 pre-export verification
        └─ agent/orchestrator.py  closed tools + guard  → AgentAnswer(evidence, tool_calls, limits)
        ▼
services/api/app/api/routes.py  →  /api/v1  →  apps/web (React + TS + Vite + Tailwind + ECharts)
```

**The LLM never computes a number.** It may choose tools and narrate evidence; every figure it states
must carry a citation that resolves to a deterministic result, or the line is withheld and reported.
See [`docs/architecture.md`](docs/architecture.md) and [`docs/agent-design.md`](docs/agent-design.md).

## 5. Quickstart

### 5.1 Backend (Python 3.10+)

```bash
git clone <your-fork-url> risk-control-analyst
cd risk-control-analyst

python -m pip install -r services/api/requirements.txt
python data/synthetic/generate.py --write      # deterministic synthetic dataset (seed 20260101)
python data/synthetic/generate.py --check      # validation: "No issues found."

cd services/api
python -m uvicorn app.main:app --reload --port 8000
# API docs   → http://127.0.0.1:8000/docs
# openapi    → http://127.0.0.1:8000/openapi.json
```

No key is required. Optional: copy `.env.example` to `.env` and set `FRED_API_KEY` to switch the market
data from labelled fixtures to live FRED observations, and `RCA_LLM_PROVIDER` / `RCA_LLM_API_KEY` to let
a model plan the analyst's tool calls.

### 5.2 Frontend (Node 18+)

```bash
cd apps/web
npm install
npm run dev          # http://127.0.0.1:5173  (proxies /api to 127.0.0.1:8000)
```

The dev server proxies `/api` to the FastAPI service, so the browser never needs CORS.

### 5.3 Docker Compose (provided, not executed in this checkout)

```bash
cp .env.example .env       # optional
docker compose up --build
# web → http://127.0.0.1:5173   api → http://127.0.0.1:8000/docs
```

> Status: the compose file, both Dockerfiles and the nginx template are written but **Not Run** — Docker
> is not installed in the environment where this project was built. See `docs/test-report.md` §3.

### 5.4 Tests

```bash
cd services/api && python -m pytest tests -q --cov=app    # 191 tests, 96% statement coverage
cd apps/web && npm run typecheck && npm test && npm run build   # 55 tests, clean build

# live integration: the UI rendering the real engine's numbers
cd services/api && python -m uvicorn app.main:app --port 8000 &
cd apps/web && VITE_API_BASE=http://127.0.0.1:8000/api/v1 npm test
```

## 6. API at a glance

```bash
curl -s "http://127.0.0.1:8000/api/v1/metrics?month=2024-12" | jq '.values.revenue'
# { "metric_id": "revenue", "label": "Revenue", "value": 322304.71, "unit": "USD",
#   "period": "2024-12", "formula": "sum(revenue_usd)",
#   "source_ids": ["actual:monthly_financials@2024-12"], "status": "ok", "synthetic": true }

curl -s "http://127.0.0.1:8000/api/v1/risk/register" | jq '{level:.overall_level, score, signals:(.signals|length)}'
# { "level": "critical", "score": 59.0, "signals": 12 }

curl -s -X POST "http://127.0.0.1:8000/api/v1/agent/ask" \
     -H "Content-Type: application/json" \
     -d '{"question":"我们的风险和现金状况如何？","month":"2024-12"}' | jq '.key_findings[0:2]'

curl -s "http://127.0.0.1:8000/api/v1/market/edgar/status" | jq '{implemented, available, reason}'
# { "implemented": false, "available": false, "reason": "The SEC EDGAR connector is designed but not implemented in v1. …" }
```

Full contract: [`docs/api-contract.md`](docs/api-contract.md) · real captured responses:
[`docs/samples/`](docs/samples/).

## 7. Data sources and the synthetic-data declaration

| Source | What is shipped | Honest label |
| --- | --- | --- |
| Synthetic company dataset | 24 months (2023-01…2024-12) × 3 regions (SG/TH/VN), seed `20260101`, SHA-256 manifest | `synthetic: true` on every response; a one declared missing cell (TH 2024-07 inventory) is used to demonstrate partial-coverage handling |
| Macro market data | 7 FRED series ids with hand-built fixture values | `is_fixture: true`, `source_name: "Local demo fixture"`, source URL shown, "NOT live" stated in the UI, the report and the API |
| Live FRED | Only when `FRED_API_KEY` is set | `is_fixture: false` + `is_stale` after 120 days without a fresh observation |

`docs/data-dictionary.md` documents every column, unit, currency and the upload contract;
`docs/financial-methodology.md` documents every formula, the period/days convention, the stock-vs-flow
rule and the missing-data policy.

## 8. Quality evidence (executed, not projected)

| Check | Result |
| --- | --- |
| `pytest` | **225 tests passed**, 96% statement coverage (`2925` statements, `113` missed) |
| `vitest` | **57 tests passed** across 7 files, including a sweep of all seven routes against a running API |
| `tsc --noEmit` | clean |
| `vite build` | 608 modules, 796.96 kB JS (gzip 265.75 kB), 19.42 kB CSS |
| Agent evaluation | **22/22 cases** across `normal`, `missing_data`, `contradictory`, `zero_denominator`, `unit_fx`, `injection`, `api_failure` |
| Privacy & secret scan | `python scripts/check_secrets.py` → `Result: clean` over 121 tracked files (the gate has 25 tests of its own) |
| Pre-export verification | V-01 111/111 citations resolved · V-02 every cited number reproduced · V-04 no uncited figure · V-05 synthetic declared · V-06 as-of stated · V-07 **warn** (fixture market data, by design without a key) · V-08 no undefined metric shown as a value |
| End-to-end | `docs/samples/report-sample.md` and `report-sample.html` are real outputs of the running service |

Details, including what is **Not Run** and why: [`docs/evaluation.md`](docs/evaluation.md),
[`docs/test-report.md`](docs/test-report.md).

### Demo walk-through (in place of screenshots)

No browser capture was possible in the build environment, so the demo is evidenced with real artefacts
rather than images:

* [`docs/samples/ui-render-snapshot.md`](docs/samples/ui-render-snapshot.md) — **the text all seven
  routes actually rendered from the live API** (Overview `$322,305`, risk register `RC-01`…`RC-14`,
  market fixtures with provenance, presets, analyst page, report centre), captured by
  `app.live.test.tsx` with `RCA_WRITE_SNAPSHOT=1`.
* [`docs/samples/report-sample.html`](docs/samples/report-sample.html) — the rendered management report
  (open it in a browser; it is the same HTML the Report Centre downloads).
* [`docs/samples/metrics-2024-12.json`](docs/samples/metrics-2024-12.json),
  [`docs/samples/risk-register.json`](docs/samples/risk-register.json),
  [`docs/samples/agent-answer.json`](docs/samples/agent-answer.json) — captured API responses.

## 9. Repository layout

```
risk-control-analyst/
├── apps/web/                   React + TypeScript + Vite + Tailwind + ECharts (7 pages, 57 tests)
├── services/api/               FastAPI + Pydantic + pandas (engine, risk, scenarios, market, reports, agent)
│   └── tests/                  225 pytest tests + tests/evaluation/agent_cases.json
├── data/synthetic/             generator + shipped synthetic CSV/JSON + SHA-256 manifest
├── scripts/check_secrets.py    privacy & secret gate (tested, CI-ready exit code)
├── docs/                       PRD, user flows, architecture, methodology, data dictionary,
│                               risk rules, market sources, agent design, evaluation, test report,
│                               samples/ (report, API responses, UI render snapshot)
├── docker-compose.yml          api + web (unverified: Docker not available here)
├── .env.example                every setting, all values empty
└── README.md
```

## 10. Limits (read this before judging the numbers)

* **Synthetic only.** The dataset is fictional and deliberately engineered to contain a deterioration;
  it is not a sample of real company performance.
* **Scenario model is linear and stated.** No demand elasticity, no ML, fixed opex within the horizon,
  debt held flat with no new financing; the full contract is in `MODEL_NOTE` and in every response.
* **Macro data is fixtures by default.** Without a FRED key the "market intelligence" page is a
  demonstration of provenance handling, not of live markets.
* **SEC EDGAR is designed, not implemented.** The interface, endpoints and access policy ship, and the
  connector refuses to fetch; no filing data is read in v1.
* **Group-level plan only.** There is no regional budget split, so regional budget variance is not
  available.
* **Not modelled:** customer concentration, covenant headroom, inventory ageing, tax computation,
  lease/pension accounting, multi-currency cash pooling. Each of these is listed as a data gap in the
  risk register.
* **LLM mode is optional and untested against a live provider** in this checkout; the deterministic
  planner is the tested default and the product is fully functional without any key.

## 11. Roadmap

**P0 — delivered**: synthetic data + validation, metric engine, risk register, scenario engine, market
adapter, EDGAR interface design, report builder + verification, agent with guard, REST API, seven-page
web UI, privacy scan gate, 282 tests (225 backend + 57 frontend).

**P1**: Playwright end-to-end + screenshots · PDF export · docker compose verification in CI ·
code-splitting to cut the 797 kB JS bundle · upload dry-run preview · regional budget layer.

**P2**: authentication and roles · PostgreSQL instead of CSV · covenant scheduling · customer
concentration · inventory ageing · more scenario drivers (working-capital reactions, FX hedging) ·
Mastra-style orchestration if the tool set grows.

Full backlog with acceptance criteria: [`docs/roadmap.md`](docs/roadmap.md).

## 12. Documentation index

| Document | Contents |
| --- | --- |
| [`docs/PRD.md`](docs/PRD.md) | Positioning, non-goals, personas, journeys, fields, edge states, success metrics |
| [`docs/user-flows.md`](docs/user-flows.md) | Step-by-step journeys with the endpoint behind each step and the failure branches |
| [`docs/architecture.md`](docs/architecture.md) | Data flow, module boundaries ("must never do"), where determinism is enforced, trade-offs |
| [`docs/api-contract.md`](docs/api-contract.md) | Every endpoint, request and response field, error behaviour |
| [`docs/financial-methodology.md`](docs/financial-methodology.md) | Formulas, units, period conventions, EBITDA/EBIT/net income, missing-data policy |
| [`docs/data-dictionary.md`](docs/data-dictionary.md) | Column-by-column contract, declared gap, upload rules, generated driver paths |
| [`docs/risk-rules.md`](docs/risk-rules.md) | `RC-01`…`RC-14`, thresholds, scoring, declared non-detection |
| [`docs/market-data-sources.md`](docs/market-data-sources.md) | FRED series, live vs fixture rules, cache/retry/rate limit, staleness |
| [`docs/agent-design.md`](docs/agent-design.md) | Tool set, guardrails, two modes, answer shape, out of scope |
| [`docs/evaluation.md`](docs/evaluation.md) | Test inventory, coverage, 22 evaluation cases, what is not covered |
| [`docs/test-report.md`](docs/test-report.md) | Acceptance checklist, executed commands, Not Run list, defect log, hygiene scan |
| [`docs/roadmap.md`](docs/roadmap.md) | P0/P1/P2 backlog, limitations, risks, open questions |

## 13. License

MIT — see [`LICENSE`](LICENSE). The licence notice restates that all shipped data is fictional.
