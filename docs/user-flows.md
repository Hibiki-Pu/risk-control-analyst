# RiskControl Analyst (风险控制分析师) — User flows

Companion documents: [`PRD.md`](PRD.md) (positioning, screens, edge states) ·
[`api-contract.md`](api-contract.md) (response shapes) · [`architecture.md`](architecture.md)
(module boundaries).

**Scope note.** Every endpoint, status code and number below was read from
`services/api/app/**`. The backend flows are implemented and produce the artefacts described. The
**frontend is implemented too** (`apps/web/src/**`, seven pages), so "what the user sees" describes
both the real API responses and the shipped rendering; the live integration test
(`apps/web/src/pages/Overview.live.test.tsx`) proves the figures reach the screen.

Base URL in all calls: `http://127.0.0.1:8000/api/v1` (`/docs` for the OpenAPI UI). The Vite dev
server proxies `/api` to that origin, so the browser never needs CORS
(`apps/web/vite.config.ts`).

Numbers quoted as examples come from the committed runtime report
`services/api/runtime/reports/RCA-202412-4966d3.verification.json` (as-of `2024-12`, report id
`RCA-202412-4966d3`, `verification_status: "warn"`). They are reproducible, not aspirational.

---

## J1 — 导入经营数据 (import operating data)

**Trigger.** The monthly close is ready; the analyst either keeps the shipped synthetic dataset or
uploads a CSV/XLSX fact table. The demo default is the synthetic seed, which is loaded at process
start.

### Steps

| # | Step | Endpoint called | What is returned / what the user sees | Decision point |
| --- | --- | --- | --- | --- |
| 1 | Confirm what is active | `GET /health`, `GET /meta/company` | `status`, `version`, `as_of` (`2024-12`), `synthetic: true`, `disclaimer`; dataset id, display name, `kind` (`synthetic_seed` \| `uploaded_file`), `seed_manifest` (seed `20260101`, generator `1.0.0`, row counts, declared gaps). | Use the seed, or upload? |
| 2 | Check the data contract before uploading | (documentation only — `POST /data/upload` has no dry-run mode) | The 13 required columns and the checks in §7 of [`PRD.md`](PRD.md). Dropping the file anywhere else fails the upload. | Do the required columns exist? |
| 3 | Upload | `POST /data/upload` (multipart, field `file`) | An `IngestRecord`: `upload_id`, `filename`, `received_at`, `report{rows, columns, months, regions, passed, missing_required, issues[], preview[]}`, `activated`. | `report.passed` true or false? |
| 4a | **Pass** | – (activation already happened inside step 3) | `activated: true`; the uploaded dataset becomes active, `synthetic` becomes `false`, the budget layer is empty, and the caches are invalidated. The macro frame is kept from the seed. | Review the numbers. |
| 4b | **Fail** | – | `activated: false`, `report.passed: false`, with per-row issues (severity `error`/`warning`, message, row index). The previous dataset **stays active**. | Fix and re-upload, or keep the current data. |
| 5 | Verify the switch | `GET /meta/company`, `GET /meta/lineage`, `GET /data/uploads` | New `dataset_id` (`UP-YYYYMMDDhhmmss-xxxx`), `kind: uploaded_file`, `has_budget_layer: false`; lineage rows for the upload; the upload history ranked newest first. | Continue to J2 with the new data, or roll back. |
| 6 | Roll back | `POST /data/activate-seed` | The seed manifest. The synthetic dataset is reloaded and `/metrics` answers again from the 24-month seed. | – |

### What the user sees

* A dataset banner: id, kind, rows, months, regions, and whether a budget layer exists.
* For a passing upload: the validation issue list is still shown (warnings such as "revenue_usd does
  not equal quantity x unit_price_local x fx_rate_to_usd for N row(s)") — a pass is not the same as a
  clean file.
* For a failing upload: the missing required columns or the offending rows, and the fact that the
  previous dataset is still live.

### Failure branches

| Condition | Real behaviour | What the user must be told |
| --- | --- | --- |
| Empty file | **400** `uploaded file is empty` | Nothing was ingested. |
| File > 20 MB | **413** `file larger than 20 MB is not accepted` | The limit is 20 MB. |
| Missing one or more of the 13 required columns | The report stops early: `missing_required` is filled and one error issue is added; nothing is activated. | Point at the data dictionary reference the message itself gives (`docs/data-dictionary.md`). |
| `month` not `YYYY-MM` | Error issue listing up to 3 offenders. | Fix the label format. |
| `quantity <= 0` or `fx_rate_to_usd <= 0` | Error issues. | Row-level fix required. |
| Duplicate `(month, region)` | Error issue "the fact table must be unique". | De-duplicate; the fact table has one row per region-month. |
| Revenue identity broken by more than 1.0 USD | **Warning**, and the engine **recomputes** `revenue_usd = quantity × unit_price_local × fx_rate_to_usd`. | The uploaded revenue column was overridden — this must be visible, not silent. |
| One region with two currencies | Warning: FX exposure will be ambiguous. | Accept with eyes open. |
| Missing optional working-capital columns | They stay empty (`pd.NA`), so DSO/DIO/CCC report "not available" later; the four zero-fill columns (D&A, interest, cash taxes, capex) become `0.0` instead — which is why interest coverage can be undefined for an uploaded file. | Distinguish "absent" from "zero". |
| API down | The screen shows a connection error; no partial activation is possible because activation is server-side. | Retry; the seed is still active. |

### Artefacts produced

`IngestRecord` (JSON, also stored under `services/api/runtime/uploads/UP-*.csv` when it passed) and
an entry in `GET /data/uploads` for the lifetime of the process.

---

## J2 — 异常发现 (find the anomaly)

**Trigger.** The close is loaded; the analyst or the finance manager opens the risk register for the
month.

### Steps

| # | Step | Endpoint called | What is returned / what the user sees | Decision point |
| --- | --- | --- | --- | --- |
| 1 | Open the register | `GET /risk/register?month=2024-12` | `overall_level`, `score`, `signals[]`, `data_gaps[]`, `lineage`. In the committed run: `overall_level: "critical"`, `score: 59.0`, 12 fired signals, 3 known data gaps. | Which signals are `high`/`critical`? |
| 2 | Read a signal | (same payload) | Each signal carries `signal_id` (RC-01…RC-14), `category` (profitability / liquidity / leverage / working_capital / budget_control / market / data_quality), `severity`, `title`, `detail`, `period`, `observed_value` + `unit`, `threshold` + `threshold_unit`, `direction`, `metric_ids`, `source_ids`, `supporting[]`, `recommended_check`. | Is the observation above/below the policy line, and by how much? |
| 3 | Trust-check the signal | `GET /metrics?month=2024-12` | The same figures as `CitedValue`s with `formula`, `status` and `source_ids`, so the user can recompute. | Accept the signal, or dig into the cause (J3). |
| 4 | Confirm nothing was hidden | (same register payload) | `data_gaps[]` always includes the three structural gaps (customer concentration, covenant headroom, inventory ageing) plus any rule that could not be evaluated. | Decide whether the register is decision-ready or needs more data. |

### Rule reference (thresholds as coded)

| Rule | Category | Fires when | Severity ladder |
| --- | --- | --- | --- |
| RC-01 | leverage | interest coverage < 2.0 x | critical < 1.5 x · high < 2.0 x · medium < 3.0 x · else info |
| RC-02 | leverage | net debt / annualised EBITDA > 3.0 x | high > 3.9 x · else medium |
| RC-03 | profitability | gross margin fell year-on-year | high ≥ 4.0 pp · medium ≥ 2.0 pp · else info |
| RC-04 | profitability | operating margin < 5 % | critical < 2 % · else high |
| RC-05 | liquidity | operating cash flow negative in any of the last 6 months | high if the negative streak ≥ 3 · medium ≥ 2 · else low |
| RC-06 | working_capital | DSO > 60 days | high > 69 days · else medium |
| RC-07 | working_capital | cash conversion cycle widened ≥ 10 days YoY | high ≥ 20 days · else medium |
| RC-08 | liquidity | cash fell ≥ 35 % YoY | high ≥ 55 % · else medium |
| RC-09 | liquidity | cash runway < 9 months at the trailing 3-month net burn | critical < 3 months · else high |
| RC-10 | budget_control | YTD revenue variance < −5 % | medium |
| RC-11 | budget_control | YTD EBIT variance < −10 % | high |
| RC-12 | market | non-USD share of TTM revenue > 0 % (largest currency reported) | medium if the largest non-USD share > 50 % · else low |
| RC-13 | data_quality | any missing source cell in the latest month | low |
| RC-14 | market | DFF policy rate rose ≥ 1.0 pp year-on-year (from the local macro frame) | medium ≥ 1.0 pp · else low |

Score = Σ severity weights (`critical 10 · high 6 · medium 3 · low 1 · info 0`), capped at 100;
overall level `critical ≥ 20`, `high ≥ 12`, `medium ≥ 5`, else `low`.

### Failure branches

| Condition | Real behaviour |
| --- | --- |
| Month has no rows | **400** `no rows match the requested scope`. |
| A rule's input is undefined (e.g. interest expense 0 on an uploaded file) | The rule is **skipped** and the reason is appended to `data_gaps` — it never becomes a silent pass. |
| Cash runway not applicable | When the trailing 3 months generated cash, `data_gaps` says so explicitly instead of reporting infinite runway. |
| DFF history < 13 observations | RC-14 is skipped and `data_gaps` gets "Market rate series unavailable, so the funding-cost backdrop could not be assessed." |
| Market series is a fixture | RC-14 still fires but its `detail` ends with "Values shown are local DEMO fixtures, not live observations." |
| API down | Panel-level error state; other panels keep working. |

### Artefacts produced

A `RiskRegister` document — the artefact the finance manager reviews and the input to the report's
Key Risks and Recommended Actions sections.

---

## J3 — 原因分析 (decompose the cause)

**Trigger.** A high/critical signal (typically RC-06 DSO, RC-07 cycle, RC-11 profit plan, or RC-14
funding costs) needs a root cause before anyone acts.

### Steps

| # | Step | Endpoint called | What is returned / what the user sees | Decision point |
| --- | --- | --- | --- | --- |
| 1 | Read the signal's metric ids | (from J2) | `metric_ids` such as `["dso_days", "dso_days_ending"]`, plus `supporting[]` for the extra figures the rule quotes. | Which metric to drill into? |
| 2 | Pull the metric pack | `GET /metrics?month=2024-12&regions=TH` | The full `MetricSet` for the scope, each value with `formula`, `status`, `note`, `source_ids`. | Is the driver working capital or earnings? |
| 3 | Look at the trend | `GET /metrics/series?start=2023-01&end=2024-12&limit=24` | `PeriodSeries.points[]` with revenue, COGS, gross profit and margin, EBIT and margin, interest, net income, OCF, FCF, DSO, cash, plus `budget_revenue_usd`, `revenue_variance_usd/_pct`, `ebit_variance_usd`, `mom_revenue_pct`, `yoy_revenue_pct`. | When did it start and is it worsening? |
| 4 | Separate plan from run-rate | `GET /metrics/budget-variance?start=2024-01&end=2024-12` | `MetricSet` with `basis: "variance"` for revenue, COGS, opex, EBIT, capex, interest — absolute and percent. | Is the miss volume, margin or cost? |
| 5 | Check the external backdrop | `GET /market/catalog`, `GET /market/series/DFF`, `.../PPIACO`, `.../DTWEXBGS`, `.../DEXTHUS` | Latest value, observation date, native frequency, `change` vs. previous, `is_fixture`, `is_stale`, `alignment_note`, `license_note`. | Is the cause internal or macro? |
| 6 | Confirm what the data cannot answer | `GET /meta/lineage` | The three lineage records including the note "One declared gap: TH 2024-07 inventory is intentionally missing." | Escalate a data request if the gap blocks the answer. |

### Worked example (committed runtime report, as-of `2024-12`)

| Evidence | Value | Citation |
| --- | --- | --- |
| Revenue, latest month | 322,305 USD | `metric:revenue@2024-12` |
| FY revenue | 3,706,443 USD | `metric:revenue@2024-01..2024-12` |
| EBIT, latest month | 14,291 USD | `metric:ebit@2024-12` |
| Gross margin | 21.9 % | `metric:gross_margin@2024-12` |
| Interest coverage | 1.56 x against a 2.00 x floor | `metric:interest_coverage@2024-12`, `risk:policy.interest_coverage` |
| Operating cash flow | −18,288 USD | `metric:operating_cash_flow@2024-12` |
| Closing cash | 274,200 USD | `metric:cash@2024-12` |
| Register | CRITICAL, score 59.0, 12 signals, 3 gaps | `risk:register.score` |

The chain is visible in the arithmetic: EBIT is thin (RC-01/RC-04), but operating cash flow is
strongly negative (RC-05) while EBIT is positive — so the drain is working capital and capex, not
accounting losses. That is exactly the distinction RC-05's `recommended_check` asks for.

### Failure branches

| Condition | Real behaviour |
| --- | --- |
| No budget layer (uploaded dataset) | Every variance comes back `status: "missing"` with `note: "No budget layer is available for this dataset, so no variance can be computed."` RC-10/RC-11 stay silent. The budget table in the report renders `n/a`. |
| Region has no rows in the requested month | **400** from `/metrics`. |
| DSO undefined | `status: "undefined"` with `note` naming the zero or missing denominator; the CCC becomes `missing` with "one or more working-capital ratios are unavailable". |
| Partial coverage (TH 2024-07 inventory) | Value is returned **with** the note "partial coverage: N source cell(s) missing in this period, totals exclude the missing values and are flagged", and RC-13 fires with `observed_value: 1` cells. |
| Market series is a fixture | `is_fixture: true`, `source_name: "Local demo fixture"`, license note says the values are hand-built demo values. Marked `is_fixture` in the report and drives V-07 to `warn`. |
| Unknown series id | **404** with the message listing the supported catalog ids. |
| API down | Panel-level error; the metric pack and register panels continue to work. |

### Artefacts produced

Chart-ready `PeriodSeries` (24 monthly points), a filtered `MetricSet`, and the budget-variance
`MetricSet` — the three data sources behind the dashboard's KPI, trend and variance charts.

---

## J3a — 模拟决策 (simulate the decision)

**Trigger.** "Can we absorb a 1.5 pp rate rise and a supplier recovery?" — a decision is needed
before anything is committed.

### Steps

| # | Step | Endpoint called | What is returned / what the user sees | Decision point |
| --- | --- | --- | --- | --- |
| 1 | Load the presets | `GET /scenarios/presets` | `base` ("Base (run-rate)"), `upside` ("Upside (price + mix recovery)"), `downside` ("Downside (cost + rate + FX squeeze)") with their full assumption sets. | Start from a preset or from zero? |
| 2 | Set the drivers | (form validation) | Allowed ranges: `horizon_months` 1–36; growth/cost/FX drivers −0.9 … 3.0; `interest_rate_delta_pp` −10 … +20; `dso_days_delta` −60 … +120; `capex_change_pct` −0.9 … 3.0. Unknown keys are rejected (`extra="forbid"`). | Are the assumptions defensible? |
| 3 | Run | `POST /scenarios/run` with `{assumptions, include_presets, label}` | `ScenarioResult`: `baseline`, `scenarios[]` (base/upside/downside/custom), `monthly` per scenario, `sensitivities[]` (tornado, largest swing first), `assumptions`, `model_note`, `lineage`. | Which case breaks the cash floor? |
| 4 | Read the comparison | (same payload) | Per scenario: revenue, gross margin, EBIT, operating margin, interest, net income, OCF, FCF, ending and minimum cash, `revenue_delta_usd`, `ebit_delta_usd/_pct`, `fcf_delta_usd`, `cash_runway_months`, `months_with_negative_cash`. | Does minimum cash go negative, and for how many months? |
| 5 | Read the sensitivity | (same payload) | 9 single-driver shocks with `ebit_impact_usd_low`, `ebit_impact_usd_high`, `ebit_swing_usd`. | Which driver dominates the outcome? |
| 6 | Accept the model limits | (same payload) | `model_note`: baseline = trailing twelve months repeated by calendar month (seasonality preserved, **not** the budget); materials priced in USD, labour/overhead in local currency; opex treated as fixed; debt flat with no new financing or amortisation; tax 22 % of positive pre-tax profit. | Is this good enough to act on? |
| 7 | Export | `POST /scenarios/export` | `text/csv` download (`scenarios.csv`): one row per scenario-month with `scenario_id` first, then every `ScenarioMonth` field. | Attach to the decision note. |

### Worked example (committed runtime report, as-of `2024-12`, horizon 12)

| Scenario | Revenue | EBIT | Δ EBIT vs run-rate | FCF | Ending cash | Minimum cash |
| --- | --- | --- | --- | --- | --- | --- |
| Base (run-rate) | 3,706,444 USD | 216,098 USD | 0 USD | −165,171 USD | 109,029 USD | 109,029 USD |
| Upside | 3,886,445 USD | 367,821 USD | +151,723 USD | −111,567 USD | 162,633 USD | 162,633 USD |
| Downside | 3,434,785 USD | −27,152 USD | −243,249 USD | −435,776 USD | −161,576 USD | −161,576 USD |

Tornado ranking (EBIT swing): selling price ±1 % = 74,129 USD → FX ±2 % = 64,090 USD → material cost
±2 % = 45,605 USD → volume ±2 pp = 18,484 USD → operating expenses ±1 % = 6,493 USD. All nine shocks
are computed and returned by the API (`sensitivities[]`); the **report** table renders only the first
five by swing.

Note the model detail this exposes: in the downside case minimum cash equals ending cash, i.e. the
cash path declines monotonically — the damage is a steady burn, not a single bad month.

### Failure branches

| Condition | Real behaviour |
| --- | --- |
| No trailing-twelve-month window | `ScenarioEngine.baseline()` slices the last 12 months of the dataset; a very short uploaded file has fewer comparable calendar months, and any calendar month absent from the baseline is **skipped** in the projection loop (`if key not in inputs.quantity: continue`). The user must be warned that the horizon then aggregates fewer regions. |
| `cash_runway_months` not applicable | `null` when the average monthly net flow is positive (no burn). Render "not applicable", never "∞". |
| Zero baseline EBIT | `ebit_delta_pct` is `null` (guarded `if baseline.ebit_usd`), never a division result. |
| A scenario produces zero revenue | `gross_margin_pct` and `operating_margin_pct` become `null`. |
| Unknown/extra driver key | **422** from FastAPI validation. |
| Out-of-range driver | **422** with the bound listed (`ge`/`le` on every field). |
| API down | Inputs are lost; the form must not claim a run happened. |

### Artefacts produced

`ScenarioResult` (JSON), the tornado chart data, and `scenarios.csv`.

---

## J3b / J4 — 管理层报告 (publish the verified report)

**Trigger.** The board pack is due and the numbers have to be defensible.

### Steps

| # | Step | Endpoint called | What is returned / what the user sees | Decision point |
| --- | --- | --- | --- | --- |
| 1 | Generate | `POST /reports/generate` with `{month, horizon_months}` (horizon 1–36, default 12) | `ReportDocument`: `report_id` (`RCA-<YYYYMM>-<6 hex>`), `title`, `as_of`, `generated_at`, `period`, `currency`, `synthetic`, `markdown`, `html`, `citations[]`, `verification[]`, `verification_status`, `engine`. | Did verification pass? |
| 2 | Read the eight sections | (same payload) | 1 Executive Summary · 2 KPI Performance · 3 Budget Performance · 4 External Market Signals · 5 Scenario Comparison · 6 Key Risks · 7 Recommended Actions · 8 Assumptions & Sources. | Is the story complete? |
| 3 | Check verification | (same payload, `verification[]`) | The checks actually returned are **V-01, V-02, V-04, V-05, V-06, V-07, V-08**. V-01 covers both citation format *and* resolution — the "citation resolves" concern that the module docstring labels V-03 is folded into V-01 and is **not** emitted as a separate item, so the response contains seven items, not eight. | `pass` → publish; `warn` → publish with the caveat visible; `fail` → **do not** publish. |
| 4 | Download | `GET /reports/{report_id}?format=markdown\|html\|json` | Markdown text, self-contained HTML, or the verification JSON. Unknown id → **404**. | – |
| 5 | Ask the AI analyst | `POST /agent/ask` with `{question, month?}` (question 2–1000 chars, month `YYYY-MM`) | `AgentAnswer`: `engine` (`deterministic-planner` by default), `conclusion`, `key_findings[]` with inline citations, `evidence[]`, `assumptions[]`, `risks[]`, `recommendations[]`, `confidence_limits[]`, `missing_data[]`, `tool_calls[]` with `status`/`duration_ms`/`citations`, `disclaimer`. | Are the findings traceable? |
| 6 | Inspect the tool trace | `GET /agent/audit?limit=20` | `count` + `records[]` (tool, arguments, status `ok`/`rejected`/`error`, `duration_ms`, `result_summary`, `citations`) and the note that prompts, secrets and personal data are never stored. | Did any call fail or get rejected? |
| 7 | Inspect the tools the model may use | `GET /agent/tools` | The 8 tool names, descriptions and JSON-Schema parameters. | Is the surface closed and sane? |

### What the user sees

* The header states the as-of date, the reporting currency and the **SYNTHETIC DEMO DATA** classification.
* Every figure is followed by a citation token such as `[metric:revenue@2024-12]`; the Appendix lists
  the datasets (name, kind, origin, rows, synthetic) and the market provenance lines.
* The verification table is part of the deliverable, not a debug view: in the committed run V-07 is
  `warn` because three of the four market series are fixtures, so `verification_status` is `"warn"`.

### Failure branches

| Condition | Real behaviour |
| --- | --- |
| Month has no data | **400** from `/reports/generate` (`ValueError` from the engine's month resolution). |
| `month` malformed | **422** (regex `^\d{4}-(0[1-9]\|1[0-2])$`). |
| `horizon_months` outside 1–36 | **422**. |
| Unknown report id | **404** `report {report_id} not found (generate it first)`. |
| All market series are fixtures | V-07 `warn`; the report body labels the provenance "local demo fixture (NOT live)". |
| A figure cannot be reproduced from its citation | V-02 `fail`; the report carries the offending line and must not be published as-is. |
| An undefined metric leaks a number | V-08 `fail`. |
| Every planned agent tool call fails | The answer says so: "I could not produce an evidence-based answer: every planned tool call failed, so there is no computed figure to report.", with `confidence_limits` recording each failure and no findings. |
| The LLM returns an untraceable sentence | `guard_narrative` withholds the line and `confidence_limits` records `"N narrative line(s) were withheld because a figure could not be traced to a tool result: …"`. Uncited numeric lines are never displayed. |
| LLM configured but unusable | A `confidence_limits` entry says the configured language model did not return a usable narrative and the deterministic narrator was used instead. |
| No LLM key at all | `engine: "deterministic-planner"`; the product still answers. This is the default. |
| API down | No report id is minted; the UI must not show a stale report as freshly generated. |

### Artefacts produced

Three files per report under `services/api/runtime/reports/`:
`RCA-<YYYYMM>-<hex>.md`, `.html` and `.verification.json` (the full `ReportDocument` including the
verification list), retrievable by id and format.

---

## Cross-journey: the "main path" in one line

`POST /data/upload` → `GET /risk/register` (异常发现) → `GET /metrics` + `/metrics/series` +
`/metrics/budget-variance` + `/market/series/{id}` (原因分析) → `POST /scenarios/run` +
`/scenarios/export` (模拟决策) → `POST /reports/generate` + `GET /reports/{id}` (管理层报告), with
`POST /agent/ask` available at any point as a read-only narrator over the same evidence.
