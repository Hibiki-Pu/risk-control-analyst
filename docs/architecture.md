# RiskControl Analyst (风险控制分析师) — Architecture

Companion documents: [`PRD.md`](PRD.md) · [`user-flows.md`](user-flows.md) ·
[`api-contract.md`](api-contract.md) · [`roadmap.md`](roadmap.md).

**Scope note.** The backend and the data pipeline described here exist in this repository and were
read module by module. The frontend is **not implemented**: `apps/web/` contains `package.json`,
`vite.config.ts`, `index.html` and TypeScript/Tailwind configuration, but **no `src/`**. The frontend
stack is therefore documented as a *chosen stack with a proxy contract*, and its screens/app modules
are **Planned (P1)**.

---

## 1. Principles

1. **Numbers are computed, never generated.** Every displayed value originates in
   `app/finance/engine.py`, `app/finance/risk.py` or `app/finance/scenarios.py`. The language model
   has no arithmetic role at all — it selects tools and narrates returned evidence.
2. **Every number is a `CitedValue`.** `metric_id`, `label`, `value`, `unit`, `period`, `basis`,
   `formula`, `source_ids`, `status`, `note`, `synthetic`. A value that cannot carry those fields
   cannot leave the service.
3. **Undefined is a first-class answer.** `safe_div`/`pct_change` return `status: "undefined"` /
   `"missing"` with a reason instead of a number; the API contract forbids rendering those as `0`.
4. **Missing data is declared, not smoothed.** One cell is intentionally absent (TH 2024-07
   inventory); totals exclude it and every affected metric carries a partial-coverage note.
5. **Provenance is visible.** Fixture vs live macro values, synthetic vs uploaded datasets and the
   data lineage travel with the payload, not in a separate document.

## 2. Data flow

```
                        ┌──────────────────────────────────────────────┐
                        │  Synthetic generator (fixed seed 20260101)   │
                        │  app/data/synthetic.py      generator v1.0.0 │
                        └───────────────┬──────────────────────────────┘
                                        │  python data/synthetic/generate.py --write
                                        ▼
        ┌───────────────────────────────────────────────────────────────────┐
        │ data/synthetic/  monthly_financials.csv (72 rows)                  │
        │                  monthly_budget.csv   (24 rows)                   │
        │                  macro_series.csv     (7 series x 24 months)       │
        │                  company_profile.json · dataset_manifest.json      │
        │                  (+ sha256 per file; one declared NaN cell)        │
        └───────────────┬───────────────────────────────────────────────────┘
                        │ load_dataset()
                        ▼
   ┌────────────────────────────────────┐        upload (multipart)
   │ DatasetStore  app/data/store.py    │◀───────────────────────────────┐
   │  active dataset (seed | upload)    │                                │
   │  runtime/uploads/UP-*.csv          │      ┌─────────────────────────┴──────────┐
   └───────┬────────────────────────────┘      │ ingest  app/data/ingest.py         │
           │  engine()                          │  13 required / 13 optional cols    │
           ▼                                    │  month regex · qty>0 · fx>0        │
   ┌────────────────────────────────────────────┴──────────────────────────────┐
   │ FinancialEngine  app/finance/engine.py      (pandas/numpy, deterministic) │
   │  monthly_frame() · metrics() · series() · budget_variance() · lineage()   │
   │  SafeValue policy: 0-denominator and NaN never become numbers             │
   └───┬───────────────┬───────────────────┬───────────────────────┬───────────┘
       │               │                   │                       │
       ▼               ▼                   ▼                       ▼
 ┌───────────┐  ┌─────────────┐   ┌──────────────────┐   ┌───────────────────────┐
 │ RiskEngine│  │ScenarioEngine│  │MarketDataAdapter │   │ ReportBuilder         │
 │ risk.py   │  │ scenarios.py │   │ market/adapter.py│   │ reports/generator.py  │
 │ RC-01..14 │  │ 3 presets +  │   │ FRED or fixture  │   │ 8 sections + citations│
 │ score/level│ │ custom, 9    │   │ cache/timeout/   │   │            │          │
 │ data_gaps │  │ shocks       │   │ retry/throttle   │   │            ▼          │
 └─────┬─────┘  └──────┬───────┘   └────────┬─────────┘   │ reports/verify.py     │
       │               │                    │             │  V-01..V-08           │
       │               │                    │             └───────────┬───────────┘
       └───────────────┴──────────┬─────────┴─────────────────────────┘
                                  │
                     ┌────────────▼─────────────┐
                     │ AgentOrchestrator        │   closed tool set (8 tools)
                     │ agent/orchestrator.py    │   deterministic planner (default)
                     │  plan → execute → compose│   optional LLM planner/narrator
                     │  guard_narrative()       │   citation guard on every line
                     └────────────┬─────────────┘
                                  │
                     ┌────────────▼─────────────┐        ┌──────────────────────┐
                     │ FastAPI routes           │◀──────▶│ runtime/ artefacts   │
                     │ api/routes.py  /api/v1   │        │ reports/*.md|html|json│
                     │ 20 endpoints             │        │ tool_calls.jsonl      │
                     └────────────┬─────────────┘        │ market_cache/*.json   │
                                  │  JSON (CitedValue)   └──────────────────────┘
                                  ▼
                     ┌──────────────────────────┐
                     │ React + TS + Vite UI     │  dev: Vite proxies /api → :8000
                     │ Charts: ECharts          │  (PLANNED — apps/web/src not yet written)
                     │ Styling: Tailwind        │
                     └──────────────────────────┘
```

**Read the diagram as:** the only path from raw files to a number on screen runs through
`FinancialEngine`; the only path from an LLM to a number on screen runs through the citation guard.

## 3. Module boundaries

| Module | Responsibility | Must never |
| --- | --- | --- |
| `apps/web/**` (React 18 + TS + Vite 5 + Tailwind 3 + ECharts 5, `react-router-dom`) — **Planned (P1)** | Render every `CitedValue` with its unit, period and status; render provenance badges; proxy `/api` to the API origin. | Compute a financial metric locally; render `0` for `status != "ok"`; hide the synthetic notice or the fixture badge; call `api.stlouisfed.org` directly. |
| `app/main.py` | FastAPI app factory, CORS from settings, lifespan warm-up, single exception handler. | Leak a stack trace, an API key or a path outside the runtime directory (returns `{detail, path, hint}` only). |
| `app/api/routes.py` | HTTP surface: parameter validation (month regex, list bounds), status-code mapping (`ValueError → 400`), upload size guard (`413`), report file lookup (`404`). | Contain financial logic; cast a `status != "ok"` value into a number. |
| `app/core/config.py` | Settings from `RCA_*` / `FRED_*` env vars with safe defaults; risk thresholds; `stale_market_data_days = 120`; runtime dir. | Hard-code a secret; require any key for the demo path (the default provider is `deterministic`). |
| `app/schemas.py` | Pydantic contracts: `CitedValue`, `MetricSet`, `MonthlyPoint`, `PeriodSeries`, `RiskSignal`/`RiskRegister`, `ScenarioAssumptions`/`ScenarioResult`, `MarketSeries`, `Evidence`/`AgentAnswer`, `VerificationItem`/`ReportDocument`, `DataLineage`. | Allow unknown fields on request models (`extra="forbid"` everywhere it matters). |
| `app/data/synthetic.py` | Deterministic generator (seed `20260101`, 24 months, SG/TH/VN), budget layer, macro fixtures, profile/manifest, dataset validation. | Emit a number that violates `revenue = quantity × unit_price_local × fx_rate_to_usd` (tolerance 1.0 USD); hide the declared gap. |
| `app/data/store.py` | Hold exactly one active dataset (seed or one upload); activate, invalidate, expose the manifest and upload history. | Merge uploaded actuals with the seed plan; invent a budget layer for an upload (it passes an **empty** budget frame so variance reports "missing"). |
| `app/data/ingest.py` | Parse CSV/XLSX, enforce the column contract, validate and report row-level issues, recompute revenue when the identity is broken. | Coerce a bad row into a good one silently; activate a file whose report failed. |
| `app/finance/engine.py` | All period and monthly metrics; group aggregation with `min_count=1`; DSO/DIO/DPO/CCC; growth vs prior month and prior year; budget variance; lineage. | Use a zero or missing denominator; treat a partial-coverage total as complete; call the network or the LLM. |
| `app/finance/formulas.py` | `safe_div`, `pct_change`, `days_in_month(s)`, `same_month_previous_year`, `annualise`, `sum_available`. | Return a value for an undefined operation. |
| `app/finance/risk.py` | 14 threshold rules, severity ladder, severity-weighted score (cap 100), level bands, `data_gaps`, one macro-rate signal from the local DFF frame. | Make a number out of missing input for a rule: an unevaluable rule becomes a `data_gap`, never a silent pass. |
| `app/finance/scenarios.py` | Driver-based projection from the trailing-12-month run-rate by calendar month; 3 presets + custom; 9 tornado shocks; CSV flattening. | Assume the budget is the baseline; scale opex with volume; add debt, equity, dividends or M&A; model price→volume elasticity. |
| `app/market/catalog.py` | The curated 7-series macro list **with the reason each series matters**. | Accept an arbitrary series id. |
| `app/market/adapter.py` | Live FRED only when `FRED_API_KEY` is set; otherwise clearly-labelled fixtures; on-disk cache with TTL; timeout/retry/throttle; staleness flag; no cross-frequency alignment. | Present a fixture as a live observation; forward-fill a monthly series into a daily one. |
| `app/reports/generator.py` | Assemble 8 sections from engine/risk/scenario/market results, register a `Citation` for every number, render markdown + self-contained HTML, persist `.md`/`.html`/`.verification.json`. | Write a figure that is not in the citation registry; publish without running verification. |
| `app/reports/verify.py` | The mechanical pre-export checks **V-01, V-02, V-04…V-08** and `overall_status` aggregation; also the `Citation.formats()` accepted-rendering table used by the narrative guard. (The module docstring numbers "V-03 citation resolves" as a separate check, but the code emits it **inside V-01**, so a response carries 7 items, not 8.) | Pass a report whose numbers cannot be reproduced from their citations. |
| `app/agent/tools.py` | The **closed** tool set (8 tools) with `extra="forbid"` argument models; each tool returns `citations` (id → value) plus `missing_data`. | Mutate financial data; reach the dataset through any path other than the engines; accept an unknown tool or extra argument key. |
| `app/agent/orchestrator.py` | Deterministic keyword planner by default; optional LLM planner (tool choice only) and LLM narrator; hard cap `MAX_TOOL_CALLS = 5`; `guard_narrative`; audit log; fixed disclaimer. | Let the model compute a number, invent a citation or bypass the tool set; keep a line whose figures are not traceable. |
| `app/agent/llm.py` | Minimal OpenAI-compatible client (`temperature 0`, JSON mode) plus a stub client for tests; returns `None` when no real provider is configured. | Store prompts or secrets in the audit log. |
| `app/services.py` | Wire store → engine → risk → scenarios → market → reports → agent into one cached `Bundle`; invalidate on dataset switch. | Hold two active datasets at once. |
| `services/api/runtime/**` | Persisted artefacts: `reports/`, `uploads/`, `market_cache/`, `tool_calls.jsonl`. | Contain secrets or prompt text. |

## 4. Where determinism is enforced

| Mechanism | Location | Effect |
| --- | --- | --- |
| Fixed seed + generator version | `app/data/synthetic.py` (`SEED = 20260101`, `GENERATOR_VERSION = "1.0.0"`) | Same seed → byte-identical CSVs; `dataset_manifest.json` records the SHA-256 of every file. |
| `SafeValue` policy | `app/finance/formulas.py` | No fabricated number for a zero denominator, missing input or NaN. |
| Group aggregation with `min_count=1` and a `missing_cells` counter | `app/finance/engine.py` | A partial total is still a total, but it is **flagged**; the count propagates into the metric `note`. |
| Explicit `formula` strings on every metric | `app/finance/engine.py` | The report and the UI can display the arithmetic, and V-02 can re-derive the value. |
| Citation registry built while the report is assembled | `app/reports/generator.py` | A figure cannot be written without a citation id being registered with the same value. |
| V-01…V-08 | `app/reports/verify.py` | Format + resolution (V-01, which absorbs the documented "V-03"), traceability (V-02), coverage (V-04), synthetic declaration (V-05), as-of date (V-06), market freshness (V-07), zero-denominator leak (V-08). |
| `guard_narrative` | `app/agent/orchestrator.py` | Post-filter on LLM output: uncited numeric lines and untraceable figures are **withheld** and counted in `confidence_limits`. |
| Closed tool set + `extra="forbid"` | `app/agent/tools.py` | Parameter-injection and out-of-set tooling are rejected and audited (`status: "rejected"`). |
| `temperature: 0` | `app/agent/llm.py` | The optional narration step is as stable as the provider allows; the arithmetic is unaffected either way. |

**Where the LLM is allowed to act:** (a) proposing a tool plan, (b) writing a narrative over the
returned evidence. Both are optional — with no `RCA_LLM_API_KEY` the orchestrator uses
`DeterministicPlanner` and the deterministic narrator, and reports `engine: "deterministic-planner"`.

## 5. Report pipeline

```
engine.metrics(monthly, TTM, FY) ─┐
engine.budget_variance(FY)       ─┤
risk.build(month)                ─┼─► ReportBuilder.build()
scenarios.run(horizon)           ─┤     1 Executive Summary
market.get_series(x4)            ─┘     2 KPI Performance         (12 KPIs, month + TTM)
                                        3 Budget Performance      (4 pairs, actual/plan/variance/%)
                                        4 External Market Signals (value, date, frequency, provenance)
                                        5 Scenario Comparison     (3 cases + top-5 tornado)
                                        6 Key Risks               (severity-ordered signals + gaps)
                                        7 Recommended Actions     (from recommended_check)
                                        8 Assumptions & Sources   (model note, tax rate, lineage, provenance)
                                                   │
                                                   ▼
                              verify_report(markdown, registry, …)  → V-01,V-02,V-04..V-08
                                                   │
                                   overall_status() → "pass" | "warn" | "fail"
                                                   ▼
                     runtime/reports/RCA-<YYYYMM>-<hex>.{md,html,verification.json}
```

Default market series in the report: `DFF`, `PPIACO`, `DEXTHUS`, `DTWEXBGS`. The catalog carries 7
series; `DGS10`, `CPIAUCSL` and `DEXSIUS` are available through `/market/catalog` and
`/market/series/{id}`.

**Observed verification outcome.** The six committed reports all report
`verification_status: "warn"`, driven by V-07: with no FRED key configured, the market inputs are
fixtures, so V-07 returns `warn` while every other check passes. That is the honest default state of
the demo, and the UI must present it as such rather than as a failure.

**Known presentation caveat (open question, see `roadmap.md`).** The report's KPI table puts a
"Trailing 12M" column beside the latest month. For **flow** metrics that column is a 12-month total
which is meaningful. For **stock** metrics (closing cash, and the debt/coverage ratios derived from
it) the engine aggregates the same way, so the TTM column shows the *sum of the monthly closing
balances* — e.g. closing cash of 274,200 for 2024-12 versus 7,114,281 in the trailing-12M column.
The label and the aggregation disagree for stocks; this is recorded as a defect candidate rather than
documented as intended behaviour.

## 6. Runtime shape

| Aspect | v1 reality |
| --- | --- |
| Processes | One Uvicorn process for the API (default `127.0.0.1:8000`); one Vite dev server for the UI (`5173`, **Planned**). |
| State | In-process: one `Services` singleton, one active dataset, one `Bundle` cache, one in-memory upload map. On disk: CSVs, reports, market cache, tool-call log. |
| Concurrency | Not designed for it: the active dataset and the upload map are process-global, so a second worker would not see the first worker's upload. Uvicorn must run single-process. |
| Persistence across restart | Seed data and generated reports survive; the *active* dataset (an upload) and the upload history do not. Reports are re-readable by id because they are files. |
| Secrets | `FRED_API_KEY`, `RCA_LLM_API_KEY` from the environment/`.env` only; never logged, never returned. |
| CORS | Allowed origins from `RCA_CORS_ORIGINS` (default `localhost:5173`, `127.0.0.1:5173`). The Vite proxy makes CORS irrelevant in the standard dev path. |

## 7. Deliberate v1 simplifications and their trade-offs

| Simplification | Why it was chosen | What it costs |
| --- | --- | --- |
| **CSV files + in-memory frames instead of PostgreSQL** | A reviewer can clone and run with zero services; the fact table is 72 rows and the generator is the schema. No migrations, no connection string, no seed script. | No concurrent writers; an upload does not survive a restart; no SQL-level auditing; fixed scope for the demo dataset size. |
| **No Mastra (or other) orchestration layer** | The agent needs deterministic planning, a hard tool cap and a citation guard — about 200 lines of explicit code. A framework would hide the guard behind abstractions that a reviewer cannot audit quickly. | No streaming, no multi-agent hand-off, no provider abstraction beyond OpenAI-compatible chat completions. Adding a second provider means touching `llm.py`. |
| **No Docker / Compose in the checkout** | Two local processes and a Python venv is the shortest path from clone to a working `/docs`. | No reproducible one-command environment; "works on my machine" risk for reviewers on other platforms. A Compose file is a P1 item. |
| **No authentication or roles** | The product question being demonstrated is *traceability of numbers*, not access control. Adding auth would also imply a user store, which contradicts the no-database choice. | Every endpoint is open on localhost; there is no notion of "who generated this report"; the demo must never be exposed publicly. |
| **JSON + markdown/HTML instead of PDF** | The HTML render is self-contained and printable; a PDF engine would add a heavy dependency for a demo artefact. | Board readers who want an attachment-compatible PDF must print from the browser for now; PDF export is a P1 item. |
| **Deterministic keyword planner by default** | The whole demo must run with **zero keys and zero cost**, and the planner is then fully reproducible (useful for evaluation cases). | Intent coverage is keyword-based; an unusual question falls back to a general metrics + risk overview. |
| **Fixtures by default, not live macro data** | No key required, deterministic reports, no external dependency in CI — and the honesty exercise (fixtures must be labelled) is itself part of the portfolio story. | The macro panel shows 2023–2024 demo values, not today's market. A reviewer must understand `is_fixture`. |
| **One active dataset at a time** | Keeps the comparison question out of v1: there is always exactly one truth to cite. | No side-by-side "last month's upload vs this month's"; switching datasets invalidates every cached bundle. |
| **Group-level budget only** | The synthetic plan is documented as group-level; a regional split would be invented data. | Cannot answer "which region missed plan?"; the variance section is group-only. |
