/** Data helpers shared by the pages. */

import type { CitedValue, MonthlyPoint, RiskSignal, Unit } from "@/api/types";
import { isAvailable } from "@/api/types";

/**
 * Wrap a raw number (scenario output, market observation) so it can go through the exact same
 * rendering path as an API `CitedValue`. `value: null` stays missing — it never becomes 0.
 */
export function cite(
  label: string,
  value: number | null | undefined,
  unit: Unit = "USD",
  period = "",
  note: string | null = null,
): CitedValue {
  const present = typeof value === "number" && Number.isFinite(value);
  return {
    metric_id: label,
    label,
    value: present ? (value as number) : null,
    unit,
    period,
    basis: "actual",
    formula: "",
    source_ids: [],
    status: present ? "ok" : "missing",
    note: present ? note : (note ?? "上游接口未提供该数值"),
    synthetic: true,
  };
}

/** Pick a metric out of a `MetricSet`, tolerating a metric the backend did not send. */
export function metric(values: Record<string, CitedValue> | undefined, metricId: string): CitedValue | null {
  return values?.[metricId] ?? null;
}

/** Value of a cited metric, or null. Never coerces missing to zero. */
export function metricValue(values: Record<string, CitedValue> | undefined, metricId: string): number | null {
  const found = metric(values, metricId);
  return isAvailable(found) ? (found as CitedValue).value : null;
}

export function metricLabel(values: Record<string, CitedValue> | undefined, metricId: string, fallback = metricId): string {
  return values?.[metricId]?.label ?? fallback;
}

/**
 * `MonthlyPoint` fields are nullable. Chart series that contain a missing month must render a gap,
 * not a zero, so the whole series is dropped to null when any point is missing and the caller is
 * told which months are incomplete.
 */
export interface SeriesExtraction {
  labels: string[];
  values: (number | null)[];
  missingMonths: string[];
}

export function extractSeries(
  points: MonthlyPoint[],
  field: keyof Omit<MonthlyPoint, "month">,
): SeriesExtraction {
  const labels: string[] = [];
  const values: (number | null)[] = [];
  const missingMonths: string[] = [];
  for (const point of points) {
    labels.push(point.month);
    const raw = point[field];
    const value = typeof raw === "number" && Number.isFinite(raw) ? raw : null;
    values.push(value);
    if (value === null) missingMonths.push(point.month);
  }
  return { labels, values, missingMonths };
}

export function hasAnyValue(values: (number | null)[]): boolean {
  return values.some((value) => value !== null);
}

/**
 * Turn a risk signal's observed value / threshold into the same auditable shape as an API
 * `CitedValue`, so a missing observation is rendered as `不可用` instead of a bare number.
 */
export function riskCited(
  signal: RiskSignal,
  value: number | null,
  unit: Unit,
  missingNote: string,
): CitedValue {
  const present = typeof value === "number" && Number.isFinite(value);
  return {
    metric_id: signal.signal_id,
    label: signal.title,
    value: present ? (value as number) : null,
    unit,
    period: signal.period,
    basis: "actual",
    formula: "",
    source_ids: signal.source_ids,
    status: present ? "ok" : "undefined",
    note: present ? null : missingNote,
    synthetic: signal.synthetic,
  };
}

/* -------------------------------------------------------------------------- */
/* month ranges                                                               */
/* -------------------------------------------------------------------------- */
export interface MonthRange {
  start: string;
  end: string;
  months: string[];
}

/** The last `count` months of the dataset, oldest first. */
export function deriveRange(months: string[], count: number): MonthRange | null {
  if (!months.length) return null;
  const sorted = [...months].sort();
  const slice = sorted.slice(Math.max(0, sorted.length - count));
  const start = slice[0];
  const end = slice[slice.length - 1];
  if (!start || !end) return null;
  return { start, end, months: slice };
}

/** Month-over-month delta of a monthly series, ignoring gaps. */
export function lastDelta(values: (number | null)[]): number | null {
  if (values.length < 2) return null;
  const current = values[values.length - 1];
  const previous = values[values.length - 2];
  if (current === null || previous === null || previous === undefined || current === undefined) return null;
  return current - previous;
}

/** The month label of the last complete observation. */
export function lastMonth(months: string[]): string | null {
  if (!months.length) return null;
  return [...months].sort()[months.length - 1] ?? null;
}
