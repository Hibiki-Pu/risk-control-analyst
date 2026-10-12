# RiskControl Analyst (风险控制分析师) — Roadmap, limitations and risks

Companion documents: [`PRD.md`](PRD.md) · [`user-flows.md`](user-flows.md) ·
[`architecture.md`](architecture.md) · [`api-contract.md`](api-contract.md).

**Status vocabulary.** **P0 = delivered** (verifiable in this repository today) · **P1 = next**
(unblocks review or usability) · **P2 = later**. Every not-yet-built item is labelled
**Planned (P1/P2)**. Acceptance criteria are written so that a reviewer can check them against a
command or a response, not against an opinion.

---

## 1. P0 — delivered

| # | Item | Evidence in the repository | Acceptance criterion (met) |
| --- | --- | --- | --- |
| P0-1 | Deterministic synthetic dataset | `app/data/synthetic.py`, `data/synthetic/*.csv`, `dataset_manifest.json` | 24 months (2023-01…2024-12) × 3 regions = **72 fact rows**, 24 budget rows, 168 macro rows; seed `20260101`, generator `1.0.0`; manifest carries the SHA-256 of all four files. |
| P0-2 | One declared data gap, honestly surfaced | `DECLARED_GAPS` (TH `2024-07` `inventory_usd`) | The affected metric keeps its value **and** carries a `partial coverage` note; RC-13 fires with `observed_value = 1` cells; `validate_dataset` fails on any *undeclared* null. |
| P0-3 | Validated ingest with activation and rollback | `app/data/ingest.py`, `app/data/store.py` | 13 required columns enforced; month regex, `quantity > 0`, `fx_rate_to_usd > 0`, revenue identity within 1.0 USD, unique `(month, region)`; failure ⇒ `activated: false` and the previous dataset stays live; `POST /data/activate-seed` restores the seed. |
| P0-4 | Deterministic metric pack and monthly series | `app/finance/engine.py` | **28 metric ids** with `formula`, `unit`, `status`, `source_ids`; a 24-point series; zero-denominator ⇒ `status: "undefined"` with a note, never `0`. |
| P0-5 | Budget-variance module with an honest no-plan path | `engine.budget_variance`, `POST`-free `/metrics/budget-variance` | With the seed: 6 metrics × (absolute + percent). With an upload: every value `status: "missing"` and the note "No budget layer is available for this dataset…". |
| P0-6 | Rule-based risk register | `app/finance/risk.py` | **14 rules (RC-01…RC-14)** with threshold, severity ladder, `recommended_check`, `metric_ids`, `source_ids`; score = Σ severity weights capped at 100; level bands 20/12/5; unevaluable rules reported in `data_gaps`. |
| P0-7 | Market adapter with fixture honesty | `app/market/adapter.py`, `catalog.py` | 7 catalogued series; live only when `FRED_API_KEY` is set; cache TTL 3600 s, timeout 8 s, 2 retries, 0.5 s throttle; `is_fixture`, `is_stale` (120-day policy), `alignment_note`, `license_note` on every response; failure degrades to a fixture **with** an `error` string. |
| P0-8 | Driver-based scenario engine | `app/finance/scenarios.py` | 3 presets + custom; **9 tornado shocks**; `model_note` states every model limit; CSV export with `scenario_id` first. |
| P0-9 | Management report with pre-export verification | `app/reports/generator.py`, `verify.py` | 8 sections; **V-01…V-08**; every figure carries a citation token; `.md`, `.html` and `.verification.json` persisted per report. |
| P0-10 | Agent with a closed tool set and a citation guard | `app/agent/tools.py`, `orchestrator.py`, `llm.py` | 8 tools, `extra="forbid"` arguments, `MAX_TOOL_CALLS = 5`; untraceable narrative lines withheld and counted; audit log of arguments/timings only; runs with zero keys on the deterministic planner. |
| P0-11 | Exception hygiene and contract-level errors | `app/main.py`, `app/api/routes.py` | 400 (no data), 404 (unknown report/series), 413 (> 20 MB), 422 (schema), 500 (typed message, no stack trace/key/path). **20 endpoints** under `/api/v1`. |
| P0-12 | Written API contract | [`api-contract.md`](api-contract.md) | Every endpoint, response shape and error code in one place; the frontend notes define the rendering rules (`status != "ok"` ⇒ "not available", `is_fixture` must be visible). |

**Not P0 (do not cite as delivered):** the frontend, tests, containers and PDF export — see §4 and
the open questions.

---

## 2. P1 — next

| # | Item | Why now | Acceptance criteria |
| --- | --- | --- | --- |
| P1-1 | **Implement the frontend** (`apps/web/src`) — **Delivered** | Seven pages render live API data in Simplified Chinese; `npm run build` and `npm run typecheck` pass, 55 Vitest tests pass, and the live integration test proves the engine's figures reach the screen. Remaining: a browser-level (Playwright) layer and screenshots. | Follow-up acceptance: `prefers-color-scheme` dark theme checked on a device matrix; bundle split below 500 kB per chunk (currently 797 kB / 266 kB gzip). |
| P1-2 | **Automated test suite** (`services/api/tests`) — **Delivered** | 191 pytest tests at 96% statement coverage plus 55 Vitest tests; every metric id, risk rule and verification check is regression-guarded, and the 22-case agent evaluation set is committed and passing. See [`evaluation.md`](evaluation.md). | Remaining: raise `agent/llm.py` coverage from 79% (the live HTTP path needs a real provider). |
| P1-3 | **Fix or re-label the trailing-12M aggregation of stock metrics** — **Delivered** | The engine now takes closing balances for `cash`, `debt` and `short_term_debt` over any period and labels the formula "point-in-time, not summed"; a regression test (`test_stock_metrics_use_the_closing_balance_not_the_sum`) pins it. | Follow-up: the UI labels the TTM column "Trailing 12M (closing balances for stock metrics)". |
| P1-4 | **Upload dry-run endpoint** — **Planned (P1)** | `POST /data/upload` activates on success and returns errors only afterwards; the analyst cannot pre-flight a file, and there is no "deactivate without re-uploading" path. | A documented `validate_only` path (or `POST /data/validate`) returns the same `IngestReport` with **no** activation and no write to the active dataset; `POST /data/upload` behaviour is unchanged; the OpenAPI schema documents both. |
| P1-5 | **PDF export of the report** — **Planned (P1)** | Board readers want an attachment, not a browser print dialog. | `GET /reports/{id}?format=pdf` returns a PDF whose content matches the HTML rendering and whose verification block is present; the verification status is visible on the PDF face, including a `warn` from V-07. |
| P1-6 | **Docker Compose (API + web)** — **Written, Not Run** | `docker-compose.yml`, `services/api/Dockerfile`, `apps/web/Dockerfile` and the nginx proxy template exist; Docker is not installed in the build environment, so the stack has never been started. | `docker compose up` starts both services from a clean clone; the web container serves the built UI on 5173 and proxies `/api` to the API container; the seed dataset is present without a manual generation step; health check on `/api/v1/health`. |
| P1-7 | **Playwright e2e over the main path** — **Planned (P1)** | The risky regressions are cross-layer: a number losing its citation, a `missing` status rendering as `0`, a fixture badge disappearing. | One spec walks upload → register → drill-down → scenario → report → verification on the seed data; asserts the V-07 `warn` badge is visible and that no `status != "ok"` metric is rendered as a digit. |
| P1-8 | **`FRED_API_KEY` smoke path in CI (manual or nightly)** | The live branch of the adapter (cache, retry, throttle, `is_fixture: false`) is currently only exercised by hand. | A run with a key configured produces `is_fixture: false`, `is_stale` reflecting the 120-day policy, a populated `market_cache/*.json`, and V-07 `pass`; without a key the same test asserts the fixture path and `warn`. |

---

## 3. P2 — later

| # | Item | Acceptance criteria |
| --- | --- | --- |
| P2-1 | **SEC EDGAR connector implementation** — **Interface designed, deliberately not implemented** | `app/market/edgar.py` ships the contract (`EdgarFiling`, `EdgarFact`), the five designed endpoints, the access policy and an explicit refusal (`EdgarNotEnabled`); `GET /api/v1/market/edgar/status` publishes it and nine tests pin the design and the refusal. Acceptance for implementation: `company_tickers.json` drives CIK resolution (never guessed); `companyconcept` is preferred over `companyfacts`; a rate limit below 10 req/s and a cached User-Agent are enforced; an absent XBRL tag is reported `missing`, never `0`; every fact carries accession number and filing date so the report can cite the filing. |
| P2-2 | **Authentication + roles** (viewer / analyst / admin) — **Planned (P2)** | Login required for write endpoints; the report records who generated it; existing demo endpoints stay reachable for a read-only visitor or are explicitly documented as protected. |
| P2-3 | **Persistent store (PostgreSQL) behind the same engine API** — **Planned (P2)** | Uploads and the active dataset survive a restart; `FinancialEngine` takes a frame and is unchanged; a migration/repository test proves the seed and an upload produce identical metric packs to today. |
| P2-4 | **Covenant scheduling and headroom** — **Planned (P2)** | Facility terms (amount, margin, covenants, test dates) are data; the register gains a covenant rule with an explicit threshold; the "covenant headroom is not modelled" data gap disappears from the register, and nothing is fabricated when terms are absent. |
| P2-5 | **Customer-level concentration** — **Planned (P2)** | A customer dimension joins the fact table; a concentration rule (largest customer share, top-5 share) fires with an observed value and a threshold; the corresponding data gap disappears. |
| P2-6 | **Inventory ageing and obsolescence** — **Planned (P2)** | Inventory carries an age bucket; DIO is complemented by a slow-moving ratio; RC-13's partial-coverage story is unaffected for datasets that ship no ageing. |
| P2-7 | **Regional budget layer** — **Planned (P2)** | The budget table gains a `region` key; `/metrics/budget-variance` accepts `regions[]`; group totals still tie exactly to the sum of regional rows. |
| P2-8 | **Additional scenario drivers** (working-capital day policies as first-class scenarios, capex programmes, dividend policy) — **Planned (P2)** | New drivers appear in `SENSITIVITY_SHOCKS` and in the tornado; `model_note` is updated in the same change; the excluded-by-design list in the module docstring shrinks by exactly the features added. |
| P2-9 | **Multi-dataset comparison** (this month's upload vs the seed, region vs group) — **Planned (P2)** | Two datasets can be held at once; citations carry the dataset id; the report states which dataset each section used. |

---

## 4. Known limitations

1. **One dataset, one shape.** The only shipped data is the synthetic Aurelia group: 24 months,
   3 regions, group-level plan, no customer, product, facility or headcount dimensions. Every rule
   and metric was tuned against this one series, so the register firing 12 signals in `2024-12` says
   nothing about general sensitivity.
2. **No covenant scheduling.** Facility agreements are not modelled; the register states this as a
   permanent data gap. RC-01/RC-02 talk about "policy" thresholds, not contractual covenants.
3. **No customer-level concentration.** RC-12 measures *currency* concentration only. A single
   customer at 40 % of revenue would be invisible.
4. **No inventory ageing.** Only aggregate inventory value exists, so obsolescence risk is
   unmeasurable — stated in `data_gaps` on every register.
5. **Fixtures, not live macro data, by default.** Without `FRED_API_KEY` every market value is a
   hand-built demo value for 2023–2024, and V-07 keeps the report at `warn`. A reviewer must not
   treat `4.83 %` as today's policy rate.
6. **No PDF export.** Markdown + self-contained HTML only.
7. **No Playwright e2e.** Nothing verifies the cross-layer rendering rules automatically; they are
   only stated in [`api-contract.md`](api-contract.md).
8. **No browser-level end-to-end test.** 191 pytest tests, 55 Vitest tests (including a jsdom live
   integration test against a running API) and the 22-case agent evaluation suite exist, but no
   Playwright spec covers a real browser, and no screenshots were captured in the build environment.
9. **`pct` vs `percent_points` duality.** Decimal-fraction percentages (`pct`) and already-scaled
   percentage points (`percent_points`, used for macro rates) coexist; `verify.py::Citation.formats`
   has a dedicated branch per unit and the distinction is a documented part of the formatting
   contract. A frontend that assumes one convention will mis-render the other.
10. **Single-process state.** The active dataset, the upload map and the bundle cache are
    process-global: run one Uvicorn worker. An upload does not survive a restart.
11. **History ends at `2024-12`.** All 24 months are synthetic and in the past; a live macro fetch
    today would land years after the dataset window, which is exactly why the fixture path is the
    default and why V-07 warns rather than fails.
12. **Documentation gaps inside the repo.** `engine.py` refers to
    `docs/financial-methodology.md`; `generator.py` refers to `docs/financial-methodology.md` and
    `docs/risk-rules.md`; `ingest.py` refers to `docs/data-dictionary.md`; and the shipped
    `monthly_budget.csv` note iterates the same reference. **None of those three files exist in this
    checkout.** Today the authoritative sources are this `docs/` set plus
    [`api-contract.md`](api-contract.md).

## 5. Honest risks

| # | Risk | Likelihood | Impact | Mitigation now | Next action |
| --- | --- | --- | --- | --- | --- |
| R1 | **Single-dataset overfitting** — thresholds look precise because they were tuned on one synthetic series. | High | Medium | Thresholds are named constants in `Thresholds` / `Settings` (`RCA_RISK_*`), not magic numbers inside rules. | P1-2: rule tests with synthetic fixtures at the boundary values (just below / just above each threshold). |
| R2 | **Fixture mistaken for live data** by a casual reader. | Medium | High | `is_fixture`, `source_name: "Local demo fixture"`, license note, report provenance column, V-07 `warn`, agent `confidence_limits` line. | P1-1: a permanent, non-dismissable provenance badge on the market screen. |
| R3 | **An LLM narrator slips an untraceable figure past a reader** who reads only the conclusion. | Low | High | `guard_narrative` withholds untraceable lines; the withheld count is surfaced in `confidence_limits`; the conclusion is composed deterministically unless narration succeeds. | P1-2 — delivered: `test_agent.py` drives a stub model that emits a wrong number and asserts the line is withheld. |
| R4 | **`status: "missing"` rendered as `0`** by a future frontend. | Medium | High | Explicit contract rule; V-08 catches the equivalent leak in reports; the API never substitutes a number. | P1-7: an e2e assertion that no non-`ok` metric renders as a digit. |
| R5 | **Scenario results read as a forecast** rather than a driver-based what-if. | Medium | Medium | `model_note` on every response, in the report, and in the agent's assumptions; the excluded-by-design list is in the module docstring. | P1-1: `model_note` pinned next to the comparison table, not behind a tooltip. |
| R6 | **Stock-metric aggregation** (TTM sums of closing balances) misread as a balance. | High | Medium | Fixed: the engine takes closing balances for stock items and the formula text says "point-in-time, not summed". | P1-3 — delivered. |
| R7 | **Upload replaces the active dataset with no undo beyond re-seeding**, and the upload history is in-memory. | Medium | Medium | Validation must pass before activation; `POST /data/activate-seed` restores the seed; the failed upload is still recorded in history. | P1-4 (dry-run) and P2-3 (persistence). |
| R8 | **No auth ⇒ the demo must never be exposed publicly.** | Medium | High | Binds `127.0.0.1` by default; CORS restricted to the two local dev origins; the shipped dataset is synthetic so a leak exposes nothing real. | P2-2; keep the binding and CORS defaults in any deployment docs. |
| R9 | **Recomputation drift**: the report claims figures can be regenerated with the generator + tests. | Low | Medium | The generator is deterministic, `dataset_manifest.json` pins SHA-256 per file, and `services/api/tests` (191 tests) now exists and is executed, so the claim in the report's Assumptions & Sources section is verifiable. | Keep `docs/test-report.md` current after any change; `test_shipped_seed_files_match_a_fresh_generation` fails if a CSV is hand-edited. |
| R10 | **Stale-data policy is data-age based (120 days) and never fires for fixtures**, so a genuinely frozen live cache could look fresh. | Low | Medium | The cache TTL (3600 s) bounds how long a live value is reused, and `fetched_at` is always returned. | P1-8: assert `fetched_at` freshness in the live smoke path. |

## 6. Open questions (documentation could not be verified against the code)

1. **~~Test count and agent-evaluation pass rate (PRD M5).~~ Resolved.** `services/api/tests` now holds
   191 pytest tests (96% statement coverage) and a 22-case agent evaluation set, all passing; see
   [`evaluation.md`](evaluation.md). Open follow-up: coverage of the live HTTP paths (`agent/llm.py`,
   real FRED) still depends on keys that were unavailable here.
2. **~~Frontend screens, routes and component names.~~ Resolved.** `apps/web/src` is implemented
   (seven pages, six test files) and matches the PRD screen list; the remaining question is only
   aesthetic (device matrix, dark-mode review).
3. **~~Missing referenced docs.~~ Resolved.** `docs/financial-methodology.md`,
   `docs/risk-rules.md` and `docs/data-dictionary.md` now exist and are the authoritative
   human-readable counterparts of the formulas, the rules and the fact-table contract.
4. **~~Stock-metric TTM semantics (P1-3).~~ Resolved.** `metrics()` takes closing balances for stock
   items and states "point-in-time, not summed" in the formula; a regression test pins it.
5. **~~No Docker / Compose file exists.~~ Resolved (written, not executed).** `docker-compose.yml`,
   `services/api/Dockerfile`, `apps/web/Dockerfile` and `apps/web/nginx.conf.template` are in the
   repository; Docker was unavailable in the build environment, so the stack is **Not Run**
   (`docs/test-report.md` §3).
6. **The "Mastra orchestration layer"** is named in the project brief as a deliberate v1 omission.
   No Mastra dependency or reference exists anywhere in the code, so this is documented as a design
   decision (no framework; a 200-line in-process orchestrator) rather than a removal. Question:
   confirm the intended wording for the portfolio narrative.
7. **`pct` vs `percent_points`:** the macro rate is rendered as `4.83%` with `unit: "percent_points"`
   while financial percentages use `unit: "pct"` as decimal fractions. `verify.py` handles both, and
   `docs/financial-methodology.md` §1 states the contract, but the distinction remains a trap for a
   new consumer (mobile, PDF export). Candidate P2: normalise to `pct` everywhere and keep the
   display scaling in one place.
