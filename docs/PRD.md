# RiskControl Analyst (风险控制分析师) — Product Requirements (v1)

Status: **v1 (delivered backend, portfolio demo)** · Reporting currency: USD · Dataset: synthetic only

> **Verification note (read this first).** This PRD was written against the code that exists in this
> repository. The FastAPI service (`services/api/app/**`), the synthetic dataset (`data/synthetic/**`)
> and the React frontend (`apps/web/src/**`) were all read directly.
>
> *Status update:* the frontend described in §6 is **implemented** — seven pages under
> `apps/web/src/pages/` rendering real API responses, verified by `npm run build`, `npm run typecheck`,
> 55 Vitest tests and a live integration test against a running API (`docs/evaluation.md`). Screen
> descriptions below are therefore requirements **and** descriptions of shipped behaviour; where a
> screen is still thinner than the requirement, it says so. The API contract lives in
> [`api-contract.md`](api-contract.md) and is not duplicated here.

---

## 1. Positioning

RiskControl Analyst is a **risk-control and FP&A decision-intelligence demo** for small and
mid-sized enterprises. It closes one loop end to end:

**导入经营数据 → 对接市场指标 → 计算财务指标 → 模拟情景 → AI 解读 → 可溯源报告**

(import operating data → connect market indicators → compute financial metrics → simulate scenarios
→ AI interpretation → traceable report)

The product's differentiator is not the model, it is the **proof**: every number that reaches a
screen or a report is produced by a deterministic calculation service and travels with its unit,
period, formula and `source_ids`. The optional language model may choose which tool to call and how
to narrate the result; it may never compute a number. See
[`architecture.md`](architecture.md) for where that is enforced.

Everything shipped is synthetic. The fictional company is **Aurelia Consumer Goods Pte. Ltd.**
(`company_id: SYNTH-AURELIA-001`), a South-East Asian consumer-goods group with three funding
centres (SG/TH/VN), 24 monthly actuals (2023-01 … 2024-12), a group-level budget layer and a macro
fixture set. The disclaimer is carried in the API payloads themselves
(`synthetic: true`, `"Synthetic demo data. Not investment advice."`).

## 2. Non-goals (explicitly out of scope)

| Non-goal | Why it is excluded |
| --- | --- |
| **Not a stock-picking or trading tool.** | No securities master, no prices, no positions, no orders. There is no order-execution code path anywhere in the service. |
| **Not a generic chatbot.** | The agent has a **closed tool set of 8 tools** (`app/agent/tools.py::TOOLS`) and cannot reach data any other way. Off-topic questions still return the fixed disclaimer. |
| **No investment advice, credit rating or audit opinion.** | Stated in the report's Recommended Actions section ("Nothing in this report is a buy/sell recommendation, a credit rating or an audit opinion.") and in every `AgentAnswer.disclaimer`. |
| **Not a statutory reporting system.** | Operating cash flow, net income and free cash flow are documented *proxies* (`ebit + D&A - cash taxes - ΔNWC`), not a cash-flow statement or a tax filing. |
| **Not a real-time market terminal.** | Live FRED values are optional; by default the Market Data Adapter serves clearly-labelled fixtures. No forward-fill across frequencies. |
| **Not multi-tenant.** | No authentication, no roles, no per-user isolation in v1 (see §7 and `roadmap.md`). |
| **Not a real customer dataset.** | No real company data may be shipped in this repository; `RCA_SYNTHETIC_DATA=true` marks it as demo material. |

## 3. Personas

| Persona | What they need | What the product must never do to them |
| --- | --- | --- |
| **FP&A analyst** (primary operator) | Upload the month's close, see which ratios moved, drill to the driver, run a what-if, export the scenario table. Suspects any number they cannot recompute. | Show a ratio computed on an incomplete period without a partial-coverage flag. Show `0` where a ratio is undefined. |
| **Finance manager / controller** (risk desk) | A ranked, threshold-based view of what actually breached policy this month, with the observed value, the threshold and the rule id — plus the known gaps that are *not* measurable. | Invent a plan when no budget layer exists. Silently pass a rule whose inputs are missing. |
| **Management / board reader** (consumer of the report) | One page: performance, plan variance, market backdrop, downside case, key risks, actions — with the data classification visible. | Present fixture market values as live observations, or an AI-written number that no engine produced. |

## 4. User journeys (summary)

The step-by-step versions, with the real endpoint at each step, are in
[`user-flows.md`](user-flows.md).

| # | Journey | Trigger | Ends with |
| --- | --- | --- | --- |
| J1 | **异常发现** — catch the breach | Monthly close is imported, or the reader opens the register | `RiskRegister` with `overall_level`, `score` and RC-01…RC-14 signals ranked by severity |
| J2 | **原因分析** — decompose the cause | A high/critical signal (e.g. DSO above policy) | Metric pack + monthly series + budget variance isolating the driver (working capital vs earnings) |
| J3a | **模拟决策** — decide under uncertainty | "Can we absorb a 1.5pp rate rise?" | `ScenarioResult` (base/upside/downside + custom), tornado sensitivities, scenario CSV |
| J3b | **管理层报告** — publish | The board pack is due | Verified `ReportDocument` (markdown/HTML) + JSON verification record |

## 5. In scope vs out of scope for v1

### In scope (delivered)

* Monthly fact table ingest with validation, activation and a re-upload/seed rollback path.
* Deterministic metric pack (single month or range) over a region subset.
* Monthly series for charts, 24 months, with budget variance and MoM/YoY columns.
* Budget-variance module (group plan) with explicit "not available" when no plan is loaded.
* Rule-based risk register: 14 documented rules, severity-weighted score, data gaps surfaced.
* Macro market layer: 7 catalogued FRED series, live-or-fixture provenance, staleness flag.
* Driver-based scenario engine: 3 presets + 1 custom case, tornado sensitivity on 9 drivers, CSV export.
* Management report builder with 8 sections and pre-export verification (**8 documented checks
  V-01…V-08; 7 emitted, because V-03 is folded into V-01**).
* Agent orchestrator with a closed 8-tool set, deterministic planner, citation guard and audit log.

### Out of scope for v1 (labelled **Planned** where a roadmap item exists)

| Item | Status |
| --- | --- |
| Frontend implementation (`apps/web/src`) | **Planned (P1)** |
| Authentication, roles, multi-user isolation | **Planned (P2)** |
| PDF export of the report | **Planned (P1)** |
| Covenant scheduling / headroom modelling | **Planned (P2)** |
| Customer-level concentration analysis | **Planned (P2)** |
| Inventory ageing / obsolescence | **Planned (P2)** |
| Live macro data by default | By design: requires `FRED_API_KEY` |
| Automated end-to-end browser tests | **Planned (P1)** |

## 6. Key screens

Seven screens. Each row states what the screen **must** show; the "Existing endpoint" column is the
real endpoint it must call (all under `/api/v1`). The UI itself is **Planned (frontend not
implemented)**.

| # | Screen | Must show | Endpoint(s) it must call |
| --- | --- | --- | --- |
| 1 | **Data & provenance (数据与来源)** | Active dataset id, kind (`synthetic_seed` / `uploaded_file`), rows, months, regions, `has_budget_layer`, the declared gap (TH 2024-07 inventory), upload history with per-row validation issues, and a "restore seed" action. | `GET /meta/company`, `GET /meta/lineage`, `GET /data/uploads`, `POST /data/upload`, `POST /data/activate-seed` |
| 2 | **KPI dashboard (指标看板)** | Latest month + TTM values for the 12 report KPIs, `status` rendered as "not available — <note>" when not `ok`, partial-coverage note when source cells are missing, and the synthetic notice. | `GET /metrics?month=`, `GET /metrics/series` |
| 3 | **Market indicators (市场指标)** | Catalog with rationale, latest value + observation date, native frequency, and a **provenance badge** (`is_fixture`, `is_stale`, `stale_after_days`, `alignment_note`, `license_note`). | `GET /market/catalog`, `GET /market/series/{id}` |
| 4 | **Risk register (风险台账)** | `overall_level` + `score`, every fired signal with severity, category, `observed_value`, `threshold`, `direction`, `metric_ids`, `source_ids`, supporting values, `recommended_check`; plus the `data_gaps` list. | `GET /risk/register?month=` |
| 5 | **Scenario simulator (情景模拟)** | Driver inputs with their allowed ranges, base/upside/downside/custom comparison table, monthly cash path, `months_with_negative_cash`, `cash_runway_months` (or explicit not-applicable), the tornado chart, `model_note`, and a CSV download. | `GET /scenarios/presets`, `POST /scenarios/run`, `POST /scenarios/export` |
| 6 | **AI analyst (智能解读)** | Conclusion, key findings with inline citation ids, evidence list (label/value/unit/period), assumptions, risks, recommendations, `confidence_limits`, `missing_data`, the tool-call trace with timings, the engine label (`deterministic-planner` vs `llm:<model>`), and the disclaimer. | `POST /agent/ask`, `GET /agent/tools`, `GET /agent/audit` |
| 7 | **Report & verification (报告与校验)** | The 8 sections, every citation token rendered, the V-01…V-08 check table with `pass`/`warn`/`fail` and detail, `verification_status`, and download links for markdown/HTML. | `POST /reports/generate`, `GET /reports/{report_id}?format=` |

## 7. Fact-table field dictionary

Two sources of truth are used below: the shipped CSV header
(`data/synthetic/monthly_financials.csv`) and the upload contract in
`services/api/app/data/ingest.py` (`REQUIRED_COLUMNS`, `OPTIONAL_COLUMNS`,
`ZERO_FILL_COLUMNS`).

| Column | Type | Unit | Currency | Required on upload | Notes |
| --- | --- | --- | --- | --- | --- |
| `month` | string `YYYY-MM` | – | – | **Required** | Regex `^\d{4}-(0[1-9]\|1[0-2])$`; non-conforming values are an ingest **error**. |
| `region` | string | – | – | **Required** | SG / TH / VN in the seed. Must be unique per `month` (duplicate `(month, region)` is an ingest **error**). |
| `region_name` | string | – | – | Optional | Defaults to `region` when absent. |
| `currency` | string | – | – | **Required** | Local billing currency (SGD/THB/VND). More than one currency per region is an ingest **warning** (ambiguous FX exposure). |
| `quantity` | number | units | – | **Required** | Must be `> 0`; otherwise ingest **error**. |
| `unit_price_local` | number | local currency / unit | local | **Required** | Driver of revenue, together with `fx_rate_to_usd`. |
| `fx_rate_to_usd` | number | USD per 1 local unit | – | **Required** | Must be `> 0`; otherwise ingest **error**. |
| `revenue_usd` | number | USD | USD | **Required** | Must satisfy `quantity × unit_price_local × fx_rate_to_usd` within **1.0 USD**; outside that tolerance the engine **recomputes** revenue from the drivers and records a warning. |
| `cogs_material_usd` | number | USD | USD | **Required** | Imported materials, priced in USD in the scenario model. |
| `cogs_labor_usd` | number | USD | USD | **Required** | Local-currency cost in the scenario model. |
| `cogs_overhead_usd` | number | USD | USD | **Required** | Production overhead. |
| `opex_sales_usd` | number | USD | USD | **Required** | Operating expense, sales. Treated as **fixed** in scenario projections. |
| `opex_admin_usd` | number | USD | USD | **Required** | Operating expense, administration. |
| `opex_rd_usd` | number | USD | USD | **Required** | Operating expense, R&D. |
| `depreciation_amortization_usd` | number | USD | USD | Optional | Zero-filled when absent. Deducted to reach EBIT, so EBITDA ≠ EBIT. |
| `interest_expense_usd` | number | USD | USD | Optional | Zero-filled when absent. Drives interest coverage. |
| `cash_taxes_paid_usd` | number | USD | USD | Optional | Zero-filled when absent. Cash basis, not a tax provision. |
| `annual_interest_rate_pct` | number | percent | – | Optional | Group weighted cost of debt; used as the scenario starting rate. Not zero-filled (left NA when absent). |
| `debt_balance_usd` | number | USD | USD | Optional | Closing total debt. Not zero-filled. |
| `short_term_debt_usd` | number | USD | USD | Optional | Used in the current ratio denominator. Not zero-filled. |
| `cash_usd` | number | USD | USD | Optional | Closing cash. Not zero-filled (a zero-filled cash balance would be a fabricated number). |
| `accounts_receivable_usd` | number | USD | USD | Optional | Closing AR; DSO uses the average of opening and closing. |
| `inventory_usd` | number | USD | USD | Optional | Closing inventory; **this is the column with the declared demo gap (TH 2024-07)**. |
| `accounts_payable_usd` | number | USD | USD | Optional | Closing AP; DPO denominator side. |
| `operating_cash_flow_usd` | number | USD | USD | Optional | Shipped in the seed; the engine also derives a proxy for periods where it is used in risk rules. |
| `capex_usd` | number | USD | USD | Optional | Zero-filled when absent. Free cash flow = OCF − capex. |

**Fields the frontend must display next to every value** (they travel inside every `CitedValue`):
`metric_id`, `label`, `unit`, `period`, `basis`, `formula`, `source_ids`, `status`, `note`,
`synthetic`.

**Period conventions.** `period` is either a single month (`2024-12`) or an inclusive span
(`2024-01..2024-12`). Flows (revenue, costs) are summed over the span; stocks (cash, debt,
receivables, inventory, payables) are closing balances at the last month of the span, and the
working-capital ratios use closing balance vs. opening balance of the span (or the closing balance
alone for the first period of the dataset, with a note saying so).

**Units in the API.** `unit` is one of `USD`, `pct`, `days`, `x`, `pp`, `months`, `cells`, `score`,
`percent_points`, `raw`. Percentages are decimal fractions (`0.2193` = 21.93%) unless `unit` says
otherwise.

## 8. Abnormal and edge states

Every row below is a state the backend actually produces; the required UI behaviour is what the
frontend must implement (`api-contract.md` "Frontend notes" is the contract).

| State | What the backend really does | Required UI behaviour |
| --- | --- | --- |
| **Empty dataset / no rows in scope** | `monthly_frame()` raises `ValueError("no rows match the requested scope")`; the route maps it to **400** with `{"detail": ...}`. A month with no data in `/metrics` also returns **400**. | Show the detail string as an inline empty-state; never render an empty chart as "0". |
| **Seed data missing on disk** | Startup logs `Seed data unavailable: ... Run: python data/synthetic/generate.py --write` and the app still boots; data endpoints then fail. | Show a setup state with the exact regeneration command. |
| **Load failure / slow response** | Any unhandled exception becomes **500** `{detail: "<ExcType>: <msg>", path, hint}` — never a stack trace, key or path outside the runtime directory. FRED failures inside an otherwise successful request are downgraded to a fixture **plus** an `error` string. | Distinguish transport failure (retry) from a 400/404 business answer (do not retry). Show `error` text on the series card. |
| **Missing value (declared gap)** | TH 2024-07 `inventory_usd` is NaN. The group total excludes it and every affected metric carries `status: "ok"` with a `note` beginning `partial coverage: 1 source cell(s) missing…`. RC-13 fires with `observed_value = 1` cells. | Render the value **and** the partial-coverage note together. Never hide the note behind a tooltip only. |
| **Zero denominator** | `safe_div` returns `status: "undefined"` with a note (e.g. "interest expense is zero, ratio is undefined"); `pct_change` on a zero base likewise. `MonthlyPoint` fields become `null`. | Print "not available — <note>". V-08 exists precisely to catch an undefined metric rendered as a number. |
| **Stale market data** | Live series older than `stale_market_data_days` (**120**) get `is_stale: true`. Fixtures are never marked stale (`is_stale` forced to `false`). | Show a staleness badge with the observation date and the 120-day policy. |
| **Fixture market data** | If `FRED_API_KEY` is unset (or a live call fails), `is_fixture: true`, `source_name: "Local demo fixture"`, license note explains the values are hand-built demo values, and the report's V-07 returns **warn**. | A non-dismissable provenance badge. Never label a fixture as "live FRED". |
| **Unknown report id / unknown series** | `GET /reports/{id}` → **404** `report {id} not found (generate it first)`. An unknown market series id returns a `MarketSeries` with `error` and no value, which the route converts to **404**. | Route to a "not found" panel with a "generate report" action; do not blank the page. |
| **Oversized upload** | Over **20 MB** → **413** `file larger than 20 MB is not accepted`; an empty file → **400** `uploaded file is empty`. | Client-side pre-check on size + a clear server-error state. |
| **Upload that fails validation** | `POST /data/upload` returns the `IngestRecord` with `report.passed: false`, `missing_required`, and per-row `issues` (severity `error`/`warning`). The upload is **stored in history but not activated**. | Render the issue table (severity, message, row) and keep the previous dataset active. |
| **Uploaded dataset has no plan** | `/metrics/budget-variance` returns every variance with `status: "missing"` and the note "No budget layer is available for this dataset…". RC-10/RC-11 do not fire. | Show "not available", remove the budget charts, and explain why. |
| **Unknown field in a request body** | All request models are `extra="forbid"` → FastAPI **422**. | Surface field-level validation errors verbatim. |
| **Slow / delayed response** | No server-side timeout is imposed on calculation routes (they are in-process and deterministic); FRED calls have `FRED_TIMEOUT_SECONDS=8`, 2 retries, 0.5 s minimum interval and a 3600 s cache TTL. | Show a loading state per panel; do not block the whole page on the market panel. |

## 9. Success metrics (portfolio project)

These are **counts taken from the code**, so they can be re-verified by reading the repository, plus
targets that a reviewer can time. They deliberately avoid any claim about user growth, revenue or
model accuracy — this is a demo with synthetic data.

| # | Metric | Value / target | How it is verified |
| --- | --- | --- | --- |
| M1 | **Deterministic coverage of every displayed number** | 100 % — every number leaves the API inside a `CitedValue` (or is derived from one inside the report builder), and the report is rejected by V-02/V-04 if a figure cannot be reproduced from its citation. | `GET /reports/{id}?format=json` → `verification`; runtime evidence: V-01 "111 distinct citations, all resolved", V-02 "All cited numbers reproduced", V-04 "No uncited figures". |
| M2 | **Tested formula coverage** | **28 metric ids** in the engine metric pack, each with an explicit `formula` string; 9 monthly-series field groups; 6 budget-variance pairs (absolute + percent). | `app/finance/engine.py` metric registration block; `MetricSet.values[*].formula` in any `/metrics` response. |
| M3 | **Risk rules shipped with thresholds and severities** | **14 rules (RC-01…RC-14)**; score = Σ severity weights (`critical 10, high 6, medium 3, low 1, info 0`), capped at 100; level bands at 20/12/5. | `app/finance/risk.py`; `/risk/register` response. |
| M4 | **Pre-export verification checks** | **8 documented check ids (V-01…V-08)**; **7 items are emitted** — V-03 ("citation resolves") is folded into V-01, which checks format *and* resolution. Each item is `pass`/`warn`/`fail`, aggregated to one `verification_status`. | `app/reports/verify.py`; `GET /reports/{id}?format=json` returns 7 items. |
| M5 | **Agent evaluation cases passing** | **22 / 22** — `services/api/tests/evaluation/agent_cases.json` across seven categories, executed by `pytest -m evaluation` (`docs/evaluation.md`). | Re-run `python -m pytest tests -m evaluation -q` after any change to the planner, the tools or the guard; report the count, do not assume it. |
| M6 | **Agent containment** | 0 un-cited figures can survive: `guard_narrative` withholds any line whose numbers are not in the citation registry, and the withheld count is reported in `confidence_limits`. | `POST /agent/ask` → `confidence_limits`; `app/agent/orchestrator.py::guard_narrative`. |
| M7 | **Closed tool surface** | **8 tools**; unknown tool names are recorded as `status: "rejected"`; unknown argument keys fail Pydantic validation (`extra="forbid"`) and are rejected, not ignored. | `GET /agent/tools`; `GET /agent/audit` (`records[*].status`). |
| M8 | **Time-to-first-chart from a clean checkout** | **Target: < 10 minutes** on a machine with Python ≥ 3.10. Blocked today by the missing frontend source. | Steps: `python data/synthetic/generate.py --write` → `uvicorn app.main:app --port 8000` from `services/api` → open `/docs`. Time it; the chart itself is **Planned (P1)**. |
| M9 | **Reproducibility of the dataset** | Same seed → byte-identical files. Seed `20260101`, generator version `1.0.0`; `dataset_manifest.json` carries the SHA-256 of every generated file. | `python data/synthetic/generate.py --check` (validates identity `revenue = qty × price × fx` within 1.0 USD, positive quantity/FX, declared gaps only, budget/actuals month parity). |
| M10 | **Exception hygiene** | Every unhandled error returns a typed 500 body with no stack trace, key or out-of-runtime path; all planned business failures use 400/404/413/422. | `app/main.py` exception handler; route table in [`api-contract.md`](api-contract.md). |

## 10. What we deliberately did not build in v1

1. **No frontend source.** `apps/web/` has tooling configuration only; the seven screens in §6 are requirements, not shipped code.
2. **No authentication or authorisation.** Single process, single active dataset, no users, no roles.
3. **No database.** The fact table is CSV on disk plus an in-memory active dataset; runtime artefacts (reports, uploads, market cache, tool log) are files under `services/api/runtime/`.
4. **No PDF export.** Markdown and a self-contained HTML render exist; the HTML is produced by a deliberately minimal markdown→HTML renderer for the subset the builder emits.
5. **No covenant modelling.** Facilities, covenants and headroom are not in the data model — listed as a known data gap in every risk register.
6. **No customer-level concentration.** Only region-level and currency-level mix exists.
7. **No inventory ageing.** Only aggregate inventory value; obsolescence is a stated data gap.
8. **No forecasting ML.** Projections are driver-based and deterministic; no trained model, no time-series fitting.
9. **No second-order elasticities.** A price change does not move volume; a volume change does not change unit cost. This is stated in `model_note` on every scenario response.
10. **No new financing logic in scenarios.** Debt is held flat: no drawdowns, amortisation, equity raises or dividends.
11. **No tax-rate scenarios.** Tax accrues at a stated 22 % of positive pre-tax profit (`TAX_RATE_USED`).
12. **No cross-frequency alignment of macro data.** Series keep their native frequency; nothing is forward-filled.
13. **No Mastra (or other) orchestration framework.** The agent loop is a small in-process orchestrator with a hard cap of 5 tool calls per question.
14. **No container/hosting setup.** No Dockerfile or Compose file exists in the checkout; the documented path is two local processes.

## 11. References

* [`api-contract.md`](api-contract.md) — endpoints, response shapes, error codes.
* [`user-flows.md`](user-flows.md) — the four journeys step by step with endpoints and failure branches.
* [`architecture.md`](architecture.md) — module boundaries, data flow, determinism, v1 simplifications.
* [`roadmap.md`](roadmap.md) — P0/P1/P2 backlog, acceptance criteria, known limitations.
