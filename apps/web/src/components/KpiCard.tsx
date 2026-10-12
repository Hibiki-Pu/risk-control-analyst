/** KPI card: one auditable figure with its unit, period, delta and missing-data state. */

import type { ReactNode } from "react";

import type { CitedValue, Unit } from "@/api/types";
import { Skeleton } from "@/components/Feedback";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDelta, formatPeriod, formatValue, isPresent, NOT_AVAILABLE, statusLabel } from "@/lib/format";

export interface KpiCardProps {
  /** Preferred input: the auditable value straight from the API. */
  cited?: CitedValue | null;
  /** Fallback presentation when a page has a raw number (scenario output, market series). */
  label?: string;
  value?: number | null;
  unit?: Unit | string;
  period?: string | null;
  delta?: number | null;
  deltaUnit?: Unit | string;
  deltaLabel?: string;
  footnote?: ReactNode;
  hint?: string;
  loading?: boolean;
  /** `unavailable` reasons surface as the "缺数据" chip. */
  unavailableReason?: string | null;
  testId?: string;
}

const UNIT_ZH: Record<string, string> = {
  USD: "USD",
  pct: "%",
  days: "天",
  x: "倍",
  pp: "pp",
  percent_points: "pp",
  months: "月",
  score: "分",
  cells: "单元格",
  raw: "",
};

export function unitLabel(unit: Unit | string | null | undefined): string {
  if (!unit) return "";
  return UNIT_ZH[unit] ?? String(unit);
}

function deltaTone(delta: number | null | undefined): string {
  if (!isPresent(delta) || delta === 0) return "text-muted";
  return delta > 0 ? "text-good" : "text-bad";
}

export function KpiCard({
  cited,
  label,
  value,
  unit,
  period,
  delta,
  deltaUnit,
  deltaLabel = "较上期",
  footnote,
  hint,
  loading = false,
  unavailableReason,
  testId,
}: KpiCardProps) {
  if (loading) {
    return (
      <div className="card space-y-3" data-testid={testId ?? "kpi-card"} data-state="loading">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-7 w-32" />
        <Skeleton className="h-3 w-20" />
      </div>
    );
  }

  const resolvedLabel = cited?.label ?? label ?? "指标";
  const resolvedUnit = cited?.unit ?? unit;
  const resolvedPeriod = cited?.period ?? period ?? null;
  const available = cited
    ? cited.status === "ok" && isPresent(cited.value)
    : isPresent(value);

  // A raw number (scenario output, market observation) is rendered with the same honesty rules.
  const rawDisplay = cited
    ? formatValue(cited)
    : available
      ? `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value as number)}${
          unitLabel(resolvedUnit) ? ` ${unitLabel(resolvedUnit)}` : ""
        }`
      : unavailableReason
        ? `${NOT_AVAILABLE}（${unavailableReason}）`
        : NOT_AVAILABLE;

  const reason = unavailableReason ?? cited?.note ?? null;

  return (
    <div className="card space-y-2" data-testid={testId ?? "kpi-card"} data-state={available ? "ok" : "missing"}>
      <div className="flex items-start justify-between gap-2">
        <div className="text-xs font-medium text-muted">{resolvedLabel}</div>
        {resolvedUnit ? <StatusBadge tone="neutral">{unitLabel(resolvedUnit)}</StatusBadge> : null}
      </div>

      <div
        className={`tnum text-2xl font-semibold tracking-tight ${available ? "text-ink" : "text-muted"}`}
        data-testid="kpi-value"
      >
        {rawDisplay}
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        {resolvedPeriod ? (
          <span data-testid="kpi-period">
            期间 <span className="tnum text-ink">{formatPeriod(resolvedPeriod)}</span>
          </span>
        ) : null}
        {isPresent(delta) ? (
          <span data-testid="kpi-delta" className={deltaTone(delta)}>
            {deltaLabel} <span className="tnum">{formatDelta(delta, deltaUnit ?? "USD")}</span>
          </span>
        ) : null}
        {!available ? (
          <span data-testid="kpi-missing-chip" className="rounded-full border border-warn/40 bg-warn/10 px-2 py-0.5 text-warn">
            {cited && cited.status !== "ok" ? statusLabel(cited.status) : "缺数据"}
          </span>
        ) : null}
      </div>

      {reason ? <div className="text-xs text-muted">{reason}</div> : null}
      {footnote ? <div className="text-xs text-muted">{footnote}</div> : null}
      {hint ? (
        <div className="text-[11px] text-muted" title={hint}>
          {hint}
        </div>
      ) : null}
    </div>
  );
}
