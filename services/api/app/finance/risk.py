"""Rule-based risk register.

The rules are deterministic, documented and testable. Each rule either fires
with an observed value and a threshold, or is skipped — and a skipped rule is
reported as a data gap rather than silently passing.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.core.config import Settings, get_settings
from app.finance.engine import FinancialEngine
from app.finance.formulas import safe_div
from app.schemas import RiskRegister, RiskSignal, SupportingValue

SEVERITY_SCORE = {"critical": 10.0, "high": 6.0, "medium": 3.0, "low": 1.0, "info": 0.0}


@dataclass(frozen=True)
class Thresholds:
    interest_coverage_min: float = 2.0
    dso_max_days: float = 60.0
    cash_runway_min_months: float = 3.0
    net_leverage_max: float = 3.0
    gross_margin_drop_pp: float = 2.0
    ccc_increase_days: float = 20.0
    cash_decline_pct: float = 0.35
    budget_revenue_variance_pct: float = -0.05
    budget_ebit_variance_pct: float = -0.10

    @classmethod
    def from_settings(cls, settings: Settings) -> "Thresholds":
        return cls(
            interest_coverage_min=settings.risk_interest_coverage_min,
            dso_max_days=settings.risk_dso_max_days,
            cash_runway_min_months=settings.risk_cash_runway_min_months,
            net_leverage_max=settings.risk_net_leverage_max,
        )


class RiskEngine:
    """Builds the risk register for the latest period."""

    def __init__(self, engine: FinancialEngine, thresholds: Thresholds | None = None, settings: Settings | None = None):
        self.engine = engine
        self.settings = settings or get_settings()
        self.thresholds = thresholds or Thresholds.from_settings(self.settings)

    # ------------------------------------------------------------------
    def _signal(
        self,
        signal_id: str,
        category: str,
        severity: str,
        title: str,
        detail: str,
        *,
        period: str,
        observed: float | None,
        unit: str,
        threshold: float | None,
        threshold_unit: str,
        direction: str,
        metric_ids: list[str],
        source_ids: list[str],
        recommended_check: str,
        supporting: list[SupportingValue] | None = None,
    ) -> RiskSignal:
        return RiskSignal(
            signal_id=signal_id,
            category=category,  # type: ignore[arg-type]
            severity=severity,  # type: ignore[arg-type]
            title=title,
            detail=detail,
            period=period,
            observed_value=None if observed is None else round(float(observed), 4),
            unit=unit,
            threshold=threshold,
            threshold_unit=threshold_unit,
            direction=direction,  # type: ignore[arg-type]
            metric_ids=metric_ids,
            source_ids=source_ids,
            supporting=supporting or [],
            recommended_check=recommended_check,
            synthetic=self.engine.synthetic,
        )

    # ------------------------------------------------------------------
    def build(self, month: str | None = None, regions: list[str] | None = None) -> RiskRegister:
        month = month or self.engine.as_of
        frame = self.engine.monthly_frame(regions)
        latest = frame.loc[month]
        index = self.engine.months.index(month)
        year_ago = self.engine.months[index - 12] if index >= 12 else None

        monthly_metrics = self.engine.metrics(months=[month], regions=regions)
        ttm_months = self.engine.months[max(0, index - 11): index + 1]
        ttm_metrics = self.engine.metrics(months=ttm_months, regions=regions)
        sources = [f"actual:monthly_financials@{month}"]
        signals: list[RiskSignal] = []
        data_gaps: list[str] = []

        def metric_value(metric_id: str, pack=None) -> float | None:
            cited = (pack or monthly_metrics).values.get(metric_id)
            return None if cited is None else cited.value

        # 1. Interest coverage -------------------------------------------------
        coverage = metric_value("interest_coverage")
        if coverage is None:
            data_gaps.append("Interest coverage could not be computed for the latest month.")
        else:
            if coverage < 1.5:
                severity = "critical"
            elif coverage < self.thresholds.interest_coverage_min:
                severity = "high"
            elif coverage < self.thresholds.interest_coverage_min * 1.5:
                severity = "medium"
            else:
                severity = "info"
            if severity == "info":
                # A healthy coverage ratio is not a risk signal; it is reported
                # through the metric pack instead of cluttering the register.
                pass
            else:
                signals.append(
                    self._signal(
                        "RC-01",
                        "leverage",
                        severity,
                        "Interest coverage is thin",
                        "EBIT coverage of interest has fallen to the policy floor, so every further rate step or "
                        "margin slip flows straight into equity value.",
                        period=month,
                        observed=coverage,
                        unit="x",
                        threshold=self.thresholds.interest_coverage_min,
                        threshold_unit="x",
                        direction="below",
                        metric_ids=["interest_coverage"],
                        source_ids=sources,
                        recommended_check="Re-test the covenant headroom with the financing bank before the next drawdown.",
                    )
                )

        # 2. Net leverage ------------------------------------------------------
        leverage = metric_value("net_leverage")
        if leverage is None:
            data_gaps.append("Net debt / EBITDA is unavailable (EBITDA is zero or negative).")
        elif leverage > self.thresholds.net_leverage_max:
            signals.append(
                self._signal(
                    "RC-02",
                    "leverage",
                    "high" if leverage > self.thresholds.net_leverage_max * 1.3 else "medium",
                    "Net leverage above policy",
                    "Net debt to annualised EBITDA has moved above the policy ceiling. Deleveraging now depends "
                    "on an EBITDA recovery rather than on cash generation.",
                    period=month,
                    observed=leverage,
                    unit="x",
                    threshold=self.thresholds.net_leverage_max,
                    threshold_unit="x",
                    direction="above",
                    metric_ids=["net_leverage", "net_debt", "ebitda"],
                    source_ids=sources,
                    recommended_check="Re-run the debt schedule and confirm the amortisation calendar still matches plan.",
                )
            )

        # 3. Gross-margin trend ------------------------------------------------
        current_gm = frame.loc[month, "gross_margin"]
        prior_gm = frame.loc[year_ago, "gross_margin"] if year_ago else None
        if pd.isna(current_gm) or prior_gm is None or pd.isna(prior_gm):
            data_gaps.append("Gross-margin trend needs 12 months of history; not enough periods available.")
        else:
            drop_pp = (float(prior_gm) - float(current_gm)) * 100.0
            severity = "high" if drop_pp >= 2 * self.thresholds.gross_margin_drop_pp else (
                "medium" if drop_pp >= self.thresholds.gross_margin_drop_pp else "info"
            )
            if drop_pp > 0 and severity != "info":
                signals.append(
                    self._signal(
                        "RC-03",
                        "profitability",
                        severity,
                        "Gross margin is being compressed",
                        "Gross margin has fallen year-on-year as material and wage inflation is not being passed "
                        "through to price.",
                        period=month,
                        observed=drop_pp,
                        unit="pp",
                        threshold=self.thresholds.gross_margin_drop_pp,
                        threshold_unit="pp",
                        direction="above",
                        metric_ids=["gross_margin"],
                        source_ids=sources,
                        supporting=[
                            SupportingValue(key="margin_now", label="Gross margin now", value=float(current_gm), unit="pct"),
                            SupportingValue(key="margin_year_ago", label="Gross margin a year ago", value=float(prior_gm), unit="pct"),
                        ],
                        recommended_check="Quantify the price increase needed to restore the margin, then test it in the simulator.",
                    )
                )

        # 4. Operating margin level -------------------------------------------
        operating_margin = metric_value("operating_margin")
        if operating_margin is None:
            data_gaps.append("Operating margin is unavailable for the latest month.")
        elif operating_margin < 0.05:
            signals.append(
                self._signal(
                    "RC-04",
                    "profitability",
                    "critical" if operating_margin < 0.02 else "high",
                    "Operating margin close to break-even",
                    "EBIT margin has fallen below the monitoring line. With interest and tax still to be served, "
                    "the group has very little room for a demand or cost shock.",
                    period=month,
                    observed=operating_margin,
                    unit="pct",
                    threshold=0.05,
                    threshold_unit="pct",
                    direction="below",
                    metric_ids=["operating_margin", "ebit"],
                    source_ids=sources,
                    recommended_check="Split the margin walk into price, mix, material and overhead before the board pack.",
                )
            )

        # 5. Operating cash-flow streak ---------------------------------------
        trailing = frame.loc[:month, "operating_cash_flow"].tail(6)
        negative_months = [m for m, value in trailing.items() if pd.notna(value) and value < 0]
        streak = 0
        for value in reversed(trailing.tolist()):
            if pd.notna(value) and value < 0:
                streak += 1
            else:
                break
        if negative_months:
            severity = "high" if streak >= 3 else ("medium" if streak >= 2 else "low")
            signals.append(
                self._signal(
                    "RC-05",
                    "liquidity",
                    severity,
                    "Operating cash flow is negative",
                    f"Operating cash flow was negative in {len(negative_months)} of the last 6 months "
                    f"({streak} consecutive). The proxy is EBIT + D&A - cash taxes - change in net working capital; "
                    "the drain is working capital, not accounting losses.",
                    period=month,
                    observed=float(-streak),
                    unit="months",
                    threshold=3.0,
                    threshold_unit="months",
                    direction="above",
                    metric_ids=["operating_cash_flow"],
                    source_ids=sources + [f"actual:monthly_financials@{m}" for m in negative_months],
                    recommended_check="Separate the working-capital drain from the earnings drain before deciding on financing.",
                )
            )

        # 6. DSO ---------------------------------------------------------------
        dso = metric_value("dso_days")
        if dso is None:
            data_gaps.append("DSO is unavailable (revenue is zero or receivables data is missing).")
        elif dso > self.thresholds.dso_max_days:
            signals.append(
                self._signal(
                    "RC-06",
                    "working_capital",
                    "high" if dso > self.thresholds.dso_max_days * 1.15 else "medium",
                    "Receivables collection is slipping",
                    f"DSO (average receivables basis) is {dso:.1f} days against a policy limit of "
                    f"{self.thresholds.dso_max_days:.0f} days. Receivables are financing the customers.",
                    period=month,
                    observed=dso,
                    unit="days",
                    threshold=self.thresholds.dso_max_days,
                    threshold_unit="days",
                    direction="above",
                    metric_ids=["dso_days", "dso_days_ending"],
                    source_ids=sources,
                    recommended_check="Age the receivables ledger and escalate the oldest overdue accounts.",
                )
            )

        # 7. Cash conversion cycle --------------------------------------------
        ccc = frame.loc[month, "cash_conversion_cycle_days"]
        ccc_prior = frame.loc[year_ago, "cash_conversion_cycle_days"] if year_ago else None
        if pd.isna(ccc) or ccc_prior is None or pd.isna(ccc_prior):
            data_gaps.append("Cash conversion cycle trend needs 12 months of history and complete inventory data.")
        else:
            increase = float(ccc) - float(ccc_prior)
            if increase >= self.thresholds.ccc_increase_days / 2:
                signals.append(
                    self._signal(
                        "RC-07",
                        "working_capital",
                        "high" if increase >= self.thresholds.ccc_increase_days else "medium",
                        "Cash conversion cycle is lengthening",
                        f"The cycle widened by {increase:.1f} days year-on-year to {float(ccc):.1f} days "
                        "(DSO + DIO - DPO). Longer collection and higher stock more than offset slower supplier payments.",
                        period=month,
                        observed=increase,
                        unit="days",
                        threshold=self.thresholds.ccc_increase_days,
                        threshold_unit="days",
                        direction="above",
                        metric_ids=["cash_conversion_cycle_days", "dio_days", "dpo_days"],
                        source_ids=sources,
                        supporting=[
                            SupportingValue(key="cycle_now", label="Cash conversion cycle now", value=float(ccc), unit="days"),
                        ],
                        recommended_check="Decide explicitly which lever to pull: collection, stock cover or supplier terms.",
                    )
                )

        # 8. Cash trend and runway --------------------------------------------
        cash_now = metric_value("cash")
        cash_then = float(frame.loc[year_ago, "cash"]) if year_ago else None
        if cash_now is None or cash_then is None or cash_then == 0:
            data_gaps.append("Cash trend needs 12 months of history.")
        else:
            decline = (cash_then - cash_now) / abs(cash_then)
            if decline >= self.thresholds.cash_decline_pct:
                signals.append(
                    self._signal(
                        "RC-08",
                        "liquidity",
                        "high" if decline >= 0.55 else "medium",
                        "Cash balance is eroding",
                        "Cash has fallen sharply year-on-year: capex and the working-capital build are consuming "
                        "the buffer that previously funded operations.",
                        period=month,
                        observed=decline,
                        unit="pct",
                        threshold=self.thresholds.cash_decline_pct,
                        threshold_unit="pct",
                        direction="above",
                        metric_ids=["cash", "free_cash_flow"],
                        source_ids=sources,
                        supporting=[
                            SupportingValue(key="cash_now", label="Closing cash", value=float(cash_now), unit="USD"),
                            SupportingValue(key="cash_year_ago", label="Cash a year ago", value=float(cash_then), unit="USD"),
                        ],
                        recommended_check="Model the liquidity runway under a no-new-financing assumption.",
                    )
                )

        burn_window = frame.loc[:month, ["operating_cash_flow", "capex"]].tail(3)
        net_burn = float(-(burn_window["operating_cash_flow"] - burn_window["capex"]).mean())
        runway = safe_div(cash_now, net_burn if net_burn > 0 else None, label="monthly net cash burn")
        if cash_now is None:
            data_gaps.append("Cash runway is unavailable (cash balance missing).")
        elif net_burn <= 0:
            data_gaps.append(
                "Cash runway is not applicable: the last 3 months generated cash, so there is no burn rate to divide by."
            )
        else:
            runway_months = runway.value
            if runway_months is not None and runway_months < self.thresholds.cash_runway_min_months * 3:
                severity = "critical" if runway_months < self.thresholds.cash_runway_min_months else "high"
                signals.append(
                    self._signal(
                        "RC-09",
                        "liquidity",
                        severity,
                        "Cash runway covers less than nine months",
                        f"At the trailing 3-month net burn of {net_burn:,.0f} {self.engine.currency}/month, the "
                        f"closing cash balance funds {runway_months:.1f} months of operations (policy floor "
                        f"{self.thresholds.cash_runway_min_months:.0f} months). No new financing is assumed.",
                        period=month,
                        observed=runway_months,
                        unit="months",
                        threshold=self.thresholds.cash_runway_min_months,
                        threshold_unit="months",
                        direction="below",
                        metric_ids=["cash", "operating_cash_flow", "free_cash_flow"],
                        source_ids=sources,
                        supporting=[
                            SupportingValue(key="net_burn", label="Trailing 3-month net burn", value=net_burn, unit="USD"),
                        ],
                        recommended_check="Agree the revolver capacity and the trigger point for drawing it.",
                    )
                )

        # 9. Budget discipline -------------------------------------------------
        fy_months = [m for m in self.engine.months if m.startswith(month[:4])]
        variance = self.engine.budget_variance(months=fy_months)
        revenue_variance = variance.values.get("revenue_variance_pct")
        ebit_variance = variance.values.get("ebit_variance_pct")
        if revenue_variance and revenue_variance.value is not None and revenue_variance.value < self.thresholds.budget_revenue_variance_pct:
            signals.append(
                self._signal(
                    "RC-10",
                    "budget_control",
                    "medium",
                    "Revenue plan is not being delivered",
                    f"Year-to-date revenue is {abs(revenue_variance.value) * 100:.1f}% below plan for {month[:4]}. "
                    "The plan assumed double-digit growth that the market is not providing.",
                    period=f"{fy_months[0]}..{fy_months[-1]}",
                    observed=revenue_variance.value,
                    unit="pct",
                    threshold=self.thresholds.budget_revenue_variance_pct,
                    threshold_unit="pct",
                    direction="below",
                    metric_ids=["revenue_variance_pct", "revenue"],
                    source_ids=variance.lineage,
                    recommended_check="Re-base the forecast on the current run-rate instead of the annual plan.",
                )
            )
        if ebit_variance and ebit_variance.value is not None and ebit_variance.value < self.thresholds.budget_ebit_variance_pct:
            signals.append(
                self._signal(
                    "RC-11",
                    "budget_control",
                    "high",
                    "Profit plan is offside",
                    f"Year-to-date EBIT is {abs(ebit_variance.value) * 100:.1f}% below plan for {month[:4]}, driven by "
                    "both the volume shortfall and the gross-margin miss.",
                    period=f"{fy_months[0]}..{fy_months[-1]}",
                    observed=ebit_variance.value,
                    unit="pct",
                    threshold=self.thresholds.budget_ebit_variance_pct,
                    threshold_unit="pct",
                    direction="below",
                    metric_ids=["ebit_variance_pct", "ebit"],
                    source_ids=variance.lineage,
                    recommended_check="Rephase discretionary opex and capex to protect the full-year profit number.",
                )
            )

        # 10. FX exposure ------------------------------------------------------
        fx_mix = self.engine.revenue_by_currency(ttm_months, regions)
        if not fx_mix:
            data_gaps.append("Revenue by currency is unavailable, so FX exposure cannot be assessed.")
        else:
            non_usd = {code: share for code, share in fx_mix.items() if code != self.engine.currency}
            if non_usd:
                largest = max(non_usd.items(), key=lambda item: item[1])
                signals.append(
                    self._signal(
                        "RC-12",
                        "market",
                        "medium" if largest[1] > 0.5 else "low",
                        "Revenue is concentrated in non-USD currencies",
                        f"{sum(non_usd.values()) * 100:.0f}% of trailing twelve-month revenue is booked in local "
                        f"currencies; {largest[0]} alone is {largest[1] * 100:.0f}%. Translating back to "
                        f"{self.engine.currency} adds unhedged volatility on top of the operating result.",
                        period=f"{ttm_months[0]}..{ttm_months[-1]}",
                        observed=largest[1],
                        unit="pct",
                        threshold=0.5,
                        threshold_unit="pct",
                        direction="above",
                        metric_ids=[f"revenue_share_{largest[0].lower()}"],
                        source_ids=[f"actual:monthly_financials@{m}" for m in ttm_months],
                        supporting=[
                            SupportingValue(
                                key="non_usd_share",
                                label="Share of revenue in non-USD currencies",
                                value=float(sum(non_usd.values())),
                                unit="pct",
                            )
                        ],
                        recommended_check="Review hedged ratio and the currency of the debt stack.",
                    )
                )

        # 11. Market rates -----------------------------------------------------
        market_view = self._market_rate_signal(month)
        if market_view is None:
            data_gaps.append("Market rate series unavailable, so the funding-cost backdrop could not be assessed.")
        else:
            signals.append(market_view)

        # 12. Data quality (declared gaps in the latest month) -----------------
        missing_cells = int(latest["missing_cells"])
        if missing_cells:
            signals.append(
                self._signal(
                    "RC-13",
                    "data_quality",
                    "low",
                    "Working-capital data is incomplete for the latest month",
                    f"{missing_cells} source cell(s) are missing in {month}. Affected ratios are published with a "
                    "partial-coverage flag; totals exclude the missing values.",
                    period=month,
                    observed=float(missing_cells),
                    unit="cells",
                    threshold=0.0,
                    threshold_unit="cells",
                    direction="above",
                    metric_ids=["dio_days", "cash_conversion_cycle_days"],
                    source_ids=sources,
                    recommended_check="Close the stock-count gap before the next reporting cycle.",
                )
            )

        data_gaps.extend(
            [
                "Customer concentration and single-customer dependency are not modelled (no customer-level data).",
                "Covenant headroom is not modelled (no facility agreement terms shipped).",
                "Inventory ageing and obsolescence are not modelled (only aggregate inventory value).",
            ]
        )

        score = min(100.0, sum(SEVERITY_SCORE[signal.severity] for signal in signals))
        if score >= 20:
            overall = "critical"
        elif score >= 12:
            overall = "high"
        elif score >= 5:
            overall = "medium"
        else:
            overall = "low"

        order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        signals.sort(key=lambda signal: (order[signal.severity], signal.signal_id))

        return RiskRegister(
            as_of=self.engine.as_of,
            period=month,
            synthetic=self.engine.synthetic,
            overall_level=overall,
            score=round(score, 1),
            signals=signals,
            data_gaps=data_gaps,
            lineage=[f"actual:monthly_financials@{month}", "rules:risk_engine@v1"],
        )

    # ------------------------------------------------------------------
    def _market_rate_signal(self, month: str) -> RiskSignal | None:
        """Funding-cost backdrop from the local macro fixtures / live FRED series."""
        macro = self.engine.dataset.macro
        subset = macro[macro["series_id"] == "DFF"].copy()
        if subset.empty:
            return None
        subset["observation_date"] = pd.to_datetime(subset["observation_date"])
        subset = subset.sort_values("observation_date")
        eligible = subset[subset["observation_date"] <= pd.Timestamp(f"{month}-01")]
        if len(eligible) < 13:
            return None
        latest = float(eligible["value"].iloc[-1])
        year_ago = float(eligible["value"].iloc[-13])
        change = latest - year_ago
        is_fixture = bool(eligible["is_fixture"].iloc[-1]) if "is_fixture" in eligible else True
        observed_date = eligible["observation_date"].iloc[-1].date().isoformat()
        return self._signal(
            "RC-14",
            "market",
            "medium" if change >= 1.0 else "low",
            "Funding costs remain elevated",
            f"The US effective policy rate stands at {latest:.2f}% ({observed_date}), {change:+.1f}pp versus a year "
            "earlier. Floating-rate debt re-prices with it."
            + (" Values shown are local DEMO fixtures, not live observations." if is_fixture else ""),
            period=month,
            observed=change,
            unit="pp",
            threshold=1.0,
            threshold_unit="pp",
            direction="above",
            metric_ids=["interest_expense", "interest_coverage"],
            source_ids=[f"market:DFF@{observed_date}"],
            supporting=[
                SupportingValue(key="policy_rate", label="Effective policy rate", value=latest, unit="percent_points"),
            ],
            recommended_check="Refresh the market series and re-test the interest sensitivity in the simulator.",
        )
