/** Overview: three primary scores (Recovery dominant), health monitor, insights. */

import { useEffect, useState } from "react";
import { PageHeader, SectionHeader } from "../components/Card";
import MetricCard from "../components/MetricCard";
import MetricHero from "../components/MetricHero";
import MetricRow from "../components/MetricRow";
import PillButton from "../components/PillButton";
import { EmptyNote, Skeleton } from "../components/primitives";
import type { DashboardResponse, HealthDay } from "../lib/api";
import { api, fmtMinutes } from "../lib/api";
import { useMode } from "../state/mode";

const INSIGHT_ICON: Record<string, string> = { positive: "▲", negative: "▼", neutral: "•", info: "ℹ" };
const INSIGHT_COLOR: Record<string, string> = {
  positive: "var(--status-good)",
  negative: "var(--status-low)",
  neutral: "var(--muted)",
  info: "var(--accent)",
};

function isoDay(offsetDays: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

export default function Overview() {
  const { mode } = useMode();
  const [dayOffset, setDayOffset] = useState(0);
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [health, setHealth] = useState<HealthDay[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const day = isoDay(dayOffset);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [d, h] = await Promise.all([api.dashboard(day, mode), api.health(14, mode)]);
      setData(d);
      setHealth(h);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    const onSync = () => void load();
    window.addEventListener("signals:synced", onSync);
    return () => window.removeEventListener("signals:synced", onSync);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, day]);

  if (loading)
    return (
      <div className="grid gap-6 md:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-52" />
        ))}
      </div>
    );

  if (error)
    return (
      <div className="rounded-card bg-surface p-6 text-sm text-muted">
        Couldn't load data. Is the backend running?
        <br />
        <span className="font-mono text-xs text-faint">{error}</span>
      </div>
    );

  if (!data) return null;

  const labels = health.map((h) => h.date);
  const hist = (f: (h: HealthDay) => number | null) => health.map(f);
  const vsY = data.recovery.vs_yesterday;
  const dayLabel =
    dayOffset === 0 ? "Today" : dayOffset === -1 ? "Yesterday" : new Date(day).toLocaleDateString("en-US", { weekday: "long", day: "numeric", month: "long" });
  const nothingToday = dayOffset === 0 && data.recovery.score == null && data.strain.score == null && data.sleep.score == null;
  const cmp = (v: number | null) => (v == null ? undefined : v.toLocaleString("en-US", { maximumFractionDigits: 0 }));

  return (
    <div className="flex flex-col gap-10">
      <PageHeader title="Overview" subtitle={`${dayLabel} · your signals at a glance`}>
        <div className="flex items-center gap-1.5">
          <PillButton variant="secondary" onClick={() => setDayOffset((o) => o - 1)} aria-label="Previous day">
            ‹
          </PillButton>
          <PillButton variant="secondary" onClick={() => setDayOffset((o) => Math.min(0, o + 1))} disabled={dayOffset === 0} aria-label="Next day">
            ›
          </PillButton>
          {dayOffset !== 0 && (
            <PillButton variant="secondary" onClick={() => setDayOffset(0)}>
              Today
            </PillButton>
          )}
        </div>
      </PageHeader>

      {nothingToday && (
        <div className="flex items-center justify-between gap-3 rounded-card bg-surface px-5 py-3 text-[13px] text-muted">
          No data has been processed for today yet.
          <PillButton variant="dark" onClick={() => setDayOffset(-1)}>
            View yesterday
          </PillButton>
        </div>
      )}

      {/* --- primary scores; Recovery dominant with supporting rows --- */}
      <section className="grid gap-6 lg:grid-cols-3" aria-label="Daily scores">
        <MetricHero
          label="Recovery"
          to="/recovery"
          value={data.recovery.score}
          status={data.recovery.status}
          confidence={data.recovery.confidence}
          accent
          sub={vsY != null ? `${vsY >= 0 ? "+" : ""}${vsY} vs. prev. day` : " "}
        >
          <MetricRow label="HRV" value={data.health.hrv != null ? String(Math.round(data.health.hrv)) : "–"} unit="ms" compare={data.health.hrv_baseline ? `Ø ${Math.round(data.health.hrv_baseline)}` : undefined} />
          <MetricRow label="Resting HR" value={data.health.resting_hr != null ? String(data.health.resting_hr) : "–"} unit="bpm" compare={data.health.resting_hr_baseline ? `Ø ${Math.round(data.health.resting_hr_baseline)}` : undefined} />
          <MetricRow label="Sleep" value={data.sleep.score != null ? String(data.sleep.score) : "–"} compare="Score" />
        </MetricHero>

        <MetricHero
          label="Strain"
          to="/strain"
          value={data.strain.score}
          decimals={1}
          max="/ 21"
          status={data.strain.status}
          confidence={data.strain.confidence}
          sub="cardiovascular load"
        >
          <MetricRow label="Steps" value={cmp(data.health.steps) ?? "–"} />
          <MetricRow label="Active zone min." value={data.health.azm != null ? String(data.health.azm) : "–"} unit="min" />
        </MetricHero>

        <MetricHero
          label="Sleep Score"
          to="/sleep"
          value={data.sleep.score}
          status={data.sleep.status}
          confidence={data.sleep.confidence}
          sub={
            data.sleep.duration_minutes != null && data.sleep.need_minutes != null
              ? `${fmtMinutes(data.sleep.duration_minutes)} / ${fmtMinutes(data.sleep.need_minutes)} need`
              : "no night recorded"
          }
        >
          <MetricRow label="Performance" value={data.sleep.performance != null ? `${Math.round(data.sleep.performance * 100)} %` : "–"} />
          <MetricRow label="SpO₂" value={data.health.spo2 != null ? data.health.spo2.toFixed(1) : "–"} unit="%" />
        </MetricHero>
      </section>

      {/* --- health monitor --- */}
      <section aria-label="Health monitor">
        <SectionHeader title="Health Monitor" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <MetricCard label="HRV" tooltip="Heart rate variability: variation between consecutive heartbeats. Higher than your baseline tends to be good." unit="ms" value={data.health.hrv} baseline={data.health.hrv_baseline} labels={labels} history={hist((h) => h.hrv)} />
          <MetricCard label="Resting HR" tooltip="Resting heart rate. Lower than your baseline tends to be good." unit="bpm" value={data.health.resting_hr} baseline={data.health.resting_hr_baseline} lowerIsBetter labels={labels} history={hist((h) => h.resting_hr)} />
          <MetricCard label="Respiratory rate" tooltip="Breaths per minute during sleep. Stable near your baseline is normal." unit="/min" decimals={1} value={data.health.respiratory_rate} baseline={data.health.respiratory_rate_baseline} labels={labels} history={hist((h) => h.respiratory_rate)} />
          <MetricCard label="SpO₂" tooltip="Average blood-oxygen saturation during sleep." unit="%" decimals={1} value={data.health.spo2} baseline={null} labels={labels} history={hist((h) => h.spo2)} />
          <MetricCard label="Skin temp Δ" tooltip="Deviation of nightly skin temperature from your baseline." unit="°C" decimals={2} value={data.health.temperature_delta} baseline={null} aroundZero labels={labels} history={hist((h) => h.skin_temp_delta)} />
        </div>
      </section>

      {/* --- insights --- */}
      <section aria-label="Insights">
        <SectionHeader title="Today at a glance" />
        {data.insights.length === 0 ? (
          <EmptyNote>Nothing notable — everything near your baselines.</EmptyNote>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {data.insights.map((ins, i) => (
              <div key={i} className="flex gap-3 rounded-card bg-surface p-5">
                <span className="mt-0.5 font-mono text-sm" style={{ color: INSIGHT_COLOR[ins.type] ?? "var(--muted)" }} aria-hidden>
                  {INSIGHT_ICON[ins.type] ?? "•"}
                </span>
                <div>
                  <div className="text-sm font-semibold">{ins.title}</div>
                  <div className="mt-0.5 text-[13px] leading-relaxed text-muted">{ins.description}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
