/**
 * Overview — the one-screen answer to "how are we doing, and what is on fire?".
 *
 * Data: `/health` (dataset identity, served by the shell), `/metrics?month=` (KPI pack),
 * `/metrics/series` (trend), `/risk/register` (top risks + data gaps).
 */

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api, errorMessage } from "@/api/client";
import type { CompanyProfileResponse, MetricSet, MonthlyPoint, PeriodSeries, RiskRegister } from "@/api/types";
import { useHealth } from "@/components/AppLayout";
import { PageHeader } from "@/components/AppLayout";
import { Chart } from "@/components/Chart";
import { EmptyState, ErrorState, Skeleton, SkeletonTable } from "@/components/Feedback";
import { KpiCard } from "@/components/KpiCard";
import { RegionFilter } from "@/components/RegionFilter";
import { SeverityBadge, StatusBadge } from "@/components/StatusBadge";
import { buildSeriesChart } from "@/lib/charts";
import { extractSeries, lastDelta, metric, riskCited } from "@/lib/data";
import { formatNumber, formatPct, formatPeriod, formatValue, NOT_AVAILABLE, severityRank } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";
import { useFilters } from "@/lib/useFilters";

const TREND_MONTHS = 12;

const KPI_METRICS: { id: string; delta?: boolean }[] = [
  { id: "revenue", delta: true },
  { id: "gross_margin" },
  { id: "ebit", delta: true },
  { id: "operating_margin" },
  { id: "dso_days" },
  { id: "cash", delta: true },
  { id: "cash_conversion_cycle_days" },
  { id: "interest_coverage" },
];

export default function Overview() {
  const { health } = useHealth();
  const filters = useFilters();
  const { regions, setRegions, month, range } = filters;
  const [showAllGaps, setShowAllGaps] = useState(false);

  const window = range(TREND_MONTHS);
  const regionKey = regions.join(",");

  const metricsState = useAsync<MetricSet>(
    (signal) => api.metrics({ month: month ?? undefined, regions }, signal),
    [month, regionKey],
  );

  const seriesState = useAsync<PeriodSeries>(
    (signal) => api.series({ start: window?.start, end: window?.end, regions, limit: TREND_MONTHS }, signal),
    [window?.start, window?.end, regionKey],
  );

  const riskState = useAsync<RiskRegister>(
    (signal) => api.riskRegister({ month: month ?? undefined, regions }, signal),
    [month, regionKey],
  );

  const companyState = useAsync<CompanyProfileResponse>((signal) => api.company(signal), []);
  const profile = companyState.data?.profile ?? null;

  const points: MonthlyPoint[] = seriesState.data?.points ?? [];
  const revenue = useMemo(() => extractSeries(points, "revenue_usd"), [points]);
  const ebit = useMemo(() => extractSeries(points, "ebit_usd"), [points]);
  const grossMargin = useMemo(() => extractSeries(points, "gross_margin_pct"), [points]);
  const operatingMargin = useMemo(() => extractSeries(points, "operating_margin_pct"), [points]);
  const cash = useMemo(() => extractSeries(points, "cash_usd"), [points]);

  const periodLabel = metricsState.data?.period ?? month ?? "";
  const values = metricsState.data?.values;

  const trendChart = useMemo(
    () =>
      buildSeriesChart({
        title: "收入 / EBIT / 营业利润率趋势",
        unit: "左轴 千美元（USD ÷ 1000），右轴小数比例（×100 显示为 %）",
        period: window ? `${window.start}..${window.end}` : "",
        labels: revenue.labels,
        note: revenue.missingMonths.length ? `缺失月份不画零：${revenue.missingMonths.join(", ")}` : undefined,
        series: [
          { name: "收入（千美元）", data: revenue.values.map((value) => (value === null ? null : value / 1000)), type: "bar" },
          { name: "EBIT（千美元）", data: ebit.values.map((value) => (value === null ? null : value / 1000)), type: "bar" },
          { name: "营业利润率（右轴）", data: operatingMargin.values, type: "line", yAxisIndex: 1 },
        ],
        yAxisName: "千美元",
        y2AxisName: "利润率",
        valueFormat: (value) => (value === null ? NOT_AVAILABLE : formatNumber(value, 1)),
      }),
    [revenue, ebit, operatingMargin, window],
  );

  const marginChart = useMemo(
    () =>
      buildSeriesChart({
        title: "毛利率 / 营业利润率",
        unit: "%（API 返回小数比例，已 ×100）",
        period: window ? `${window.start}..${window.end}` : "",
        labels: grossMargin.labels,
        series: [
          { name: "毛利率", data: grossMargin.values, type: "line" },
          { name: "营业利润率", data: operatingMargin.values, type: "line" },
        ],
        yAxisName: "小数比例",
        valueFormat: (value) => (value === null ? NOT_AVAILABLE : formatPct(value)),
      }),
    [grossMargin, operatingMargin, window],
  );

  const cashChart = useMemo(
    () =>
      buildSeriesChart({
        title: "期末现金",
        unit: "USD",
        period: window ? `${window.start}..${window.end}` : "",
        labels: cash.labels,
        series: [{ name: "期末现金 USD", data: cash.values, area: true }],
        yAxisName: "USD",
      }),
    [cash, window],
  );

  const risks = riskState.data?.signals ?? [];
  const topRisks = useMemo(
    () => [...risks].sort((left, right) => severityRank(right.severity) - severityRank(left.severity)).slice(0, 3),
    [risks],
  );
  const gaps = riskState.data?.data_gaps ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="总览"
        description={
          <>
            当前期间 <span className="tnum text-ink">{formatPeriod(periodLabel)}</span>，
            数据集 <span className="text-ink">{health?.dataset.dataset_id ?? NOT_AVAILABLE}</span>。
            所有金额单位为 USD；比率为小数比例（已 ×100 显示）。
          </>
        }
        actions={<RegionFilter value={regions} onChange={setRegions} disabled={metricsState.loading} />}
      />

      {/* KPI pack ---------------------------------------------------------- */}
      {metricsState.loading ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {KPI_METRICS.map((item) => (
            <KpiCard key={item.id} loading />
          ))}
        </div>
      ) : metricsState.error ? (
        <ErrorState
          error={metricsState.error}
          message={errorMessage(metricsState.error)}
          onRetry={metricsState.reload}
          retrying={metricsState.reloading}
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {KPI_METRICS.map((item) => {
            const cited = metric(values, item.id);
            const deltaSource = item.id === "revenue" ? revenue.values : item.id === "ebit" ? ebit.values : item.id === "cash" ? cash.values : null;
            const delta = item.delta && deltaSource ? lastDelta(deltaSource) : null;
            return (
              <KpiCard
                key={item.id}
                cited={cited}
                label={item.id}
                delta={delta}
                deltaUnit="USD"
                deltaLabel="较上月"
                unavailableReason={cited ? undefined : "接口未返回该指标"}
              />
            );
          })}
        </div>
      )}

      {/* Trends ------------------------------------------------------------ */}
      <div className="grid gap-3 xl:grid-cols-2">
        <section className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="card-title">收入 / EBIT / 营业利润率</h2>
            {seriesState.data ? (
              <StatusBadge tone="neutral">粒度：月度 · {seriesState.data.points.length} 个观测</StatusBadge>
            ) : null}
          </div>
          {seriesState.loading ? (
            <Skeleton className="h-72 w-full" />
          ) : seriesState.error ? (
            <ErrorState
              error={seriesState.error}
              message={errorMessage(seriesState.error)}
              onRetry={seriesState.reload}
              retrying={seriesState.reloading}
            />
          ) : points.length === 0 ? (
            <EmptyState title="该区间无数据" description="所选月份区间内没有观测值。" />
          ) : (
            <Chart option={trendChart} height={300} ariaLabel="收入、EBIT 与营业利润率月度趋势图（单位 USD 与小数比例）" />
          )}
        </section>

        <section className="card">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="card-title">利润率与现金</h2>
            <span className="text-xs text-muted">单位：% / USD · 期间 {formatPeriod(window ? `${window.start}..${window.end}` : "")}</span>
          </div>
          {seriesState.loading ? (
            <Skeleton className="h-72 w-full" />
          ) : seriesState.error ? (
            <ErrorState error={seriesState.error} message={errorMessage(seriesState.error)} onRetry={seriesState.reload} />
          ) : points.length === 0 ? (
            <EmptyState title="该区间无数据" />
          ) : (
            <div className="space-y-2">
              <Chart option={marginChart} height={150} ariaLabel="毛利率与营业利润率趋势图（单位：小数比例）" testId="chart-margin" />
              <Chart option={cashChart} height={150} ariaLabel="期末现金趋势图（单位：USD）" testId="chart-cash" />
            </div>
          )}
        </section>
      </div>

      {/* Risks ------------------------------------------------------------- */}
      <div className="grid gap-3 xl:grid-cols-3">
        <section className="card xl:col-span-2">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="card-title">前三大风险信号</h2>
            <Link className="link text-xs" to="/risk">
              查看完整风险台账 →
            </Link>
          </div>
          {riskState.loading ? (
            <SkeletonTable rows={3} columns={3} />
          ) : riskState.error ? (
            <ErrorState
              error={riskState.error}
              message={errorMessage(riskState.error)}
              onRetry={riskState.reload}
              retrying={riskState.reloading}
            />
          ) : topRisks.length === 0 ? (
            <EmptyState title="本期未触发风险信号" description="规则引擎在当前期间没有触发任何阈值。" />
          ) : (
            <ul className="space-y-2">
              {topRisks.map((signal) => (
                <li key={signal.signal_id} className="rounded-md border border-line bg-surface-3/40 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <SeverityBadge severity={signal.severity} />
                    <span className="font-mono text-xs text-muted">{signal.signal_id}</span>
                    <span className="text-sm font-medium">{signal.title}</span>
                    <span className="tnum ml-auto text-xs text-muted">
                      观测 {formatValue(riskCited(signal, signal.observed_value, signal.unit, "规则引擎未提供观测值"))} / 阈值{" "}
                      {formatValue(riskCited(signal, signal.threshold, signal.threshold_unit, "该信号没有数值阈值"))}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted">{signal.detail}</p>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card">
          <h2 className="card-title mb-2">数据缺口说明</h2>
          {riskState.loading ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          ) : riskState.error ? (
            <ErrorState error={riskState.error} message={errorMessage(riskState.error)} onRetry={riskState.reload} />
          ) : gaps.length === 0 ? (
            <EmptyState title="无数据缺口" description="规则引擎未报告缺失输入，或所有信号都有完整输入。" />
          ) : (
            <>
              <ul className="list-disc space-y-1 pl-4 text-xs text-muted">
                {(showAllGaps ? gaps : gaps.slice(0, 5)).map((gap) => (
                  <li key={gap}>{gap}</li>
                ))}
              </ul>
              {gaps.length > 5 ? (
                <button type="button" className="btn mt-2" onClick={() => setShowAllGaps((value) => !value)}>
                  {showAllGaps ? "收起" : `展开全部 ${gaps.length} 条`}
                </button>
              ) : null}
            </>
          )}
          {metricsState.data ? (
            <p className="mt-3 text-[11px] text-muted">
              口径：{metricsState.data.scope.regions === "ALL" || !regions.length ? "全部区域" : regions.join(" / ")} ·{" "}
              币种 {metricsState.data.currency} · 合成数据 {String(metricsState.data.synthetic)}
            </p>
          ) : null}
        </section>
      </div>

      {/* Dataset identity --------------------------------------------------- */}
      <section className="card">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="card-title">数据集与公司口径</h2>
          <StatusBadge tone="info">GET /meta/company</StatusBadge>
        </div>
        {companyState.loading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        ) : companyState.error ? (
          <ErrorState
            error={companyState.error}
            message={errorMessage(companyState.error)}
            onRetry={companyState.reload}
            retrying={companyState.reloading}
          />
        ) : !profile ? (
          <EmptyState title="没有公司档案" description="/meta/company 未返回 profile。" />
        ) : (
          <dl className="grid gap-3 text-xs sm:grid-cols-2 xl:grid-cols-4">
            <div>
              <dt className="label">公司</dt>
              <dd className="text-ink">
                {profile.display_name_zh ?? profile.display_name}
                <div className="text-muted">{profile.display_name}</div>
              </dd>
            </div>
            <div>
              <dt className="label">行业</dt>
              <dd className="text-ink">{profile.industry}</dd>
            </div>
            <div>
              <dt className="label">报告币种 / 本币</dt>
              <dd className="text-ink">
                {profile.reporting_currency} · {profile.local_currencies.join(" / ")}
              </dd>
            </div>
            <div>
              <dt className="label">区间</dt>
              <dd className="tnum text-ink">
                {formatPeriod(profile.period_range.start)} – {formatPeriod(profile.period_range.end)}（
                {profile.period_range.months} 个月，财年结束 {profile.fiscal_year_end}）
              </dd>
            </div>
            <div className="sm:col-span-2 xl:col-span-3">
              <dt className="label">合并口径说明</dt>
              <dd className="text-muted">{profile.consolidation_note}</dd>
            </div>
            <div>
              <dt className="label">区域</dt>
              <dd className="text-ink">
                {profile.regions.map((item) => `${item.code}(${item.currency})`).join(" · ")}
              </dd>
            </div>
            <div className="sm:col-span-2 xl:col-span-4">
              <dt className="label">免责声明</dt>
              <dd className="text-muted">{profile.disclaimer}</dd>
            </div>
          </dl>
        )}
      </section>
    </div>
  );
}
