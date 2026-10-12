import { describe, expect, it } from "vitest";

import type { CitedValue } from "@/api/types";
import {
  formatDays,
  formatDelta,
  formatMoney,
  formatMoneyCompact,
  formatNumber,
  formatPct,
  formatPeriod,
  formatRatio,
  formatValue,
  formatWithUnit,
  isPresent,
  NOT_AVAILABLE,
  severityColor,
  severityLabel,
} from "@/lib/format";

function cited(overrides: Partial<CitedValue> = {}): CitedValue {
  return {
    metric_id: "gross_margin",
    label: "Gross margin",
    value: 0.2193,
    unit: "pct",
    period: "2024-12",
    basis: "actual",
    formula: "gross_profit / revenue",
    source_ids: ["actual:monthly_financials@2024-12"],
    status: "ok",
    note: null,
    synthetic: true,
    ...overrides,
  };
}

describe("isPresent", () => {
  it("rejects null, undefined, NaN and Infinity", () => {
    expect(isPresent(null)).toBe(false);
    expect(isPresent(undefined)).toBe(false);
    expect(isPresent(Number.NaN)).toBe(false);
    expect(isPresent(Number.POSITIVE_INFINITY)).toBe(false);
    expect(isPresent(0)).toBe(true);
  });
});

describe("formatMoney", () => {
  it("renders whole dollars with thousands separators", () => {
    expect(formatMoney(322304.71)).toBe("$322,305");
    expect(formatMoney(1234567)).toBe("$1,234,567");
    expect(formatMoney(0)).toBe("$0");
  });

  it("uses a typographic minus for negative amounts", () => {
    expect(formatMoney(-48188)).toBe("−$48,188");
  });

  it("returns 不可用 for missing values — never 0", () => {
    for (const missing of [null, undefined, Number.NaN]) {
      const rendered = formatMoney(missing);
      expect(rendered).toBe(NOT_AVAILABLE);
      expect(rendered).not.toContain("0");
    }
  });

  it("formats compact magnitudes for charts", () => {
    expect(formatMoneyCompact(3434785)).toBe("$3.43M");
    expect(formatMoneyCompact(-161576)).toBe("−$161.58K");
    expect(formatMoneyCompact(null)).toBe(NOT_AVAILABLE);
  });
});

describe("formatPct", () => {
  it("scales decimal fractions by 100", () => {
    expect(formatPct(0.2193)).toBe("21.93%");
    expect(formatPct(0.01)).toBe("1%");
    expect(formatPct(-1.13)).toBe("−113%");
  });

  it("adds a sign when asked", () => {
    expect(formatPct(0.052, { signed: true })).toBe("+5.2%");
    expect(formatPct(-0.052, { signed: true })).toBe("−5.2%");
  });

  it("can render percentage points instead of percent", () => {
    expect(formatPct(2.5, { points: true })).toBe("2.5 pp");
  });

  it("never turns a missing ratio into 0", () => {
    expect(formatPct(null)).toBe(NOT_AVAILABLE);
    expect(formatPct(undefined)).toBe(NOT_AVAILABLE);
  });
});

describe("formatDays / formatRatio", () => {
  it("renders days with the Chinese unit", () => {
    expect(formatDays(69.42)).toBe("69.4 天");
    expect(formatDays(null)).toBe(NOT_AVAILABLE);
  });

  it("renders ratios with an x suffix", () => {
    expect(formatRatio(1.5618)).toBe("1.56x");
    expect(formatRatio(undefined)).toBe(NOT_AVAILABLE);
  });
});

describe("formatWithUnit", () => {
  it("maps API units onto the right renderer", () => {
    expect(formatWithUnit(1234, "USD")).toBe("$1,234");
    expect(formatWithUnit(0.1, "pct")).toBe("10%");
    expect(formatWithUnit(45.678, "days")).toBe("45.68 天");
    expect(formatWithUnit(1.5, "x")).toBe("1.5x");
    expect(formatWithUnit(59, "score")).toBe("59 分");
    expect(formatWithUnit(12, "months")).toBe("12 个月");
  });

  it("keeps an unknown unit visible rather than dropping it", () => {
    expect(formatWithUnit(4.83, "percent")).toBe("4.83 percent");
  });

  it("returns 不可用 for missing values", () => {
    expect(formatWithUnit(null, "USD")).toBe(NOT_AVAILABLE);
    expect(formatWithUnit(undefined, "pct")).toBe(NOT_AVAILABLE);
  });
});

describe("formatValue (CitedValue renderer)", () => {
  it("renders an ok percentage value with the unit applied", () => {
    expect(formatValue(cited())).toBe("21.93%");
  });

  it("renders ok money and day values", () => {
    expect(formatValue(cited({ unit: "USD", value: 274200.03 }))).toBe("$274,200");
    expect(formatValue(cited({ unit: "days", value: 69.42 }))).toBe("69.42 天");
    expect(formatValue(cited({ unit: "x", value: 1.56 }))).toBe("1.56x");
  });

  it("returns 不可用 plus the note when status is missing", () => {
    const rendered = formatValue(
      cited({ status: "missing", value: null, note: "No budget layer is available for this dataset." }),
    );
    expect(rendered).toBe(`${NOT_AVAILABLE}（No budget layer is available for this dataset.）`);
  });

  it("returns 不可用 plus the note when status is undefined", () => {
    const rendered = formatValue(cited({ status: "undefined", value: null, note: "zero denominator" }));
    expect(rendered).toBe(`${NOT_AVAILABLE}（zero denominator）`);
  });

  it("treats a null value with status ok as missing", () => {
    expect(formatValue(cited({ value: null }))).toBe(NOT_AVAILABLE);
  });

  it("returns bare 不可用 when there is no note at all", () => {
    expect(formatValue(cited({ status: "missing", value: null, note: null }))).toBe(NOT_AVAILABLE);
    expect(formatValue(null)).toBe(NOT_AVAILABLE);
    expect(formatValue(undefined)).toBe(NOT_AVAILABLE);
  });

  it("never renders 0 for a missing value", () => {
    const missing = formatValue(cited({ status: "missing", value: null, note: null }));
    expect(missing).not.toContain("0");
    expect(missing).toBe(NOT_AVAILABLE);
  });

  it("keeps a partial-coverage note next to a real value", () => {
    expect(formatValue(cited({ unit: "USD", value: 100, note: "partial coverage: 2 source cell(s) missing" }))).toBe(
      "$100（partial coverage: 2 source cell(s) missing）",
    );
  });
});

describe("formatNumber / formatDelta", () => {
  it("groups thousands and respects the decimal budget", () => {
    expect(formatNumber(1234.5678, 2)).toBe("1,234.57");
    expect(formatNumber(0.5, 2)).toBe("0.5");
    expect(formatNumber(null as unknown as number)).toBe(NOT_AVAILABLE);
  });

  it("signs deltas explicitly", () => {
    expect(formatDelta(1200.4, "USD")).toBe("+$1,200");
    expect(formatDelta(-17695, "USD")).toBe("−$17,695");
    expect(formatDelta(null, "USD")).toBe(NOT_AVAILABLE);
  });
});

describe("formatPeriod", () => {
  it("renders single months in Chinese", () => {
    expect(formatPeriod("2024-12")).toBe("2024年12月");
  });

  it("renders spans", () => {
    expect(formatPeriod("2024-01..2024-12")).toBe("2024年1月 – 2024年12月");
  });

  it("returns 不可用 for an absent period", () => {
    expect(formatPeriod(null)).toBe(NOT_AVAILABLE);
    expect(formatPeriod("")).toBe(NOT_AVAILABLE);
  });

  it("passes unknown formats through untouched", () => {
    expect(formatPeriod("Q4-2024")).toBe("Q4-2024");
  });
});

describe("severity helpers", () => {
  it("labels severities in Chinese", () => {
    expect(severityLabel("critical")).toBe("严重");
    expect(severityLabel("medium")).toBe("中");
    expect(severityLabel(null)).toBe(NOT_AVAILABLE);
  });

  it("gives critical and high the danger palette", () => {
    expect(severityColor("critical")).toContain("text-bad");
    expect(severityColor("high")).toContain("text-bad");
    expect(severityColor("medium")).toContain("text-warn");
    expect(severityColor("low")).toContain("text-good");
    expect(severityColor(null)).toContain("text-muted");
  });
});
