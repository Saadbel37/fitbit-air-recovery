/** Shared primitives: count-up number, status pill, confidence, info tooltip,
 *  skeletons, empty state. Light clinical theme. */

import { useEffect, useRef, useState } from "react";
import { confidenceWord } from "../lib/api";

/** Animates 0 -> value on first render (spec §22); respects reduced motion. */
export function CountUp({ value, decimals = 0 }: { value: number | null; decimals?: number }) {
  const [shown, setShown] = useState<number>(0);
  const done = useRef(false);
  useEffect(() => {
    if (value == null) return;
    if (done.current || matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setShown(value);
      return;
    }
    done.current = true;
    const t0 = performance.now();
    const dur = 700;
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / dur);
      setShown(value * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  if (value == null) return <>–</>;
  return <>{shown.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}</>;
}

const STATUS_COLOR: Record<string, string> = {
  high: "var(--status-good)",
  optimal: "var(--status-good)",
  solid: "var(--status-good)",
  good: "var(--status-good)",
  moderate: "var(--status-mid)",
  light: "var(--muted)",
  neutral: "var(--muted)",
  low: "var(--status-low)",
  poor: "var(--status-low)",
  "all-out": "var(--status-low)",
};

/** Status word + color — never color alone. Uppercase, tracked. */
export function StatusPill({ status, size = "sm" }: { status: string | null; size?: "sm" | "lg" }) {
  if (!status) return <span className="font-mono text-xs text-faint">no data</span>;
  const color = STATUS_COLOR[status] ?? "var(--muted)";
  const pad = size === "lg" ? "px-3 py-1 text-xs" : "px-2.5 py-0.5 text-[11px]";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-button font-disp font-semibold uppercase tracking-[0.12em] ${pad}`}
      style={{ color, background: "color-mix(in srgb, " + color + " 12%, transparent)" }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} aria-hidden />
      {status}
    </span>
  );
}

/** Hover/focus tooltip marked with a small ⓘ — for explaining any term inline. */
export function InfoTip({ text, label = "Explanation" }: { text: string; label?: string }) {
  return (
    <span className="group relative inline-flex align-middle">
      <button
        type="button"
        aria-label={label}
        className="flex h-4 w-4 items-center justify-center rounded-full border border-line font-mono text-[9px] leading-none text-faint transition hover:border-accent hover:text-accent"
      >
        i
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-1/2 top-6 z-30 w-56 -translate-x-1/2 rounded-xl border border-line bg-card px-3 py-2 text-[12px] leading-relaxed text-ink opacity-0 shadow-lg transition group-hover:opacity-100 group-focus-within:opacity-100"
      >
        {text}
      </span>
    </span>
  );
}

const CONFIDENCE_HELP =
  "Data quality = how complete the inputs for this number were. It drops when a sensor is missing or the personal baseline is still young — the value is never guessed.";

/** Data quality (formerly "Konfidenz") in plain words + an explainer. */
export function ConfidenceNote({ value }: { value: number | null }) {
  if (value == null) return null;
  return (
    <span className="inline-flex items-center gap-1 font-mono text-[11px] text-faint">
      Data quality {confidenceWord(value)}
      <InfoTip text={CONFIDENCE_HELP} label="What is data quality?" />
    </span>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-card bg-surface ${className}`} aria-hidden />;
}

export const SkeletonCard = Skeleton;

export function EmptyNote({ children }: { children: React.ReactNode }) {
  return <div className="text-[13px] text-muted">{children}</div>;
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-card bg-surface px-6 py-12 text-center">
      <div className="heading text-lg font-semibold">{title}</div>
      {hint && <div className="mt-1.5 max-w-sm text-[13px] text-muted">{hint}</div>}
    </div>
  );
}
