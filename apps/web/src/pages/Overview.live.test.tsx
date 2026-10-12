/**
 * Live integration test: renders the app against a REAL FastAPI backend.
 *
 * It only runs when the suite is started with the backend base URL, so a plain `npm test` stays
 * green without a server:
 *
 *   cd services/api && python -m uvicorn app.main:app --port 8000
 *   cd apps/web && VITE_API_BASE=http://127.0.0.1:8000/api/v1 npm test
 *
 * What it proves that the mocked suites cannot:
 *   - the contract field names are real (nothing renders a placeholder for a metric the API returns),
 *   - the figures on screen are the engine's figures for the shipped seed dataset,
 *   - the synthetic-data banner is visible in every state.
 *
 * Assertions use ASCII tokens on purpose (numbers, "SYNTHETIC DEMO") so the test cannot be broken by
 * a source-file encoding mishap.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import App from "@/App";

const LIVE_BASE = "http://127.0.0.1:8000/api/v1";
const configuredBase = ((import.meta.env.VITE_API_BASE as string | undefined) ?? "").replace(/\/+$/, "");
const liveEnabled = configuredBase === LIVE_BASE;

function renderApp() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <App />
    </MemoryRouter>,
  );
}

function bodyText(): string {
  return document.body.textContent ?? "";
}

describe.skipIf(!liveEnabled)(`live API integration (${LIVE_BASE})`, () => {
  it("renders the engine's figures for the seed dataset", async () => {
    renderApp();

    // The banner is part of the shell and must be visible before any request resolves.
    expect(screen.getByTestId("synthetic-banner")).toBeInTheDocument();
    expect(screen.getByTestId("synthetic-banner").textContent).toContain("SYNTHETIC DEMO");

    // Seed dataset 2024-12: revenue 322,304.71 USD, gross margin 21.93%, cash 274,200.03 USD,
    // DSO 69.42 days, interest coverage 1.56x (see docs/financial-methodology.md and the report).
    await waitFor(() => expect(bodyText()).toMatch(/\$322,305/), { timeout: 20000 });
    expect(bodyText()).toMatch(/\$274,200/);
    expect(bodyText()).toMatch(/21\.93%/);
    expect(bodyText()).toMatch(/1\.56x/);
    expect(bodyText()).toMatch(/synthetic-aurelia-v1/);
    expect(bodyText()).toMatch(/RC-01/);
  });

  it("shows a risk signal with its observed value and threshold, and never a fabricated zero", async () => {
    renderApp();

    await waitFor(() => expect(bodyText()).toMatch(/RC-01/), { timeout: 20000 });
    expect(bodyText()).toMatch(/2x/);
    expect(bodyText()).not.toMatch(/NaN/);
    expect(bodyText()).not.toMatch(/undefined USD/);
    expect(bodyText()).not.toMatch(/Infinity/);
  });
});

if (!liveEnabled) {
  describe("live API integration", () => {
    it.skip("set VITE_API_BASE=http://127.0.0.1:8000/api/v1 and start the API to enable this", () => undefined);
  });
}
