/**
 * Application shell: sidebar navigation, top bar (as-of date, dataset badge) and the
 * always-visible synthetic-data banner.
 *
 * The banner is rendered by the shell rather than by each page, so no page can forget it. It is
 * visible unconditionally: when `/health` says the data is synthetic it says so, and when `/health`
 * has not answered yet it still warns that this deployment is a demo.
 */

import type { ReactNode } from "react";
import { createContext, useContext, useMemo } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { api, errorMessage } from "@/api/client";
import type { HealthResponse } from "@/api/types";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDate, formatPeriod } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";

export interface HealthContextValue {
  health: HealthResponse | null;
  loading: boolean;
  error: unknown;
  errorText: string | null;
  reload: () => void;
}

const HealthContext = createContext<HealthContextValue>({
  health: null,
  loading: true,
  error: null,
  errorText: null,
  reload: () => undefined,
});

export function useHealth(): HealthContextValue {
  return useContext(HealthContext);
}

interface NavItem {
  to: string;
  label: string;
  hint: string;
}

const NAV: NavItem[] = [
  { to: "/", label: "总览", hint: "Overview" },
  { to: "/pnl", label: "损益分析", hint: "P&L analysis" },
  { to: "/risk", label: "风险控制", hint: "Risk control" },
  { to: "/market", label: "市场情报", hint: "Market intelligence" },
  { to: "/scenarios", label: "情景模拟", hint: "Scenario simulator" },
  { to: "/analyst", label: "AI 分析师", hint: "AI analyst" },
  { to: "/reports", label: "报告中心", hint: "Report centre" },
];

export function SyntheticBanner({ health, loading }: { health: HealthResponse | null; loading: boolean }) {
  const dataset = health?.dataset ?? null;
  const isSynthetic = health ? health.synthetic : true;
  return (
    <div
      data-testid="synthetic-banner"
      role="note"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-warn/40 bg-warn/15 px-4 py-2 text-xs text-ink"
    >
      <span className="font-semibold tracking-wide text-warn">合成演示数据 SYNTHETIC DEMO</span>
      <span className="text-muted">
        {loading && !health
          ? "正在读取 /health …"
          : isSynthetic
            ? "本演示的全部财务数字均由合成数据集生成，不代表任何真实企业，也不构成投资建议。"
            : "当前数据集由用户上传，未经外部来源核验。"}
      </span>
      <span className="tnum text-muted">
        数据截止 {health ? formatPeriod(health.as_of) : "不可用"} · 版本 {health?.version ?? "不可用"}
      </span>
      {health?.disclaimer ? <span className="text-muted">· {health.disclaimer}</span> : null}
      {dataset ? <span className="text-muted">· 数据集 {dataset.dataset_id}</span> : null}
    </div>
  );
}

export function AppShell() {
  const state = useAsync<HealthResponse>((signal) => api.health(signal), []);
  const { data, loading, error, reload } = state;

  const value = useMemo<HealthContextValue>(
    () => ({
      health: data,
      loading,
      error,
      errorText: error ? errorMessage(error) : null,
      reload,
    }),
    [data, loading, error, reload],
  );

  const dataset = data?.dataset ?? null;

  return (
    <HealthContext.Provider value={value}>
      <div className="flex min-h-screen flex-col bg-surface text-ink">
        <SyntheticBanner health={data} loading={loading} />
        <div className="flex flex-1 flex-col lg:flex-row">
          <aside className="shrink-0 border-b border-line bg-surface-2 lg:w-56 lg:border-b-0 lg:border-r">
            <div className="px-4 py-4">
              <div className="text-base font-semibold leading-tight">风险控制分析师</div>
              <div className="text-[11px] uppercase tracking-widest text-muted">RiskControl Analyst</div>
            </div>
            <nav className="flex flex-wrap gap-1 px-2 pb-3 lg:flex-col lg:flex-nowrap">
              {NAV.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) =>
                    `flex items-baseline gap-2 rounded-md px-3 py-2 text-sm transition-colors ${
                      isActive ? "bg-accent/15 font-semibold text-accent" : "text-ink hover:bg-surface-3"
                    }`
                  }
                >
                  <span>{item.label}</span>
                  <span className="text-[10px] uppercase tracking-wide text-muted">{item.hint}</span>
                </NavLink>
              ))}
            </nav>
          </aside>

          <div className="flex min-w-0 flex-1 flex-col">
            <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line bg-surface-2 px-4 py-2">
              <div className="text-xs text-muted">
                数据截止 <span className="tnum text-ink">{data ? formatPeriod(data.as_of) : "不可用"}</span>
              </div>
              <div className="text-xs text-muted">
                最新数据日 <span className="tnum text-ink">{formatDate(dataset?.months?.at(-1) ?? null)}</span>
              </div>
              <StatusBadge tone="info" title="由 /health 返回的数据集标识">
                数据集 {dataset?.dataset_id ?? "不可用"}
              </StatusBadge>
              <StatusBadge tone="neutral">{dataset?.kind ?? "不可用"}</StatusBadge>
              {dataset ? (
                <StatusBadge tone={dataset.has_budget_layer ? "good" : "warn"}>
                  {dataset.has_budget_layer ? "含预算层" : "无预算层（预算差异不可用）"}
                </StatusBadge>
              ) : null}
              {dataset ? (
                <span className="tnum text-xs text-muted">
                  {dataset.rows} 行 · {dataset.months.length} 个月 · 区域 {dataset.regions.join(" / ") || "全部"}
                </span>
              ) : null}
              <div className="ml-auto flex items-center gap-2">
                {error ? (
                  <button type="button" className="btn" onClick={reload}>
                    重新连接
                  </button>
                ) : null}
              </div>
            </header>

            <main className="min-w-0 flex-1 px-4 py-4">
              <Outlet />
            </main>

            <footer className="border-t border-line px-4 py-3 text-[11px] text-muted">
              合成演示数据 · 数字全部来自确定性引擎并带引证 · 缺失值显示为“不可用”，绝不显示为 0。
            </footer>
          </div>
        </div>
      </div>
    </HealthContext.Provider>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-ink">{title}</h1>
        {description ? <p className="mt-1 max-w-3xl text-xs text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export default AppShell;
