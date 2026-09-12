/** Circular score gauge (SVG). Arc length + color encode the value;
 *  the number and status word carry it non-visually too. */

import { CountUp } from "./primitives";

interface Props {
  value: number | null;
  max?: number;
  status: string | null;
  color: string;
  size?: number;
  decimals?: number;
  caption?: string;
}

export default function RadialScore({
  value,
  max = 100,
  status,
  color,
  size = 200,
  decimals = 0,
  caption,
}: Props) {
  const stroke = 12;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const frac = value != null ? Math.max(0, Math.min(1, value / max)) : 0;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#eef0f3" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - frac)}
          style={{
            transition: reduce ? undefined : "stroke-dashoffset 900ms cubic-bezier(0.22,1,0.36,1)",
          }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="tnum heading text-5xl font-bold" style={{ color: "var(--ink)" }}>
          {value != null ? <CountUp value={value} decimals={decimals} /> : "–"}
        </span>
        {status && (
          <span className="mt-1 font-disp text-xs font-semibold uppercase tracking-[0.15em] text-muted">
            {status}
          </span>
        )}
        {caption && <span className="mt-0.5 font-mono text-[10px] text-faint">{caption}</span>}
      </div>
    </div>
  );
}
