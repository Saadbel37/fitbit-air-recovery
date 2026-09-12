/** A subordinate metric line inside a MetricHero group: label + value,
 *  optional comparison to baseline. */

export default function MetricRow({
  label,
  value,
  unit,
  compare,
  compareColor,
}: {
  label: string;
  value: string;
  unit?: string;
  compare?: string;
  compareColor?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-2">
      <span className="eyebrow normal-case tracking-normal text-muted">{label}</span>
      <div className="flex items-baseline gap-2">
        {compare && (
          <span className="font-mono text-[11px]" style={compareColor ? { color: compareColor } : undefined}>
            {compare}
          </span>
        )}
        <span className="tnum font-mono text-sm font-medium text-ink">
          {value}
          {unit ? <span className="text-muted"> {unit}</span> : null}
        </span>
      </div>
    </div>
  );
}
