# Data dictionary

Everything in `data/synthetic/` is **synthetic demo data** for a fictional
South-East Asian consumer-goods group. The company, its regions, products,
budget and market values do not describe any real business.

Files:

| File | Rows | Purpose |
| --- | --- | --- |
| `monthly_financials.csv` | 72 (24 months x 3 regions) | The fact table: one row per `(month, region)`. |
| `monthly_budget.csv` | 24 | Group-level plan, one row per month. |
| `macro_series.csv` | 168 (7 series x 24 months) | Macro fixtures for the Market Data Adapter. |
| `company_profile.json` | – | Company metadata, currencies, period range, disclaimer. |
| `dataset_manifest.json` | – | Seed, row counts, declared gaps and SHA-256 of every file. |

## 1. `monthly_financials.csv`

Grain: **one row per `(month, region)`**. `(month, region)` is unique and is the
primary key. All money is USD unless the column ends in `_local`.

| Column | Type | Unit / currency | Upload | Notes |
| --- | --- | --- | --- | --- |
| `month` | string | `YYYY-MM` | **required** | Calendar month, 2023-01 … 2024-12. |
| `region` | string | code | **required** | `SG`, `TH`, `VN`. |
| `region_name` | string | – | optional | Human label; filled from `region` if absent. |
| `currency` | string | ISO code | **required** | `SGD`, `THB`, `VND`. One currency per region. |
| `quantity` | float | units | **required** | Must be > 0. |
| `unit_price_local` | float | local currency per unit | **required** | Selling price in the local currency. |
| `fx_rate_to_usd` | float | USD per 1 local unit | **required** | Must be > 0. |
| `revenue_usd` | float | USD | **required** | Must equal `quantity x unit_price_local x fx_rate_to_usd` within 1 USD; an upload that violates this is recomputed from the drivers and flagged as a warning. |
| `cogs_material_usd` | float | USD | **required** | Imported material, invoiced in USD. |
| `cogs_labor_usd` | float | USD | **required** | Direct labour (local currency, translated). |
| `cogs_overhead_usd` | float | USD | **required** | Production overhead. |
| `opex_sales_usd` | float | USD | **required** | Selling and distribution. |
| `opex_admin_usd` | float | USD | **required** | Administration and shared services. |
| `opex_rd_usd` | float | USD | **required** | Product development. |
| `depreciation_amortization_usd` | float | USD | optional (default 0) | Deducted from EBITDA to reach EBIT. |
| `interest_expense_usd` | float | USD | optional (default 0) | Period interest charge. |
| `cash_taxes_paid_usd` | float | USD | optional (default 0) | Cash taxes, not an accrual. |
| `annual_interest_rate_pct` | float | percent p.a. | optional | Weighted cost of debt for the period. |
| `debt_balance_usd` | float | USD | optional | Closing total debt (stock). |
| `short_term_debt_usd` | float | USD | optional | Current portion (stock). |
| `cash_usd` | float | USD | optional | Closing cash (stock). |
| `accounts_receivable_usd` | float | USD | optional | Closing receivables (stock). |
| `inventory_usd` | float | USD | optional | Closing inventory (stock). |
| `accounts_payable_usd` | float | USD | optional | Closing payables (stock). |
| `operating_cash_flow_usd` | float | USD | optional | Used as the reported OCF proxy; the engine does not recompute it from the balance sheet. |
| `capex_usd` | float | USD | optional (default 0) | Cash capital expenditure. |

### Declared gap

`TH` / `2024-07` / `inventory_usd` is **intentionally missing**. It exists so the
product can demonstrate real missing-data behaviour:

* the monthly aggregate is the sum of the available regions and is flagged
  `partial coverage: 1 source cell(s) missing`;
* `dio_days` and `cash_conversion_cycle_days` carry the same flag;
* the risk register raises `RC-13` (data quality).

Any *undeclared* missing value makes `validate_dataset()` fail, and the value is
not silently zero-filled.

### Generated driver paths

The generator (`services/api/app/data/synthetic.py`) applies deterministic
drivers so the demo contains a believable deterioration:

| Driver | Behaviour over 24 months |
| --- | --- |
| Volume | Region-specific growth (SG 3%, TH 7%, VN 14% p.a.) with SG softness in year 2 and a VN plateau; ±1.8% seeded noise. |
| Seasonality | Calendar-month factors 0.88 (Feb) … 1.12 (Dec), scaled per region. |
| Price | 2.0%–4.5% p.a. drift, with a promotional reset in SG in 2024 H1. |
| Material cost | +0.28pp per month plus a 2.5pp step across 2023 H2 (≈ +9% cumulative). |
| Labour cost | +0.26pp per month plus a 2.2pp minimum-wage step in 2024-03. |
| Overhead | +0.25pp per month. |
| FX (USD per local unit) | SG −1.0%, TH −6.2%, VN −4.8% across the period, ramped. |
| DSO / DIO / DPO | 45 → 68 days, 62 → 78 days, 52 → 43 days. |
| Interest rate | 6.50% → 9.00% through 2024. |
| Debt | +180k (2024-03), +150k (2024-09), −60k from 2024-09. |
| Capex | 26k/month, plus 185k (2024-09) and 95k (2024-10). |

## 2. `monthly_budget.csv`

Group level, one row per month. There is **no regional plan**, which is itself a
documented limitation (see `docs/roadmap.md`).

| Column | Notes |
| --- | --- |
| `month` | Primary key. |
| `budget_revenue_usd` | Plan revenue. |
| `budget_cogs_usd` | Plan cost of goods sold. |
| `budget_opex_usd` | Plan operating expenses. |
| `budget_depreciation_amortization_usd` | Plan D&A. |
| `budget_interest_expense_usd` | Plan interest at a 7.0% plan rate. |
| `budget_capex_usd` | Plan capex, 30,000 USD/month. |
| `budget_note` | Qualitative basis of the plan (numbers are in `docs/financial-methodology.md`). |

Derived plan lines: `budget_gross_profit = budget_revenue - budget_cogs`,
`budget_ebit = budget_gross_profit - budget_opex - budget_depreciation_amortization`.

## 3. `macro_series.csv`

Long format, one row per `(series_id, observation_date)`. Metadata mirrors the
public FRED catalogue; **the values are hand-built fixtures** for this demo.

| Column | Notes |
| --- | --- |
| `series_id` | `DFF`, `DGS10`, `CPIAUCSL`, `PPIACO`, `DTWEXBGS`, `DEXTHUS`, `DEXSIUS`. |
| `title`, `units`, `frequency`, `country` | Series metadata. |
| `observation_date` | First of the month. |
| `value` | Fixture level (percent, index or FX rate as per `units`). |
| `source_url` | The canonical FRED landing page for the series. |
| `is_fixture` | `true` for every shipped row. Live rows (`false`) only exist when `FRED_API_KEY` is set. |
| `fetched_at` | When the fixture set was produced. |
| `license_note` | States that the numbers are demo values, not observations. |

## 4. Upload contract

`POST /api/v1/data/upload` accepts CSV, XLSX or XLS (≤ 20 MB). Checks performed
by `services/api/app/data/ingest.py`:

| Check | Severity |
| --- | --- |
| All `required` columns present | error (upload rejected) |
| `month` matches `YYYY-MM` | error |
| `quantity` > 0 | error |
| `fx_rate_to_usd` > 0 | error |
| `(month, region)` unique | error |
| `revenue_usd` equals the revenue identity within 1 USD | warning (value is recomputed) |
| Any missing value in a required column | warning |
| A region reporting more than one currency | warning (FX exposure becomes ambiguous) |

Optional columns absent from the file are created: money columns default to `0`
(`depreciation_amortization_usd`, `interest_expense_usd`, `cash_taxes_paid_usd`,
`capex_usd`) and the remaining balance-sheet columns are left empty, which makes
the dependent metrics report `missing` rather than `0`. An uploaded dataset has
**no budget layer**, so variance metrics return `status = "missing"` with an
explanation.

`POST /api/v1/data/activate-seed` switches back to the shipped synthetic dataset.
