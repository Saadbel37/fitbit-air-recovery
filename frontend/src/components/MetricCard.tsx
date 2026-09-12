/** Health-monitor card: value, baseline, deviation, sparkline, info tip.
 *  Flat light surface (no heavy borders); monochrome sparkline. */

import Sparkline from "./Sparkline";
import { EmptyNote, InfoTip } from "./primitives";

interface Props {
  label: string;
  tooltip: string;
  unit: string;
  decimals?: number;
  value: number | null;
  baseline: number | null;
  /** true when a lower value is better (e.g. resting HR) */
  lowerIsBetter?: boolean;
  /** deviation-only metric: any deviation from ~0 is notable (skin temp) */
  aroundZero?: boolean;
  labels: string[];
  history: (number | null)[];
}

export default function MetricCard(p: Props) {
  const dev =
    p.value != null && p.baseline != null && p.baseline !== 0 && !p.aroundZero
      ? ((p.value - p.baseline) / p.baseline) * 100
      : null;
  const better = dev != null ? (p.lowerIsBetter ? dev < 0 : dev > 0) : null;
  const devColor =
    dev == null || Math.abs(dev) < 2 ? "var(--faint)" : better ? "var(--status-good)" : "var(--status-low)";

  return (
    <div className="rounded-card bg-surface p-5">
      <div className="mb-1 flex items-center gap-1.5">
        <span className="eyebrow normal-case tracking-normal">{p.label}</span>
        <InfoTip text={p.tooltip} label={`Was ist ${p.label}?`} />
      </div>
      <div className="flex items-baseline gap-2">
        <span className="tnum heading text-3xl font-bold">
          {p.value != null
            ? p.value.toLocaleString("en-US", { maximumFractionDigits: p.decimals ?? 0 })
            : "–"}
        </span>
        <span className="text-xs text-muted">{p.unit}</span>
        {dev != null && (
          <span className="tnum ml-auto font-mono text-xs" style={{ color: devColor }}>
            {dev > 0 ? "↑" : "↓"} {Math.abs(dev).toFixed(0)} %
          </span>
        )}
      </div>
      <div className="mt-0.5 font-mono text-[11px] text-faint">
        {p.baseline != null
          ? `Baseline ${p.baseline.toLocaleString("en-US", { maximumFractionDigits: p.decimals ?? 0 })} ${p.unit}`
          : "Baseline: needs ≥ 7 days"}
      </div>
      <div className="mt-3">
        {p.history.some((v) => v != null) ? (
          <Sparkline labels={p.labels} values={p.history} color="var(--ink)" height={40} unit={p.unit} />
        ) : (
          <EmptyNote>no history yet</EmptyNote>
        )}
      </div>
    </div>
  );
}
