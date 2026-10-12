/** Status / severity / provenance badges. */

import type { ReactNode } from "react";

import type { Severity, VerificationStatus } from "@/api/types";
import { levelColor, levelLabel, severityColor, severityLabel, verificationLabel } from "@/lib/format";

export type BadgeTone = "neutral" | "good" | "warn" | "bad" | "info" | "accent";

const TONES: Record<BadgeTone, string> = {
  neutral: "border-line bg-surface-3 text-muted",
  good: "border-good/40 bg-good/10 text-good",
  warn: "border-warn/40 bg-warn/10 text-warn",
  bad: "border-bad/40 bg-bad/10 text-bad",
  info: "border-info/40 bg-info/10 text-info",
  accent: "border-accent/40 bg-accent/10 text-accent",
};

export interface StatusBadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
  title?: string;
  className?: string;
}

export function StatusBadge({ tone = "neutral", children, title, className = "" }: StatusBadgeProps) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${TONES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: Severity | string | null | undefined }) {
  return (
    <span
      data-testid="severity-badge"
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${severityColor(severity)}`}
    >
      {severityLabel(severity)}
    </span>
  );
}

export function LevelBadge({ level, label = "总体风险等级" }: { level: string | null | undefined; label?: string }) {
  return (
    <span
      data-testid="level-badge"
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-semibold ${levelColor(level)}`}
    >
      <span className="text-xs font-normal opacity-80">{label}</span>
      {levelLabel(level)}
    </span>
  );
}

export function VerificationBadge({ status }: { status: VerificationStatus | string | null | undefined }) {
  const tone: BadgeTone = status === "pass" ? "good" : status === "warn" ? "warn" : status === "fail" ? "bad" : "neutral";
  return (
    <StatusBadge tone={tone} title={`校验状态 ${String(status ?? "")}`}>
      校验：{verificationLabel(status)}
    </StatusBadge>
  );
}

export interface ProvenanceBadgeProps {
  isFixture?: boolean | undefined;
  isStale?: boolean | undefined;
  sourceName?: string | null;
  synthetic?: boolean | undefined;
  fetchedAt?: string | null;
  compact?: boolean;
}

/**
 * Provenance is not decoration: it states whether a number came from a live provider
 * (FRED) or from a bundled demo fixture, and whether the observation is stale.
 */
export function ProvenanceBadge({
  isFixture,
  isStale,
  sourceName,
  synthetic,
  fetchedAt,
  compact = false,
}: ProvenanceBadgeProps) {
  const tone: BadgeTone = isFixture ? "warn" : "good";
  const label = isFixture ? "本地演示数据 FIXTURE" : isStale ? "实时数据（已过期）" : "实时数据 LIVE";
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5" data-testid="provenance-badge">
      <StatusBadge
        tone={tone}
        title={[sourceName ?? undefined, fetchedAt ? `抓取时间 ${fetchedAt}` : undefined]
          .filter(Boolean)
          .join(" · ")}
      >
        {label}
      </StatusBadge>
      {isStale ? <StatusBadge tone="bad">STALE 数据过期</StatusBadge> : null}
      {synthetic ? <StatusBadge tone="info">合成数据</StatusBadge> : null}
      {!compact && sourceName ? <span className="text-xs text-muted">{sourceName}</span> : null}
    </span>
  );
}
