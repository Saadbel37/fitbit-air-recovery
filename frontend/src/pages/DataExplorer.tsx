/** Data Explorer (engineering/debug view): raw data per type with gap
 *  visualization and CSV export. Focused per grilling Q18 — charts + gaps +
 *  range + export; tables only where they help. */

import { useMemo, useState } from "react";
import Card, { PageHeader } from "../components/Card";
import HeartRateChart from "../components/HeartRateChart";
import RangeToggle from "../components/RangeToggle";
import TimeSeriesChart from "../components/TimeSeriesChart";
import { EmptyNote, Skeleton } from "../components/primitives";
import type { HealthDay } from "../lib/api";
import { api, fmtMinutes } from "../lib/api";
import { downloadCSV } from "../lib/csv";
import { useApiData } from "../lib/hooks";
import { useMode } from "../state/mode";

type Tab = "hr" | "daily" | "sleep" | "activities";

const DAILY_METRICS = [
  { key: "hrv", label: "HRV", unit: "ms", color: "var(--accent)", decimals: 1 },
  { key: "resting_hr", label: "Resting HR", unit: "bpm", color: "var(--accent)", decimals: 0 },
  { key: "spo2", label: "SpO₂", unit: "%", color: "var(--accent)", decimals: 1 },
  { key: "respiratory_rate", label: "Respiratory rate", unit: "/min", color: "var(--accent)", decimals: 1 },
  { key: "skin_temp_delta", label: "Skin temp Δ", unit: "°C", color: "var(--accent)", decimals: 2 },
  { key: "steps", label: "Steps", unit: "", color: "var(--accent)", decimals: 0 },
] as const;

const TABS: { id: Tab; label: string }[] = [
  { id: "hr", label: "Heart rate" },
  { id: "daily", label: "Daily values" },
  { id: "sleep", label: "Sleep" },
  { id: "activities", label: "Workouts" },
];

function shiftDay(iso: string, delta: number): string {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + delta);
  return d.toISOString().slice(0, 10);
}

export default function DataExplorer() {
  const [tab, setTab] = useState<Tab>("hr");
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Data Explorer" />
      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            aria-pressed={tab === t.id}
            className={`rounded-lg border px-3.5 py-1.5 font-mono text-xs transition ${
              tab === t.id ? "border-transparent bg-surface-2 text-ink" : "border-line text-muted hover:text-ink"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tab === "hr" && <HeartRateTab />}
      {tab === "daily" && <DailyTab />}
      {tab === "sleep" && <SleepTab />}
      {tab === "activities" && <ActivitiesTab />}
    </div>
  );
}

/* ------------------------------ heart rate ------------------------------ */

function HeartRateTab() {
  const [day, setDay] = useState(() => shiftDay(new Date().toISOString().slice(0, 10), -1));
  const { data, loading } = useApiData((m) => api.heartRate(day, m), [day]);

  const exportCSV = () => {
    if (!data) return;
    downloadCSV(
      `heart-rate_${day}.csv`,
      [["minute_of_day", "hh:mm", "bpm"], ...data.minutes.map((m) => {
        const hh = String(Math.floor(m.minute / 60)).padStart(2, "0");
        const mm = String(m.minute % 60).padStart(2, "0");
        return [m.minute, `${hh}:${mm}`, m.bpm];
      })],
    );
  };

  return (
    <Card
      title="Heart rate (intraday)"
      sub={`Per-minute means · ${day}`}
      right={
        <div className="flex items-center gap-1.5">
          <button onClick={() => setDay((d) => shiftDay(d, -1))} className="rounded border border-line px-2 py-1 font-mono text-sm text-muted hover:text-ink">‹</button>
          <button onClick={() => setDay((d) => shiftDay(d, 1))} className="rounded border border-line px-2 py-1 font-mono text-sm text-muted hover:text-ink">›</button>
          <ExportButton onClick={exportCSV} disabled={!data || data.sample_count === 0} />
        </div>
      }
    >
      {loading || !data ? (
        <Skeleton className="h-64" />
      ) : data.sample_count === 0 ? (
        <EmptyNote>No heart-rate data for {day}.</EmptyNote>
      ) : (
        <>
          <HeartRateChart minutes={data.minutes} zones={[]} />
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Samples" value={data.sample_count.toLocaleString("en-US")} />
            <Stat label="Coverage" value={`${Math.round(data.coverage * 100)}%`} />
            <Stat label="Minutes" value={String(data.minutes.length)} />
            <Stat label="Gaps" value={String(data.gaps.length)} />
          </div>
          {data.gaps.length > 0 && (
            <div className="mt-4">
              <div className="mb-2 font-mono text-[11px] uppercase tracking-wider text-faint">Data gaps</div>
              <div className="flex flex-col gap-1">
                {data.gaps.map((g, i) => {
                  const f = `${String(Math.floor(g.from_minute / 60)).padStart(2, "0")}:${String(g.from_minute % 60).padStart(2, "0")}`;
                  const t = `${String(Math.floor(g.to_minute / 60)).padStart(2, "0")}:${String(g.to_minute % 60).padStart(2, "0")}`;
                  return (
                    <div key={i} className="flex items-center gap-3 rounded border border-status-mid/25 bg-status-mid/5 px-3 py-1.5 font-mono text-xs">
                      <span className="text-status-mid">GAP</span>
                      <span>{f} → {t}</span>
                      <span className="ml-auto text-faint">{g.missing_minutes} min missing</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

/* ------------------------------ daily ------------------------------ */

function DailyTab() {
  const [range, setRange] = useState(30);
  const [metric, setMetric] = useState<string>("hrv");
  const { data, loading } = useApiData((m) => api.health(range, m), [range]);
  const def = DAILY_METRICS.find((m) => m.key === metric)!;

  const series = useMemo(() => (data ?? []).map((d) => (d[metric as keyof HealthDay] as number | null) ?? null), [data, metric]);
  const missing = (data ?? []).filter((d) => (d[metric as keyof HealthDay] as number | null) == null).length;

  const exportCSV = () => {
    if (!data) return;
    downloadCSV(
      `${metric}_${range}days.csv`,
      [["date", metric, "unit"], ...data.map((d) => [d.date, (d[metric as keyof HealthDay] as number | null) ?? "", def.unit])],
    );
  };

  return (
    <Card
      title="Daily values"
      sub="One value per day · missing days are data gaps"
      right={
        <div className="flex items-center gap-2">
          <RangeToggle value={range} onChange={setRange} options={[30, 90, 365]} />
          <ExportButton onClick={exportCSV} disabled={!data} />
        </div>
      }
    >
      <div className="mb-4 flex flex-wrap gap-2">
        {DAILY_METRICS.map((m) => (
          <button
            key={m.key}
            onClick={() => setMetric(m.key)}
            aria-pressed={metric === m.key}
            className={`rounded-button border px-3.5 py-1.5 font-disp text-[13px] font-medium transition duration-180 ${
              metric === m.key ? "border-transparent bg-ink text-white" : "border-line text-muted hover:text-ink"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>
      {loading || !data ? (
        <Skeleton className="h-64" />
      ) : series.filter((v) => v != null).length < 2 ? (
        <EmptyNote>Not enough values yet.</EmptyNote>
      ) : (
        <>
          <TimeSeriesChart
            labels={data.map((d) => d.date)}
            series={[{ name: def.label, data: series, color: def.color, areaOpacity: 0.1 }]}
            height={280}
            zoom={range >= 90}
          />
          <div className="mt-2 font-mono text-[11px] text-faint">
            {missing > 0 ? `${missing} day(s) without a ${def.label} value in this range.` : "No gaps in this range."}
          </div>
        </>
      )}
    </Card>
  );
}

/* ------------------------------ sleep ------------------------------ */

function SleepTab() {
  const { data, loading } = useApiData((m) => api.sleepDetail("latest", m));
  return (
    <Card title="Sleep sessions" sub={data ? `latest: ${data.date}` : ""}>
      {loading ? (
        <Skeleton className="h-48" />
      ) : !data || data.sessions.length === 0 ? (
        <EmptyNote>No sleep data.</EmptyNote>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left font-mono text-[11px] uppercase tracking-wider text-faint">
                <th className="py-2 pr-4 font-normal">Start</th>
                <th className="py-2 pr-4 font-normal">End</th>
                <th className="py-2 pr-4 text-right font-normal">In bed</th>
                <th className="py-2 pr-4 text-right font-normal">Slept</th>
                <th className="py-2 pr-4 text-right font-normal">Efficiency</th>
                <th className="py-2 text-right font-normal">Stages</th>
              </tr>
            </thead>
            <tbody>
              {data.sessions.map((s, i) => {
                const tz = s.utc_offset_seconds;
                const fmt = (iso: string) => {
                  const d = new Date(new Date(iso).getTime() + tz * 1000);
                  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
                };
                return (
                  <tr key={i} className="border-b border-line/50 font-mono text-xs">
                    <td className="py-2.5 pr-4">{fmt(s.start)}</td>
                    <td className="py-2.5 pr-4">{fmt(s.end)}</td>
                    <td className="py-2.5 pr-4 text-right">{fmtMinutes(s.time_in_bed_minutes)}</td>
                    <td className="py-2.5 pr-4 text-right">{fmtMinutes(s.sleep_minutes)}</td>
                    <td className="py-2.5 pr-4 text-right">{s.efficiency != null ? `${Math.round(s.efficiency * 100)} %` : "–"}</td>
                    <td className="py-2.5 text-right text-faint">{s.stages.length}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

/* ------------------------------ activities ------------------------------ */

function ActivitiesTab() {
  const { mode } = useMode();
  const { data, loading } = useApiData((m) => api.activities(90, m));
  const exportCSV = () => {
    if (!data) return;
    downloadCSV(
      `workouts_${mode}.csv`,
      [
        ["type", "start", "end", "duration_min", "avg_hr", "max_hr", "calories", "azm", "strain"],
        ...data.map((a) => [a.type, a.start, a.end, a.duration_minutes, a.avg_hr, a.max_hr, a.calories, a.azm, a.strain]),
      ],
    );
  };
  return (
    <Card title="Workouts" sub="last 90 days" right={<ExportButton onClick={exportCSV} disabled={!data || data.length === 0} />}>
      {loading ? (
        <Skeleton className="h-48" />
      ) : !data || data.length === 0 ? (
        <EmptyNote>No workouts.</EmptyNote>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left font-mono text-[11px] uppercase tracking-wider text-faint">
                <th className="py-2 pr-4 font-normal">Type</th>
                <th className="py-2 pr-4 font-normal">Date</th>
                <th className="py-2 pr-4 text-right font-normal">Duration</th>
                <th className="py-2 pr-4 text-right font-normal">Avg HR</th>
                <th className="py-2 pr-4 text-right font-normal">Max HR</th>
                <th className="py-2 pr-4 text-right font-normal">kcal</th>
                <th className="py-2 text-right font-normal">Strain</th>
              </tr>
            </thead>
            <tbody>
              {data.map((a, i) => (
                <tr key={i} className="border-b border-line/50 text-xs">
                  <td className="py-2.5 pr-4 font-disp font-medium">{a.type}</td>
                  <td className="py-2.5 pr-4 font-mono text-faint">
                    {new Date(a.start).toLocaleDateString("en-US", { day: "2-digit", month: "2-digit" })}
                  </td>
                  <td className="py-2.5 pr-4 text-right font-mono">{fmtMinutes(a.duration_minutes)}</td>
                  <td className="py-2.5 pr-4 text-right font-mono">{a.avg_hr ?? "–"}</td>
                  <td className="py-2.5 pr-4 text-right font-mono">{a.max_hr ?? "–"}</td>
                  <td className="py-2.5 pr-4 text-right font-mono">{a.calories ?? "–"}</td>
                  <td className="py-2.5 text-right font-mono text-move">{a.strain != null ? a.strain.toFixed(1) : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

/* ------------------------------ shared ------------------------------ */

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line bg-bg-2 p-3">
      <div className="font-mono text-[10px] uppercase tracking-wider text-faint">{label}</div>
      <div className="tnum mt-0.5 font-mono text-lg">{value}</div>
    </div>
  );
}

function ExportButton({ onClick, disabled }: { onClick: () => void; disabled?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="rounded-lg border border-line bg-surface px-3 py-1.5 font-mono text-xs text-muted transition hover:bg-surface-2 hover:text-ink disabled:opacity-40"
    >
      CSV
    </button>
  );
}
