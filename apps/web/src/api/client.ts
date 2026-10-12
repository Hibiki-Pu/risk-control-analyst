/**
 * Typed fetch wrapper around the FastAPI service.
 *
 * - base path is `/api/v1` (the Vite dev proxy forwards `/api` to the API, so the browser
 *   never needs CORS). Override with `VITE_API_BASE` when the API lives elsewhere.
 * - non-2xx answers are parsed into a typed `ApiError {status, detail}`;
 * - reads use an AbortController timeout so a hung backend cannot freeze a page;
 * - one helper per endpoint the pages use — no string URLs in the pages themselves.
 */

import type {
  AgentAnswer,
  AgentAskRequest,
  AgentAuditResponse,
  AgentToolsResponse,
  CompanyProfileResponse,
  HealthResponse,
  IngestRecord,
  LineageResponse,
  MarketCatalogResponse,
  MarketSeries,
  MetricSet,
  PeriodSeries,
  ReportDocument,
  ReportRequest,
  RiskRegister,
  ScenarioPresetsResponse,
  ScenarioRequest,
  ScenarioResult,
  UploadsResponse,
} from "@/api/types";

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? "/api/v1";

/** Default read timeout. POST /scenarios/run and /reports/generate can be slow, so the
 *  write helpers take an explicit (longer) timeout. */
export const DEFAULT_TIMEOUT_MS = 15_000;
export const HEAVY_TIMEOUT_MS = 60_000;

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }

  /** Human-readable, of the form `HTTP 400 · <detail>`. */
  get display(): string {
    return `HTTP ${this.status} · ${this.detail}`;
  }
}

export class NetworkError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NetworkError";
  }
}

export type QueryValue = string | number | boolean | null | undefined | Array<string | number>;

export function buildQuery(params?: Record<string, QueryValue>): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, raw] of Object.entries(params)) {
    if (raw === null || raw === undefined || raw === "") continue;
    if (Array.isArray(raw)) {
      for (const item of raw) search.append(key, String(item));
    } else {
      search.append(key, String(raw));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

/** Turn a FastAPI error body into one readable line (422 bodies are arrays of errors). */
export function extractDetail(payload: unknown, fallback: string): string {
  if (typeof payload === "string" && payload.trim()) return payload.trim();
  if (payload && typeof payload === "object") {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail.trim();
    if (Array.isArray(detail)) {
      const parts = detail.map((item) => {
        if (item && typeof item === "object") {
          const loc = (item as { loc?: unknown[] }).loc;
          const msg = (item as { msg?: unknown }).msg;
          const where = Array.isArray(loc) ? loc.join(".") : "";
          return where ? `${where}: ${String(msg ?? "")}` : String(msg ?? "");
        }
        return String(item);
      });
      const joined = parts.filter(Boolean).join("; ");
      if (joined) return joined;
    }
    if (detail && typeof detail === "object") return JSON.stringify(detail);
  }
  return fallback;
}

interface RequestOptions {
  query?: Record<string, QueryValue>;
  method?: "GET" | "POST";
  body?: unknown;
  timeoutMs?: number;
  signal?: AbortSignal;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { query, method = "GET", body, timeoutMs = DEFAULT_TIMEOUT_MS, signal } = options;
  const url = `${API_BASE}${path}${buildQuery(query)}`;

  const controller = new AbortController();
  let timedOut = false;
  const timer = timeoutMs > 0 ? setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs) : null;
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    const aborted = controller.signal.aborted;
    if (timedOut) throw new NetworkError(`请求超时（${Math.round(timeoutMs / 1000)}s）：${url}`);
    if (aborted) throw new NetworkError(`请求已取消：${url}`);
    const message = error instanceof Error ? error.message : String(error);
    throw new NetworkError(`无法连接后端 ${API_BASE}（${message}）。请确认 FastAPI 已在 127.0.0.1:8000 运行。`);
  } finally {
    if (timer !== null) clearTimeout(timer);
  }

  if (!response.ok) {
    let payload: unknown = null;
    let text = "";
    try {
      text = await response.text();
      payload = text ? (JSON.parse(text) as unknown) : null;
    } catch {
      payload = text;
    }
    throw new ApiError(response.status, extractDetail(payload, response.statusText || "request failed"));
  }

  if (response.status === 204) return undefined as T;
  const text = await response.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

/** Raw text/blob download (CSV, markdown, HTML). */
async function requestText(path: string, options: RequestOptions = {}): Promise<string> {
  const { query, method = "GET", body, timeoutMs = HEAVY_TIMEOUT_MS } = options;
  const url = `${API_BASE}${path}${buildQuery(query)}`;
  const controller = new AbortController();
  const timer = timeoutMs > 0 ? setTimeout(() => controller.abort(), timeoutMs) : null;
  try {
    const response = await fetch(url, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    if (!response.ok) {
      const text = await response.text();
      let payload: unknown = text;
      try {
        payload = text ? (JSON.parse(text) as unknown) : null;
      } catch {
        /* keep the raw text */
      }
      throw new ApiError(response.status, extractDetail(payload, response.statusText || "request failed"));
    }
    return await response.text();
  } catch (error) {
    if (error instanceof ApiError) throw error;
    const message = error instanceof Error ? error.message : String(error);
    throw new NetworkError(`无法连接后端 ${API_BASE}（${message}）`);
  } finally {
    if (timer !== null) clearTimeout(timer);
  }
}

/* -------------------------------------------------------------------------- */
/* endpoint helpers                                                           */
/* -------------------------------------------------------------------------- */

export interface RangeQuery {
  start?: string;
  end?: string;
  month?: string;
  regions?: string[];
  limit?: number;
}

export const api = {
  health: (signal?: AbortSignal) => request<HealthResponse>("/health", { signal }),

  lineage: (signal?: AbortSignal) => request<LineageResponse>("/meta/lineage", { signal }),

  company: (signal?: AbortSignal) => request<CompanyProfileResponse>("/meta/company", { signal }),

  metrics: (query: RangeQuery = {}, signal?: AbortSignal) =>
    request<MetricSet>("/metrics", {
      query: { month: query.month, start: query.start, end: query.end, regions: query.regions },
      signal,
    }),

  series: (query: RangeQuery = {}, signal?: AbortSignal) =>
    request<PeriodSeries>("/metrics/series", {
      query: { start: query.start, end: query.end, regions: query.regions, limit: query.limit },
      signal,
    }),

  budgetVariance: (query: RangeQuery = {}, signal?: AbortSignal) =>
    request<MetricSet>("/metrics/budget-variance", {
      query: { month: query.month, start: query.start, end: query.end },
      signal,
    }),

  riskRegister: (query: { month?: string; regions?: string[] } = {}, signal?: AbortSignal) =>
    request<RiskRegister>("/risk/register", { query: { month: query.month, regions: query.regions }, signal }),

  marketCatalog: (signal?: AbortSignal) => request<MarketCatalogResponse>("/market/catalog", { signal }),

  marketSeries: (seriesId: string, query: { allow_live?: boolean; limit?: number } = {}, signal?: AbortSignal) =>
    request<MarketSeries>(`/market/series/${encodeURIComponent(seriesId)}`, {
      query: { allow_live: query.allow_live, limit: query.limit },
      signal,
    }),

  scenarioPresets: (signal?: AbortSignal) =>
    request<ScenarioPresetsResponse>("/scenarios/presets", { signal }),

  runScenario: (payload: ScenarioRequest, signal?: AbortSignal) =>
    request<ScenarioResult>("/scenarios/run", { method: "POST", body: payload, timeoutMs: HEAVY_TIMEOUT_MS, signal }),

  exportScenarioCsv: (payload: ScenarioRequest) =>
    requestText("/scenarios/export", { method: "POST", body: payload }),

  askAgent: (payload: AgentAskRequest, signal?: AbortSignal) =>
    request<AgentAnswer>("/agent/ask", { method: "POST", body: payload, timeoutMs: HEAVY_TIMEOUT_MS, signal }),

  agentTools: (signal?: AbortSignal) => request<AgentToolsResponse>("/agent/tools", { signal }),

  agentAudit: (limit = 20, signal?: AbortSignal) =>
    request<AgentAuditResponse>("/agent/audit", { query: { limit }, signal }),

  generateReport: (payload: ReportRequest, signal?: AbortSignal) =>
    request<ReportDocument>("/reports/generate", {
      method: "POST",
      body: payload,
      timeoutMs: HEAVY_TIMEOUT_MS,
      signal,
    }),

  /** `format=markdown|html` returns raw text; `format=json` returns a JSON envelope. */
  reportText: (reportId: string, format: "markdown" | "html") =>
    requestText(`/reports/${encodeURIComponent(reportId)}`, { query: { format } }),

  uploads: (signal?: AbortSignal) => request<UploadsResponse>("/data/uploads", { signal }),

  uploadDataset: async (file: File): Promise<IngestRecord> => {
    const form = new FormData();
    form.append("file", file);
    const response = await fetch(`${API_BASE}/data/upload`, { method: "POST", body: form });
    if (!response.ok) {
      const text = await response.text();
      let payload: unknown = text;
      try {
        payload = text ? (JSON.parse(text) as unknown) : null;
      } catch {
        /* keep raw text */
      }
      throw new ApiError(response.status, extractDetail(payload, response.statusText));
    }
    return (await response.json()) as IngestRecord;
  },
};

/* -------------------------------------------------------------------------- */
/* UI helpers                                                                 */
/* -------------------------------------------------------------------------- */

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.display;
  if (error instanceof NetworkError) return error.message;
  if (error instanceof Error) return error.message;
  return String(error);
}

/** Trigger a browser download for a generated text artefact (CSV / markdown / HTML). */
export function downloadText(filename: string, text: string, mime = "text/plain;charset=utf-8"): void {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
