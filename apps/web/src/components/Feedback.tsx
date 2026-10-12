/** Small building blocks: skeleton, empty, error, badges. */

import type { ReactNode } from "react";

export interface SkeletonProps {
  className?: string;
  /** Accessible label, rendered for screen readers only. */
  label?: string;
}

export function Skeleton({ className = "h-4 w-full", label = "载入中" }: SkeletonProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className={`animate-pulse rounded bg-surface-3 ${className}`}
    >
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function SkeletonCard({ rows = 3, title }: { rows?: number; title?: string }) {
  return (
    <div className="card space-y-3" data-testid="skeleton-card">
      {title ? <div className="card-title">{title}</div> : null}
      <Skeleton className="h-6 w-1/3" />
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className="h-4 w-full" />
      ))}
    </div>
  );
}

export function SkeletonTable({ rows = 5, columns = 4 }: { rows?: number; columns?: number }) {
  return (
    <div className="space-y-2" data-testid="skeleton-table">
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div key={rowIndex} className="grid gap-2" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
          {Array.from({ length: columns }).map((__, cellIndex) => (
            <Skeleton key={cellIndex} className="h-6 w-full" />
          ))}
        </div>
      ))}
    </div>
  );
}

export interface EmptyStateProps {
  title?: string;
  description?: ReactNode;
  action?: ReactNode;
}

export function EmptyState({ title = "暂无数据", description, action }: EmptyStateProps) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-line bg-surface-2 px-6 py-10 text-center"
      data-testid="empty-state"
    >
      <div className="text-sm font-semibold text-ink">{title}</div>
      {description ? <div className="max-w-xl text-xs text-muted">{description}</div> : null}
      {action}
    </div>
  );
}

export interface ErrorStateProps {
  title?: string;
  error: unknown;
  message: string;
  onRetry?: () => void;
  retrying?: boolean;
}

export function ErrorState({ title = "加载失败", error, message, onRetry, retrying }: ErrorStateProps) {
  const status = (error as { status?: number } | null)?.status;
  const kind = (error as { name?: string } | null)?.name;
  return (
    <div
      role="alert"
      className="rounded-lg border border-bad/40 bg-bad/10 p-4 text-sm text-ink"
      data-testid="error-state"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-semibold text-bad">{title}</div>
        {onRetry ? (
          <button type="button" className="btn" onClick={onRetry} disabled={retrying}>
            {retrying ? "重试中…" : "重试"}
          </button>
        ) : null}
      </div>
      <p className="mt-2 font-mono text-xs break-all text-ink" data-testid="error-detail">
        {message}
      </p>
      {status || kind ? (
        <p className="mt-1 text-xs text-muted">
          {status ? `状态码 HTTP ${status}` : null}
          {status && kind ? " · " : null}
          {kind ?? null}
        </p>
      ) : null}
    </div>
  );
}
