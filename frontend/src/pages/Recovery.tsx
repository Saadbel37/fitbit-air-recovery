/** Recovery detail: radial gauge, "Why?" contributor breakdown, history. */

import { useState } from "react";
import Card, { PageHeader } from "../components/Card";
import RadialScore from "../components/RadialScore";
import RangeToggle from "../components/RangeToggle";
import TimeSeriesChart from "../components/TimeSeriesChart";
import { ConfidenceNote, EmptyNote, Skeleton } from "../components/primitives";
import { api } from "../lib/api";
import { useApiData } from "../lib/hooks";
import { label } from "../lib/labels";

const CONTRIB_ORDER = ["hrv", "resting_hr", "sleep", "respiratory_rate", "skin_temp", "spo2"];

/** Build a plain-English value + comparison string for one factor. */
function describe(
  name: string,
  inputs: Record<string, number | null>,
  baselines: { hrv: number | null; resting_hr: number | null; respiratory_rate: number | null },
): { value: string; compare: string } {
  const fmt = (v: number | null, d = 0, unit = "") =>
    v == null ? "–" : `${v.toLocaleString("en-US", { maximumFractionDigits: d })}${unit ? " " + unit : ""}`;
  switch (name) {
    case "hrv":
      return { value: fmt(inputs.hrv, 0, "ms"), compare: cmpPct(inputs.hrv, baselines.hrv, "higher", "lower") };
    case "resting_hr":
      return { value: fmt(inputs.resting_hr, 0, "bpm"), compare: cmpAbs(inputs.resting_hr, baselines.resting_hr, "bpm") };
    case "sleep":
      return { value: `Score ${fmt(inputs.sleep_score)}`, compare: "from your sleep last night" };
    case "respiratory_rate":
      return { value: fmt(inputs.respiratory_rate, 1, "/min"), compare: cmpPct(inputs.respiratory_rate, baselines.respiratory_rate, "higher", "lower", true) };
    case "skin_temp":
      return {
        value: inputs.skin_temp_delta != null ? `${inputs.skin_temp_delta > 0 ? "+" : ""}${inputs.skin_temp_delta.toFixed(1)} °C` : "–",
        compare: "deviation from your usual night temperature",
      };
    case "spo2":
      return { value: fmt(inputs.spo2, 1, "%"), compare: "average blood-oxygen saturation during sleep" };
    default:
      return { value: "–", compare: "" };
  }
}

function cmpPct(v: number | null, base: number | null, up: string, down: string, stableIfClose = false): string {
  if (v == null || base == null || base === 0) return "no comparison yet";
  const pct = ((v - base) / base) * 100;
  if (Math.abs(pct) < 2) return "in line with your average";
  const near = stableIfClose && Math.abs(pct) < 6 ? "slightly " : "";
  return `${Math.abs(pct).toFixed(0)}% ${near}${pct > 0 ? up : down} than your average (${base.toFixed(0)})`;
}

function cmpAbs(v: number | null, base: number | null, unit: string): string {
  if (v == null || base == null) return "no comparison yet";
  const d = v - base;
  if (Math.abs(d) < 1) return "in line with your average";
  return `${Math.abs(d).toFixed(0)} ${unit} ${d > 0 ? "higher" : "lower"} than your average (${base.toFixed(0)})`;
}

const INPUT_KEY: Record<string, string> = {
  hrv: "hrv",
  resting_hr: "resting_hr",
  sleep: "sleep_score",
  respiratory_rate: "respiratory_rate",
  skin_temp: "skin_temp_delta",
  spo2: "spo2",
};

/** One-sentence plain-English explanation of the score. */
function summarize(data: import("../lib/api").RecoveryDetail): string {
  const c = data.detail?.contributors ?? {};
  const pos = Object.entries(c).filter(([, v]) => v >= 0.62).sort((a, b) => b[1] - a[1]).map(([k]) => label(k));
  const neg = Object.entries(c).filter(([, v]) => v <= 0.38).sort((a, b) => a[1] - b[1]).map(([k]) => label(k));
  const list = (arr: string[]) =>
    arr.length <= 1 ? arr[0] : `${arr.slice(0, -1).join(", ")} and ${arr[arr.length - 1]}`;

  let s = `Your recovery is ${data.status ?? "unclear"}`;
  if (pos.length) s += `, mainly because ${list(pos.slice(0, 2))} ${pos.length > 1 ? "look" : "looks"} good for you`;
  s += ".";
  if (neg.length) s += ` It is held back by ${list(neg.slice(0, 2))}.`;
  return s;
}

/** Labels of metrics that were measured today but don't count yet (no baseline). */
function missingContributors(data: import("../lib/api").RecoveryDetail): string[] {
  const c = data.detail?.contributors ?? {};
  return CONTRIB_ORDER.filter(
    (k) => c[k] == null && data.inputs[INPUT_KEY[k]] != null,
  ).map((k) => label(k));
}

function ContributorRow({
  name,
  value,
  desc,
}: {
  name: string;
  value: number; // 0..1 contribution
  desc: { value: string; compare: string };
}) {
  const helps = value >= 0.62;
  const hurts = value <= 0.38;
  const color = helps ? "var(--status-good)" : hurts ? "var(--status-low)" : "var(--muted)";
  const impact = helps ? "lifts" : hurts ? "drags" : "neutral";
  const arrow = helps ? "↑" : hurts ? "↓" : "→";

  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="font-disp text-sm font-medium">{label(name)}</span>
          <span className="tnum font-mono text-sm" style={{ color }}>
            {desc.value}
          </span>
        </div>
        <div className="mt-0.5 text-[12px] text-muted">{desc.compare}</div>
      </div>
      <span
        className="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[11px]"
        style={{ color, borderColor: color + "55" }}
        title="How this value affects today's recovery"
      >
        <span aria-hidden>{arrow}</span> {impact}
      </span>
    </div>
  );
}

export default function Recovery() {
  const [range, setRange] = useState(30);
  const { data, loading } = useApiData((m) => api.recoveryDetail("latest", m));
  const hist = useApiData((m) => api.history("recovery", range, m), [range]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Recovery" />

      {loading || !data ? (
        <Skeleton className="h-64" />
      ) : data.score == null ? (
        <Card>
          <EmptyNote>No recovery score for {data.date} (not enough data or baseline).</EmptyNote>
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[auto,1fr]">
          <Card className="flex flex-col items-center justify-center">
            <RadialScore value={data.score} status={data.status} color="var(--accent)" caption={data.date} />
            <div className="mt-3">
              <ConfidenceNote value={data.confidence} />
            </div>
          </Card>

          <Card title="Why this recovery?">
            <p className="mb-4 text-[15px] leading-relaxed text-ink">{summarize(data)}</p>
            <div className="divide-y divide-line border-t border-line">
              {CONTRIB_ORDER.filter((k) => data.detail?.contributors[k] != null).map((k) => (
                <ContributorRow
                  key={k}
                  name={k}
                  value={data.detail!.contributors[k]}
                  desc={describe(k, data.inputs, data.baselines)}
                />
              ))}
            </div>
            {/* explain metrics that exist but don't count yet */}
            {missingContributors(data).length > 0 && (
              <div className="mt-3 rounded-lg border border-line bg-bg-2 px-3 py-2 text-[12px] text-muted">
                Not counted yet: <span className="text-ink">{missingContributors(data).join(", ")}</span>.
                The personal baseline is still forming (
                {data.baselines.coverage != null ? `${Math.round(data.baselines.coverage * 100)}%` : "0%"} of 28 days) —
                it builds over the coming days and confidence rises with it.
              </div>
            )}
          </Card>
        </div>
      )}

      <Card
        title="History"
        right={<RangeToggle value={range} onChange={setRange} />}
      >
        {hist.loading || !hist.data ? (
          <Skeleton className="h-64" />
        ) : hist.data.filter((d) => d.score != null).length < 2 ? (
          <EmptyNote>Not enough history yet.</EmptyNote>
        ) : (
          <TimeSeriesChart
            labels={hist.data.map((d) => d.date)}
            series={[
              {
                name: "Recovery",
                data: hist.data.map((d) => d.score),
                color: "var(--accent)",
                areaOpacity: 0.1,
              },
            ]}
            yAxes={[{ min: 0, max: 100 }]}
            zoom={range >= 90}
            height={280}
          />
        )}
      </Card>
    </div>
  );
}
