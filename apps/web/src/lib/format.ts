/**
 * Formatting utilities with honest missing-data semantics.
 *
 * The single rule that matters: a value that is absent (`null`, `undefined`, `NaN`) or that the
 * backend marked `missing` / `undefined` is rendered as `不可用` plus the citation note — never as
 * `0`, never as a dash that could be mistaken for a small number.
 *
 * Percentages arrive as decimal fractions and are multiplied by 100 for display.
 */

import type { CitedValue, RiskLevel, Severity, Status, Unit, VerificationStatus } from "@/api/types";

export const NOT_AVAILABLE = "不可用";
export const NOTE_SEPARATOR = " · ";

const MINUS = "−"; // typographic minus, so negatives cannot be missed
const LOCALE = "en-US";

export function isPresent(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function group(value: number, minimum: number, maximum: number): string {
  return new Intl.NumberFormat(LOCALE, {
    minimumFractionDigits: minimum,
    maximumFractionDigits: maximum,
    useGrouping: true,
  }).format(value);
}

/** Round to a sensible number of decimals and group thousands. */
export function formatNumber(value: number, decimals = 2): string {
  if (!isPresent(value)) return NOT_AVAILABLE;
  const rounded = Number(value.toFixed(decimals));
  return group(rounded, 0, decimals);
}

/** USD amounts with thousands separators. Default: whole dollars. */
export function formatMoney(value: number | null | undefined, decimals = 0): string {
  if (!isPresent(value)) return NOT_AVAILABLE;
  const sign = value < 0 ? MINUS : "";
  return `${sign}$${group(Math.abs(value), decimals, decimals)}`;
}

/**
 * Compact USD for charts and KPI cards: `$1.23M`, `$456.7K`, `$12,345`.
 * Magnitudes only; the unit label (`USD`) is rendered separately.
 */
export function formatMoneyCompact(value: number | null | undefined): string {
  if (!isPresent(value)) return NOT_AVAILABLE;
  const sign = value < 0 ? MINUS : "";
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000) return `${sign}$${trimZero(abs / 1_000_000_000)}B`;
  if (abs >= 1_000_000) return `${sign}$${trimZero(abs / 1_000_000)}M`;
  if (abs >= 1_000) return `${sign}$${trimZero(abs / 1_000)}K`;
  return `${sign}$${group(abs, 0, 0)}`;
}

function trimZero(value: number): string {
  return value.toFixed(2).replace(/\.?0+$/, "");
}

/**
 * A decimal fraction as a percentage: `0.2193` -> `21.93%`.
 * `signed` prefixes a `+` for positive numbers (useful for deltas).
 */
export function formatPct(
  value: number | null | undefined,
  options: { decimals?: number; signed?: boolean; points?: boolean } = {},
): string {
  if (!isPresent(value)) return NOT_AVAILABLE;
  const { decimals = 2, signed = false, points = false } = options;
  const scaled = points ? value : value * 100;
  const suffix = points ? " pp" : "%";
  const sign = scaled < 0 ? MINUS : signed && scaled > 0 ? "+" : "";
  return `${sign}${group(Math.abs(scaled), 0, decimals)}${suffix}`;
}

/** Days, e.g. `69.42 天`. */
export function formatDays(value: number | null | undefined, decimals = 1): string {
  if (!isPresent(value)) return NOT_AVAILABLE;
  return `${formatNumber(value, decimals)} 天`;
}

/** A ratio such as interest coverage or net leverage, e.g. `1.56x`. */
export function formatRatio(value: number | null | undefined, decimals = 2): string {
  if (!isPresent(value)) return NOT_AVAILABLE;
  return `${formatNumber(value, decimals)}x`;
}

/** Plain number with an explicit unit suffix (used for `score`, `cells`, unknown units). */
export function formatWithUnit(
  value: number | null | undefined,
  unit: Unit | string | null | undefined,
  decimals = 2,
): string {
  if (!isPresent(value)) return NOT_AVAILABLE;
  switch (unit) {
    case "USD":
      return formatMoney(value);
    case "pct":
      return formatPct(value, { decimals });
    case "percent_points":
    case "pp":
      return formatPct(value, { decimals, points: true });
    case "days":
      return formatDays(value, decimals);
    case "x":
      return formatRatio(value, decimals);
    case "score":
      return `${formatNumber(value, decimals)} 分`;
    case "months":
      return `${formatNumber(value, decimals)} 个月`;
    case "cells":
      return `${formatNumber(value, decimals)} 个单元格`;
    case "raw":
    case undefined:
    case null:
    case "":
      return formatNumber(value, decimals);
    default:
      return `${formatNumber(value, decimals)} ${unit}`;
  }
}

/** Currency-sensitive helper: only labels USD, otherwise falls back to the plain number. */
export function formatUnitValue(
  value: number | null | undefined,
  unit: Unit | string | null | undefined,
  currency = "USD",
  decimals = 2,
): string {
  if (!isPresent(value)) return NOT_AVAILABLE;
  if (unit === "USD") return currency === "USD" ? formatMoney(value) : `${formatMoney(value)} ${currency}`;
  return formatWithUnit(value, unit, decimals);
}

/**
 * The contract-mandated renderer for a `CitedValue`.
 *
 * Returns `不可用` plus the citation `note` whenever `status !== "ok"` or the value is `null`.
 * A present value keeps its unit, and any note (for example "partial coverage") is appended.
 */
export function formatValue(citedValue: CitedValue | null | undefined, decimals = 2): string {
  if (!citedValue) return NOT_AVAILABLE;
  const note = citedValue.note ? citedValue.note.trim() : "";
  if (citedValue.status !== "ok" || !isPresent(citedValue.value)) {
    return note ? `${NOT_AVAILABLE}（${note}）` : NOT_AVAILABLE;
  }
  const rendered = formatWithUnit(citedValue.value, citedValue.unit, decimals);
  return note ? `${rendered}（${note}）` : rendered;
}

/** Just the number part of a cited value, without unit or note. */
export function formatValueOnly(citedValue: CitedValue | null | undefined): string {
  if (!citedValue || citedValue.status !== "ok" || !isPresent(citedValue.value)) return NOT_AVAILABLE;
  return formatNumber(citedValue.value, 2);
}

export function statusLabel(status: Status | string | null | undefined): string {
  switch (status) {
    case "ok":
      return "状态：正常";
    case "missing":
      return "缺数据";
    case "undefined":
      return "口径未定义";
    default:
      return NOT_AVAILABLE;
  }
}

/* -------------------------------------------------------------------------- */
/* domain labels                                                              */
/* -------------------------------------------------------------------------- */

const SEVERITY_ZH: Record<Severity, string> = {
  info: "提示",
  low: "低",
  medium: "中",
  high: "高",
  critical: "严重",
};

export function severityLabel(severity: Severity | string | null | undefined): string {
  if (!severity) return NOT_AVAILABLE;
  return SEVERITY_ZH[severity as Severity] ?? String(severity);
}

/** Tailwind classes for a severity chip. Full literal names so Tailwind's scanner sees them. */
export function severityColor(severity: Severity | string | null | undefined): string {
  switch (severity) {
    case "critical":
      return "border-bad/40 bg-bad/10 text-bad";
    case "high":
      return "border-bad/40 bg-bad/10 text-bad";
    case "medium":
      return "border-warn/40 bg-warn/10 text-warn";
    case "low":
      return "border-good/40 bg-good/10 text-good";
    case "info":
      return "border-line bg-surface-3 text-muted";
    default:
      return "border-line bg-surface-3 text-muted";
  }
}

export function severityRank(severity: Severity | string | null | undefined): number {
  switch (severity) {
    case "critical":
      return 4;
    case "high":
      return 3;
    case "medium":
      return 2;
    case "low":
      return 1;
    default:
      return 0;
  }
}

const LEVEL_ZH: Record<RiskLevel, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "严重",
};

export function levelLabel(level: RiskLevel | string | null | undefined): string {
  if (!level) return NOT_AVAILABLE;
  return LEVEL_ZH[level as RiskLevel] ?? String(level);
}

export function levelColor(level: RiskLevel | string | null | undefined): string {
  switch (level) {
    case "critical":
      return "border-bad/50 bg-bad/15 text-bad";
    case "high":
      return "border-bad/40 bg-bad/10 text-bad";
    case "medium":
      return "border-warn/40 bg-warn/10 text-warn";
    case "low":
      return "border-good/40 bg-good/10 text-good";
    default:
      return "border-line bg-surface-3 text-muted";
  }
}

const VERIFICATION_ZH: Record<VerificationStatus, string> = {
  pass: "通过",
  warn: "警告",
  fail: "失败",
};

export function verificationLabel(status: VerificationStatus | string | null | undefined): string {
  if (!status) return NOT_AVAILABLE;
  return VERIFICATION_ZH[status as VerificationStatus] ?? String(status);
}

const CATEGORY_ZH: Record<string, string> = {
  profitability: "盈利能力",
  liquidity: "流动性",
  leverage: "杠杆",
  working_capital: "营运资本",
  budget_control: "预算控制",
  market: "市场",
  data_quality: "数据质量",
};

export function categoryLabel(category: string | null | undefined): string {
  if (!category) return NOT_AVAILABLE;
  return CATEGORY_ZH[category] ?? category;
}

const BASIS_ZH: Record<string, string> = {
  actual: "实际",
  budget: "预算",
  variance: "差异",
  forecast: "预测",
  market: "市场",
};

export function basisLabel(basis: string | null | undefined): string {
  if (!basis) return NOT_AVAILABLE;
  return BASIS_ZH[basis] ?? basis;
}

/* -------------------------------------------------------------------------- */
/* periods                                                                    */
/* -------------------------------------------------------------------------- */

/** `2024-12` -> `2024年12月`; a span `2024-01..2024-12` -> `2024年1月 – 2024年12月`. */
export function formatPeriod(period: string | null | undefined): string {
  if (!period) return NOT_AVAILABLE;
  if (period.includes("..")) {
    const [start, end] = period.split("..");
    return `${formatPeriod(start)} – ${formatPeriod(end)}`;
  }
  const match = /^(\d{4})-(\d{2})$/.exec(period.trim());
  if (!match) return period;
  const year = match[1] as string;
  const month = Number(match[2]);
  return `${year}年${month}月`;
}

/** A date or timestamp as `YYYY-MM-DD` (empty when absent). */
export function formatDate(value: string | null | undefined): string {
  if (!value) return NOT_AVAILABLE;
  const match = /^(\d{4}-\d{2}-\d{2})/.exec(value.trim());
  return match ? (match[1] as string) : value;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return NOT_AVAILABLE;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toISOString().slice(0, 16).replace("T", " ");
}

/** Delta with an explicit sign, used by KPI cards and variance tables. */
export function formatDelta(value: number | null | undefined, unit: Unit | string = "USD"): string {
  if (!isPresent(value)) return NOT_AVAILABLE;
  const sign = value > 0 ? "+" : value < 0 ? MINUS : "";
  const body =
    unit === "USD"
      ? formatMoney(Math.abs(value))
      : unit === "pct"
        ? formatPct(Math.abs(value))
        : formatNumber(Math.abs(value), 2);
  return `${sign}${body}`;
}
