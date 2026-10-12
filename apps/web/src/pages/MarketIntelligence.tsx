/**
 * Market intelligence — macro series with explicit provenance.
 *
 * The important distinction on this page: a FRED observation (`is_fixture: false`) and a bundled
 * local demo fixture (`is_fixture: true`) look identical as numbers but mean very different things,
 * so the provenance badge is rendered next to every value, and the alignment/licence notes are shown
 * verbatim.
 */

import { useMemo, useState } from "react";

import { api, errorMessage } from "@/api/client";
import type { MarketCatalogResponse, MarketSeries } from "@/api/types";
import { PageHeader } from "@/components/AppLayout";
import { Chart } from "@/components/Chart";
import { EmptyState, ErrorState, Skeleton, SkeletonCard } from "@/components/Feedback";
import { KpiCard } from "@/components/KpiCard";
import { ProvenanceBadge, StatusBadge } from "@/components/StatusBadge";
import { buildSeriesChart } from "@/lib/charts";
import { formatDate, formatDateTime, formatNumber, NOT_AVAILABLE } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";

const OBSERVATION_LIMIT = 120;

function SeriesPanel({ seriesId }: { seriesId: string }) {
  const state = useAsync<MarketSeries>(
    (signal) => api.marketSeries(seriesId, { allow_live: true, limit: OBSERVATION_LIMIT }, signal),
    [seriesId],
  );

  const series = state.data;
  const observations = series?.observations ?? [];

  const chart = useMemo(
    () =>
      buildSeriesChart({
        title: `${series?.title ?? seriesId}（${series?.units ?? "单位不可用"}）`,
        unit: series?.units ?? "单位不可用",
        period: `${formatDate(observations[0]?.date ?? null)}..${formatDate(observations[observations.length - 1]?.date ?? null)}`,
        labels: observations.map((item) => item.date),
        series: [
          {
            name: series?.title ?? seriesId,
            data: observations.map((item) => (typeof item.value === "number" ? item.value : null)),
            type: "line",
            area: true,
          },
        ],
        yAxisName: series?.units ?? "单位不可用",
        valueFormat: (value) => (value === null ? NOT_AVAILABLE : formatNumber(value, 3)),
      }),
    [series, observations, seriesId],
  );

  if (state.loading) {
    return (
      <section className="card space-y-3">
        <Skeleton className="h-5 w-64" />
        <Skeleton className="h-64 w-full" />
      </section>
    );
  }

  if (state.error) {
    return (
      <section className="card">
        <ErrorState error={state.error} message={errorMessage(state.error)} onRetry={state.reload} retrying={state.reloading} />
      </section>
    );
  }

  if (!series) return <EmptyState title="该序列没有返回数据" />;

  return (
    <section className="card space-y-3" data-testid={`market-series-${series.series_id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="card-title">{series.title}</h2>
          <div className="font-mono text-[11px] text-muted">
            {series.series_id} · 频率 {series.frequency} · 国家/地区 {series.country}
          </div>
        </div>
        <ProvenanceBadge
          isFixture={series.is_fixture}
          isStale={series.is_stale}
          sourceName={series.source_name}
          fetchedAt={formatDateTime(series.fetched_at)}
        />
      </div>

      {series.error ? (
        <div role="alert" className="rounded-md border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-ink">
          后端返回的序列错误：{series.error}
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <KpiCard
          label="最新观测值"
          value={series.latest_value}
          unit={series.units}
          period={formatDate(series.latest_observation_date)}
          unavailableReason="该序列没有观测值"
          footnote={`观测日 ${formatDate(series.latest_observation_date)}`}
          testId="market-latest"
        />
        <KpiCard
          label="上一期观测值"
          value={series.previous_value}
          unit={series.units}
          period={formatDate(series.latest_observation_date)}
          unavailableReason="没有可比的前一期观测"
        />
        <KpiCard
          label="变化（最新 − 上一期）"
          value={series.change}
          unit={series.units}
          period={formatDate(series.latest_observation_date)}
          unavailableReason="无法计算变化"
          footnote={`过期阈值 ${series.stale_after_days} 天`}
        />
      </div>

      {observations.length === 0 ? (
        <EmptyState title="该序列没有观测点" description="后端返回的 observations 为空。" />
      ) : (
        <Chart
          option={chart}
          height={320}
          ariaLabel={`${series.title} 走势图，单位 ${series.units}，观测区间 ${formatDate(observations[0]?.date ?? null)} 至 ${formatDate(observations[observations.length - 1]?.date ?? null)}`}
          testId="chart-market-series"
        />
      )}

      <div className="grid gap-2 text-xs text-muted sm:grid-cols-2">
        <div className="rounded-md border border-line bg-surface-3/40 p-2">
          <div className="label mb-1">口径对齐说明 alignment_note</div>
          <p>{series.alignment_note || "后端未提供对齐说明。"}</p>
        </div>
        <div className="rounded-md border border-line bg-surface-3/40 p-2">
          <div className="label mb-1">许可说明 license_note</div>
          <p>{series.license_note || "后端未提供许可说明。"}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
        <StatusBadge tone={series.is_fixture ? "warn" : "good"}>
          {series.is_fixture ? "本地演示样本（非实时）" : "实时来源"}
        </StatusBadge>
        <StatusBadge tone={series.is_stale ? "bad" : "neutral"}>
          {series.is_stale ? `已过期（>${series.stale_after_days} 天）` : "未过期"}
        </StatusBadge>
        <span>抓取时间 {formatDateTime(series.fetched_at)}</span>
        {series.source_url ? (
          <a className="link" href={series.source_url} target="_blank" rel="noreferrer noopener">
            来源链接
          </a>
        ) : null}
        <span>观测点 {observations.length} 个</span>
      </div>
    </section>
  );
}

export default function MarketIntelligence() {
  const catalogState = useAsync<MarketCatalogResponse>((signal) => api.marketCatalog(signal), []);
  const [selected, setSelected] = useState<string | null>(null);

  const catalog = catalogState.data?.series ?? [];
  const activeId = selected ?? catalog[0]?.series_id ?? null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="市场情报"
        description={
          <>
            宏观序列用于给财务模型提供外部锚点（利率、汇率、价格指数）。
            每个数值都必须连同来源一起阅读：<strong>实时 FRED 观测</strong> 与 <strong>本地演示样本</strong> 在界面上有明确区分。
          </>
        }
        actions={
          catalogState.data ? (
            <StatusBadge tone={catalogState.data.fred_configured ? "good" : "warn"}>
              FRED_API_KEY {catalogState.data.fred_configured ? "已配置（可实时抓取）" : "未配置（仅本地样本）"}
            </StatusBadge>
          ) : null
        }
      />

      {catalogState.loading ? (
        <div className="grid gap-3 xl:grid-cols-3">
          <SkeletonCard rows={5} />
          <div className="xl:col-span-2">
            <Skeleton className="h-80 w-full" />
          </div>
        </div>
      ) : catalogState.error ? (
        <ErrorState
          error={catalogState.error}
          message={errorMessage(catalogState.error)}
          onRetry={catalogState.reload}
          retrying={catalogState.reloading}
        />
      ) : catalog.length === 0 ? (
        <EmptyState title="目录为空" description="/market/catalog 未返回任何序列。" />
      ) : (
        <div className="grid gap-3 xl:grid-cols-3">
          <section className="card space-y-2">
            <h2 className="card-title">序列目录</h2>
            <p className="text-[11px] text-muted">{catalogState.data?.policy}</p>
            <ul className="space-y-1">
              {catalog.map((item) => {
                const active = item.series_id === activeId;
                return (
                  <li key={item.series_id}>
                    <button
                      type="button"
                      onClick={() => setSelected(item.series_id)}
                      className={`w-full rounded-md border px-2.5 py-2 text-left transition-colors ${
                        active ? "border-accent bg-accent/10" : "border-line bg-surface-2 hover:bg-surface-3"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-xs text-muted">{item.series_id}</span>
                        <StatusBadge tone={item.available ? "good" : "bad"}>
                          {item.available ? "可用" : "不可用"}
                        </StatusBadge>
                      </div>
                      <div className="text-sm font-medium text-ink">{item.title}</div>
                      <div className="text-[11px] text-muted">
                        单位 {item.units} · 频率 {item.frequency} · {item.country}
                      </div>
                      <p className="mt-1 text-[11px] text-muted">{item.rationale}</p>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>

          <div className="xl:col-span-2">
            {activeId ? <SeriesPanel key={activeId} seriesId={activeId} /> : <EmptyState title="请选择一个序列" />}
          </div>
        </div>
      )}

      {catalogState.data ? (
        <section className="card text-[11px] text-muted">
          <div className="label mb-1">数据来源政策 policy</div>
          <p>{catalogState.data.policy}</p>
          <p className="mt-1">
            合成演示说明：企业财务数据为合成数据；宏观序列在未配置 FRED_API_KEY 时全部为本地样本（
            <span className="code">is_fixture = true</span>），界面绝不将其标注为实时观测。
          </p>
        </section>
      ) : null}
    </div>
  );
}
