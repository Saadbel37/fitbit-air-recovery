/** Health monitor: status table + click a metric for its history. */

import { useMemo, useState } from "react";
import Card, { PageHeader } from "../components/Card";
import RangeToggle from "../components/RangeToggle";
import TimeSeriesChart from "../components/TimeSeriesChart";
import { EmptyNote, Skeleton } from "../components/primitives";
import type { HealthDay } from "../lib/api";
import { api } from "../lib/api";
import { useApiData } from "../lib/hooks";

interface MetricDef {
  key: keyof HealthDay;
  baselineKey?: keyof NonNullable<HealthDay["baselines"]>;
  label: string;
  unit: string;
  color: string;
  decimals?: number;
  lowerIsBetter?: boolean;
  aroundZero?: boolean;
}

const METRICS: MetricDef[] = [
  { key: "hrv", baselineKey: "hrv", label: "HRV", unit: "ms", color: "var(--ink)" },
  { key: "resting_hr", baselineKey: "resting_hr", label: "Resting HR", unit: "bpm", color: "var(--ink)", lowerIsBetter: true },
  { key: "respiratory_rate", baselineKey: "respiratory_rate", label: "Respiratory rate", unit: "/min", color: "var(--ink)", decimals: 1 },
  { key: "spo2", label: "SpO₂", unit: "%", color: "var(--ink)", decimals: 1 },
  { key: "skin_temp_delta", baselineKey: "skin_temp", label: "Skin temp Δ", unit: "°C", color: "var(--ink)", decimals: 2, aroundZero: true },
  { key: "steps", label: "Steps", unit: "", color: "var(--ink)" },
  { key: "azm", label: "Active zone min.", unit: "min", color: "var(--ink)" },
];

function statusOf(m: MetricDef, value: number | null, baseline: number | null): { word: string; color: string } {
  if (value == null) return { word: "no data", color: "var(--faint)" };
  if (m.aroundZero) {
    return Math.abs(value) < 0.5 ? { word: "normal", color: "var(--status-good)" } : { word: "deviating", color: "var(--status-mid)" };
  }
  if (baseline == null) return { word: "—", color: "var(--muted)" };
  const dev = (value - baseline) / baseline;
  if (Math.abs(dev) < 0.03) return { word: "normal", color: "var(--status-good)" };
  const good = m.lowerIsBetter ? dev < 0 : dev > 0;
  return good ? { word: "good", color: "var(--status-good)" } : { word: "watch", color: "var(--status-mid)" };
}

export default function Health() {
  const [range, setRange] = useState(30);
  const [selected, setSelected] = useState<string>("hrv");
  const { data, loading } = useApiData((m) => api.health(range, m), [range]);

  // most recent day that actually carries vitals (today is often still empty)
  const latest = useMemo(() => {
    if (!data) return null;
    for (let i = data.length - 1; i >= 0; i--) {
      const d = data[i];
      if (d.hrv != null || d.resting_hr != null || d.spo2 != null || d.steps != null) return d;
    }
    return data[data.length - 1] ?? null;
  }, [data]);
  const sel = METRICS.find((m) => m.key === selected)!;
  const labels = useMemo(() => (data ?? []).map((d) => d.date), [data]);
  const selSeries = useMemo(
    () => (data ?? []).map((d) => (d[sel.key] as number | null) ?? null),
    [data, sel.key],
  );
  const selBaseline = useMemo(
    () => (sel.baselineKey ? (data ?? []).map((d) => d.baselines?.[sel.baselineKey!] ?? null) : null),
    [data, sel.baselineKey],
  );

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Health">
        <RangeToggle value={range} onChange={setRange} />
      </PageHeader>

      {loading || !data ? (
        <Skeleton className="h-72" />
      ) : (
        <>
          <Card title="Monitor" sub="Latest day's values against your baseline. Select a row for its history.">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-left font-mono text-[11px] uppercase tracking-wider text-faint">
                    <th className="py-2 pr-4 font-normal">Metric</th>
                    <th className="py-2 pr-4 text-right font-normal">Current</th>
                    <th className="py-2 pr-4 text-right font-normal">Baseline</th>
                    <th className="py-2 text-right font-normal">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {METRICS.map((m) => {
                    const val = (latest?.[m.key] as number | null) ?? null;
                    const base = m.baselineKey ? latest?.baselines?.[m.baselineKey] ?? null : null;
                    const st = statusOf(m, val, base);
                    const active = selected === m.key;
                    return (
                      <tr
                        key={m.key}
                        onClick={() => setSelected(m.key)}
                        tabIndex={0}
                        onKeyDown={(e) => e.key === "Enter" && setSelected(m.key)}
                        className={`cursor-pointer border-b border-line/50 transition ${
                          active ? "bg-surface-2" : "hover:bg-bg-2"
                        }`}
                      >
                        <td className="py-2.5 pr-4">
                          <span className="inline-flex items-center gap-2">
                            <span className="h-1.5 w-1.5 rounded-full" style={{ background: m.color }} />
                            {m.label}
                          </span>
                        </td>
                        <td className="tnum py-2.5 pr-4 text-right font-mono">
                          {val != null ? val.toLocaleString("en-US", { maximumFractionDigits: m.decimals ?? 0 }) : "–"}{" "}
                          <span className="text-faint">{m.unit}</span>
                        </td>
                        <td className="tnum py-2.5 pr-4 text-right font-mono text-muted">
                          {base != null ? base.toLocaleString("en-US", { maximumFractionDigits: m.decimals ?? 0 }) : "–"}
                        </td>
                        <td className="py-2.5 text-right font-mono text-xs" style={{ color: st.color }}>
                          {st.word}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title={`${sel.label} · history`}>
            {selSeries.filter((v) => v != null).length < 2 ? (
              <EmptyNote>Not enough history yet.</EmptyNote>
            ) : (
              <TimeSeriesChart
                labels={labels}
                series={[
                  { name: sel.label, data: selSeries, color: "var(--accent)", areaOpacity: 0.1 },
                  ...(selBaseline && selBaseline.some((v) => v != null)
                    ? [{ name: "Baseline", data: selBaseline, color: "var(--faint)" }]
                    : []),
                ]}
                height={300}
                zoom={range >= 90}
              />
            )}
          </Card>
        </>
      )}
    </div>
  );
}
