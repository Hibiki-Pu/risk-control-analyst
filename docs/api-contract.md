# API contract (v1)

Base URL: `http://127.0.0.1:8000/api/v1` · OpenAPI UI: `/docs` · All money values are **USD**, all
percentages are **decimal fractions** (`0.2193` = 21.93%) unless `unit` says otherwise.

**Every numeric value travels as a `CitedValue`.** The frontend must render `value` together with `unit`,
`period` and `status`, and must show "not available" whenever `status != "ok"` — never a zero.

```jsonc
// CitedValue
{
  "metric_id": "gross_margin", "label": "Gross margin", "value": 0.2193, "unit": "pct",
  "period": "2024-12", "basis": "actual", "formula": "gross_profit / revenue",
  "source_ids": ["actual:monthly_financials@2024-12"], "status": "ok", "note": null, "synthetic": true
}
```

`unit` is one of `USD`, `pct`, `days`, `x`, `pp`, `months`, `cells`, `score`, `percent_points`, `raw`.
`status` is one of `ok`, `missing`, `undefined`.

## Read endpoints

| Method | Path | Query | Returns |
| --- | --- | --- | --- |
| GET | `/health` | – | `{status, version, dataset, as_of, synthetic, disclaimer}` |
| GET | `/meta/company` | – | `{profile, dataset_id, kind, synthetic, seed_manifest}` |
| GET | `/meta/lineage` | – | `{lineage: DataLineage[]}` |
| GET | `/metrics` | `month` \| `start`,`end`, `regions[]` | `MetricSet` |
| GET | `/metrics/series` | `start`,`end`,`regions[]`,`limit` | `PeriodSeries` |
| GET | `/metrics/budget-variance` | `month` \| `start`,`end` | `MetricSet` (basis `variance`) |
| GET | `/risk/register` | `month`, `regions[]` | `RiskRegister` |
| GET | `/market/catalog` | – | `{series: MarketCatalogItem[], fred_configured, policy}` |
| GET | `/market/series/{id}` | `allow_live`, `limit` | `MarketSeries` |
| GET | `/market/edgar/status` | – | `{connector, implemented, enabled, configured, available, reason, access_policy, endpoints, planned_models}` — the SEC EDGAR connector is designed but **not implemented** in v1 and always reports `implemented: false` |
| GET | `/scenarios/presets` | – | `{presets: [{scenario_id,label,description,assumptions}]}` |
| GET | `/agent/tools` | – | `{tools: [{name, description, parameters}]}` |
| GET | `/agent/audit` | `limit` | `{count, records: ToolCallRecord[], note}` |
| GET | `/reports/{report_id}` | `format=markdown\|html\|json` | raw text/HTML or JSON |
| GET | `/data/uploads` | – | `{uploads: [...]}` |

## Write endpoints

| Method | Path | Body | Returns |
| --- | --- | --- | --- |
| POST | `/scenarios/run` | `{assumptions: ScenarioAssumptions, include_presets: bool, label: str}` | `ScenarioResult` |
| POST | `/scenarios/export` | same | `text/csv` |
| POST | `/agent/ask` | `{question: str, month?: "YYYY-MM"}` | `AgentAnswer` |
| POST | `/reports/generate` | `{month?: "YYYY-MM", horizon_months: int}` | `ReportDocument` |
| POST | `/data/upload` | `multipart/form-data`, field `file` | `IngestRecord` |
| POST | `/data/activate-seed` | – | dataset manifest |

## Key response shapes

```jsonc
// MetricSet
{ "as_of": "2024-12", "period": "2024-12", "scope": {"regions": "ALL", "months": ["2024-12"]},
  "currency": "USD", "synthetic": true, "values": { "<metric_id>": CitedValue }, "lineage": ["..."] }

// PeriodSeries.points[i]
{ "month": "2024-12", "revenue_usd": 322304.71, "cogs_usd": 251626.03, "gross_profit_usd": 70678.68,
  "gross_margin_pct": 0.2193, "ebit_usd": 14290.68, "operating_margin_pct": 0.0443,
  "interest_expense_usd": 9150.3, "net_income_usd": 5141.2, "operating_cash_flow_usd": -18288.0,
  "free_cash_flow_usd": -48188.0, "dso_days": 69.42, "cash_usd": 274200.03,
  "budget_revenue_usd": 340000.0, "revenue_variance_usd": -17695.0, "revenue_variance_pct": -0.052,
  "ebit_variance_usd": -20000.0, "mom_revenue_pct": 0.002, "yoy_revenue_pct": 0.03 }
// any field may be null when it is undefined (zero denominator / missing input)

// RiskRegister
{ "as_of": "2024-12", "period": "2024-12", "overall_level": "critical", "score": 59.0,
  "signals": [{ "signal_id": "RC-06", "category": "working_capital", "severity": "high",
                "title": "...", "detail": "...", "period": "2024-12", "observed_value": 69.42,
                "unit": "days", "threshold": 60.0, "threshold_unit": "days", "direction": "above",
                "metric_ids": ["dso_days"], "source_ids": ["actual:monthly_financials@2024-12"],
                "supporting": [{"key":"cycle_now","label":"...","value":104.45,"unit":"days"}],
                "recommended_check": "..." }],
  "data_gaps": ["..."], "lineage": ["..."] }

// MarketSeries
{ "series_id": "DFF", "title": "Federal Funds Effective Rate", "units": "Percent", "frequency": "daily",
  "country": "US", "source_name": "Local demo fixture", "source_url": "https://fred.stlouisfed.org/series/DFF",
  "fetched_at": "2026-01-01T00:00:00Z", "latest_observation_date": "2024-12-01", "latest_value": 4.83,
  "previous_value": 4.83, "change": 0.0, "observations": [{"date":"2024-12-01","value":4.83}],
  "is_fixture": true, "is_stale": false, "stale_after_days": 120, "alignment_note": "...",
  "license_note": "...", "error": null }

// ScenarioResult
{ "as_of": "2024-12", "base_period": "2024-01..2024-12", "horizon_months": 12, "currency": "USD",
  "baseline": ScenarioSummary, "scenarios": [ScenarioSummary], "monthly": {"base": [ScenarioMonth]},
  "sensitivities": [{ "driver": "price_change_pct", "label": "Selling price", "shock": "+0.01",
                      "ebit_impact_usd_low": -74129.0, "ebit_impact_usd_high": 74129.0,
                      "ebit_swing_usd": 148258.0 }],
  "assumptions": {"base": ScenarioAssumptions}, "model_note": "...", "lineage": ["..."] }

// ScenarioSummary (subset)
{ "scenario_id": "downside", "label": "Downside (cost + rate + FX squeeze)", "revenue_usd": 3434785.0,
  "gross_margin_pct": 0.17, "ebit_usd": -27152.0, "operating_margin_pct": -0.008,
  "interest_expense_usd": 118000.0, "net_income_usd": -30000.0, "operating_cash_flow_usd": -90000.0,
  "free_cash_flow_usd": -260000.0, "ending_cash_usd": -161576.0, "minimum_cash_usd": -200000.0,
  "revenue_delta_usd": -268000.0, "ebit_delta_usd": -243249.0, "ebit_delta_pct": -1.13,
  "fcf_delta_usd": -300000.0, "cash_runway_months": null, "months_with_negative_cash": 5 }

// AgentAnswer
{ "question": "...", "engine": "deterministic-planner", "as_of": "2024-12", "synthetic": true,
  "conclusion": "...", "key_findings": ["... [risk:RC-06@2024-12]"], "evidence": [Evidence],
  "assumptions": ["..."], "risks": ["..."], "recommendations": ["..."], "confidence_limits": ["..."],
  "missing_data": ["..."], "tool_calls": [{ "call_id": "...", "tool": "get_risk_signals",
  "arguments": {...}, "status": "ok", "error": null, "duration_ms": 12.3, "result_summary": "...",
  "started_at": "...", "citations": ["risk:RC-06@2024-12"] }], "disclaimer": "..." }

// ReportDocument
{ "report_id": "RCA-202412-xxxxxx", "title": "...", "as_of": "2024-12", "generated_at": "...",
  "period": "2024-01..2024-12", "currency": "USD", "synthetic": true, "markdown": "# ...",
  "html": "<!doctype html>...", "citations": ["..."],
  "verification": [{ "check_id": "V-02", "description": "...", "status": "pass", "detail": "..." }],
  "verification_status": "warn", "engine": "deterministic-report-builder" }
```

## Errors

* `400` — the request is valid JSON but cannot be answered (for example a month with no data).
  Body: `{"detail": "..."}`.
* `404` — unknown series/report id.
* `413` — upload larger than 20 MB.
* `422` — request body/query failed schema validation (FastAPI default body; unknown fields are rejected).
* `500` — unexpected failure. The body carries the exception type and message but never a stack trace,
  a key or a file path outside the runtime directory.

## Frontend notes

* The Vite dev server proxies `/api` to `http://127.0.0.1:8000`; the browser never needs CORS.
* Always render the synthetic-data notice when `synthetic === true`.
* Treat `status: "missing" | "undefined"` as "not available — <note>", never as 0.
* `is_fixture: true` on a market series must be visible in the UI (provenance badge).
