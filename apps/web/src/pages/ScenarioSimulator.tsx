/**
 * Scenario simulator — driver-based what-if analysis.
 *
 * Sliders for every `ScenarioAssumptions` field, presets loaded from the API, a run button that
 * POSTs the assumptions, and three artefacts: a scenario comparison table, monthly EBIT / cash
 * charts per scenario, and a tornado chart of the sensitivity swings. CSV export posts the same
 * payload to `/scenarios/export` and downloads the returned blob.
 */

import { useMemo, useState } from "react";

import { api, downloadText, errorMessage } from "@/api/client";
import type { ScenarioAssumptions, ScenarioPresetsResponse, ScenarioResult, ScenarioSummary } from "@/api/types";
import { PageHeader } from "@/components/AppLayout";
import { Chart } from "@/components/Chart";
import { DataTable } from "@/components/DataTable";
import type { Column } from "@/components/DataTable";
import { EmptyState, ErrorState, Skeleton, SkeletonTable } from "@/components/Feedback";
import { KpiCard } from "@/components/KpiCard";
import { StatusBadge } from "@/components/StatusBadge";
import { buildSeriesChart, buildTornadoChart } from "@/lib/charts";
import { formatDays, formatPct, formatPeriod, isPresent, NOT_AVAILABLE } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";
import { useFilters } from "@/lib/useFilters";

/* -------------------------------------------------------------------------- */
/* assumption fields                                                          */
/* -------------------------------------------------------------------------- */

interface FieldSpec {
  key: keyof ScenarioAssumptions;
  label: string;
  hint: string;
  min: number;
  max: number;
  step: number;
  /** How the raw number is shown next to the slider. */
  display: "pct" | "number";
}

const FIELDS: FieldSpec[] = [
  { key: "volume_growth_pct", label: "销量增长", hint: "年化销量增长（按 (1+g)^(i/12) 逐月复利）", min: -0.9, max: 1, step: 0.005, display: "pct" },
  { key: "price_change_pct", label: "售价变化", hint: "本地销售价格变化，自第 1 个月起生效", min: -0.9, max: 1, step: 0.005, display: "pct" },
  { key: "material_cost_change_pct", label: "材料成本变化", hint: "以 USD 计价的单位材料成本（进口）", min: -0.9, max: 1, step: 0.005, display: "pct" },
  { key: "labor_cost_change_pct", label: "人工成本变化", hint: "以本币计价的单位人工成本，按情景汇率折算", min: -0.9, max: 1, step: 0.005, display: "pct" },
  { key: "overhead_cost_change_pct", label: "制造费用变化", hint: "以本币计价的单位制造费用", min: -0.9, max: 1, step: 0.005, display: "pct" },
  { key: "opex_change_pct", label: "期间费用变化", hint: "销售/管理/研发费用（模型内视为固定费用，不随销量变化）", min: -0.9, max: 1, step: 0.005, display: "pct" },
  { key: "interest_rate_delta_pp", label: "利率变化", hint: "年化利率变动，单位为百分点（pp），债务余额保持不变", min: -10, max: 20, step: 0.25, display: "number" },
  { key: "fx_change_pct", label: "汇率变化", hint: "USD per 本币；+5% 表示本币升值（0.05）", min: -0.9, max: 1, step: 0.005, display: "pct" },
  { key: "dso_days_delta", label: "DSO 变化", hint: "在期末应收天数上增加的幅度，单位：天", min: -60, max: 120, step: 1, display: "number" },
  { key: "capex_change_pct", label: "资本开支变化", hint: "资本开支相对基准运行率的变动（影响现金流，不影响 EBIT）", min: -0.9, max: 3, step: 0.05, display: "pct" },
  {
    key: "horizon_months",
    label: "预测期（月）",
    hint: "情景月份数，1–36",
    min: 1,
    max: 36,
    step: 1,
    display: "number",
  },
];

export const DEFAULT_ASSUMPTIONS: ScenarioAssumptions = {
  horizon_months: 12,
  volume_growth_pct: 0,
  price_change_pct: 0,
  material_cost_change_pct: 0,
  labor_cost_change_pct: 0,
  overhead_cost_change_pct: 0,
  opex_change_pct: 0,
  interest_rate_delta_pp: 0,
  fx_change_pct: 0,
  dso_days_delta: 0,
  capex_change_pct: 0,
};

/* -------------------------------------------------------------------------- */
/* comparison table                                                           */
/* -------------------------------------------------------------------------- */

interface ComparisonRow {
  key: keyof ScenarioSummary;
  label: string;
  unit: "USD" | "months" | "count";
}

const COMPARISON: ComparisonRow[] = [
  { key: "revenue_usd", label: "收入 Revenue", unit: "USD" },
  { key: "ebit_usd", label: "EBIT", unit: "USD" },
  { key: "ebit_delta_usd", label: "EBIT 差异 vs 基准", unit: "USD" },
  { key: "free_cash_flow_usd", label: "自由现金流 FCF", unit: "USD" },
  { key: "ending_cash_usd", label: "期末现金", unit: "USD" },
  { key: "minimum_cash_usd", label: "最低现金", unit: "USD" },
  { key: "cash_runway_months", label: "现金跑道", unit: "months" },
  { key: "months_with_negative_cash", label: "现金为负的月份数", unit: "count" },
];

function formatComparison(value: number | null | undefined, unit: ComparisonRow["unit"]): string {
  if (!isPresent(value)) return NOT_AVAILABLE;
  switch (unit) {
    case "USD":
      return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
    case "months":
      return `${value.toFixed(1)} 个月`;
    case "count":
      return `${value} 个月`;
  }
}

export default function ScenarioSimulator() {
  const { latest } = useFilters();
  const [assumptions, setAssumptions] = useState<ScenarioAssumptions>(DEFAULT_ASSUMPTIONS);
  const [label, setLabel] = useState("自定义情景");
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<unknown>(null);
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<unknown>(null);
  const [visibleScenarios, setVisibleScenarios] = useState<string[]>([]);

  const presetsState = useAsync<ScenarioPresetsResponse>((signal) => api.scenarioPresets(signal), []);
  const presets = presetsState.data?.presets ?? [];

  const payload = useMemo(
    () => ({ assumptions, include_presets: true, label }),
    [assumptions, label],
  );

  const update = (key: keyof ScenarioAssumptions, value: number) => {
    setAssumptions((current) => ({ ...current, [key]: value }));
  };

  const applyPreset = (preset: ScenarioAssumptions) => {
    setAssumptions({ ...preset });
  };

  const run = async () => {
    setRunning(true);
    setRunError(null);
    try {
      const response = await api.runScenario(payload);
      setResult(response);
      setVisibleScenarios(response.scenarios.map((item) => item.scenario_id));
    } catch (caught) {
      setRunError(caught);
      setResult(null);
    } finally {
      setRunning(false);
    }
  };

  const exportCsv = async () => {
    setExporting(true);
    setExportError(null);
    try {
      const csv = await api.exportScenarioCsv(payload);
      downloadText(`scenarios-${latest ?? "export"}.csv`, csv, "text/csv;charset=utf-8");
    } catch (caught) {
      setExportError(caught);
    } finally {
      setExporting(false);
    }
  };

  /* ---- charts ---------------------------------------------------------- */

  const scenarioIds = result?.scenarios.map((item) => item.scenario_id) ?? [];

  const ebitChart = useMemo(() => {
    if (!result) return null;
    const anyMonthly = Object.values(result.monthly)[0] ?? [];
    const labels = anyMonthly.map((month) => month.month);
    return buildSeriesChart({
      title: "各情景月度 EBIT",
      unit: "USD",
      period: `${result.as_of} 起 ${result.horizon_months} 个月`,
      labels,
      series: scenarioIds
        .filter((id) => visibleScenarios.includes(id))
        .map((id) => ({
          name: result.scenarios.find((item) => item.scenario_id === id)?.label ?? id,
          data: (result.monthly[id] ?? []).map((month) => month.ebit_usd),
          type: "line" as const,
        })),
      yAxisName: "USD",
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, visibleScenarios]);

  const cashChart = useMemo(() => {
    if (!result) return null;
    const anyMonthly = Object.values(result.monthly)[0] ?? [];
    const labels = anyMonthly.map((month) => month.month);
    return buildSeriesChart({
      title: "各情景月末现金",
      unit: "USD",
      period: `${result.as_of} 起 ${result.horizon_months} 个月`,
      labels,
      series: scenarioIds
        .filter((id) => visibleScenarios.includes(id))
        .map((id) => ({
          name: result.scenarios.find((item) => item.scenario_id === id)?.label ?? id,
          data: (result.monthly[id] ?? []).map((month) => month.cash_usd),
          type: "line" as const,
        })),
      yAxisName: "USD",
      note: "现金为负的月份以真实负值绘制，不做截断",
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, visibleScenarios]);

  const tornado = useMemo(
    () => (result ? buildTornadoChart(result.sensitivities, result.base_period) : null),
    [result],
  );

  /* ---- table ----------------------------------------------------------- */

  const columns = useMemo<Column<ScenarioSummary>[]>(() => {
    const first: Column<ScenarioSummary> = {
      key: "scenario",
      header: "情景",
      render: (row) => (
        <div>
          <div className="font-medium">{row.label}</div>
          <div className="font-mono text-[11px] text-muted">{row.scenario_id}</div>
        </div>
      ),
      sortValue: (row) => row.label,
    };
    const rest: Column<ScenarioSummary>[] = COMPARISON.map((item) => ({
      key: item.key,
      header: item.label,
      align: "right" as const,
      render: (row: ScenarioSummary) => {
        const value = row[item.key];
        const numeric = typeof value === "number" ? value : null;
        const tone =
          item.key === "ebit_delta_usd" || item.key === "ebit_usd"
            ? numeric === null
              ? "text-muted"
              : numeric > 0
                ? "text-good"
                : numeric < 0
                  ? "text-bad"
                  : "text-ink"
            : item.key === "cash_runway_months" && numeric === null
              ? "text-muted"
              : "text-ink";
        return <span className={`tnum ${tone}`}>{formatComparison(numeric, item.unit)}</span>;
      },
      sortValue: (row: ScenarioSummary) => {
        const value = row[item.key];
        return typeof value === "number" ? value : null;
      },
    }));
    return [first, ...rest];
  }, []);

  const custom = result?.scenarios.find((item) => item.scenario_id === "custom") ?? null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="情景模拟"
        description={
          <>
            驱动因子式 what-if 模型（确定性计算，不含 LLM）。所有金额为 USD，比率为小数比例。
            基准 = 最近 12 个月实际值的运行率（按自然月重复，保留季节性），<strong>不是</strong>预算。
          </>
        }
        actions={
          <>
            <button type="button" className="btn btn-primary" onClick={run} disabled={running} data-testid="run-scenario">
              {running ? "运行中…" : "运行情景"}
            </button>
            <button type="button" className="btn" onClick={exportCsv} disabled={exporting || running} data-testid="export-csv">
              {exporting ? "导出中…" : "导出 CSV"}
            </button>
          </>
        }
      />

      {exportError ? <ErrorState title="CSV 导出失败" error={exportError} message={errorMessage(exportError)} /> : null}

      {/* Assumptions ------------------------------------------------------- */}
      <section className="card space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="card-title">假设条件</h2>
          <div className="flex flex-wrap items-center gap-2">
            <span className="label">预设</span>
            {presetsState.loading ? (
              <Skeleton className="h-6 w-40" />
            ) : presetsState.error ? (
              <span className="text-xs text-bad">预设加载失败：{errorMessage(presetsState.error)}</span>
            ) : (
              presets.map((preset) => (
                <button key={preset.scenario_id} type="button" className="btn-chip" onClick={() => applyPreset(preset.assumptions)}>
                  {preset.label}
                </button>
              ))
            )}
            <button type="button" className="btn-chip" onClick={() => setAssumptions(DEFAULT_ASSUMPTIONS)}>
              重置为全零
            </button>
          </div>
        </div>

        {presetsState.data ? (
          <ul className="grid gap-1 text-[11px] text-muted sm:grid-cols-3">
            {presets.map((preset) => (
              <li key={preset.scenario_id}>
                <span className="font-mono">{preset.scenario_id}</span> · {preset.description}
              </li>
            ))}
          </ul>
        ) : null}

        <div className="grid gap-3 md:grid-cols-2">
          {FIELDS.map((field) => {
            const value = assumptions[field.key];
            return (
              <div key={String(field.key)} className="rounded-md border border-line bg-surface-3/30 p-3">
                <div className="flex items-baseline justify-between gap-2">
                  <label className="text-xs font-medium text-ink" htmlFor={`field-${String(field.key)}`}>
                    {field.label}
                  </label>
                  <span className="tnum text-xs text-muted" data-testid={`value-${String(field.key)}`}>
                    {field.display === "pct" ? `${(value * 100).toFixed(1)}%` : field.key === "horizon_months" ? `${value} 个月` : `${value} ${field.key === "dso_days_delta" ? "天" : "pp"}`}
                  </span>
                </div>
                <input
                  id={`field-${String(field.key)}`}
                  className="mt-2 w-full accent-[rgb(var(--accent))]"
                  type="range"
                  min={field.min}
                  max={field.max}
                  step={field.step}
                  value={value}
                  onChange={(event) => update(field.key, Number(event.target.value))}
                />
                <div className="mt-1 flex items-center gap-2">
                  <input
                    className="input tnum w-28"
                    type="number"
                    min={field.min}
                    max={field.max}
                    step={field.step}
                    value={value}
                    onChange={(event) => update(field.key, Number(event.target.value))}
                  />
                  <span className="text-[11px] text-muted">{field.hint}</span>
                </div>
              </div>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label className="label" htmlFor="scenario-label">
            情景名称
          </label>
          <input
            id="scenario-label"
            className="input w-64"
            type="text"
            maxLength={80}
            value={label}
            onChange={(event) => setLabel(event.target.value)}
          />
          <StatusBadge tone="neutral">请求：POST /scenarios/run（include_presets=true）</StatusBadge>
        </div>
      </section>

      {/* Run state --------------------------------------------------------- */}
      {running ? (
        <section className="card space-y-3">
          <Skeleton className="h-5 w-48" />
          <SkeletonTable rows={4} columns={8} />
        </section>
      ) : runError ? (
        <ErrorState
          title="情景计算失败"
          error={runError}
          message={errorMessage(runError)}
          onRetry={run}
          retrying={running}
        />
      ) : !result ? (
        <EmptyState
          title="尚未运行情景"
          description="调整左侧驱动因子后点击「运行情景」。结果会包含基准、上行情景、下行情景与自定义情景。"
          action={
            <button type="button" className="btn btn-primary" onClick={run}>
              运行情景
            </button>
          }
        />
      ) : (
        <>
          {custom ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <KpiCard label="自定义情景收入" value={custom.revenue_usd} unit="USD" period={`${result.as_of} 起 ${custom.horizon_months} 个月`} />
              <KpiCard label="自定义情景 EBIT" value={custom.ebit_usd} unit="USD" period={`${result.as_of} 起 ${custom.horizon_months} 个月`} />
              <KpiCard
                label="EBIT 差异 vs 基准"
                value={custom.ebit_delta_usd}
                unit="USD"
                period={`${result.as_of} 起 ${custom.horizon_months} 个月`}
                footnote={custom.ebit_delta_pct === null ? "差异率不可用（基准 EBIT 为 0）" : `差异率 ${formatPct(custom.ebit_delta_pct)}`}
              />
              <KpiCard
                label="期末现金"
                value={custom.ending_cash_usd}
                unit="USD"
                period={`${result.as_of} 起 ${custom.horizon_months} 个月`}
                footnote={`最低现金 ${formatComparison(custom.minimum_cash_usd, "USD")} · 现金为负 ${custom.months_with_negative_cash} 个月`}
              />
            </div>
          ) : null}

          <section className="card">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <h2 className="card-title">三情景对比</h2>
              <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
                <span>基准期 {formatPeriod(result.base_period)}</span>
                <span>预测期 {result.horizon_months} 个月</span>
                <span>币种 {result.currency}</span>
              </div>
            </div>
            <DataTable
              columns={columns}
              rows={result.scenarios}
              rowKey={(row) => row.scenario_id}
              initialSortKey="revenue_usd"
              caption="所有金额单位 USD；「EBIT 差异」为相对基准情景的差额；现金跑道不可用时显示“不可用”。"
            />
          </section>

          <section className="card space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="card-title">月度明细</h2>
              <span className="label">显示情景</span>
              {result.scenarios.map((scenario) => (
                <button
                  key={scenario.scenario_id}
                  type="button"
                  className={`btn-chip ${visibleScenarios.includes(scenario.scenario_id) ? "chip-active" : ""}`}
                  onClick={() =>
                    setVisibleScenarios((current) =>
                      current.includes(scenario.scenario_id)
                        ? current.filter((item) => item !== scenario.scenario_id)
                        : [...current, scenario.scenario_id],
                    )
                  }
                >
                  {scenario.label}
                </button>
              ))}
            </div>
            {visibleScenarios.length === 0 ? (
              <EmptyState title="未选择任何情景" description="请至少选择一个情景以绘制月度曲线。" />
            ) : (
              <div className="grid gap-3 xl:grid-cols-2">
                {ebitChart ? (
                  <Chart option={ebitChart} height={300} ariaLabel="各情景月度 EBIT 曲线（单位：USD）" testId="chart-scenario-ebit" />
                ) : null}
                {cashChart ? (
                  <Chart option={cashChart} height={300} ariaLabel="各情景月末现金曲线（单位：USD）" testId="chart-scenario-cash" />
                ) : null}
              </div>
            )}
          </section>

          <section className="card">
            <h2 className="card-title mb-2">敏感度（EBIT 摆动）</h2>
            {result.sensitivities.length === 0 ? (
              <EmptyState title="没有敏感度数据" description="后端未返回 sensitivities。" />
            ) : (
              <>
                {tornado ? (
                  <Chart option={tornado} height={Math.max(240, result.sensitivities.length * 34 + 90)} ariaLabel="敏感度龙卷风图：各驱动因子对 EBIT 的影响区间（单位：USD）" testId="chart-tornado" />
                ) : null}
                <DataTable
                  columns={[
                    { key: "label", header: "驱动因子", render: (row) => row.label, sortValue: (row) => row.label },
                    { key: "driver", header: "字段", render: (row) => <span className="font-mono text-[11px] text-muted">{row.driver}</span> },
                    { key: "shock", header: "冲击幅度", align: "right", render: (row) => <span className="tnum">{row.shock}</span> },
                    {
                      key: "swing",
                      header: "EBIT 摆动 (USD)",
                      align: "right",
                      render: (row) => <span className="tnum">{formatComparison(row.ebit_swing_usd, "USD")}</span>,
                      sortValue: (row) => row.ebit_swing_usd,
                    },
                    {
                      key: "low",
                      header: "下限影响 (USD)",
                      align: "right",
                      render: (row) => <span className="tnum text-bad">{formatComparison(row.ebit_impact_usd_low, "USD")}</span>,
                      sortValue: (row) => row.ebit_impact_usd_low,
                    },
                    {
                      key: "high",
                      header: "上限影响 (USD)",
                      align: "right",
                      render: (row) => <span className="tnum text-good">{formatComparison(row.ebit_impact_usd_high, "USD")}</span>,
                      sortValue: (row) => row.ebit_impact_usd_high,
                    },
                  ]}
                  rows={result.sensitivities}
                  rowKey={(row) => row.driver}
                  testId="sensitivity-table"
                />
              </>
            )}
          </section>

          <section className="card text-xs text-muted">
            <div className="label mb-1">模型说明 model_note</div>
            <p className="text-ink">{result.model_note || "后端未提供模型说明。"}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <StatusBadge tone="info">as_of {result.as_of}</StatusBadge>
              {result.assumptions.custom ? (
                <StatusBadge tone="neutral">
                  自定义 DSO 变化 {formatDays(result.assumptions.custom.dso_days_delta, 0)}
                </StatusBadge>
              ) : null}
              <StatusBadge tone="info">合成数据 {String(result.synthetic)}</StatusBadge>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
