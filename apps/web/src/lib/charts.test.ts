/**
 * Axis-tick formatting.
 *
 * Regression under test: percentage axes were labelled with 0 decimals on an unscaled decimal
 * fraction, so a margin chart read "0 0 0 0" — the data was right, the axis was unreadable.
 */

import { describe, expect, it } from "vitest";

import { axisFormatterFor, buildSeriesChart } from "@/lib/charts";

describe("axisFormatterFor", () => {
  it("scales a percentage axis by 100", () => {
    const fmt = axisFormatterFor("小数比例");
    expect(fmt(0.2193)).toBe("22%");
    expect(fmt(0)).toBe("0%");
    expect(fmt(-0.05)).toBe("−5%");
  });

  it("recognises percent-ish labels in both languages", () => {
    for (const name of ["利润率", "Percent", "ratio (%)", "毛利率（%）"]) {
      expect(axisFormatterFor(name)(0.25)).toBe("25%");
    }
  });

  it("keeps money axes ungrouped-free of decimals", () => {
    expect(axisFormatterFor("USD")(322304.71)).toBe("322,305");
    expect(axisFormatterFor("千美元")(250)).toBe("250");
  });

  it("does not mistake an index label for a ratio", () => {
    // "Index 1982=100" contains an "x" inside a word and must stay an integer axis.
    expect(axisFormatterFor("Index 1982=100")(261.4)).toBe("261");
  });

  it("handles days and multiples", () => {
    expect(axisFormatterFor("天")(69.42)).toBe("69.4");
    expect(axisFormatterFor("倍")(1.5618)).toBe("1.56");
    expect(axisFormatterFor("x")(1.5618)).toBe("1.56");
  });

  it("falls back to thousands for an unknown label", () => {
    expect(axisFormatterFor(undefined)(1234.5)).toBe("1,235");
  });
});

describe("buildSeriesChart", () => {
  const base = {
    title: "利润率与现金",
    unit: "% / USD",
    period: "2024-01..2024-12",
    labels: ["24-01", "24-02"],
  };

  it("formats the two axes from their own labels", () => {
    const option = buildSeriesChart({
      ...base,
      yAxisName: "USD",
      y2AxisName: "利润率",
      series: [
        { name: "期末现金", data: [1000, 900] },
        { name: "毛利率", data: [0.2193, 0.21], yAxisIndex: 1 },
      ],
    });
    const axes = option.yAxis as Array<{ axisLabel: { formatter: (value: number) => string } }>;
    expect(axes).toHaveLength(2);
    expect(axes[0]!.axisLabel.formatter(322304.71)).toBe("322,305");
    expect(axes[1]!.axisLabel.formatter(0.2193)).toBe("22%");
  });

  it("honours an explicit axis format override", () => {
    const option = buildSeriesChart({
      ...base,
      yAxisName: "USD",
      yAxisFormat: (value: number) => `~${Math.round(value / 1000)}k`,
      series: [{ name: "收入", data: [1000] }],
    });
    const axes = option.yAxis as Array<{ axisLabel: { formatter: (value: number) => string } }>;
    expect(axes[0]!.axisLabel.formatter(322304.71)).toBe("~322k");
  });

  it("renders a single axis when no right axis is requested", () => {
    const option = buildSeriesChart({ ...base, series: [{ name: "收入", data: [1] }] });
    expect(option.yAxis as unknown[]).toHaveLength(1);
  });

  it("always states the unit and the period", () => {
    const option = buildSeriesChart({ ...base, series: [{ name: "收入", data: [1] }] });
    const title = option.title as { subtext?: string };
    expect(title.subtext).toContain("单位：% / USD");
    expect(title.subtext).toContain("2024年1月");
  });
});
