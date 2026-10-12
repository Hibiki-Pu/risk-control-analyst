/**
 * Chart option builders with mandatory units.
 *
 * Every builder puts the unit and the period into the chart title/subtitle, so a chart can never be
 * read without knowing what it measures and over which window. Colour tokens are injected later by
 * `Chart` (which reads the CSS custom properties), so nothing here hard-codes a theme.
 */

import type { ChartOption } from "@/components/Chart";
import { baseChartOption } from "@/components/Chart";
import { formatNumber, formatPct, formatPeriod } from "@/lib/format";

export interface SeriesSpec {
  name: string;
  data: (number | null)[];
  type?: "line" | "bar";
  yAxisIndex?: number;
  area?: boolean;
  dashed?: boolean;
  color?: string;
}

export interface BuildChartArgs {
  title: string;
  /** Human-readable unit, e.g. `USD`, `%（小数比例）`, `天`. Always rendered. */
  unit: string;
  period: string;
  labels: string[];
  series: SeriesSpec[];
  yAxisName?: string;
  y2AxisName?: string;
  /** Format applied inside the tooltip; defaults to a formatter derived from the unit. */
  valueFormat?: (value: number | null) => string;
  /** Adds a note to the subtitle, e.g. which months could not be plotted. */
  note?: string;
}

// Placeholder palette; `Chart` overrides grid/ink colours from the live CSS tokens.
const NEUTRAL_TOKENS = { grid: "#ccd4e0", ink: "#8899aa", accent: "#1a5cc4", dark: false };

function defaultFormatter(unit: string): (value: number | null) => string {
  if (unit.includes("%")) return (value) => (value === null ? "不可用" : formatPct(value));
  if (unit === "天") return (value) => (value === null ? "不可用" : `${formatNumber(value, 1)} 天`);
  if (unit === "倍") return (value) => (value === null ? "不可用" : `${formatNumber(value, 2)}x`);
  return (value) => (value === null ? "不可用" : formatNumber(value, 0));
}

/** Build a line/bar chart option that always declares its unit and period. */
export function buildSeriesChart(args: BuildChartArgs): ChartOption {
  const periodText = formatPeriod(args.period);
  const subtitleParts = [`单位：${args.unit}`, `期间：${periodText}`];
  if (args.note) subtitleParts.push(args.note);
  const base = baseChartOption(NEUTRAL_TOKENS, args.title, subtitleParts.join(" · "));
  const formatter = args.valueFormat ?? defaultFormatter(args.unit);

  const option: ChartOption = {
    ...base,
    xAxis: {
      type: "category",
      data: args.labels,
      name: "月份",
      nameLocation: "end",
      boundaryGap: args.series.some((item) => item.type === "bar"),
      axisLabel: { hideOverlap: true, formatter: (value: string) => value.slice(2) },
    },
    yAxis: [
      {
        type: "value",
        name: args.yAxisName ?? args.unit,
        axisLabel: { formatter: (value: number) => formatNumber(value, 0) },
      },
      ...(args.y2AxisName
        ? [
            {
              type: "value" as const,
              name: args.y2AxisName,
              position: "right" as const,
              axisLabel: { formatter: (value: number) => formatNumber(value, 2) },
              splitLine: { show: false },
            },
          ]
        : []),
    ],
    series: args.series.map((spec) => ({
      name: spec.name,
      type: spec.type ?? "line",
      data: spec.data,
      yAxisIndex: spec.yAxisIndex ?? 0,
      smooth: (spec.type ?? "line") === "line",
      showSymbol: false,
      connectNulls: false,
      barMaxWidth: 26,
      itemStyle: spec.color ? { color: spec.color } : undefined,
      lineStyle: spec.dashed ? { type: "dashed" } : undefined,
      areaStyle: spec.area ? { opacity: 0.12 } : undefined,
      emphasis: { focus: "series" },
    })),
    tooltip: {
      ...(base.tooltip as object),
      valueFormatter: (value: unknown) => formatter(typeof value === "number" ? value : null),
    },
  };

  return option;
}

export interface TornadoItem {
  driver: string;
  label: string;
  shock: string;
  ebit_impact_usd_low: number;
  ebit_impact_usd_high: number;
  ebit_swing_usd: number;
}

const NEGATIVE_COLOR = "#ef4444";
const POSITIVE_COLOR = "#10b981";

/** Colour encodes the direction of the impact, never the series index. */
function impactPoint(value: number): { value: number; itemStyle: { color: string } } {
  return { value, itemStyle: { color: value < 0 ? NEGATIVE_COLOR : POSITIVE_COLOR } };
}

/** Tornado chart: EBIT impact of each driver at ±shock, sorted by swing. */
export function buildTornadoChart(items: TornadoItem[], period: string): ChartOption {
  const base = baseChartOption(
    NEUTRAL_TOKENS,
    "敏感度（EBIT 摆动）",
    `单位：USD · 基准期：${formatPeriod(period)} · 每根条形为一个驱动因子的 ±冲击区间`,
  );
  const sorted = [...items].sort((left, right) => left.ebit_swing_usd - right.ebit_swing_usd);
  const option: ChartOption = {
    ...base,
    grid: { left: 8, right: 24, top: 62, bottom: 8, containLabel: true },
    xAxis: {
      type: "value",
      name: "EBIT 影响 (USD)",
      axisLabel: { formatter: (value: number) => formatNumber(value, 0) },
    },
    yAxis: {
      type: "category",
      data: sorted.map((item) => item.label),
      axisLabel: { fontSize: 11 },
    },
    series: [
      {
        name: "EBIT 影响（负向）",
        type: "bar",
        stack: "impact",
        data: sorted.map((item) => impactPoint(item.ebit_impact_usd_low)),
      },
      {
        name: "EBIT 影响（正向）",
        type: "bar",
        stack: "impact",
        data: sorted.map((item) => impactPoint(item.ebit_impact_usd_high)),
      },
    ],
    tooltip: {
      ...(base.tooltip as object),
      // Item trigger: the driver label is the category, so the default body already names the driver.
      trigger: "item",
    },
  };
  return option;
}
