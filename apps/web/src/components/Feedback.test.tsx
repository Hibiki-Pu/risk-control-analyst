import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError, errorMessage } from "@/api/client";
import { ErrorState } from "@/components/Feedback";

describe("ErrorState", () => {
  it("shows the real API error detail, not a generic message", () => {
    const error = new ApiError(400, "no data in the requested period");
    render(<ErrorState error={error} message={errorMessage(error)} onRetry={vi.fn()} />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByTestId("error-detail")).toHaveTextContent("HTTP 400 · no data in the requested period");
    expect(screen.getByText(/状态码 HTTP 400/)).toBeInTheDocument();
  });

  it("runs the retry handler when the button is pressed", () => {
    const onRetry = vi.fn();
    render(<ErrorState error={new ApiError(500, "boom")} message="HTTP 500 · boom" onRetry={onRetry} />);

    screen.getByRole("button", { name: "重试" }).click();
    expect(onRetry).toHaveBeenCalledTimes(1);  });

  it("disables the retry button while retrying", () => {
    render(<ErrorState error={new ApiError(500, "boom")} message="HTTP 500 · boom" onRetry={vi.fn()} retrying />);
    expect(screen.getByRole("button")).toBeDisabled();
    expect(screen.getByRole("button")).toHaveTextContent("重试中…");
  });
});
