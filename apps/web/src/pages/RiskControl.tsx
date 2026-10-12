/**
 * Risk control — the signature page.
 *
 * Everything here is rule-based and traceable: `/risk/register` returns an overall level and score,
 * a list of signals (observed value vs threshold), the source ids behind each signal, and the data
 * gaps that could not be filled. Nothing is inferred on the client.
 */

import { useMemo, useState } from "react";

import { api, errorMessage } from "@/api/client";
import type { RiskRegister, RiskSignal, Severity } from "@/api/types";
import { PageHeader } from "@/components/AppLayout";
import { Chart } from "@/components/Chart";
import type { ChartOption } from "@/components/Chart";
import { EmptyState, ErrorState, SkeletonCard } from "@/components/Feedback";
import { KpiCard } from "@/components/KpiCard";
import { RegionFilter } from "@/components/RegionFilter";
import { LevelBadge, SeverityBadge, StatusBadge } from "@/components/StatusBadge";
import { riskCited } from "@/lib/data";
import { categoryLabel, formatDateTime, formatPeriod, formatValue, levelLabel, severityLabel, severityRank } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";
import { useFilters } from "@/lib/useFilters";

const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"];

const CHART_GRID = "#ccd4e0";
const CHART_INK = "#8899aa";

export function scoreOption(score: number | null, level: string | null | undefined): ChartOption {
  const present = typeof score === "number" && Number.isFinite(score);
  return {
    backgroundColor: "transparent",
    textStyle: { color: CHART_INK },
    series: [
      {
        type: "gauge",
        startAngle: 210,
        endAngle: -30,
        min: 0,
        max: 100,
        radius: "95%",
        center: ["50%", "62%"],
        progress: { show: true, width: 14, roundCap: true },
        axisLine: {
          lineStyle: {
            width: 14,
            color: [
              [0.3, "#10b981"],
              [0.55, "#f59e0b"],
              [0.78, "#ef4444"],
              [1, "#b91c1c"],
            ],
          },
        },
        pointer: { width: 4, length: "60%", itemStyle: { color: CHART_INK } },
        axisTick: { show: false },
        splitLine: { length: 10, lineStyle: { color: CHART_GRID, width: 1 } },
        axisLabel: { color: CHART_INK, distance: 14, fontSize: 10 },
        anchor: { show: false },
        detail: {
          valueAnimation: true,
          offsetCenter: [0, "32%"],
          fontSize: 22,
          fontWeight: "bolder",
          color: CHART_INK,
          formatter: present ? (value: number) => `${value.toFixed(1)} 分` : () => "不可用",
        },
        title: { offsetCenter: [0, "58%"], fontSize: 11, color: CHART_INK },
        data: [{ value: present ? (score as number) : 0, name: `总体风险等级：${levelLabel(level)}` }],
      },
    ],
    tooltip: { show: false },
  };
}

function SignalCard({ signal }: { signal: RiskSignal }) {
  const observed = riskCited(signal, signal.observed_value, signal.unit, "规则引擎未提供观测值");
  const threshold = riskCited(signal, signal.threshold, signal.threshold_unit, "该信号没有数值阈值");
  const directionText =
    signal.direction === "above" ? "高于阈值" : signal.direction === "below" ? "低于阈值" : "变化触发";

  return (
    <article className="rounded-lg border border-line bg-surface-2 p-3" data-testid={`signal-${signal.signal_id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={signal.severity} />
        <span className="font-mono text-xs text-muted">{signal.signal_id}</span>
        <span className="text-sm font-semibold text-ink">{signal.title}</span>
        <StatusBadge tone="neutral" title="风险分类">
          {categoryLabel(signal.category)}
        </StatusBadge>
        <span className="tnum ml-auto text-xs text-muted">期间 {formatPeriod(signal.period)}</span>
      </div>

      <p className="mt-2 text-xs text-muted">{signal.detail}</p>

      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <div className="rounded-md bg-surface-3/60 px-2 py-1.5">
          <dt className="label">观测值</dt>
          <dd className="tnum text-sm font-semibold text-ink" data-testid="signal-observed">
            {formatValue(observed)}
          </dd>
        </div>
        <div className="rounded-md bg-surface-3/60 px-2 py-1.5">
          <dt className="label">阈值</dt>
          <dd className="tnum text-sm font-semibold text-ink">{formatValue(threshold)}</dd>
        </div>
        <div className="rounded-md bg-surface-3/60 px-2 py-1.5">
          <dt className="label">方向</dt>
          <dd className="text-sm text-ink">{directionText}</dd>
        </div>
        <div className="rounded-md bg-surface-3/60 px-2 py-1.5">
          <dt className="label">单位</dt>
          <dd className="text-sm text-ink">
            {signal.unit}
            {signal.threshold_unit !== signal.unit ? ` / ${signal.threshold_unit}` : ""}
          </dd>
        </div>
      </dl>

      {signal.supporting.length > 0 ? (
        <div className="mt-3">
          <div className="label mb-1">支撑数据</div>
          <ul className="flex flex-wrap gap-2 text-[11px]">
            {signal.supporting.map((item) => (
              <li key={item.key} className="tnum rounded border border-line bg-surface-3/50 px-2 py-0.5 text-muted">
                {item.label}: {formatValue(riskCited(signal, item.value, item.unit, "该支撑值为空"))}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {signal.recommended_check ? (
        <div className="mt-3 rounded-md border border-accent/30 bg-accent/5 px-2 py-1.5 text-xs text-ink">
          <span className="font-semibold">建议核查：</span>
          {signal.recommended_check}
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
        <span className="label">引证</span>
        {signal.source_ids.length === 0 ? (
          <span>无来源标识</span>
        ) : (
          signal.source_ids.map((source) => (
            <span key={source} className="code" title="后端返回的 source_ids">
              {source}
            </span>
          ))
        )}
        {signal.metric_ids.length > 0 ? <span>· 指标：{signal.metric_ids.join(", ")}</span> : null}
      </div>
    </article>
  );
}

export default function RiskControl() {
  const filters = useFilters();
  const { regions, setRegions, month } = filters;
  const regionKey = regions.join(",");
  const [activeSeverities, setActiveSeverities] = useState<Severity[]>([]);

  const state = useAsync<RiskRegister>(
    (signal) => api.riskRegister({ month: month ?? undefined, regions }, signal),
    [month, regionKey],
  );

  const signals = state.data?.signals ?? [];
  const filtered = useMemo(
    () =>
      activeSeverities.length === 0
        ? signals
        : signals.filter((signal) => activeSeverities.includes(signal.severity)),
    [signals, activeSeverities],
  );

  const counts = useMemo(() => {
    const map = new Map<string, number>();
    for (const signal of signals) map.set(signal.severity, (map.get(signal.severity) ?? 0) + 1);
    return map;
  }, [signals]);

  const highest = useMemo(
    () => [...signals].sort((left, right) => severityRank(right.severity) - severityRank(left.severity))[0] ?? null,
    [signals],
  );

  const toggle = (severity: Severity) =>
    setActiveSeverities((current) =>
      current.includes(severity) ? current.filter((item) => item !== severity) : [...current, severity],
    );

  return (
    <div className="space-y-6">
      <PageHeader
        title="风险控制"
        description={
          <>
            规则化风险台账：每个信号都带观测值、阈值、单位与来源标识。 期间{" "}
            <span className="tnum text-ink">{formatPeriod(state.data?.period ?? month ?? "")}</span>，规则引擎为确定性实现，不含任何 LLM 推断。
          </>
        }
        actions={<RegionFilter value={regions} onChange={setRegions} disabled={state.loading} />}
      />

      {state.loading ? (
        <div className="grid gap-3 xl:grid-cols-3">
          <SkeletonCard rows={4} />
          <div className="xl:col-span-2 space-y-3">
            <SkeletonCard rows={3} />
            <SkeletonCard rows={3} />
          </div>
        </div>
      ) : state.error ? (
        <ErrorState error={state.error} message={errorMessage(state.error)} onRetry={state.reload} retrying={state.reloading} />
      ) : !state.data ? (
        <EmptyState title="风险台账为空" />
      ) : (
        <>
          <div className="grid gap-3 xl:grid-cols-3">
            <section className="card">
              <h2 className="card-title mb-2">总体风险</h2>
              <Chart
                option={scoreOption(state.data.score, state.data.overall_level)}
                height={190}
                ariaLabel={`总体风险评分仪表盘：${state.data.score} 分（满分 100）`}
                testId="chart-risk-score"
              />
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <LevelBadge level={state.data.overall_level} />
                <StatusBadge tone="info">评分 {state.data.score.toFixed(1)} / 100</StatusBadge>
                <StatusBadge tone="neutral">期间 {formatPeriod(state.data.period)}</StatusBadge>
              </div>
              <p className="mt-2 text-[11px] text-muted">
                评分与等级由后端规则引擎计算（0–100，分数越高风险越高）；仪表盘单位：分。
              </p>
            </section>

            <section className="grid gap-3 sm:grid-cols-2 xl:col-span-2">
              <KpiCard
                label="风险信号总数"
                value={signals.length}
                unit="raw"
                period={state.data.period}
                footnote="按当前区域与月份筛选后的信号数量"
              />
              <KpiCard
                label="最高严重度"
                value={highest ? severityRank(highest.severity) : null}
                unit="score"
                period={highest?.period ?? state.data.period}
                unavailableReason={highest ? undefined : "当前期间没有触发任何信号"}
                footnote={highest ? `${highest.signal_id} · ${highest.title}（等级：${severityLabel(highest.severity)}）` : undefined}
              />
              <KpiCard
                label="严重 / 高风险信号"
                value={(counts.get("critical") ?? 0) + (counts.get("high") ?? 0)}
                unit="raw"
                period={state.data.period}
                footnote="severity ∈ {critical, high}"
              />
              <KpiCard
                label="数据缺口条数"
                value={state.data.data_gaps.length}
                unit="raw"
                period={state.data.period}
                footnote="缺口会在下方完整列出"
              />
            </section>
          </div>

          {/* Filters ------------------------------------------------------- */}
          <section className="card">
            <div className="flex flex-wrap items-center gap-2">
              <span className="label">严重度筛选</span>
              <button
                type="button"
                className={`btn-chip ${activeSeverities.length === 0 ? "chip-active" : ""}`}
                onClick={() => setActiveSeverities([])}
              >
                全部（{signals.length}）
              </button>
              {SEVERITIES.map((severity) => (
                <button
                  key={severity}
                  type="button"
                  className={`btn-chip ${activeSeverities.includes(severity) ? "chip-active" : ""}`}
                  onClick={() => toggle(severity)}
                >
                  {severityLabel(severity)}（{counts.get(severity) ?? 0}）
                </button>
              ))}
              <span className="ml-auto text-[11px] text-muted">
                显示 {filtered.length} / {signals.length} 条
              </span>
            </div>
          </section>

          {/* Signals ------------------------------------------------------- */}
          {filtered.length === 0 ? (
            <EmptyState
              title={signals.length === 0 ? "当前期间未触发任何风险信号" : "筛选后没有信号"}
              description={
                signals.length === 0
                  ? "规则引擎在该期间没有触发阈值；这表示输入数据正常，而不是数据缺失。"
                  : "请放宽严重度筛选条件。"
              }
            />
          ) : (
            <div className="grid gap-3 xl:grid-cols-2">
              {filtered.map((signal) => (
                <SignalCard key={signal.signal_id} signal={signal} />
              ))}
            </div>
          )}

          {/* Data gaps ----------------------------------------------------- */}
          <section className="card">
            <h2 className="card-title mb-2">数据缺口</h2>
            {state.data.data_gaps.length === 0 ? (
              <p className="text-xs text-muted">规则引擎未报告数据缺口。</p>
            ) : (
              <ul className="list-disc space-y-1 pl-4 text-xs text-ink">
                {state.data.data_gaps.map((gap) => (
                  <li key={gap}>{gap}</li>
                ))}
              </ul>
            )}
            <div className="mt-3 border-t border-line pt-2 text-[11px] text-muted">
              <div>
                台账生成时间口径 as_of <span className="tnum">{formatDateTime(`${state.data.as_of}-01T00:00:00Z`)}</span> ·
                合成数据 {String(state.data.synthetic)}
              </div>
              <div className="mt-1 flex flex-wrap gap-1">
                <span className="label">lineage</span>
                {state.data.lineage.slice(0, 8).map((item) => (
                  <span key={item} className="code">
                    {item}
                  </span>
                ))}
                {state.data.lineage.length > 8 ? <span>… 共 {state.data.lineage.length} 条</span> : null}
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
