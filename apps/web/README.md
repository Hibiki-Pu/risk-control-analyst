# RiskControl Analyst — web frontend (风险控制分析师)

React 18 + TypeScript (strict) + Vite + Tailwind CSS + ECharts + React Router, tested with Vitest and
`@testing-library/react` on jsdom. The UI language is Simplified Chinese; all code, comments, test
names and this README are in English.

This app is a **read-and-visualise** client for the FastAPI service in `services/api`. It contains no
mock data: every figure on screen comes from `GET/POST /api/v1/*`.

## How to run

```powershell
# 1. backend (from services/api)
python -m uvicorn app.main:app --port 8000

# 2. frontend (from apps/web)
npm.cmd install            # Windows: npm is blocked by execution policy, use npm.cmd
npm.cmd run dev            # http://localhost:5173
```

> Heads-up from the build environment this app was authored in: the DSH file sandbox could not
> initialise on the `D:` drive (`SetNamedSecurityInfoW failed (Win32 5)`), so `npm.cmd install`,
> `typecheck`, `build` and `test` could not be executed there. The code was written against the
> contract, but the four commands above are the acceptance gate and should be run once in an
> environment where shell access to `D:\deepseekworkplace` works. If `tsc` reports a problem with
> `test` inside `vite.config.ts`, import `defineConfig` from `vitest/config` instead of `vite`.

Other scripts:

| Script | What it does |
| --- | --- |
| `npm.cmd run dev` | Vite dev server on port 5173 with the `/api` proxy |
| `npm.cmd run build` | `tsc --noEmit -p tsconfig.app.json` then `vite build` into `dist/` |
| `npm.cmd run preview` | Serve the production build |
| `npm.cmd test` | `vitest run` (jsdom, globals, `src/test/setup.ts`) |
| `npm.cmd run typecheck` | Type-checks the app and the Vite config with no emit |

## How it talks to the API

* Base path is `/api/v1` (`src/api/client.ts`). Every request goes to the **Vite origin**, and
  `vite.config.ts` proxies `/api` to `http://127.0.0.1:8000` (`changeOrigin: true`), so the browser
  never needs CORS and no backend change is required.
* Point it elsewhere when needed:
  `VITE_API_BASE=https://host/api/v1` for the client,
  `VITE_PROXY_TARGET=http://127.0.0.1:8010` for the dev proxy.
* Reads use an `AbortController` timeout (15s; 60s for the heavy `POST` calls) and are aborted when a
  page unmounts.
* Non-2xx answers are parsed into a typed `ApiError { status, detail }`; FastAPI `422` bodies
  (arrays of validation errors) are flattened into one readable line. Pages render that real detail —
  never a generic "something went wrong" — next to a retry button.

## Honest-data rules (non-negotiable)

1. **A missing value is never a zero.** If `status !== "ok"` or `value === null`, the UI renders
   `不可用` plus the citation `note` (`formatValue` in `src/lib/format.ts`). Charts use
   `connectNulls: false`, so a gap stays a gap.
2. **Every number carries its unit and period.** Charts state both in the title/subtitle; KPI cards
   show the unit badge and the period; money is USD.
3. **Percentages are decimal fractions** coming from the API (`0.2193`) and are multiplied by 100 for
   display (`21.93%`).
4. **Provenance is visible.** A market series with `is_fixture: true` is badged
   `本地演示数据 FIXTURE`; a stale one additionally gets `STALE 数据过期`. Live FRED observations are
   badged `实时数据 LIVE`.
5. **The synthetic-data banner is always on screen.** It is rendered by `AppShell`, not by the pages,
   and it also covers the window before `/health` has answered.
6. **Variance colouring follows economics, not signs.** Revenue/EBIT variances are favourable when
   positive, cost lines when negative; the `PnlAnalysis` page prints that convention as a legend.
7. **Optional region filter.** No region is selected by default, so the request simply omits
   `regions[]` and the backend aggregates every region.

## Layout

```
src/
  api/        types.ts (mirror of docs/api-contract.md), client.ts (typed fetch wrapper)
  components/ AppLayout (shell + synthetic banner), KpiCard, Chart, DataTable,
              Feedback (Skeleton/EmptyState/ErrorState), StatusBadge (incl. ProvenanceBadge),
              RegionFilter, Markdown (small purpose-built renderer)
  lib/        format.ts (honest formatting), data.ts, charts.ts, useAsync.ts, useFilters.ts
  pages/      Overview, PnlAnalysis, RiskControl, MarketIntelligence,
              ScenarioSimulator, AiAnalyst, ReportCenter
  test/       setup.ts
```

Each page handles all four states: loading (skeleton), error (message + retry), empty (no data in the
selected range), and loaded.

## Tests

`npm.cmd test` runs four suites: `src/lib/format.test.ts` (missing/undefined/null handling, unit
formatting, "no `0` for missing"), `src/components/KpiCard.test.tsx` (value and missing state),
`src/components/Feedback.test.tsx` (error detail + retry), and `src/pages/Overview.test.tsx`
(loading → loaded against a stubbed `fetch`, plus the endpoint URLs the page calls).

## Deliberate omissions

* **No component or state library.** React hooks only; `useAsync` covers the fetch lifecycle.
* **No markdown dependency.** `src/components/Markdown.tsx` implements exactly the constructs the
  deterministic report builder emits (headings, tables, lists, blockquotes, bold/italic/code).
* **No capex slider in the scenario simulator.** The backend's `ScenarioAssumptions` has
  `extra="forbid"` and no capex driver, so the field is shown read-only with an explanation instead of
  sending a request that FastAPI would reject with `422`.
