import { describe, expect, it } from "vitest";

import type { CitedValue } from "@/api/types";
import { buildVarianceRows, isFavourable, varianceConvention } from "@/pages/PnlAnalysis";

function cited(metricId: string, value: number | null, status: "ok" | "missing" | "undefined" = "ok", note: string | null = null): CitedValue {
  return {
    metric_id: metricId,
    label: `${metricId} variance vs budget`,
    value,
    unit: "USD",
    period: "2024-12",
    basis: "variance",
    formula: "actual - budget",
    source_ids: [],
    status,
    note,
    synthetic: true,
  };
}

describe("variance sign convention", () => {
  it("treats revenue and EBIT as favourable when the variance is positive", () => {
    expect(varianceConvention("revenue")).toBe("positive");
    expect(varianceConvention("ebit")).toBe("positive");
    expect(isFavourable("revenue", 1000)).toBe(true);
    expect(isFavourable("revenue", -1000)).toBe(false);
    expect(isFavourable("ebit", 500)).toBe(true);
  });

  it("treats cost lines as favourable when the variance is negative", () => {
    for (const metricId of ["cogs", "opex", "capex", "interest_expense"]) {
      expect(varianceConvention(metricId)).toBe("negative");
      expect(isFavourable(metricId, -250)).toBe(true);
      expect(isFavourable(metricId, 250)).toBe(false);
    }
  });

  it("never calls a missing variance favourable or unfavourable", () => {
    expect(isFavourable("revenue", null)).toBeNull();
    expect(isFavourable("revenue", undefined)).toBeNull();
    expect(isFavourable("cogs", null)).toBeNull();
  });

  it("has no convention for an unknown metric id", () => {
    expect(varianceConvention("mystery_line")).toBe("unknown");
    expect(isFavourable("mystery_line", 10)).toBeNull();
  });
});

describe("buildVarianceRows", () => {
  it("returns one row per budgeted metric and keeps the API note", () => {
    const rows = buildVarianceRows({
      revenue_variance: cited("revenue_variance", -17695, "ok", "favorable when actual > plan"),
      revenue_variance_pct: cited("revenue_variance_pct", -0.052),
      cogs_variance: cited("cogs_variance", 1200, "ok", "favorable when actual < plan"),
    });

    expect(rows.map((row) => row.metricId)).toEqual(["revenue", "cogs", "opex", "ebit", "capex", "interest_expense"]);

    const revenue = rows[0];
    expect(revenue?.variance?.note).toBe("favorable when actual > plan");
    expect(revenue?.favourable).toBe(false);

    const cogs = rows[1];
    expect(cogs?.favourable).toBe(false);

    // Metrics the response omitted must not be invented.
    const opex = rows[2];
    expect(opex?.variance).toBeNull();
    expect(opex?.favourable).toBeNull();
  });

  it("marks missing variances as not judgeable", () => {
    const rows = buildVarianceRows({
      revenue_variance: cited("revenue_variance", null, "missing", "No budget layer is available for this dataset."),
    });
    expect(rows[0]?.variance?.status).toBe("missing");
    expect(rows[0]?.favourable).toBeNull();
  });

  it("tolerates an undefined metric set", () => {
    const rows = buildVarianceRows(undefined);
    expect(rows).toHaveLength(6);
    expect(rows.every((row) => row.variance === null && row.favourable === null)).toBe(true);
  });
});
