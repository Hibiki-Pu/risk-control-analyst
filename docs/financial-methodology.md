# Financial methodology

Every number the product displays is produced by `services/api/app/finance/` and
carries its unit, period, formula and source ids in the API response. This
document is the human-readable counterpart of that contract.

## 1. Conventions

| Item | Rule |
| --- | --- |
| Reporting currency | **USD**. Local ledgers are SGD (SG), THB (TH) and VND (VN). |
| Money unit | Absolute USD (not thousands). Rounded to 2 decimals in the seed data, 6 decimals in `CitedValue`. |
| Percentage unit | **Decimal fraction** everywhere in the API (`0.2193` = 21.93%). Formatting to `%` is a presentation concern. |
| Period label | `YYYY-MM` for a month; `YYYY-MM..YYYY-MM` (inclusive) for a range. |
| Days in period | Sum of calendar days of the months covered (leap-year aware), e.g. `2024-01..2024-03` = 91 days. |
| Flow vs stock | Revenue, costs, cash flow and capex are **flows** and are summed. Cash, debt and working-capital balances are **stocks** and are taken at the period end. |
| FX translation | Each regional row stores `fx_rate_to_usd` (USD per 1 unit of local currency) and `revenue_usd = quantity x unit_price_local x fx_rate_to_usd`. Group totals are the sum of the translated rows. |
| Consolidation | Regions are funding centres with fixed weights (SG 50%, TH 30%, VN 20%) applied to cash, debt and capex, so group balances are exact sums of the regional rows. No intercompany eliminations exist in this demo. |

## 2. Profit and loss

| metric_id | Formula | Unit |
| --- | --- | --- |
| `revenue` | `sum(revenue_usd)` | USD |
| `cogs` | `cogs_material + cogs_labor + cogs_overhead` | USD |
| `gross_profit` | `revenue - cogs` | USD |
| `gross_margin` | `gross_profit / revenue` | pct |
| `opex` | `opex_sales + opex_admin + opex_rd` | USD |
| `ebitda` | `gross_profit - opex` (D&A is **not** deducted) | USD |
| `depreciation_amortization` | `sum(depreciation_amortization_usd)` | USD |
| `ebit` | `ebitda - depreciation_amortization` | USD |
| `operating_margin` | `ebit / revenue` | pct |
| `interest_expense` | `sum(interest_expense_usd)` | USD |
| `ebt` | `ebit - interest_expense` | USD |
| `cash_taxes` | `sum(cash_taxes_paid_usd)` | USD |
| `net_income` | `ebit - interest_expense - cash_taxes` | USD |
| `net_margin` | `net_income / revenue` | pct |

**EBITDA / EBIT / net income are never mixed.** `ebitda` excludes D&A only;
`ebit` deducts D&A; `net_income` additionally deducts interest and cash taxes.
The API returns all three so a reader can check the bridge.

The dataset provides cash taxes (not an accrual tax charge), so `net_income` is
labelled *net income (proxy)*. It is not a statutory profit figure.

## 3. Cash flow

| metric_id | Formula | Unit |
| --- | --- | --- |
| `operating_cash_flow` | `ebit + D&A - cash_taxes_paid - change in net working capital` | USD |
| `capex` | `sum(capex_usd)` | USD |
| `free_cash_flow` | `operating_cash_flow - capex` | USD |

`change in net working capital = delta(accounts_receivable + inventory - accounts_payable)`.
In the generator the opening month has no comparative, so month 1 carries no
working-capital movement; in the scenario engine the first projected month moves
receivables only (inventory and payables have no opening balance in that model).

**This is a documented proxy, not a statutory cash-flow statement.** It omits the
FX translation reserve, lease classification, provisions, dividends and equity
movements. `free_cash_flow` here means operating cash flow less capex; it is not
"free cash flow to equity".

## 4. Working capital, liquidity and leverage

| metric_id | Formula | Unit |
| --- | --- | --- |
| `dso_days` | `average receivables / (revenue / days in period)` | days |
| `dso_days_ending` | `closing receivables / (revenue / days in period)` | days |
| `dio_days` | `average inventory / (cogs / days in period)` | days |
| `dpo_days` | `average payables / (cogs / days in period)` | days |
| `cash_conversion_cycle_days` | `dso + dio - dpo` | days |
| `current_ratio` | `(cash + receivables + inventory) / (payables + short-term debt)` | x |
| `net_debt` | `total debt - cash` (both at period end) | USD |
| `net_leverage` | `net_debt / (ebitda x 12 / months in period)` | x |
| `interest_coverage` | `ebit / interest_expense` | x |
| `revenue_mom` / `revenue_yoy` | `revenue_m / revenue_m-1 - 1`, `revenue_m / revenue_m-12 - 1` | pct |

**DSO is reported on two bases on purpose.** `dso_days` uses the average of the
opening and closing receivable balances (the textbook definition, used by the
risk rules); `dso_days_ending` uses the closing balance alone (the definition
most ERP reports use). The seed data is generated with the ending-balance
definition, so the two differ by roughly one day.

When a period starts on the first month of the dataset there is no opening
balance: the closing balance is used and the metric note says
*"no opening balance exists for the first period of the dataset"*.

## 5. Budget variance

| metric_id | Formula | Unit |
| --- | --- | --- |
| `<line>_variance` | `actual - budget` | USD |
| `<line>_variance_pct` | `(actual - budget) / abs(budget)` | pct |

Lines covered: `revenue`, `cogs`, `opex`, `ebit`, `capex`, `interest_expense`.
**Sign convention:** positive is favourable for revenue and EBIT, unfavourable for
costs, capex and interest. Every variance metric carries the note
"favorable when actual > plan" or "favorable when actual < plan" so the consumer
never has to guess — and the frontend prints that convention next to the table.

The plan is group level only; there is no regional budget split in this dataset.
Plan parameters used by the generator:

* FY2023 plan = the same month's actual x `0.985`, gross margin `27.5%`, opex ratio `15.2%`.
* FY2024 plan = the same month of the prior year x `1.12`, gross margin `28.5%`, opex ratio `15.0%`.
* Plan interest = `debt path x 7.0% / 12` (a plan rate held below the actual path, which is how the demo produces an interest variance).
* Plan capex = `30,000 USD/month` (the actual FY2023 spike is not repeated).

## 6. Missing data, zero denominators and other limits

The engine never substitutes a number:

| Situation | Behaviour |
| --- | --- |
| Denominator is 0 | `value = null`, `status = "undefined"`, note explains which denominator. |
| Numerator or denominator is missing | `value = null`, `status = "missing"`, note names the missing input. |
| Any source cell missing in the period | Aggregates use `sum(min_count=1)`, the missing count is reported, and every metric in that period carries a `partial coverage: N source cell(s) missing` note. Totals therefore **understate** by the missing amount and say so. |
| A first period has no opening balance | Closing balance used, stated in the note. |
| No budget layer (uploaded dataset) | Every variance metric returns `status = "missing"` with "No budget layer is available for this dataset". |
| A metric cannot be computed at all | The metric is absent from `MetricSet.values` or returned with a `missing`/`undefined` status; the report renders "not available" and never a zero. |
| FX or inflation assumptions | Any projection is a model output, labelled `basis = "forecast"` / `source_ids = ["model:driver-based-forecast@v1"]`. |

## 7. Determinism

* The seed dataset is generated with a fixed seed (`20260101`) and the manifest
  records a SHA-256 for every file; regeneration is byte-identical.
* No machine-learning model is used anywhere. The scenario engine is a
  driver-based projection (see `docs/architecture.md`).
* The LLM layer may select tools and narrate results. It never computes a value,
  and any narrative figure that cannot be traced to a tool result is withheld by
  `app.agent.orchestrator.guard_narrative`.

## 8. Known simplifications

* Cash taxes are `22%` of positive pre-tax profit (a modelling choice, not a tax
  computation).
* D&A is a fixed share of revenue in the generator (`1.5%`), not an asset register.
* No lease, pension, provision, minority interest or equity accounting.
* Working-capital days in the scenario engine are held at the closing level plus
  any user-specified delta; they do not react to volume.
* Unit economics in the projection are linear: a price change does not move volume
  (no demand elasticity is claimed).
