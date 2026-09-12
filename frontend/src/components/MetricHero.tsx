/** Editorial metric group: one dominant number + status, optional supporting
 *  rows beneath. The primary number visually dominates. Optionally a link. */

import { Link } from "react-router-dom";
import { ConfidenceNote, CountUp, StatusPill } from "./primitives";

interface Props {
  label: string;
  to?: string;
  value: number | null;
  unit?: string;
  max?: string;
  decimals?: number;
  status: string | null;
  confidence?: number | null;
  sub?: React.ReactNode;
  accent?: boolean; // render the number in violet (the page's primary metric)
  children?: React.ReactNode; // supporting MetricRows
}

export default function MetricHero({
  label,
  to,
  value,
  unit,
  max,
  decimals = 0,
  status,
  confidence,
  sub,
  accent = false,
  children,
}: Props) {
  const inner = (
    <>
      <div className="flex items-center justify-between">
        <span className="eyebrow">{label}</span>
        <StatusPill status={status} />
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <span
          className="tnum heading text-6xl font-bold leading-none"
          style={accent ? { color: "var(--accent)" } : undefined}
        >
          {value != null ? <CountUp value={value} decimals={decimals} /> : "–"}
        </span>
        {unit && value != null && <span className="text-lg text-muted">{unit}</span>}
        {max && <span className="font-mono text-sm text-faint">{max}</span>}
      </div>
      {(sub || confidence != null) && (
        <div className="mt-2 flex items-center justify-between gap-2">
          <span className="text-[13px] text-muted">{value != null ? sub : "no data for this day yet"}</span>
          {value != null && confidence != null && <ConfidenceNote value={confidence} />}
        </div>
      )}
      {children && <div className="mt-5 border-t border-line pt-2">{children}</div>}
    </>
  );

  const cls =
    "block rounded-card bg-surface p-6 transition duration-180" +
    (to ? " hover:bg-[color-mix(in_srgb,var(--surface)_60%,var(--bg))]" : "");

  return to ? (
    <Link to={to} className={cls}>
      {inner}
    </Link>
  ) : (
    <div className={cls}>{inner}</div>
  );
}
