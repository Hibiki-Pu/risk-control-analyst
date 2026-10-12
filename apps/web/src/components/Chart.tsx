/**
 * Thin ECharts wrapper.
 *
 * Only the chart types this app needs are registered, and the wrapper owns the parts that are easy
 * to get wrong: instance lifecycle, container resizing, and the colour tokens that flip with the
 * light/dark preference. Every chart built on top of it is required to state its unit and period in
 * the title, because a chart without units is an unverifiable chart.
 */

import type { BarSeriesOption, GaugeSeriesOption, LineSeriesOption } from "echarts/charts";
import { BarChart, GaugeChart, LineChart } from "echarts/charts";
import type {
  DataZoomComponentOption,
  GridComponentOption,
  LegendComponentOption,
  TitleComponentOption,
  TooltipComponentOption,
} from "echarts/components";
import { DataZoomComponent, GridComponent, LegendComponent, TitleComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import type { ComposeOption, EChartsType } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useMemo, useRef, useState } from "react";

export type ChartOption = ComposeOption<
  | LineSeriesOption
  | BarSeriesOption
  | GaugeSeriesOption
  | GridComponentOption
  | TooltipComponentOption
  | LegendComponentOption
  | TitleComponentOption
  | DataZoomComponentOption
>;

echarts.use([
  LineChart,
  BarChart,
  GaugeChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  DataZoomComponent,
  CanvasRenderer,
]);

export const CHART_PALETTE = ["#3b82f6", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#06b6d4", "#84cc16"];

function readToken(name: string, fallback: string): string {
  if (typeof window === "undefined" || typeof window.getComputedStyle !== "function") return fallback;
  const value = window.getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

export interface TokenSet {
  grid: string;
  ink: string;
  accent: string;
  dark: boolean;
}
function readTokens(): TokenSet {
  const dark = typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-color-scheme: dark)").matches
    : false;
  return {
    grid: readToken("--chart-grid", dark ? "#2c3646" : "#dde3ec"),
    ink: readToken("--chart-ink", dark ? "#9aa8bd" : "#4a566a"),
    accent: readToken("--accent", dark ? "#6aa2ff" : "#1a5cc4"),
    dark,
  };
}

/** Shared look-and-feel; page-level options are merged on top of this. */
export function baseChartOption(tokens: TokenSet, title: string, subtitle?: string): ChartOption {
  return {
    backgroundColor: "transparent",
    color: CHART_PALETTE,
    textStyle: { color: tokens.ink, fontFamily: "inherit" },
    title: {
      text: title,
      subtext: subtitle,
      left: 0,
      top: 0,
      textStyle: { color: tokens.ink, fontSize: 13, fontWeight: 600 },
      subtextStyle: { color: tokens.ink, fontSize: 11 },
    },
    grid: { left: 8, right: 16, top: subtitle ? 62 : 44, bottom: 8, containLabel: true },
    legend: {
      top: subtitle ? 30 : 4,
      right: 0,
      icon: "roundRect",
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: tokens.ink, fontSize: 11 },
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: tokens.dark ? "#1b2230" : "#ffffff",
      borderColor: tokens.grid,
      textStyle: { color: tokens.dark ? "#e8edf4" : "#171e28", fontSize: 12 },
      axisPointer: { type: "cross", label: { backgroundColor: tokens.accent } },
    },
    dataZoom: [
      { type: "inside", throttle: 50 },
      { type: "slider", height: 14, bottom: 0, borderColor: tokens.grid, textStyle: { color: tokens.ink, fontSize: 10 } },
    ],
  };
}

function withTokenColors(option: ChartOption, tokens: TokenSet): ChartOption {
  const merged = { ...option } as ChartOption & Record<string, unknown>;

  const colourAxis = (axis: unknown): unknown => {
    if (!axis) return axis;
    const list = Array.isArray(axis) ? axis : [axis];
    return list.map((entry) => {
      const item = { ...(entry as Record<string, unknown>) };
      item["axisLine"] = { lineStyle: { color: tokens.grid }, ...(item["axisLine"] as object | undefined) };
      item["axisLabel"] = { color: tokens.ink, ...(item["axisLabel"] as object | undefined) };
      item["splitLine"] = { lineStyle: { color: tokens.grid, type: "dashed" }, ...(item["splitLine"] as object | undefined) };
      item["nameTextStyle"] = { color: tokens.ink, ...(item["nameTextStyle"] as object | undefined) };
      return item;
    });
  };

  if (merged.xAxis) merged.xAxis = colourAxis(merged.xAxis) as ChartOption["xAxis"];
  if (merged.yAxis) merged.yAxis = colourAxis(merged.yAxis) as ChartOption["yAxis"];
  return merged;
}

export interface ChartProps {
  option: ChartOption;
  height?: number | string;
  className?: string;
  ariaLabel: string;
  testId?: string;
}

export function Chart({ option, height = 320, className = "", ariaLabel, testId = "chart" }: ChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<EChartsType | null>(null);
  const [tokens, setTokens] = useState<TokenSet>(() => readTokens());

  // Follow the OS light/dark preference so the chart canvas matches the CSS surfaces.
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setTokens(readTokens());
    if (typeof query.addEventListener === "function") {
      query.addEventListener("change", onChange);
      return () => query.removeEventListener("change", onChange);
    }
    query.addListener(onChange);
    return () => query.removeListener(onChange);
  }, []);

  useEffect(() => {
    if (!containerRef.current) return;
    const instance = echarts.init(containerRef.current, undefined, { renderer: "canvas" });
    chartRef.current = instance;
    return () => {
      instance.dispose();
      chartRef.current = null;
    };
  }, []);

  const resolved = useMemo(() => withTokenColors(option, tokens), [option, tokens]);

  useEffect(() => {
    const instance = chartRef.current;
    if (!instance) return;
    instance.setOption(resolved, { notMerge: true });
  }, [resolved]);

  useEffect(() => {
    const container = containerRef.current;
    const instance = chartRef.current;
    if (!container || !instance) return;
    const resize = () => instance.resize();
    let observer: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(resize);
      observer.observe(container);
    }
    window.addEventListener("resize", resize);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label={ariaLabel}
      data-testid={testId}
      className={className}
      style={{ width: "100%", height: typeof height === "number" ? `${height}px` : height }}
    />
  );
}

export default Chart;
