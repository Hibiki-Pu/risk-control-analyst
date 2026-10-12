# Risk rules (risk register)

The risk register is produced by `services/api/app/finance/risk.py`. Rules are
deterministic, documented and testable. A rule that cannot be evaluated is
reported as a **data gap**, never as a silent pass.

* Response shape: `GET /api/v1/risk/register?month=YYYY-MM&regions[]=SG`
* Every signal carries `observed_value`, `unit`, `threshold`, `threshold_unit`,
  `metric_ids`, `source_ids`, `supporting` values and a `recommended_check`.
* Thresholds are configuration, not magic numbers: `.env` keys
  `RCA_RISK_INTEREST_COVERAGE_MIN`, `RCA_RISK_DSO_MAX_DAYS`,
  `RCA_RISK_CASH_RUNWAY_MIN_MONTHS`, `RCA_RISK_NET_LEVERAGE_MAX`.

## Thresholds used by the shipped demo

| Setting | Default | Meaning |
| --- | --- | --- |
| `risk_interest_coverage_min` | 2.00x | EBIT / interest expense floor |
| `risk_dso_max_days` | 60 days | Receivables collection limit (average-receivables basis) |
| `risk_cash_runway_min_months` | 3 months | Liquidity floor under the trailing burn rate |
| `risk_net_leverage_max` | 3.00x | Net debt / annualised EBITDA ceiling |
| `gross_margin_drop_pp` | 2.0 pp | Year-on-year margin deterioration that triggers review |
| `ccc_increase_days` | 20 days | Year-on-year cash-conversion-cycle widening |
| `cash_decline_pct` | 35% | Year-on-year cash erosion |
| `budget_revenue_variance_pct` | −5% | Year-to-date revenue behind plan |
| `budget_ebit_variance_pct` | −10% | Year-to-date EBIT behind plan |

## Rules

| ID | Category | Fires when | Severity ladder | Evidence |
| --- | --- | --- | --- | --- |
| RC-01 | leverage | Interest coverage below the floor | `< 1.5x` critical · `< 2.0x` high · `< 3.0x` medium · else no signal | `interest_coverage` |
| RC-02 | leverage | Net leverage above the ceiling | `> 3.9x` high · `> 3.0x` medium | `net_leverage`, `net_debt`, `ebitda` |
| RC-03 | profitability | Gross margin down year-on-year | `≥ 4.0pp` high · `≥ 2.0pp` medium | `gross_margin` + supporting current/prior-year margin |
| RC-04 | profitability | Operating margin below 5% | `< 2%` critical · `< 5%` high | `operating_margin`, `ebit` |
| RC-05 | liquidity | Negative operating cash flow in the trailing 6 months | `≥ 3` consecutive high · `≥ 2` medium · else low | `operating_cash_flow`, one source id per negative month |
| RC-06 | working capital | DSO above the limit | `> 69` days high · `> 60` days medium | `dso_days`, `dso_days_ending` |
| RC-07 | working capital | Cash conversion cycle widened year-on-year | `≥ 20` days high · `≥ 10` days medium | `cash_conversion_cycle_days`, `dio_days`, `dpo_days` |
| RC-08 | liquidity | Cash down year-on-year | `≥ 55%` high · `≥ 35%` medium | `cash`, `free_cash_flow` + supporting balances |
| RC-09 | liquidity | Trailing 3-month net burn funds fewer than nine months | `< 3` months critical · `< 9` months high | `cash`, `operating_cash_flow`, `free_cash_flow` + supporting burn |
| RC-10 | budget control | Year-to-date revenue more than 5% behind plan | medium | `revenue_variance_pct` |
| RC-11 | budget control | Year-to-date EBIT more than 10% behind plan | high | `ebit_variance_pct` |
| RC-12 | market | More than half of trailing revenue is booked in non-reporting currencies | `> 50%` medium · else low | `revenue_share_<ccy>` + supporting non-USD share |
| RC-13 | data quality | Source cells missing in the reported month | low | `dio_days`, `cash_conversion_cycle_days` |
| RC-14 | market | Policy-rate move over twelve months | `≥ +1.0pp` medium · else low | `market:DFF@<date>` + supporting rate level |

## Scoring

```
score = min(100, Σ weight(severity))          weight: critical 10, high 6, medium 3, low 1, info 0
level = critical if score ≥ 20 · high if ≥ 12 · medium if ≥ 5 · else low
```

Signals are sorted by severity (critical → high → medium → low → info). A rule
that would only produce an `info` outcome **does not emit a signal** — a healthy
metric belongs in the KPI pack, not in the risk register.

## Deliberate non-detection (declared data gaps)

The register always reports what it *cannot* see, so an empty category is never
mistaken for safety:

* customer concentration and single-customer dependency (no customer-level data);
* covenant headroom (no facility agreement terms);
* inventory ageing and obsolescence (only aggregate inventory value is modelled).

Additional gaps appear dynamically: missing history, an unavailable denominator,
or a burn rate that does not exist because the company generated cash.

## Why these rules

The set is deliberately narrow and each rule maps to a decision a finance team
actually makes: refinance (RC-01/02), reprice (RC-03/04), collect (RC-06/07),
fund (RC-05/08/09), re-plan (RC-10/11), hedge (RC-12/14) and fix the data
(RC-13). No rule produces a buy/sell recommendation or a credit rating.
