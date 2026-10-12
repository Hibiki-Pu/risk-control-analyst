/** Optional region filter. Defaults to every region (`regions` is simply omitted). */

import { useHealth } from "@/components/AppLayout";
import { StatusBadge } from "@/components/StatusBadge";

export interface RegionFilterProps {
  value: string[];
  onChange: (regions: string[]) => void;
  disabled?: boolean;
}

export function RegionFilter({ value, onChange, disabled = false }: RegionFilterProps) {
  const { health } = useHealth();
  const regions = health?.dataset.regions ?? [];
  if (regions.length === 0) return null;

  const toggle = (region: string) => {
    if (value.includes(region)) onChange(value.filter((item) => item !== region));
    else onChange([...value, region]);
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid="region-filter">
      <span className="label">区域</span>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onChange([])}
        className={`btn-chip ${value.length === 0 ? "chip-active" : ""}`}
      >
        全部区域
      </button>
      {regions.map((region) => (
        <button
          key={region}
          type="button"
          disabled={disabled}
          onClick={() => toggle(region)}
          className={`btn-chip ${value.includes(region) ? "chip-active" : ""}`}
        >
          {region}
        </button>
      ))}
      {value.length === 0 ? (
        <StatusBadge tone="neutral" title="未传 regions 参数时后端按全部区域汇总">
          默认：全部区域
        </StatusBadge>
      ) : null}
    </div>
  );
}

export default RegionFilter;
