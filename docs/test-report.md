# Test report

Executed on Windows, Python 3.10.2, Node 24.11.1, pytest 9.0.1, Vitest 2.x.
Every row marked **Pass** was executed in this checkout; anything not executed is
marked **Not Run** and says why. Nothing is marked Pass on the strength of a code
reading.

## 1. Acceptance checklist (from the project brief)

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | A user can start the project from zero and load the demo data | **Pass** | `python data/synthetic/generate.py --write` produced 72 fact rows; `uvicorn app.main:app` served `/api/v1/health` with `status=ok`; `npm run build` completed in under 5s |
| 2 | Upload a CSV/Excel or use the seed data and see metrics and charts | **Pass** | `POST /api/v1/data/upload` activates a validated file (`test_api.py::test_upload_validates_then_activates_and_can_be_reverted`); `/api/v1/metrics` and `/api/v1/metrics/series` feed the charts; `docs/samples/metrics-2024-12.json` is a real response |
| 3 | At least one scenario with formulas and tests where changing a parameter really changes the result | **Pass** | `test_scenarios.py` (22 tests): the base case reproduces the trailing twelve months, price +5% lifts EBIT, material +8% cuts margin, DSO +20 days cuts operating cash flow, capex changes cash but not EBIT, tornado ranking |
| 4 | Numbers in the AI report match the calculation tools and carry sources, assumptions and period | **Pass** | `report-sample.verification.json`: V-01 111/111 citations resolved, V-02 all cited numbers reproduced, V-04 no uncited figures, V-05/V-06/V-08 pass (V-07 warns about fixture market data) |
| 5 | Offline, missing data, wrong currency and zero denominators must not produce fake conclusions | **Pass** | `test_market.py` (fixture fallback + provenance), `test_engine.py` (zero denominator becomes `undefined`, a missing input becomes `missing`, plus the partial-coverage note), `test_api.py` (no-plan upload returns `status: "missing"`), evaluation cases EV-10/11/21/22 |
| 6 | README contains architecture, screenshots, quickstart, synthetic declaration and executed tests | **Pass** | `README.md` is bilingual, carries three Mermaid diagrams (data flow, report verification sequence, citation-guard flow) and embeds **eight real screenshots** in `docs/screenshots/` captured from the running app with headless Chrome |
| 7 | No keys, private data or fabricated test results in the repository | **Pass** | `python scripts/check_secrets.py` returned `Result: clean` over 135 tracked files; `.env.example` values are empty; all shipped data is generated from a fixed seed |

## 2. Commands executed (verbatim results)

| Command | Result |
| --- | --- |
| `python data/synthetic/generate.py --write` | `Generated 72 fact rows across 24 months (2023-01..2024-12)`; SHA-256 written for 4 files |
| `python data/synthetic/generate.py --check` | `No issues found.` |
| `python -m pytest tests -q --cov=app` | 227 collected, all passed, exit code 0, coverage 96% (`2925` statements, `113` missed) |
| `python -m pytest tests -m evaluation -q` | 24 passed |
| `python scripts/check_secrets.py` | `Privacy & secret scan - 135 file(s) scanned` then `Result: clean` (also verified from a cp932 console, where the earlier version crashed on a non-ASCII dash) |
| `npm run typecheck` (apps/web) | clean (`tsc --noEmit` on both tsconfigs) |
| `npm test` (apps/web, mocked) | 6 files, 59 tests passed, 5 skipped (the live suites skip without `VITE_API_BASE`) |
| `VITE_API_BASE=... npx vitest run src/pages/app.live.test.tsx` | 4 passed: all seven routes plus the `/analyst?q=` and `/reports?auto=1` deep links against the running API |
| Node-API run of the full suite (see the caveat below) | 8 files, **69 tests passed**, 0 failed |
| `npm run build` (apps/web) | 608 modules; `index-*.js` about 797 kB (gzip about 266 kB); `index-*.css` about 19.4 kB (gzip about 4.4 kB) |
| `chrome --headless=new --screenshot=... --window-size=1600,1000 <route>` | 8 screenshots written to `docs/screenshots/`, each verified by eye; the first pass exposed the percentage-axis defect recorded below |
| `python -m uvicorn app.main:app --port 8000` + `curl` | `/health` ok; `/metrics?month=2024-12` revenue 322,304.71 USD, gross margin 0.219339, EBIT 14,290.68, cash 274,200.03, coverage 1.5618x, DSO 69.4168 days; `/risk/register` level `critical`, score 59.0, 12 signals, 3 data gaps; `/market/series/DFF` 4.83 on 2024-12-01 (`is_fixture=true`); `/market/edgar/status` `implemented=false` with the documented endpoints; `POST /scenarios/run` base/upside/downside/custom EBIT 216,098 / 367,821 / -27,152 / 290,227; `POST /agent/ask` 21 findings, 33 evidence items, tools `get_risk_signals,get_financial_metrics`; `POST /reports/generate` verification `warn` with 7 checks, 0 failures |

### 2.1 Environment caveat for the web commands

In the final pass the DSH sandbox denied esbuild a directory read above the project
(`Cannot read directory "../../../..": Access is denied`), so `npm run build` and `npm test` could not
load `vite.config.ts`, even though `tsc` and a direct esbuild call both worked. Both were therefore run
through the equivalent programmatic entry points with **identical options** (`configFile: false`, the
same React plugin, the `@` alias, the jsdom environment, `src/test/setup.ts`, the same include pattern
and timeouts): 8 files / 69 tests passed and the bundle contains the same 608 modules. The standard
commands had already succeeded earlier in the same session and are what the README documents for a
normal machine.

## 3. Not Run

| Item | Reason |
| --- | --- |
| `docker compose up` | Docker is not installed in this environment; the compose file and Dockerfiles are provided as unverified artefacts. |
| Playwright end-to-end and an automated screenshot pipeline | Not installed; the screenshots in `docs/screenshots/` were captured with headless Chrome as a manual step, and `app.live.test.tsx` covers rendering, routing and the deep links in jsdom. |
| Live FRED call | No `FRED_API_KEY`; the live path is exercised with `httpx.MockTransport` (200, 503 plus retry, empty payload, connection error) instead. |
| Live LLM provider call | No key; the planner and narrator are exercised with `StubLLMClient`, including a deliberately hallucinated figure. |
| Load test, accessibility audit, mobile device matrix | Out of scope for v1. |

## 4. Defects found and fixed during this build (honest log)

| # | Defect | Fix |
| --- | --- | --- |
| 1 | Stock metrics (cash, debt) were summed over a multi-month period, producing a meaningless 7.1M "cash" for FY2024 | `metrics()` now takes closing balances for stock items and says "point-in-time, not summed" in the formula; a regression test was added |
| 2 | The trailing-12M column in the report could not be traced to a citation, so `V-02` failed | The TTM metric citation is now emitted next to the value |
| 3 | Risk narratives quoted derived figures (margin levels, cash balances, burn rate) that had no citation | `RiskSignal.supporting` carries those values and the report cites each one |
| 4 | A risk rule emitted `info`-level noise for healthy metrics | Rules now emit nothing unless a real threshold is breached |
| 5 | The budget section compared against a plan that did not exist for uploaded datasets | The section states "Plan comparison is not available" and the API returns `status: "missing"` |
| 6 | `V-03` was documented but never emitted | The docstring now states that V-01 also covers citation resolution; seven checks are emitted |
| 7 | A flaky market test depended on sub-second wall-clock timing | The TTL test now ages the cache file explicitly |
| 8 | The P&L page compared actuals against a plan for a 24-month window (mixing two plan years), so its variance figures disagreed with the management report | The page now scopes the plan comparison to the fiscal year of the month on screen; the live sweep asserts the FY2024 revenue variance of -3.96%, matching the report |
| 9 | `scripts/check_secrets.py` crashed with `UnicodeEncodeError` on a cp932 console (the em dash in its own output), and would have done the same for any CJK path | Output is forced to UTF-8 and every printed line is ASCII-escaped; regression tests cover both the line renderer and a real end-to-end `main()` run |
| 10 | **Chart axes were unreadable for percentages**: the left axis was hard-coded to 0 decimals and the right one to 2, so a margin chart (values around 0.22) was labelled `0 0 0 0`. Found by looking at the first screenshot, not by a test | `axisFormatterFor()` derives the tick format from the axis label (percentage axes are scaled by 100 like the tooltip); `lib/charts.test.ts` pins it, including that an `Index 1982=100` axis is not mistaken for a ratio |
| 11 | Three documentation files (`README.md`, `docs/evaluation.md`, `docs/test-report.md`) were corrupted by a PowerShell text round-trip: Chinese text and symbols such as the arrow and em dash became mojibake, and a few bytes were lost | All three were rewritten with the file tools in clean UTF-8 and re-verified by reading them back; the lesson is recorded here rather than hidden: do not round-trip non-ASCII files through a shell `-replace` |

## 4b. Screenshot pipeline (how the images were produced)

```bash
# 1. API plus a static server that serves apps/web/dist with SPA fallback and proxies /api
cd services/api && python -m uvicorn app.main:app --port 8000
python <static-server-with-spa-fallback>            # 127.0.0.1:5173

# 2. one screenshot per route (a fresh browser profile each time, so nothing is cached)
chrome --headless=new --disable-gpu --no-sandbox --hide-scrollbars \
       --user-data-dir=<temp> --window-size=1600,1000 --virtual-time-budget=15000 \
       --screenshot=docs/screenshots/03-risk-control.png http://127.0.0.1:5173/risk

# 3. the two interactive pages use their shareable deep links
chrome ... --screenshot=docs/screenshots/06-ai-analyst.png    "<url>/analyst?q=<question>"
chrome ... --screenshot=docs/screenshots/07-report-centre.png "<url>/reports?auto=1&months=12"
```

The deep-link parameters (`?q=` on the analyst page, `?auto=1&months=` on the report centre) are a
product feature, not a test hook: they make a page state shareable, and both are covered by the live
test suite.

## 5. Repository hygiene

* `.gitignore` excludes `.env`, `node_modules`, `dist`, `runtime/`, caches and coverage output.
* Secret scan: `python scripts/check_secrets.py` returned `Result: clean` across 135 tracked files
  (credential shapes, a committed `.env`, absolute developer paths, oversized artefacts). The gate is
  itself tested (`test_security_scan.py`, 27 tests, including ASCII-safe output on a cp932 console) and
  exits non-zero on any finding, so it can run in CI.
* No real company, customer or employee data exists anywhere in the repository: the dataset is generated
  from seed `20260101` and every response carries `synthetic: true`.
* Reports and tool-call logs are written to `services/api/runtime/`, which is ignored by git; the copies
  under `docs/samples/` are intentional evidence and contain only synthetic figures.
