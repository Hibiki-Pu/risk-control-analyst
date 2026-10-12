import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CitedValue } from "@/api/types";
import { KpiCard } from "@/components/KpiCard";
import { NOT_AVAILABLE } from "@/lib/format";

function cited(overrides: Partial<CitedValue> = {}): CitedValue {
  return {
    metric_id: "revenue",
    label: "Revenue",
    value: 322304.71,
    unit: "USD",
    period: "2024-12",
    basis: "actual",
    formula: "sum(revenue_usd)",
    source_ids: ["actual:monthly_financials@2024-12"],
    status: "ok",
    note: null,
    synthetic: true,
    ...overrides,
  };
}

describe("KpiCard", () => {
  it("renders the value with its unit and period", () => {
    render(<KpiCard cited={cited()} />);

    expect(screen.getByText("Revenue")).toBeInTheDocument();
    expect(screen.getByTestId("kpi-value")).toHaveTextContent("$322,305");
    expect(screen.getByTestId("kpi-period")).toHaveTextContent("2024年12月");
    expect(screen.getByText("USD")).toBeInTheDocument();
    expect(screen.getByTestId("kpi-card")).toHaveAttribute("data-state", "ok");
  });

  it("shows the 缺数据 state instead of a number when the value is missing", () => {
    render(
      <KpiCard
        cited={cited({
          metric_id: "budget_variance",
          label: "Revenue variance vs budget",
          value: null,
          unit: "USD",
          status: "missing",
          note: "No budget layer is available for this dataset.",
        })}
      />,
    );

    const value = screen.getByTestId("kpi-value");
    expect(value).toHaveTextContent(NOT_AVAILABLE);
    expect(value).not.toHaveTextContent("$0");
    expect(screen.getByTestId("kpi-missing-chip")).toBeInTheDocument();
    expect(screen.getByText("缺数据")).toBeInTheDocument();
    // The citation note must be visible; the number must never silently become zero.
    expect(screen.getAllByText(/No budget layer is available/).length).toBeGreaterThan(0);
    expect(screen.getByTestId("kpi-card")).toHaveAttribute("data-state", "missing");
  });

  it("explains an undefined ratio (zero denominator) instead of printing 0", () => {
    render(
      <KpiCard
        cited={cited({
          metric_id: "revenue_variance_pct",
          label: "Revenue variance vs budget (%)",
          value: null,
          unit: "pct",
          status: "undefined",
          note: "budget value is zero",
        })}
      />,
    );

    expect(screen.getByTestId("kpi-value")).toHaveTextContent(`${NOT_AVAILABLE}（budget value is zero）`);
    expect(screen.getByText("口径未定义")).toBeInTheDocument();
  });

  it("renders a skeleton while loading", () => {
    render(<KpiCard cited={cited()} loading />);
    expect(screen.getByTestId("kpi-card")).toHaveAttribute("data-state", "loading");
    expect(screen.queryByTestId("kpi-value")).not.toBeInTheDocument();
  });

  it("renders a raw number honestly when no CitedValue is supplied", () => {
    render(<KpiCard label="风险信号总数" value={4} unit="raw" period="2024-12" />);
    expect(screen.getByTestId("kpi-value")).toHaveTextContent("4");
  });

  it("does not invent a value when the raw number is absent", () => {
    render(<KpiCard label="现金跑道" value={null} unit="months" period="2024-12" unavailableReason="无净燃烧" />);
    expect(screen.getByTestId("kpi-value")).toHaveTextContent(`${NOT_AVAILABLE}（无净燃烧）`);
  });

  it("shows the delta when provided", () => {
    render(<KpiCard cited={cited()} delta={-17695} deltaUnit="USD" deltaLabel="较上月" />);
    const delta = screen.getByTestId("kpi-delta");
    expect(delta).toHaveTextContent("较上月");
    expect(delta).toHaveTextContent("−$17,695");
  });
});
