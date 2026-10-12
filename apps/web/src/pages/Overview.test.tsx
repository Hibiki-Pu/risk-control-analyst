/**
 * Page-level integration test for the Overview page.
 *
 * The whole `/api/v1` surface the page touches is stubbed at the `fetch` boundary, so this exercises
 * the real client (URL building, error parsing, abort handling), the real shell (health context and
 * the synthetic banner) and the real page: skeleton first, then the loaded values.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "@/App";

const MONTHS = [
  "2024-01",
  "2024-02",
  "2024-03",
  "2024-04",
  "2024-05",
  "2024-06",
  "2024-07",
  "2024-08",
  "2024-09",
  "2024-10",
  "2024-11",
  "2024-12",
];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function cited(metricId: string, label: string, value: number | null, unit: string, status = "ok", note: string | null = null) {
  return {
    metric_id: metricId,
    label,
    value,
    unit,
    period: "2024-12",
    basis: "actual",
    formula: "test",
    source_ids: ["actual:monthly_financials@2024-12"],
    status,
    note,
    synthetic: true,
  };
}

const HEALTH = {
  status: "ok",
  version: "0.1.0",
  dataset: {
    dataset_id: "synthetic-aurelia-v1",
    label: "Aurelia Synthetic Manufacturing",
    kind: "synthetic_seed",
    synthetic: true,
    source_path: "/data/synthetic",
    rows: 120,
    months: MONTHS,
    regions: ["APAC", "EMEA"],
    has_budget_layer: true,
    disclaimer: "Synthetic demo data. Not investment advice.",
  },
  as_of: "2024-12",
  synthetic: true,
  disclaimer: "Synthetic demo data. Not investment advice.",
};

const METRICS = {
  as_of: "2024-12",
  period: "2024-12",
  scope: { regions: "ALL", months: ["2024-12"] },
  currency: "USD",
  synthetic: true,
  values: {
    revenue: cited("revenue", "Revenue", 322304.71, "USD"),
    gross_margin: cited("gross_margin", "Gross margin", 0.2193, "pct"),
    ebit: cited("ebit", "EBIT (operating profit)", 14290.68, "USD"),
    operating_margin: cited("operating_margin", "Operating margin", 0.0443, "pct"),
    dso_days: cited("dso_days", "Days sales outstanding (average receivables)", 69.42, "days"),
    cash: cited("cash", "Cash (closing)", 274200.03, "USD"),
    cash_conversion_cycle_days: cited("cash_conversion_cycle_days", "Cash conversion cycle", 104.45, "days"),
    interest_coverage: cited(
      "interest_coverage",
      "Interest coverage",
      null,
      "x",
      "undefined",
      "interest expense is zero for this period",
    ),
  },
  lineage: ["actual:monthly_financials@2024-12"],
};

const SERIES = {
  as_of: "2024-12",
  granularity: "month",
  currency: "USD",
  synthetic: true,
  scope: { regions: "ALL" },
  points: MONTHS.map((month, index) => ({
    month,
    revenue_usd: 300000 + index * 1000,
    cogs_usd: 230000 + index * 500,
    gross_profit_usd: 70000 + index * 500,
    gross_margin_pct: 0.22,
    ebit_usd: 14000 + index * 100,
    operating_margin_pct: 0.04,
    interest_expense_usd: 9150.3,
    net_income_usd: 5141.2,
    operating_cash_flow_usd: -18288,
    free_cash_flow_usd: -48188,
    dso_days: 69.42,
    cash_usd: 250000 + index * 2000,
    budget_revenue_usd: 340000,
    revenue_variance_usd: -17695,
    revenue_variance_pct: -0.052,
    ebit_variance_usd: -20000,
    mom_revenue_pct: 0.002,
    yoy_revenue_pct: 0.03,
  })),
  lineage: ["actual:monthly_financials@2024-01"],
};

const RISK = {
  as_of: "2024-12",
  period: "2024-12",
  synthetic: true,
  overall_level: "high",
  score: 59,
  signals: [
    {
      signal_id: "RC-06",
      category: "working_capital",
      severity: "high",
      title: "应收账款回收天数超阈值",
      detail: "DSO 69.42 天高于阈值 60 天，现金周转周期被拉长。",
      period: "2024-12",
      observed_value: 69.42,
      unit: "days",
      threshold: 60,
      threshold_unit: "days",
      direction: "above",
      metric_ids: ["dso_days"],
      source_ids: ["actual:monthly_financials@2024-12"],
      supporting: [{ key: "cycle_now", label: "现金周转周期", value: 104.45, unit: "days" }],
      recommended_check: "核对前五大客户的账期与实际回款流水。",
      synthetic: true,
    },
  ],
  data_gaps: ["部分区域缺少 2024-11 的存货明细，DIO 以其余区域估算。"],
  lineage: ["actual:monthly_financials@2024-12"],
};

const COMPANY = {
  profile: {
    company_id: "SYNTH-AURELIA-001",
    display_name: "Aurelia Consumer Goods Pte. Ltd. (Synthetic Demo)",
    display_name_zh: "奥瑞利亚消费品集团（合成演示数据）",
    industry: "Consumer packaged goods",
    regions: [
      { code: "SG", name: "Singapore", currency: "SGD" },
      { code: "TH", name: "Thailand", currency: "THB" },
    ],
    reporting_currency: "USD",
    local_currencies: ["SGD", "THB"],
    fiscal_year_end: "12-31",
    period_range: { start: "2023-01", end: "2024-12", months: 24 },
    consolidation_note: "Regions are funding centres with fixed weights.",
    synthetic: true,
    disclaimer: "Every figure in this dataset is computer generated.",
    generator: { module: "app.data.synthetic", version: "1.0.0", seed: 20260101 },
  },
  dataset_id: "synthetic-aurelia-v1",
  kind: "synthetic_seed",
  synthetic: true,
  seed_manifest: {},
};

let requestedUrls: string[] = [];

beforeEach(() => {
  requestedUrls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      requestedUrls.push(url);
      if (url.includes("/health")) return Promise.resolve(json(HEALTH));
      if (url.includes("/meta/company")) return Promise.resolve(json(COMPANY));
      if (url.includes("/metrics/series")) return Promise.resolve(json(SERIES));
      if (url.includes("/metrics/budget-variance")) return Promise.resolve(json(METRICS));
      if (url.includes("/metrics")) return Promise.resolve(json(METRICS));
      if (url.includes("/risk/register")) return Promise.resolve(json(RISK));
      return Promise.resolve(json({ detail: `unexpected request: ${url}` }, 404));
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function renderApp() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <App />
    </MemoryRouter>,
  );
}

describe("Overview page", () => {
  it("shows skeletons first, then the loaded KPI values", async () => {
    renderApp();

    // Loading state: the KPI grid renders skeletons and no figures yet.
    expect(screen.getAllByTestId("kpi-card").length).toBeGreaterThanOrEqual(8);
    expect(screen.queryByTestId("kpi-value")).not.toBeInTheDocument();

    // Loaded state: the real figure arrives from the mocked API.
    const revenue = await screen.findByText("$322,305");
    expect(revenue).toBeInTheDocument();
    expect(screen.getByText("21.93%")).toBeInTheDocument();
    expect(screen.getByText("69.42 天")).toBeInTheDocument();
  });

  it("keeps the synthetic-data banner and dataset identity visible", async () => {
    renderApp();

    expect(screen.getByTestId("synthetic-banner")).toHaveTextContent("合成演示数据 SYNTHETIC DEMO");
    await waitFor(() => expect(screen.getAllByText(/synthetic-aurelia-v1/).length).toBeGreaterThan(0));
    expect(screen.getByText(/本演示的全部财务数字均由合成数据集生成/)).toBeInTheDocument();
  });

  it("renders the top risk signal and the data-gap note", async () => {
    renderApp();

    expect(await screen.findByText("应收账款回收天数超阈值")).toBeInTheDocument();
    expect(screen.getByText(/部分区域缺少 2024-11 的存货明细/)).toBeInTheDocument();
  });

  it("shows 不可用 for a metric the backend marked undefined", async () => {
    renderApp();

    await screen.findByText("$322,305");
    const unavailable = screen.getByText(/不可用（interest expense is zero for this period）/);
    expect(unavailable).toBeInTheDocument();
    expect(unavailable.textContent).not.toContain("0x");
  });

  it("calls the documented endpoints", async () => {
    renderApp();
    await screen.findByText("$322,305");

    const paths = requestedUrls.map((url) => new URL(url, "http://localhost").pathname + new URL(url, "http://localhost").search);
    expect(paths.some((path) => path.startsWith("/api/v1/health"))).toBe(true);
    expect(paths.some((path) => path.startsWith("/api/v1/metrics?"))).toBe(true);
    expect(paths.some((path) => path.startsWith("/api/v1/metrics/series"))).toBe(true);
    expect(paths.some((path) => path.startsWith("/api/v1/risk/register"))).toBe(true);
    expect(paths.some((path) => path.startsWith("/api/v1/meta/company"))).toBe(true);
  });

  it("renders the dataset identity section from /meta/company", async () => {
    renderApp();
    await screen.findByText(/奥瑞利亚消费品集团/);
    expect(screen.getByText(/Regions are funding centres with fixed weights/)).toBeInTheDocument();
  });
});
