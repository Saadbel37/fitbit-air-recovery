/** Sleep detail: hypnogram, summary cards, consistency, history. */

import { useState } from "react";
import Card, { PageHeader } from "../components/Card";
import RangeToggle from "../components/RangeToggle";
import SleepTimeline from "../components/SleepTimeline";
import TimeSeriesChart from "../components/TimeSeriesChart";
import { EmptyNote, InfoTip, Skeleton, StatusPill } from "../components/primitives";
import { api, fmtMinutes } from "../lib/api";
import { useApiData } from "../lib/hooks";

function Stat({ label, value, hint, tip }: { label: string; value: string; hint?: string; tip?: string }) {
  return (
    <div className="rounded-card border border-line bg-surface p-4">
      <div className="flex items-center gap-1.5 font-disp text-[11px] uppercase tracking-wider text-muted">
        {label}
        {tip && <InfoTip text={tip} label={label} />}
      </div>
      <div className="tnum mt-1 font-mono text-2xl font-semibold">{value}</div>
      {hint && <div className="font-mono text-[10px] text-faint">{hint}</div>}
    </div>
  );
}

const SLEEP_MEANING: Record<string, string> = {
  optimal: "a restorative night.",
  solid: "a decent night.",
  poor: "a short or restless night — try to get a bit more sleep today.",
};

function sleepSummary(score: number | null, status: string | null, sleptMin: number | null, needMin?: number): string {
  if (score == null) return "No usable sleep data for last night.";
  const slept = fmtMinutes(sleptMin);
  const need = needMin != null ? fmtMinutes(needMin) : null;
  const meaning = SLEEP_MEANING[status ?? ""] ?? "your last night.";
  return `Sleep score ${score} of 100 — ${meaning} You slept ${slept}${need ? ` of ${need} need` : ""}.`;
}

export default function Sleep() {
  const [range, setRange] = useState(30);
  const { data, loading } = useApiData((m) => api.sleepDetail("latest", m));
  const hist = useApiData((m) => api.history("sleep", range, m), [range]);

  const main = data?.sessions?.[0];
  const det = data?.detail;
  const night = det?.night as Record<string, number> | undefined;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Sleep">
        {data?.status && <StatusPill status={data.status} />}
      </PageHeader>

      {loading || !data ? (
        <Skeleton className="h-64" />
      ) : !main ? (
        <Card>
          <EmptyNote>No sleep recorded for {data.date}.</EmptyNote>
        </Card>
      ) : (
        <>
          <p className="-mt-2 text-[15px] leading-relaxed text-ink">
            {sleepSummary(data.score, data.status, main.sleep_minutes, det?.need_minutes)}
          </p>
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <Stat
              label="Sleep Score"
              value={data.score != null ? String(data.score) : "–"}
              tip="Overall grade of your night (0–100) from duration, efficiency, consistency and sleep stages."
            />
            <Stat
              label="Performance"
              value={det?.performance != null ? `${Math.round(det.performance * 100)} %` : "–"}
              hint={det ? `Need ${fmtMinutes(det.need_minutes)}` : undefined}
              tip="How much of your calculated sleep need you reached (slept ÷ need)."
            />
            <Stat label="Slept" value={fmtMinutes(main.sleep_minutes)} />
            <Stat
              label="Efficiency"
              value={main.efficiency != null ? `${Math.round(main.efficiency * 100)} %` : "–"}
              tip="Share of time in bed that you were actually asleep."
            />
            <Stat
              label="Sleep debt"
              value={det ? fmtMinutes(det.debt_minutes) : "–"}
              tip="Total missing sleep over the last 14 nights versus your need. A backlog you pay down across several nights."
            />
          </div>

          <Card title="Sleep stages" sub={`Night ending ${data.date}`}>
            {main.stages.length > 0 ? (
              <SleepTimeline stages={main.stages} offsetS={main.utc_offset_seconds} />
            ) : (
              <EmptyNote>No stage data for this night.</EmptyNote>
            )}
            {night && (
              <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {[
                  ["Deep", night.deep_minutes, "#4a53ff"],
                  ["Light", night.light_minutes, "#c7cbff"],
                  ["REM", night.rem_minutes, "#8b93ff"],
                  ["Awake", night.awake_minutes, "#d1495b"],
                ].map(([lbl, min, c]) => (
                  <div key={lbl as string} className="flex items-center gap-2 font-mono text-xs">
                    <span className="h-2.5 w-2.5 rounded-sm" style={{ background: c as string }} />
                    <span className="text-muted">{lbl}</span>
                    <span className="ml-auto">{fmtMinutes(min as number)}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Sleep consistency" sub="Bedtime and wake time over the last 14 nights">
            {data.consistency.length < 2 ? (
              <EmptyNote>Not enough nights yet.</EmptyNote>
            ) : (
              <ConsistencyBars data={data.consistency} />
            )}
          </Card>
        </>
      )}

      <Card title="History" right={<RangeToggle value={range} onChange={setRange} />}>
        {hist.loading || !hist.data ? (
          <Skeleton className="h-64" />
        ) : hist.data.filter((d) => d.score != null).length < 2 ? (
          <EmptyNote>Not enough history yet.</EmptyNote>
        ) : (
          <TimeSeriesChart
            labels={hist.data.map((d) => d.date)}
            series={[
              { name: "Sleep Score", data: hist.data.map((d) => d.score), color: "var(--rest)", type: "bar" },
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

/** Horizontal bar per night from bedtime to wake — visualizes timing spread. */
function ConsistencyBars({ data }: { data: { date: string; bed_local: string; wake_local: string }[] }) {
  const toMin = (t: string) => {
    const [h, m] = t.split(":").map(Number);
    let v = h * 60 + m;
    if (v < 12 * 60) v += 24 * 60; // unwrap past-midnight bedtimes onto a 12:00→36:00 axis
    return v;
  };
  const axisStart = 20 * 60; // 20:00
  const axisEnd = 12 * 60 + 24 * 60; // 12:00 next day
  const span = axisEnd - axisStart;
  const pos = (v: number) => ((v - axisStart) / span) * 100;

  return (
    <div className="flex flex-col gap-1.5">
      {data.map((d) => {
        const bed = toMin(d.bed_local);
        const wake = toMin(d.wake_local) + (toMin(d.wake_local) < bed ? 24 * 60 : 0);
        return (
          <div key={d.date} className="flex items-center gap-2">
            <span className="w-12 font-mono text-[10px] text-faint">
              {d.date.slice(8)}.{d.date.slice(5, 7)}.
            </span>
            <div className="relative h-3 flex-1 rounded bg-surface-2">
              <div
                className="absolute h-full rounded bg-rest/70"
                style={{ left: `${pos(bed)}%`, width: `${pos(wake) - pos(bed)}%` }}
                title={`${d.bed_local} – ${d.wake_local}`}
              />
            </div>
            <span className="w-24 text-right font-mono text-[10px] text-muted">
              {d.bed_local}–{d.wake_local}
            </span>
          </div>
        );
      })}
    </div>
  );
}
