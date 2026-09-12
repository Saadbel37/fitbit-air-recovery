/** Segmented period selector: 7 / 30 / 90 / 365 days. Pill container, the
 *  selected segment carries the violet accent. */

export const RANGES = [
  { days: 7, label: "7d" },
  { days: 30, label: "30d" },
  { days: 90, label: "90d" },
  { days: 365, label: "1y" },
] as const;

export default function RangeToggle({
  value,
  onChange,
  options = RANGES.map((r) => r.days),
}: {
  value: number;
  onChange: (d: number) => void;
  options?: number[];
}) {
  const items = RANGES.filter((r) => options.includes(r.days));
  return (
    <div className="inline-flex rounded-button bg-surface p-1" role="group" aria-label="Zeitraum">
      {items.map((r) => (
        <button
          key={r.days}
          onClick={() => onChange(r.days)}
          aria-pressed={value === r.days}
          className={`rounded-button px-4 py-1.5 font-disp text-[13px] font-medium transition duration-180 ${
            value === r.days ? "bg-accent text-white" : "text-muted hover:text-ink"
          }`}
        >
          {r.label}
        </button>
      ))}
    </div>
  );
}
