/** Shared page-level filter state. */

import { useMemo, useState } from "react";

import { useHealth } from "@/components/AppLayout";
import type { MonthRange } from "@/lib/data";
import { deriveRange, lastMonth } from "@/lib/data";

export interface FilterState {
  regions: string[];
  setRegions: (regions: string[]) => void;
  /** Trailing `count` months of the active dataset. */
  range: (count: number) => MonthRange | null;
  /** Latest month present in the dataset. */
  latest: string | null;
  month: string | null;
  setMonth: (month: string | null) => void;
  months: string[];
}

export function useFilters(): FilterState {
  const { health } = useHealth();
  const [regions, setRegions] = useState<string[]>([]);
  const [month, setMonth] = useState<string | null>(null);

  const months = useMemo(() => health?.dataset.months ?? [], [health]);
  const latest = useMemo(() => lastMonth(months), [months]);

  return {
    regions,
    setRegions,
    months,
    latest,
    month: month ?? latest,
    setMonth,
    range: (count: number) => deriveRange(months, count),
  };
}

export default useFilters;
