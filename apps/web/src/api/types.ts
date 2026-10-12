/**
 * TypeScript mirror of the v1 API contract (docs/api-contract.md + services/api/app/schemas.py).
 *
 * Rules encoded here:
 *  - every number travels as a `CitedValue` that carries its unit, period, citation and status;
 *  - `status !== "ok"` (or a `null` value) means "not available" — never zero;
 *  - percentages are DECIMAL FRACTIONS (`0.2193` = 21.93%).
 */

/* -------------------------------------------------------------------------- */
/* shared vocabulary                                                          */
/* -------------------------------------------------------------------------- */

export type Status = "ok" | "missing" | "undefined";
export type Basis = "actual" | "budget" | "variance" | "forecast" | "market";

/** Units the backend is allowed to send. `unit` is a free string server-side, so we
 *  keep a union of the documented values plus `string` for forward compatibility. */
export type Unit =
  | "USD"
  | "pct"
  | "days"
  | "x"
  | "pp"
  | "percent_points"
  | "months"
  | "cells"
  | "score"
  | "raw"
  | (string & {});

export type Severity = "info" | "low" | "medium" | "high" | "critical";
export type RiskLevel = "low" | "medium" | "high" | "critical";
export type VerificationStatus = "pass" | "warn" | "fail";
export type RiskCategory =
  | "profitability"
  | "liquidity"
  | "leverage"
  | "working_capital"
  | "budget_control"
  | "market"
  | "data_quality";

/** A single auditable number. */
export interface CitedValue {
  metric_id: string;
  label: string;
  value: number | null;
  unit: Unit;
  period: string;
  basis: Basis;
  formula: string;
  source_ids: string[];
  status: Status;
  note: string | null;
  synthetic: boolean;
}

/** A cited number is renderable only when the backend says so and sent a value. */
export function isAvailable(value: Pick<CitedValue, "value" | "status"> | null | undefined): boolean {
  return !!value && value.status === "ok" && value.value !== null && value.value !== undefined;
}

/* -------------------------------------------------------------------------- */
/* health / meta                                                              */
/* -------------------------------------------------------------------------- */

export interface DatasetManifest {
  dataset_id: string;
  label: string;
  kind: string; // "synthetic_seed" | "uploaded_file"
  synthetic: boolean;
  source_path: string | null;
  rows: number;
  months: string[];
  regions: string[];
  has_budget_layer: boolean;
  disclaimer: string | null;
}

export interface HealthResponse {
  status: string;
  version: string;
  dataset: DatasetManifest;
  as_of: string;
  synthetic: boolean;
  disclaimer: string;
}

export interface DataLineage {
  dataset_id: string;
  name: string;
  kind: "synthetic_seed" | "uploaded_file" | "market_fixture" | "market_live";
  origin: string;
  as_of: string;
  rows: number;
  synthetic: boolean;
  columns: string[];
  notes: string[];
}

export interface LineageResponse {
  lineage: DataLineage[];
}

export interface CompanyRegion {
  code: string;
  name: string;
  currency: string;
}

export interface CompanyProfile {
  company_id: string;
  display_name: string;
  display_name_zh?: string;
  industry: string;
  regions: CompanyRegion[];
  reporting_currency: string;
  local_currencies: string[];
  fiscal_year_end: string;
  period_range: { start: string; end: string; months: number };
  consolidation_note: string;
  synthetic: boolean;
  disclaimer: string;
  generator: { module: string; version: string; seed: number | null };
}

export interface CompanyProfileResponse {
  profile: CompanyProfile;
  dataset_id: string;
  kind: string;
  synthetic: boolean;
  seed_manifest: Record<string, unknown>;
}

/* -------------------------------------------------------------------------- */
/* metrics                                                                    */
/* -------------------------------------------------------------------------- */

export interface MetricSetScope {
  regions?: string[] | "ALL";
  months?: string[];
}

/** `/metrics` and `/metrics/budget-variance` both return this shape. */
export interface MetricSet {
  as_of: string;
  period: string;
  scope: MetricSetScope;
  currency: string;
  synthetic: boolean;
  values: Record<string, CitedValue>;
  lineage: string[];
}

export interface MonthlyPoint {
  month: string;
  revenue_usd: number | null;
  cogs_usd: number | null;
  gross_profit_usd: number | null;
  gross_margin_pct: number | null;
  ebit_usd: number | null;
  operating_margin_pct: number | null;
  interest_expense_usd: number | null;
  net_income_usd: number | null;
  operating_cash_flow_usd: number | null;
  free_cash_flow_usd: number | null;
  dso_days: number | null;
  cash_usd: number | null;
  budget_revenue_usd: number | null;
  revenue_variance_usd: number | null;
  revenue_variance_pct: number | null;
  ebit_variance_usd: number | null;
  mom_revenue_pct: number | null;
  yoy_revenue_pct: number | null;
}

export interface PeriodSeries {
  as_of: string;
  granularity: "month";
  currency: string;
  synthetic: boolean;
  scope: MetricSetScope;
  points: MonthlyPoint[];
  lineage: string[];
}

/* -------------------------------------------------------------------------- */
/* risk register                                                              */
/* -------------------------------------------------------------------------- */

export interface SupportingValue {
  key: string;
  label: string;
  value: number | null;
  unit: Unit;
}

export interface RiskSignal {
  signal_id: string;
  category: RiskCategory;
  severity: Severity;
  title: string;
  detail: string;
  period: string;
  observed_value: number | null;
  unit: Unit;
  threshold: number | null;
  threshold_unit: Unit;
  direction: "above" | "below" | "change";
  metric_ids: string[];
  source_ids: string[];
  supporting: SupportingValue[];
  recommended_check: string;
  synthetic: boolean;
}

export interface RiskRegister {
  as_of: string;
  period: string;
  synthetic: boolean;
  overall_level: RiskLevel;
  score: number;
  signals: RiskSignal[];
  data_gaps: string[];
  lineage: string[];
}

/* -------------------------------------------------------------------------- */
/* market                                                                     */
/* -------------------------------------------------------------------------- */

export interface MarketCatalogItem {
  series_id: string;
  title: string;
  units: string;
  frequency: string;
  country: string;
  rationale: string;
  source_url: string;
  available: boolean;
}

export interface MarketCatalogResponse {
  series: MarketCatalogItem[];
  fred_configured: boolean;
  policy: string;
}

export interface MarketObservation {
  date: string;
  value: number | null;
}

export interface MarketSeries {
  series_id: string;
  title: string;
  units: string;
  frequency: "daily" | "weekly" | "monthly" | "quarterly" | "annual" | "unknown";
  country: string;
  source_name: string;
  source_url: string;
  fetched_at: string;
  latest_observation_date: string | null;
  latest_value: number | null;
  previous_value: number | null;
  change: number | null;
  observations: MarketObservation[];
  is_fixture: boolean;
  is_stale: boolean;
  stale_after_days: number;
  alignment_note: string;
  license_note: string;
  error: string | null;
}

/* -------------------------------------------------------------------------- */
/* scenarios                                                                  */
/* -------------------------------------------------------------------------- */

/** Driver-based what-if inputs. Mirrors `ScenarioAssumptions` (extra="forbid"). */
export interface ScenarioAssumptions {
  horizon_months: number;
  volume_growth_pct: number;
  price_change_pct: number;
  material_cost_change_pct: number;
  labor_cost_change_pct: number;
  overhead_cost_change_pct: number;
  opex_change_pct: number;
  interest_rate_delta_pp: number;
  fx_change_pct: number;
  dso_days_delta: number;
}

export interface ScenarioRequest {
  assumptions: ScenarioAssumptions;
  include_presets: boolean;
  label: string;
}

export interface ScenarioDefinition {
  scenario_id: "base" | "upside" | "downside";
  label: string;
  description: string;
  assumptions: ScenarioAssumptions;
}

export interface ScenarioPresetsResponse {
  presets: ScenarioDefinition[];
}

export interface ScenarioMonth {
  month: string;
  revenue_usd: number;
  cogs_usd: number;
  gross_profit_usd: number;
  gross_margin_pct: number | null;
  ebit_usd: number;
  operating_margin_pct: number | null;
  interest_expense_usd: number;
  net_income_usd: number;
  operating_cash_flow_usd: number;
  free_cash_flow_usd: number;
  cash_usd: number;
  dso_days: number | null;
}

export interface ScenarioSummary {
  scenario_id: string;
  label: string;
  currency: string;
  horizon_months: number;
  revenue_usd: number;
  gross_profit_usd: number;
  gross_margin_pct: number | null;
  ebit_usd: number;
  operating_margin_pct: number | null;
  interest_expense_usd: number;
  net_income_usd: number;
  operating_cash_flow_usd: number;
  free_cash_flow_usd: number;
  ending_cash_usd: number;
  minimum_cash_usd: number;
  revenue_delta_usd: number;
  ebit_delta_usd: number;
  ebit_delta_pct: number | null;
  fcf_delta_usd: number;
  cash_runway_months: number | null;
  months_with_negative_cash: number;
}

export interface SensitivityItem {
  driver: string;
  label: string;
  shock: string;
  ebit_impact_usd_low: number;
  ebit_impact_usd_high: number;
  ebit_swing_usd: number;
}

export interface ScenarioResult {
  as_of: string;
  base_period: string;
  horizon_months: number;
  currency: string;
  synthetic: boolean;
  baseline: ScenarioSummary;
  scenarios: ScenarioSummary[];
  monthly: Record<string, ScenarioMonth[]>;
  sensitivities: SensitivityItem[];
  assumptions: Record<string, ScenarioAssumptions>;
  model_note: string;
  lineage: string[];
}

/* -------------------------------------------------------------------------- */
/* agent                                                                      */
/* -------------------------------------------------------------------------- */

export interface ToolCallRecord {
  call_id: string;
  tool: string;
  arguments: Record<string, unknown>;
  status: "ok" | "rejected" | "error";
  error: string | null;
  duration_ms: number;
  result_summary: string;
  started_at: string;
  citations: string[];
}

export interface Evidence {
  citation_id: string;
  kind: "metric" | "risk_signal" | "scenario" | "market_series" | "lineage";
  label: string;
  value: number | null;
  unit: Unit;
  period: string;
  source_ids: string[];
}

export interface AgentAnswer {
  question: string;
  engine: string;
  as_of: string;
  synthetic: boolean;
  conclusion: string;
  key_findings: string[];
  evidence: Evidence[];
  assumptions: string[];
  risks: string[];
  recommendations: string[];
  confidence_limits: string[];
  missing_data: string[];
  tool_calls: ToolCallRecord[];
  disclaimer: string;
}

export interface AgentAskRequest {
  question: string;
  month?: string | null;
}

export interface AgentToolsResponse {
  tools: { name: string; description: string; parameters: Record<string, unknown> }[];
}

export interface AgentAuditResponse {
  count: number;
  records: ToolCallRecord[];
  note: string;
}

/* -------------------------------------------------------------------------- */
/* reports                                                                    */
/* -------------------------------------------------------------------------- */

export interface VerificationItem {
  check_id: string;
  description: string;
  status: VerificationStatus;
  detail: string;
}

export interface ReportDocument {
  report_id: string;
  title: string;
  as_of: string;
  generated_at: string;
  period: string;
  currency: string;
  synthetic: boolean;
  markdown: string;
  html: string;
  citations: string[];
  verification: VerificationItem[];
  verification_status: VerificationStatus;
  engine: string;
}

export interface ReportRequest {
  month?: string | null;
  horizon_months: number;
}

/* -------------------------------------------------------------------------- */
/* data                                                                       */
/* -------------------------------------------------------------------------- */

export interface IngestRecord {
  upload_id: string;
  filename: string;
  received_at: string;
  report: Record<string, unknown>;
  activated: boolean;
}

export interface UploadsResponse {
  uploads: IngestRecord[];
}
