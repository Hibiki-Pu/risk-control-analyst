# Risk Control & Financial Performance Report

**As-of date:** 2024-12 | **Reporting currency:** USD | **Data classification:** SYNTHETIC DEMO DATA (fictional company)

**Overall risk level:** CRITICAL (register score 59.0 [risk:register.score] across the live signal set) | **Scenario horizon:** 12 months [scenario:base.horizon_months] from 2024-12

All figures are computed deterministically by the calculation service. Every number below carries a citation of the form `metric:gross_margin@2024-12`; the pre-export verifier re-computes each one before the report can be exported.

## 1. Executive Summary

- **Revenue** in 2024-12 was 322,305 USD [metric:revenue@2024-12], taking 2024-01..2024-12 revenue to 3,706,443 USD [metric:revenue@2024-01..2024-12].
- **Profitability:** EBIT of 14,291 USD [metric:ebit@2024-12] on a gross margin of 21.9% [metric:gross_margin@2024-12].
- **Debt service:** interest cover of 1.56 x [metric:interest_coverage@2024-12] against a policy floor of 2.00 x [risk:policy.interest_coverage].
- **Liquidity:** closing cash of 274,200 USD [metric:cash@2024-12] with operating cash flow of -18,288 USD [metric:operating_cash_flow@2024-12] and free cash flow of -48,188 USD [metric:free_cash_flow@2024-12].
- **Risk register:** overall level **CRITICAL** with score 59.0 [risk:register.score] across 12 fired signals (3 known data gaps).
- **Headline exposure:** Interest coverage is thin — EBIT coverage of interest has fallen to the policy floor, so every further rate step or margin slip flows straight into equity value. [risk:RC-01@2024-12]
- **Scenario view:** under the downside case EBIT reaches -27,152 USD [scenario:downside.ebit_usd], a change of -243,249 USD [scenario:downside.ebit_delta_usd] versus the run-rate, with ending cash of -161,576 USD [scenario:downside.ending_cash_usd].

## 2. KPI Performance

Latest month 2024-12; trailing twelve months = 2024-01..2024-12.

| Metric | Latest month | Trailing 12M | Source citation |
| --- | --- | --- | --- |
| Revenue | 322,305 [metric:revenue@2024-12] | 3,706,443 [metric:revenue@2024-01..2024-12] | [metric:revenue@2024-12] |
| Gross margin | 21.9% [metric:gross_margin@2024-12] | 23.2% [metric:gross_margin@2024-01..2024-12] | [metric:gross_margin@2024-12] |
| EBIT | 14,291 [metric:ebit@2024-12] | 216,097 [metric:ebit@2024-01..2024-12] | [metric:ebit@2024-12] |
| Operating margin | 4.4% [metric:operating_margin@2024-12] | 5.8% [metric:operating_margin@2024-01..2024-12] | [metric:operating_margin@2024-12] |
| Net income (proxy) | 3,744 [metric:net_income@2024-12] | 79,634 [metric:net_income@2024-01..2024-12] | [metric:net_income@2024-12] |
| Operating cash flow (proxy) | -18,288 [metric:operating_cash_flow@2024-12] | -171,268 [metric:operating_cash_flow@2024-01..2024-12] | [metric:operating_cash_flow@2024-12] |
| Free cash flow (proxy) | -48,188 [metric:free_cash_flow@2024-12] | -530,068 [metric:free_cash_flow@2024-01..2024-12] | [metric:free_cash_flow@2024-12] |
| DSO (average receivables) | 69.4 days [metric:dso_days@2024-12] | 61.6 days [metric:dso_days@2024-01..2024-12] | [metric:dso_days@2024-12] |
| Cash conversion cycle | 104.5 days [metric:cash_conversion_cycle_days@2024-12] | 86.1 days [metric:cash_conversion_cycle_days@2024-01..2024-12] | [metric:cash_conversion_cycle_days@2024-12] |
| Interest coverage | 1.56 x [metric:interest_coverage@2024-12] | 1.92 x [metric:interest_coverage@2024-01..2024-12] | [metric:interest_coverage@2024-12] |
| Net debt / EBITDA (annualised) | 4.12 x [metric:net_leverage@2024-12] | 3.48 x [metric:net_leverage@2024-01..2024-12] | [metric:net_leverage@2024-12] |
| Closing cash | 274,200 [metric:cash@2024-12] | 274,200 [metric:cash@2024-01..2024-12] | [metric:cash@2024-12] |

Period note: partial coverage: 1 source cell(s) missing in this period; totals exclude the missing values and are flagged [metric:revenue@2024-01..2024-12]

## 3. Budget Performance

Plan comparison for 2024-01..2024-12. Positive revenue variance is favourable; for a cost line a positive variance is unfavourable.

| Metric | Actual | Plan | Variance | Variance % | Citation |
| --- | --- | --- | --- | --- | --- |
| Revenue | 3,706,443 [metric:revenue@2024-01..2024-12] | 3,859,123 [budget:revenue_plan@2024-01..2024-12] | -152,680 [budget:revenue_variance@2024-01..2024-12] | -4.0% [budget:revenue_variance_pct@2024-01..2024-12] | [budget:revenue_variance@2024-01..2024-12] |
| Cost of goods sold | 2,846,223 [metric:cogs@2024-01..2024-12] | 2,759,273 [budget:cogs_plan@2024-01..2024-12] | 86,950 [budget:cogs_variance@2024-01..2024-12] | +3.2% [budget:cogs_variance_pct@2024-01..2024-12] | [budget:cogs_variance@2024-01..2024-12] |
| Operating expenses | 588,526 [metric:opex@2024-01..2024-12] | 578,868 [budget:opex_plan@2024-01..2024-12] | 9,658 [budget:opex_variance@2024-01..2024-12] | +1.7% [budget:opex_variance_pct@2024-01..2024-12] | [budget:opex_variance@2024-01..2024-12] |
| EBIT | 216,097 [metric:ebit@2024-01..2024-12] | 463,095 [budget:ebit_plan@2024-01..2024-12] | -246,998 [budget:ebit_variance@2024-01..2024-12] | -53.3% [budget:ebit_variance_pct@2024-01..2024-12] | [budget:ebit_variance@2024-01..2024-12] |

Plan basis: Plan built on prior-year revenue growth with a target gross margin and operating-expense ratio set by the budget committee; the parameter values are documented in docs/financial-methodology.md. Months covered: 12.

## 4. External Market Signals

Market inputs are read through the Market Data Adapter. Fixtures are never presented as live observations.

| Series | Latest value | Observation date | Frequency | Provenance | Citation |
| --- | --- | --- | --- | --- | --- |
| DFF | 4.83% | 2024-12-01 | daily | local demo fixture (NOT live) | [series:DFF@2024-12-01] |
| PPIACO | 261.00 | 2024-12-01 | monthly | local demo fixture (NOT live) | [series:PPIACO@2024-12-01] |
| DEXTHUS | 34.30 | 2024-12-01 | daily | local demo fixture (NOT live) | [series:DEXTHUS@2024-12-01] |
| DTWEXBGS | 127.70 | 2024-12-01 | daily | local demo fixture (NOT live) | [series:DTWEXBGS@2024-12-01] |

Alignment policy: series keep their native frequency and are never forward-filled across frequencies; consumers must select the observation date they need.

## 5. Scenario Comparison

Driver-based projection over 12 months from 2024-12. Baseline run-rate window: 2024-01..2024-12.

Model note: Baseline = trailing twelve months run-rate repeated by calendar month (seasonality preserved), NOT the budget. Materials are priced in USD, labour and overhead in local currency. Operating expenses are treated as fixed within the horizon. Debt is held flat with no new financing or amortisation. Taxes accrue at 22% of positive pre-tax profit. Working-capital days are held at the closing level plus any user-specified delta. [model:tax_rate@v1]

| Scenario | Revenue | EBIT | EBIT vs base | FCF | Ending cash | Minimum cash |
| --- | --- | --- | --- | --- | --- | --- |
| Base (run-rate) | 3,706,444 [scenario:base.revenue_usd] | 216,098 [scenario:base.ebit_usd] | 0 [scenario:base.ebit_delta_usd] | -165,171 [scenario:base.free_cash_flow_usd] | 109,029 [scenario:base.ending_cash_usd] | 109,029 [scenario:base.minimum_cash_usd] |
| Upside (price + mix recovery) | 3,886,445 [scenario:upside.revenue_usd] | 367,821 [scenario:upside.ebit_usd] | 151,723 [scenario:upside.ebit_delta_usd] | -111,567 [scenario:upside.free_cash_flow_usd] | 162,633 [scenario:upside.ending_cash_usd] | 162,633 [scenario:upside.minimum_cash_usd] |
| Downside (cost + rate + FX squeeze) | 3,434,785 [scenario:downside.revenue_usd] | -27,152 [scenario:downside.ebit_usd] | -243,249 [scenario:downside.ebit_delta_usd] | -435,776 [scenario:downside.free_cash_flow_usd] | -161,576 [scenario:downside.ending_cash_usd] | -161,576 [scenario:downside.minimum_cash_usd] |

Sensitivity of horizon EBIT to a single-driver shock (tornado, largest swing first):

| Driver | Shock | EBIT impact down | EBIT impact up | Swing | Citation |
| --- | --- | --- | --- | --- | --- |
| Selling price | +0.01 | -37,064 [scenario:sensitivity.price_change_pct.low] | 37,064 [scenario:sensitivity.price_change_pct.high] | 74,129 [scenario:sensitivity.price_change_pct.swing] | [scenario:sensitivity.price_change_pct.swing] |
| FX (USD per local currency) | +0.02 | -32,141 [scenario:sensitivity.fx_change_pct.low] | 31,949 [scenario:sensitivity.fx_change_pct.high] | 64,090 [scenario:sensitivity.fx_change_pct.swing] | [scenario:sensitivity.fx_change_pct.swing] |
| Material cost | +0.02 | 22,870 [scenario:sensitivity.material_cost_change_pct.low] | -22,735 [scenario:sensitivity.material_cost_change_pct.high] | 45,605 [scenario:sensitivity.material_cost_change_pct.swing] | [scenario:sensitivity.material_cost_change_pct.swing] |
| Volume growth | +0.02 | -9,271 [scenario:sensitivity.volume_growth_pct.low] | 9,214 [scenario:sensitivity.volume_growth_pct.high] | 18,484 [scenario:sensitivity.volume_growth_pct.swing] | [scenario:sensitivity.volume_growth_pct.swing] |
| Operating expenses | +0.01 | 3,252 [scenario:sensitivity.opex_change_pct.low] | -3,242 [scenario:sensitivity.opex_change_pct.high] | 6,493 [scenario:sensitivity.opex_change_pct.swing] | [scenario:sensitivity.opex_change_pct.swing] |

## 6. Key Risks

- **[HIGH] RC-01 — Interest coverage is thin** (leverage). Observed 1.56 x [risk:RC-01@2024-12] [risk:RC-01.threshold@2024-12] against a threshold of 2.00 x. EBIT coverage of interest has fallen to the policy floor, so every further rate step or margin slip flows straight into equity value. Check: Re-test the covenant headroom with the financing bank before the next drawdown.
- **[HIGH] RC-02 — Net leverage above policy** (leverage). Observed 4.12 x [risk:RC-02@2024-12] [risk:RC-02.threshold@2024-12] against a threshold of 3.00 x. Net debt to annualised EBITDA has moved above the policy ceiling. Deleveraging now depends on an EBITDA recovery rather than on cash generation. Check: Re-run the debt schedule and confirm the amortisation calendar still matches plan.
- **[HIGH] RC-04 — Operating margin close to break-even** (profitability). Observed 4.4% [risk:RC-04@2024-12] [risk:RC-04.threshold@2024-12] against a threshold of 5.0%. EBIT margin has fallen below the monitoring line. With interest and tax still to be served, the group has very little room for a demand or cost shock. Check: Split the margin walk into price, mix, material and overhead before the board pack.
- **[HIGH] RC-05 — Operating cash flow is negative** (liquidity). Observed -6.0 months [risk:RC-05@2024-12] [risk:RC-05.threshold@2024-12] against a threshold of 3.0 months. Operating cash flow was negative in 6 of the last 6 months (6 consecutive). The proxy is EBIT + D&A - cash taxes - change in net working capital; the drain is working capital, not accounting losses. Check: Separate the working-capital drain from the earnings drain before deciding on financing.
- **[HIGH] RC-06 — Receivables collection is slipping** (working capital). Observed 69.4 days [risk:RC-06@2024-12] [risk:RC-06.threshold@2024-12] against a threshold of 60.0 days. DSO (average receivables basis) is 69.4 days against a policy limit of 60 days. Receivables are financing the customers. Check: Age the receivables ledger and escalate the oldest overdue accounts.
- **[HIGH] RC-07 — Cash conversion cycle is lengthening** (working capital). Observed 43.1 days [risk:RC-07@2024-12] [risk:RC-07.threshold@2024-12] [risk:RC-07.cycle_now@2024-12] against a threshold of 20.0 days. The cycle widened by 43.1 days year-on-year to 104.5 days (DSO + DIO - DPO). Longer collection and higher stock more than offset slower supplier payments. Check: Decide explicitly which lever to pull: collection, stock cover or supplier terms.
- **[HIGH] RC-08 — Cash balance is eroding** (liquidity). Observed 68.3% [risk:RC-08@2024-12] [risk:RC-08.threshold@2024-12] [risk:RC-08.cash_now@2024-12] [risk:RC-08.cash_year_ago@2024-12] against a threshold of 35.0%. Cash has fallen sharply year-on-year: capex and the working-capital build are consuming the buffer that previously funded operations. Check: Model the liquidity runway under a no-new-financing assumption.
- **[HIGH] RC-09 — Cash runway covers less than nine months** (liquidity). Observed 5.4 months [risk:RC-09@2024-12] [risk:RC-09.threshold@2024-12] [risk:RC-09.net_burn@2024-12] against a threshold of 3.0 months. At the trailing 3-month net burn of 50,624 USD/month, the closing cash balance funds 5.4 months of operations (policy floor 3 months). No new financing is assumed. Check: Agree the revolver capacity and the trigger point for drawing it.
- **[HIGH] RC-11 — Profit plan is offside** (budget control). Observed -53.3% [risk:RC-11@2024-01..2024-12] [risk:RC-11.threshold@2024-01..2024-12] against a threshold of -10.0%. Year-to-date EBIT is 53.3% below plan for 2024, driven by both the volume shortfall and the gross-margin miss. Check: Rephase discretionary opex and capex to protect the full-year profit number.
- **[MEDIUM] RC-03 — Gross margin is being compressed** (profitability). Observed +3.3pp [risk:RC-03@2024-12] [risk:RC-03.threshold@2024-12] [risk:RC-03.margin_now@2024-12] [risk:RC-03.margin_year_ago@2024-12] against a threshold of +2.0pp. Gross margin has fallen year-on-year as material and wage inflation is not being passed through to price. Check: Quantify the price increase needed to restore the margin, then test it in the simulator.
- **[LOW] RC-12 — Revenue is concentrated in non-USD currencies** (market). Observed 45.1% [risk:RC-12@2024-01..2024-12] [risk:RC-12.threshold@2024-01..2024-12] [risk:RC-12.non_usd_share@2024-01..2024-12] against a threshold of 50.0%. 100% of trailing twelve-month revenue is booked in local currencies; VND alone is 45%. Translating back to USD adds unhedged volatility on top of the operating result. Check: Review hedged ratio and the currency of the debt stack.
- **[LOW] RC-14 — Funding costs remain elevated** (market). Observed -0.5pp [risk:RC-14@2024-12] [risk:RC-14.threshold@2024-12] [risk:RC-14.policy_rate@2024-12] against a threshold of +1.0pp. The US effective policy rate stands at 4.83% (2024-12-01), -0.5pp versus a year earlier. Floating-rate debt re-prices with it. Values shown are local DEMO fixtures, not live observations. Check: Refresh the market series and re-test the interest sensitivity in the simulator.

Known data gaps (not measurable with the shipped dataset):
- Customer concentration and single-customer dependency are not modelled (no customer-level data).
- Covenant headroom is not modelled (no facility agreement terms shipped).
- Inventory ageing and obsolescence are not modelled (only aggregate inventory value).

## 7. Recommended Actions

Actions are derived from the fired risk rules. They are operational checks, not investment advice.

- **RC-01** Re-test the covenant headroom with the financing bank before the next drawdown.
- **RC-02** Re-run the debt schedule and confirm the amortisation calendar still matches plan.
- **RC-04** Split the margin walk into price, mix, material and overhead before the board pack.
- **RC-05** Separate the working-capital drain from the earnings drain before deciding on financing.
- **RC-06** Age the receivables ledger and escalate the oldest overdue accounts.
- **RC-07** Decide explicitly which lever to pull: collection, stock cover or supplier terms.
- **RC-08** Model the liquidity runway under a no-new-financing assumption.
- **RC-09** Agree the revolver capacity and the trigger point for drawing it.
- **RC-11** Rephase discretionary opex and capex to protect the full-year profit number.
- **RC-03** Quantify the price increase needed to restore the margin, then test it in the simulator.
- **RC-12** Review hedged ratio and the currency of the debt stack.
- **RC-14** Refresh the market series and re-test the interest sensitivity in the simulator.

Nothing in this report is a buy/sell recommendation, a credit rating or an audit opinion.

## 8. Assumptions & Sources

- **As-of date:** 2024-12; **currency:** USD; **period covered:** 2024-01..2024-12 (run-rate) plus 12 projected months.
- **Data classification:** SYNTHETIC DEMO DATA. The company is fictional, the seeded dataset is generated with a fixed seed, and the market values in fixture mode are hand-built demo values.
- **Model assumptions:** Baseline = trailing twelve months run-rate repeated by calendar month (seasonality preserved), NOT the budget. Materials are priced in USD, labour and overhead in local currency. Operating expenses are treated as fixed within the horizon. Debt is held flat with no new financing or amortisation. Taxes accrue at 22% of positive pre-tax profit. Working-capital days are held at the closing level plus any user-specified delta. [model:tax_rate@v1]
- **Methodology:** `docs/financial-methodology.md` (formulas, units, period conventions, zero-denominator and missing-data policy).
- **Risk rules:** `docs/risk-rules.md` (thresholds, severities and scoring).

| Dataset | Kind | Origin | Rows | Synthetic |
| --- | --- | --- | --- | --- |
| Monthly financial actuals | synthetic_seed | app/data/synthetic.py (seed 20260101) | 72 | yes |
| Monthly budget layer | synthetic_seed | app/data/synthetic.py (seed 20260101) | 24 | yes |
| Macro market fixtures | market_fixture | app/data/synthetic.py + services/api/app/market/fixtures.py | 168 | yes |

Market data provenance:
- DFF: local demo fixture (NOT live data); units=Percent; frequency=daily; latest=2024-12-01; fetched_at=2026-01-01T00:00:00+00:00; source=https://fred.stlouisfed.org/series/DFF
- PPIACO: local demo fixture (NOT live data); units=Index 1982=100; frequency=monthly; latest=2024-12-01; fetched_at=2026-01-01T00:00:00+00:00; source=https://fred.stlouisfed.org/series/PPIACO
- DEXTHUS: local demo fixture (NOT live data); units=Thai Baht to One U.S. Dollar; frequency=daily; latest=2024-12-01; fetched_at=2026-01-01T00:00:00+00:00; source=https://fred.stlouisfed.org/series/DEXTHUS
- DTWEXBGS: local demo fixture (NOT live data); units=Index Jan 2006=100; frequency=daily; latest=2024-12-01; fetched_at=2026-01-01T00:00:00+00:00; source=https://fred.stlouisfed.org/series/DTWEXBGS

Recomputation: every figure above can be regenerated with `python data/synthetic/generate.py --write` followed by `python -m pytest services/api/tests`.
