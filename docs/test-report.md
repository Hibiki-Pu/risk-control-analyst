# Test report

Executed on Windows, Python 3.10.2, Node 24.11.1, pytest 9.0.1, Vitest 2.x.
Every row marked **Pass** was executed in this checkout; anything not executed is
marked **Not Run** and says why. Nothing is marked Pass on the strength of a code
reading.

## 1. Acceptance checklist (from the project brief)

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | A user can start the project from zero and load the demo data | **Pass** | `python data/synthetic/generate.py --write` → 72 fact rows; `uvicorn app.main:app` → `/api/v1/health` `status=ok`; `npm run build` → `built in 4.75s` |
| 2 | Upload a CSV/Excel or use the seed data and see metrics and charts | **Pass** | `POST /api/v1/data/upload` activates a validated file (`test_api.py::test_upload_validates_then_activates_and_can_be_reverted`); `/api/v1/metrics`, `/api/v1/metrics/series` feed the charts; `docs/samples/metrics-2024-12.json` is a real response |
| 3 | At least one scenario with formulas and tests where changing a parameter really changes the result | **Pass** | `test_scenarios.py` (22 tests): base case reproduces the trailing twelve months, price +5% lifts EBIT, material +8% cuts margin, DSO +20 days cuts OCF, capex changes cash but not EBIT, tornado ranking |
| 4 | Numbers in the AI report match the calculation tools and carry sources, assumptions and period | **Pass** | `report-sample.verification.json`: V-01 111/111 citations resolved, V-02 all cited numbers reproduced, V-04 no uncited figures, V-05/V-06/V-08 pass (V-07 warns: fixture market data) |
| 5 | Offline, missing data, wrong currency and zero denominators must not produce fake conclusions | **Pass** | `test_market.py` (fixture fallback + provenance), `test_engine.py` (zero denominator → `undefined`, missing → `missing`, partial-coverage note), `test_api.py` (no-plan upload → `status: "missing"`), evaluation cases EV-10/11/21/22 |
| 6 | README contains architecture, screenshots, quickstart, synthetic declaration and executed tests | **Pass (screenshots excepted)** | `README.md` covers architecture, quickstart, the synthetic declaration and the executed test results; it points to a real generated report (`docs/samples/report-sample.html`) instead of a screenshot, because no browser capture was possible here |
| 7 | No keys, private data or fabricated test results in the repository | **Pass** | Secret scan below; `.env.example` contains empty values only; all shipped data is generated from a fixed seed |

## 2. Commands executed (verbatim results)

| Command | Result |
| --- | --- |
| `python data/synthetic/generate.py --write` | `Generated 72 fact rows across 24 months (2023-01..2024-12)`; SHA-256 written for 4 files |
| `python data/synthetic/generate.py --check` | `No issues found.` |
| `python -m pytest tests -q --cov=app` | 191 collected, all passed, exit code 0, coverage 96% |
| `python -m pytest tests -m evaluation -q` | 24 passed |
| `npm run typecheck` (apps/web) | clean (`tsc --noEmit` on both tsconfigs) |
| `npm test` (apps/web) | 6 files, 55 tests, all passed |
| `npm run build` (apps/web) | 608 modules; `index-*.js` 797.40 kB (gzip 265.92 kB); `index-*.css` 19.49 kB (gzip 4.40 kB); built in 4.75s |
| `python -m uvicorn app.main:app --port 8000` + `curl` | `/health` ok; `/metrics?month=2024-12` revenue 322,304.71 USD, gross margin 0.219339, EBIT 14,290.68, cash 274,200.03, coverage 1.5618x, DSO 69.4168 days; `/risk/register` level `critical`, score 59.0, 12 signals, 3 data gaps; `/market/series/DFF` 4.83 on 2024-12-01 (`is_fixture=true`); `POST /scenarios/run` base/upside/downside/custom EBIT 216,098 / 367,821 / −27,152 / 290,227; `POST /agent/ask` 21 findings, 33 evidence items, tools `get_risk_signals,get_financial_metrics`; `POST /reports/generate` → `RCA-202412-9b41c8`, verification `warn` |
| `VITE_API_BASE=http://127.0.0.1:8000/api/v1 npx vitest run src/pages/Overview.live.test.tsx` | 2 passed — the browser bundle renders the live engine's numbers |

## 3. Not Run

| Item | Reason |
| --- | --- |
| `docker compose up` | Docker is not installed in this environment; the compose file and Dockerfiles are provided as unverified artefacts. |
| Playwright end-to-end / screenshots | Not installed; the jsdom live test substitutes for the rendering check only. |
| Live FRED call | No `FRED_API_KEY`; the live path is exercised with `httpx.MockTransport` (200, 503 + retry, empty payload, connection error) instead. |
| Live LLM provider call | No key; planner and narrator are exercised with `StubLLMClient`, including a deliberately hallucinated figure. |
| Load test, accessibility audit, mobile device matrix | Out of scope for v1. |

## 4. Defects found and fixed during this build (honest log)

| # | Defect | Fix |
| --- | --- | --- |
| 1 | Stock metrics (cash, debt) were summed over a multi-month period, producing a meaningless 7.1M "cash" for FY2024 | `metrics()` now takes closing balances for stock items and says "point-in-time, not summed" in the formula; regression test added |
| 2 | The trailing-12M column in the report could not be traced to a citation, so `V-02` failed | The TTM metric citation is now emitted next to the value |
| 3 | Risk narratives quoted derived figures (margin levels, cash balances, burn rate) that had no citation | `RiskSignal.supporting` carries those values and the report cites each one |
| 4 | A risk rule emitted `info`-level noise for healthy metrics | Rules now emit nothing unless a real threshold is breached |
| 5 | The budget section compared against a plan that did not exist for uploaded datasets | The section states "Plan comparison is not available" and the API returns `status: "missing"` |
| 6 | `V-03` was documented but never emitted | The docstring now states that V-01 also covers citation resolution; seven checks are emitted |
| 7 | A flaky market test depended on sub-second wall-clock timing | The TTL test now ages the cache file explicitly |

## 5. Repository hygiene

* `.gitignore` excludes `.env`, `node_modules`, `dist`, `runtime/`, caches and coverage output.
* Secret scan: `git grep -nIE "(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY)"` → no matches; `.env.example` values are empty.
* No real company, customer or employee data exists anywhere in the repository: the dataset is generated from seed `20260101` and every response carries `synthetic: true`.
* Reports and tool-call logs are written to `services/api/runtime/`, which is ignored by git; the copies under `docs/samples/` are intentional evidence and contain only synthetic figures.
