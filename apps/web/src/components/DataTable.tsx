/** Generic table with optional sortable headers. */

import type { ReactNode } from "react";
import { useMemo, useState } from "react";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T, index: number) => ReactNode;
  /** Provide to make the header sortable. */
  sortValue?: (row: T) => number | string | null | undefined;
  align?: "left" | "right" | "center";
  className?: string;
  headerTitle?: string;
}

export interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string;
  caption?: string;
  emptyMessage?: ReactNode;
  dense?: boolean;
  initialSortKey?: string;
  initialSortDir?: "asc" | "desc";
  footer?: ReactNode;
  testId?: string;
}

function compareValues(a: number | string | null | undefined, b: number | string | null | undefined, dir: "asc" | "desc"): number {
  // Missing values always sort last: they are not "smallest", they are unknown.
  const aMissing = a === null || a === undefined || a === "";
  const bMissing = b === null || b === undefined || b === "";
  if (aMissing && bMissing) return 0;
  if (aMissing) return 1;
  if (bMissing) return -1;
  let result: number;
  if (typeof a === "number" && typeof b === "number") result = a - b;
  else result = String(a).localeCompare(String(b), "zh-Hans-CN");
  return dir === "asc" ? result : -result;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  emptyMessage = "暂无数据",
  dense = false,
  initialSortKey,
  initialSortDir = "desc",
  footer,
  testId = "data-table",
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(initialSortKey ?? null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">(initialSortDir);

  const sorted = useMemo(() => {
    if (!sortKey) return rows;
    const column = columns.find((item) => item.key === sortKey);
    if (!column?.sortValue) return rows;
    const copy = [...rows];
    copy.sort((left, right) => compareValues(column.sortValue?.(left), column.sortValue?.(right), sortDir));
    return copy;
  }, [rows, columns, sortKey, sortDir]);

  const toggleSort = (column: Column<T>) => {
    if (!column.sortValue) return;
    if (sortKey === column.key) setSortDir((dir) => (dir === "asc" ? "desc" : "asc"));
    else {
      setSortKey(column.key);
      setSortDir("desc");
    }
  };

  return (
    <div className="overflow-x-auto" data-testid={testId}>
      <table className={`table ${dense ? "text-xs" : ""}`}>
        {caption ? <caption className="pb-2 text-left text-xs text-muted">{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((column) => {
              const active = sortKey === column.key;
              const align = column.align === "right" ? "text-right" : column.align === "center" ? "text-center" : "text-left";
              return (
                <th
                  key={column.key}
                  title={column.headerTitle ?? (column.sortValue ? "点击排序" : undefined)}
                  className={`${align} ${column.className ?? ""} ${column.sortValue ? "cursor-pointer select-none" : ""}`}
                  onClick={() => toggleSort(column)}
                  aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : "none"}
                >
                  <span className="inline-flex items-center gap-1">
                    {column.header}
                    {column.sortValue ? <span className="text-[10px] text-muted">{active ? (sortDir === "asc" ? "▲" : "▼") : "↕"}</span> : null}
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="py-6 text-center text-muted">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            sorted.map((row, index) => (
              <tr key={rowKey(row, index)} className="hover:bg-surface-3/60">
                {columns.map((column) => {
                  const align = column.align === "right" ? "text-right" : column.align === "center" ? "text-center" : "text-left";
                  return (
                    <td key={column.key} className={`${align} ${column.className ?? ""}`}>
                      {column.render(row, index)}
                    </td>
                  );
                })}
              </tr>
            ))
          )}
        </tbody>
        {footer ? <tfoot className="text-xs text-muted">{footer}</tfoot> : null}
      </table>
    </div>
  );
}

export default DataTable;
