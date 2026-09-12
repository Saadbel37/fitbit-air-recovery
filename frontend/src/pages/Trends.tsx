/** Trends: normalized (z-score) overlay of chosen metrics, correlations, and
 *  fixed lag analyses. Correlations are hidden below n = 14 (settled Q17). */

import { useMemo, useState } from "react";
import Card, { PageHeader } from "../components/Card";
import RangeToggle from "../components/RangeToggle";
import TimeSeriesChart, { type Series } from "../components/TimeSeriesChart";
import { EmptyNote, InfoTip, Skeleton } from "../components/primitives";
import { api } from "../lib/api";
import { useApiData } from "../lib/hooks";
import { label, TREND_PALETTE as COLORS } from "../lib/labels";

const AVAILABLE = ["recovery", "strain", "sleep", "hrv", "resting_hr", "steps", "spo2"];

function zscore(values: (number | null)[]): (number | null)[] {
  const nums = values.filter((v): v is number => v != null);
  if (nums.length < 2) return values.map(() => null);
  const mean = nums.reduce((a, b) => a + b, 0) / nums.length;
  const sd = Math.sqrt(nums.reduce((a, b) => a + (b - mean) ** 2, 0) / nums.length) || 1;
  return values.map((v) => (v == null ? null : Number(((v - mean) / sd).toFixed(2))));
}

function corrColor(r: number | null): string {
  if (r == null) return "var(--faint)";
  const a = Math.abs(r);
  if (a >= 0.5) return r > 0 ? "var(--status-good)" : "var(--status-low)";
  if (a >= 0.3) return "var(--status-mid)";
  return "var(--muted)";
}

/** Plain-English reading of a correlation coefficient. */
function corrWord(r: number | null): string {
  if (r == null) return "";
  const a = Math.abs(r);
  const strength = a < 0.2 ? "barely any" : a < 0.4 ? "a weak" : a < 0.6 ? "a moderate" : "a strong";
  const dir = a < 0.2 ? "link" : r > 0 ? "positive link" : "inverse link";
  return `${strength} ${dir}`;
}

const CORR_HELP =
  "A correlation r ranges from −1 to +1. Near 0 = no link, +1 = both rise together, −1 = when one rises the other falls. It is an observation, not proof of cause and effect.";

const LAG_LABEL: Record<string, string> = {
  strain_yesterday_vs_recovery: "Strain (prev. day) → Recovery",
  sleep_vs_recovery: "Sleep → Recovery (same day)",
};

export default function Trends() {
  const [range, setRange] = useState(90);
  const [chosen, setChosen] = useState<string[]>(["recovery", "hrv"]);
  const { data, loading } = useApiData((m) => api.trends(chosen.length ? chosen : ["recovery"], range, m), [
    range,
    chosen.join(","),
  ]);

  const toggle = (k: string) =>
    setChosen((c) => (c.includes(k) ? c.filter((x) => x !== k) : [...c, k]));

  const series: Series[] = useMemo(() => {
    if (!data) return [];
    return chosen.map((k) => ({
      name: label(k),
      data: zscore(data.series[k] ?? []),
      color: COLORS[k] ?? "var(--muted)",
    }));
  }, [data, chosen]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Trends">
        <RangeToggle value={range} onChange={setRange} options={[30, 90, 365]} />
      </PageHeader>

      <Card title="Compare" sub="normalized (z-score) so different units are comparable">
        <div className="mb-4 flex flex-wrap gap-2">
          {AVAILABLE.map((k) => {
            const on = chosen.includes(k);
            return (
              <button
                key={k}
                onClick={() => toggle(k)}
                aria-pressed={on}
                className={`inline-flex items-center gap-1.5 rounded-button border px-3.5 py-1.5 font-disp text-[13px] font-medium transition duration-180 ${
                  on ? "border-transparent bg-ink text-white" : "border-line text-muted hover:text-ink"
                }`}
              >
                <span className="h-2 w-2 rounded-full" style={{ background: COLORS[k] }} aria-hidden />
                {label(k)}
              </button>
            );
          })}
        </div>
        {loading || !data ? (
          <Skeleton className="h-72" />
        ) : chosen.length === 0 ? (
          <EmptyNote>Select at least one metric.</EmptyNote>
        ) : (
          <TimeSeriesChart labels={data.labels} series={series} height={320} zoom />
        )}
      </Card>

      {data && (
        <div className="grid gap-6 md:grid-cols-2">
          <Card
            title="Correlations"
            sub={`only from ${data.correlation_gate_days} shared days`}
            right={<InfoTip text={CORR_HELP} label="What does the r value mean?" />}
          >
            {data.correlations.length === 0 ? (
              <EmptyNote>Select at least two metrics.</EmptyNote>
            ) : (
              <div className="flex flex-col divide-y divide-line">
                {data.correlations.map((c, i) => (
                  <div key={i} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                    <span>
                      {label(c.a)} <span className="text-faint">&</span> {label(c.b)}
                    </span>
                    <div className="text-right">
                      {c.r != null ? (
                        <>
                          <div style={{ color: corrColor(c.r) }} className="text-[13px]">
                            {corrWord(c.r)}
                          </div>
                          <div className="tnum font-mono text-[10px] text-faint">
                            r = {c.r.toFixed(2)} · n={c.n}
                          </div>
                        </>
                      ) : (
                        <span className="font-mono text-[11px] text-faint">
                          {c.needs_days} more days of data needed
                        </span>
                      )}
                    </div>
                  </div>
                ))}
                <p className="pt-2 text-[11px] leading-relaxed text-faint">
                  These are observations, not causes — a link does not mean one triggers the other.
                </p>
              </div>
            )}
          </Card>

          <Card title="Does one affect the other?" sub="fixed comparisons across consecutive days">
            <div className="flex flex-col divide-y divide-line">
              {data.lag_analyses.map((l) => (
                <div key={l.name} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                  <span>{LAG_LABEL[l.name] ?? l.name}</span>
                  <div className="text-right">
                    {l.r != null ? (
                      <>
                        <div style={{ color: corrColor(l.r) }} className="text-[13px]">
                          {corrWord(l.r)}
                        </div>
                        <div className="tnum font-mono text-[10px] text-faint">
                          r = {l.r.toFixed(2)} · n={l.n}
                        </div>
                      </>
                    ) : (
                      <span className="font-mono text-[11px] text-faint">{l.needs_days} more days needed</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
