/**
 * P&L analysis — monthly revenue / cost / gross profit / EBIT, plus actual-versus-budget variance.
 *
 * The colour of a variance is decided by the metric's economics, not by its sign:
 * revenue and EBIT are favourable when the variance is positive, cost lines when it is negative.
 * The legend below the table states that convention explicitly.
 */

import { useMemo } from "react";

import { api, errorMessage } from "@/api/client";
import type { CitedValue, MetricSet, MonthlyPoint, PeriodSeries } from "@/api/types";
import { PageHeader } from "@/components/AppLayout";
import { Chart } from "@/components/Chart";
import { DataTable } from "@/components/DataTable";
import type { Column } from "@/components/DataTable";
import { EmptyState, ErrorState, Skeleton, SkeletonTable } from "@/components/Feedback";
import { KpiCard } from "@/components/KpiCard";
import { RegionFilter } from "@/components/RegionFilter";
import { ProvenanceBadge, StatusBadge } from "@/components/StatusBadge";
import { buildSeriesChart } from "@/lib/charts";
import { extractSeries } from "@/lib/data";
import { basisLabel, formatMoney, formatPeriod, formatValue, isPresent, NOT_AVAILABLE } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";
import { useFilters } from "@/lib/useFilters";

const TREND_MONTHS = 12;

/** Sign convention, keyed by the metric id the API uses. */
const FAVOURABLE_WHEN_POSITIVE = new Set(["revenue", "ebit", "gross_profit"]);

export interface VarianceRow {
  metricId: string;
  label: string;
  variance: CitedValue | null;
  variancePct: CitedValue | null;
  convention: "positive" | "negative" | "unknown";
  favourable: boolean | null;
}

export function varianceConvention(metricId: string): "positive" | "negative" | "unknown" {
  if (FAVOURABLE_WHEN_POSITIVE.has(metricId)) return "positive";
  if (metricId === "cogs" || metricId === "opex" || metricId === "capex" || metricId === "interest_expense") return "negative";
  return "unknown";
}

/** `null` means "cannot be judged" (missing value), never "unfavourable". */
export function isFavourable(metricId: string, variance: number | null | undefined): boolean | null {
  if (!isPresent(variance)) return null;
  const convention = varianceConvention(metricId);
  if (convention === "positive") return variance > 0 || variance === 0;
  if (convention === "negative") return variance < 0 || variance === 0;
  return null;
}

function varianceClass(metricId: string, value: number | null | undefined): string {
  const verdict = isFavourable(metricId, value);
  if (verdict === null) return "text-muted";
  if (value === 0) return "text-ink";
  return verdict ? "text-good" : "text-bad";
}

export function buildVarianceRows(values: Record<string, CitedValue> | undefined): VarianceRow[] {
  const ids = ["revenue", "cogs", "opex", "ebit", "capex", "interest_expense"];
  return ids.map((metricId) => {
    const variance = values?.[`${metricId}_variance`] ?? null;
    const variancePct = values?.[`${metricId}_variance_pct`] ?? null;
    const convention = varianceConvention(metricId);
    return {
      metricId,
      label: variance?.label ?? `${metricId} variance vs budget`,
      variance,
      variancePct,
      convention,
      favourable: isFavourable(metricId, variance?.value),
    };
  });
}

export default function PnlAnalysis() {
  const filters = useFilters();
  const { regions, setRegions, month, range } = filters;
  const regionKey = regions.join(",");
  const window = range(TREND_MONTHS);

  const seriesState = useAsync<PeriodSeries>(
    (signal) => api.series({ start: window?.start, end: window?.end, regions, limit: TREND_MONTHS }, signal),
    [window?.start, window?.end, regionKey],
  );

  // Plan comparison covers the fiscal year of the month on screen, so the table matches the
  // period the management report uses instead of silently mixing two plan years.
  const fiscalYear = (month ?? window?.end ?? "").slice(0, 4);
  const varianceState = useAsync<MetricSet>(
    (signal) =>
      api.budgetVariance(
        fiscalYear
          ? { start: `${fiscalYear}-01`, end: `${fiscalYear}-12` }
          : { month: month ?? undefined },
        signal,
      ),
    [month, fiscalYear],
  );

  const points: MonthlyPoint[] = seriesState.data?.points ?? [];
  const revenue = useMemo(() => extractSeries(points, "revenue_usd"), [points]);
  const cogs = useMemo(() => extractSeries(points, "cogs_usd"), [points]);
  const grossProfit = useMemo(() => extractSeries(points, "gross_profit_usd"), [points]);
  const ebit = useMemo(() => extractSeries(points, "ebit_usd"), [points]);
  // Derived series are memoised separately so the chart options below keep stable dependencies.
  const budgetRevenue = useMemo(() => extractSeries(points, "budget_revenue_usd"), [points]);
  const operatingMargin = useMemo(() => extractSeries(points, "operating_margin_pct"), [points]);

  const toK = useMemo(
    () => (values: (number | null)[]) => values.map((value) => (value === null ? null : value / 1000)),
    [],
  );
  const kFormat = (value: number | null) => (value === null ? NOT_AVAILABLE : formatMoney(value * 1000));

  const revenueChart = useMemo(
    () =>
      buildSeriesChart({
        title: "收入与预算收入",
        unit: "USD",
        period: window ? `${window.start}..${window.end}` : "",
        labels: revenue.labels,
        series: [
          { name: "收入", data: toK(revenue.values), type: "bar" },
          { name: "预算收入", data: toK(budgetRevenue.values), type: "line", dashed: true },
        ],
        yAxisName: "USD",
        valueFormat: kFormat,
      }),
    [revenue, budgetRevenue, toK, window],
  );

  const costChart = useMemo(
    () =>
      buildSeriesChart({
        title: "成本结构（COGS / 毛利）",
        unit: "USD",
        period: window ? `${window.start}..${window.end}` : "",
        labels: cogs.labels,
        series: [
          { name: "销售成本 COGS", data: toK(cogs.values), type: "bar" },
          { name: "毛利", data: toK(grossProfit.values), type: "bar" },
        ],
        yAxisName: "USD",
        valueFormat: kFormat,
      }),
    [cogs, grossProfit, toK, window],
  );

  const ebitChart = useMemo(
    () =>
      buildSeriesChart({
        title: "EBIT 与营业利润率",
        unit: "左轴 USD，右轴小数比例（×100 显示为 %）",
        period: window ? `${window.start}..${window.end}` : "",
        labels: ebit.labels,
        series: [
          { name: "EBIT", data: toK(ebit.values), type: "bar" },
          { name: "营业利润率（右轴）", data: operatingMargin.values, type: "line", yAxisIndex: 1 },
        ],
        yAxisName: "USD",
        y2AxisName: "利润率",
        valueFormat: kFormat,
      }),
    [ebit, operatingMargin, toK, window],
  );

  const rows = useMemo(() => buildVarianceRows(varianceState.data?.values), [varianceState.data]);
  const periodLabel = varianceState.data?.period ?? month ?? "";
  const lastPoint: MonthlyPoint | undefined = points[points.length - 1];

  const columns: Column<VarianceRow>[] = [
    {
      key: "metric",
      header: "科目",
      render: (row) => (
        <div>
          <div className="font-medium">{row.variance?.label ?? row.label}</div>
          <div className="font-mono text-[11px] text-muted">{row.metricId}</div>
        </div>
      ),
      sortValue: (row) => row.label,
    },
    {
      key: "variance",
      header: "实际 − 预算 (USD)",
      align: "right",
      render: (row) => (
        <span className={`tnum font-medium ${varianceClass(row.metricId, row.variance?.value)}`}>
          {row.variance ? formatValue(row.variance) : NOT_AVAILABLE}
        </span>
      ),
      sortValue: (row) => row.variance?.value ?? null,
    },
    {
      key: "variance_pct",
      header: "差异率",
      align: "right",
      render: (row) => (
        <span className={`tnum ${varianceClass(row.metricId, row.variance?.value)}`}>
          {row.variancePct ? formatValue(row.variancePct) : NOT_AVAILABLE}
        </span>
      ),
      sortValue: (row) => row.variancePct?.value ?? null,
    },
    {
      key: "convention",
      header: "有利方向",
      render: (row) =>
        row.convention === "positive" ? (
          <StatusBadge tone="info">正值有利</StatusBadge>
        ) : row.convention === "negative" ? (
          <StatusBadge tone="info">负值有利</StatusBadge>
        ) : (
          <StatusBadge tone="neutral">无口径</StatusBadge>
        ),
    },
    {
      key: "verdict",
      header: "判定",
      render: (row) =>
        row.favourable === null ? (
          <StatusBadge tone="neutral">无法判定</StatusBadge>
        ) : row.favourable ? (
          <StatusBadge tone="good">有利</StatusBadge>
        ) : (
          <StatusBadge tone="bad">不利</StatusBadge>
        ),
      sortValue: (row) => (row.favourable === null ? null : row.favourable ? 1 : 0),
    },
    {
      key: "note",
      header: "口径说明",
      render: (row) => <span className="text-[11px] text-muted">{row.variance?.note ?? "—"}</span>,
    },
  ];

  const hasVariance = rows.some((row) => row.variance?.status === "ok");

  return (
    <div className="space-y-6">
      <PageHeader
        title="损益分析"
        description={
          <>
            月度损益趋势与「实际 vs 预算」差异。所有金额为 USD，比率为小数比例。
            期间 <span className="tnum text-ink">{formatPeriod(window ? `${window.start}..${window.end}` : "")}</span>。
            预算层状态：{" "}
            {varianceState.data ? (
              <StatusBadge tone={hasVariance ? "good" : "warn"}>{hasVariance ? "可用" : "不可用（该数据集无预算层）"}</StatusBadge>
            ) : (
              NOT_AVAILABLE
            )}
          </>
        }
        actions={<RegionFilter value={regions} onChange={setRegions} disabled={seriesState.loading} />}
      />

      {/* Trend charts ------------------------------------------------------ */}
      {seriesState.loading ? (
        <div className="grid gap-3 xl:grid-cols-2">
          <Skeleton className="h-72 w-full" />
          <Skeleton className="h-72 w-full" />
        </div>
      ) : seriesState.error ? (
        <ErrorState error={seriesState.error} message={errorMessage(seriesState.error)} onRetry={seriesState.reload} retrying={seriesState.reloading} />
      ) : points.length === 0 ? (
        <EmptyState title="该区间无数据" description="所选月份区间内没有损益观测值。" />
      ) : (
        <div className="grid gap-3 xl:grid-cols-2">
          <section className="card">
            <h2 className="card-title mb-2">收入与预算</h2>
            <Chart option={revenueChart} height={300} ariaLabel="收入与预算收入月度对比图（单位：USD）" testId="chart-revenue" />
          </section>
          <section className="card">
            <h2 className="card-title mb-2">成本结构</h2>
            <Chart option={costChart} height={300} ariaLabel="销售成本与毛利月度图（单位：USD）" testId="chart-cost" />
          </section>
          <section className="card xl:col-span-2">
            <h2 className="card-title mb-2">EBIT 与营业利润率</h2>
            <Chart option={ebitChart} height={280} ariaLabel="EBIT 与营业利润率月度图（单位：USD 与小数比例）" testId="chart-ebit" />
          </section>
        </div>
      )}

      {/* Key P&L figures for the selected month ---------------------------- */}
      {seriesState.data && lastPoint ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard label="收入" value={lastPoint.revenue_usd} unit="USD" period={lastPoint.month} />
          <KpiCard label="销售成本 COGS" value={lastPoint.cogs_usd} unit="USD" period={lastPoint.month} />
          <KpiCard label="毛利" value={lastPoint.gross_profit_usd} unit="USD" period={lastPoint.month} />
          <KpiCard label="EBIT" value={lastPoint.ebit_usd} unit="USD" period={lastPoint.month} />
        </div>
      ) : null}

      {/* Budget variance --------------------------------------------------- */}
      <section className="card">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="card-title">预算差异（实际 − 预算）</h2>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted">期间 {formatPeriod(periodLabel)}</span>
            <StatusBadge tone="info">基准：{basisLabel("variance")}</StatusBadge>
            <ProvenanceBadge synthetic={varianceState.data?.synthetic} sourceName="合成数据集 / 预算层" />
          </div>
        </div>

        <div className="mb-3 rounded-md border border-line bg-surface-3/40 p-3 text-xs text-muted">
          <div className="font-semibold text-ink">符号约定说明</div>
          <ul className="mt-1 list-disc space-y-1 pl-4">
            <li>
              <span className="tnum text-good">绿色 = 有利</span>，<span className="tnum text-bad">红色 = 不利</span>，
              <span className="tnum text-muted">灰色 = 缺数据无法判定</span>。
            </li>
            <li>收入（revenue）、EBIT：差异为<strong>正</strong>表示实际高于预算 → 有利。</li>
            <li>成本类科目（cogs、opex、capex、interest_expense）：差异为<strong>负</strong>表示实际低于预算 → 有利。</li>
            <li>差异率 = (实际 − 预算) ÷ |预算|；预算为 0 时后端返回“口径未定义”，界面显示“不可用”而非 0。</li>
          </ul>
        </div>

        {varianceState.loading ? (
          <SkeletonTable rows={6} columns={6} />
        ) : varianceState.error ? (
          <ErrorState error={varianceState.error} message={errorMessage(varianceState.error)} onRetry={varianceState.reload} retrying={varianceState.reloading} />
        ) : (
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(row) => row.metricId}
            initialSortKey="variance"
            initialSortDir="asc"
            emptyMessage="没有可显示的差异行"
            caption="差异 = 实际 − 预算；单位 USD，差异率为小数比例。"
          />
        )}

        {!hasVariance && !varianceState.loading && !varianceState.error ? (
          <p className="mt-3 text-xs text-warn">
            当前数据集没有预算层，后端对所有差异返回 status=missing 并附说明，因此表中显示“不可用”。这是有意设计：不使用编造的计划值。
          </p>
        ) : null}
      </section>
    </div>
  );
}
