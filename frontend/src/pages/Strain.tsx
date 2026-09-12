/** Strain detail: score, HR timeline (zone-colored), time in zones, activities. */

import { useState } from "react";
import Card, { PageHeader } from "../components/Card";
import HeartRateChart, { ZONE_COLOR } from "../components/HeartRateChart";
import RadialScore from "../components/RadialScore";
import RangeToggle from "../components/RangeToggle";
import TimeSeriesChart from "../components/TimeSeriesChart";
import { ConfidenceNote, EmptyNote, Skeleton } from "../components/primitives";
import { InfoTip } from "../components/primitives";
import { api, fmtMinutes } from "../lib/api";
import { useApiData } from "../lib/hooks";

const STRAIN_MEANING: Record<string, string> = {
  light: "a calm day with little load on your cardiovascular system.",
  moderate: "a solidly active day — noticeable but manageable load.",
  high: "a demanding day — plan for recovery today or tomorrow.",
  "all-out": "a very high load — pay extra attention to recovery.",
};

function strainSummary(score: number | null, status: string | null): string {
  if (score == null) return "Not enough heart-rate data for a strain value on this day.";
  const s = score.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return `Strain ${s} of 21 — ${STRAIN_MEANING[status ?? ""] ?? "your cardiovascular load today."}`;
}

const ZONE_ORDER = ["PEAK", "VIGOROUS", "MODERATE", "LIGHT"];
const ZONE_LABEL: Record<string, string> = {
  PEAK: "Peak",
  VIGOROUS: "Vigorous",
  MODERATE: "Moderate",
  LIGHT: "Light",
};

const HR_MAX_SOURCE: Record<string, string> = {
  observed_p999: "observed",
  age_formula: "age formula",
  blended: "blended",
};

export default function Strain() {
  const [range, setRange] = useState(30);
  const { data, loading } = useApiData((m) => api.strainDetail("latest", m));
  // heart-rate is keyed to the day the strain detail resolved to
  const day = data?.date ?? "yesterday";
  const hr = useApiData((m) => api.heartRate(day, m), [day]);
  const hist = useApiData((m) => api.history("strain", range, m), [range]);

  const zoneMinutes = data?.detail?.zone_minutes ?? {};

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Strain" />

      {loading || !data ? (
        <Skeleton className="h-64" />
      ) : (
        <>
        <p className="-mt-2 text-[15px] leading-relaxed text-ink">{strainSummary(data.score, data.status)}</p>
        <div className="grid gap-6 lg:grid-cols-[auto,1fr]">
          <Card className="flex flex-col items-center justify-center">
            <RadialScore
              value={data.score}
              max={21}
              decimals={1}
              status={data.status}
              color="var(--accent)"
              caption={data.date}
            />
            <div className="mt-3 flex flex-col items-center gap-1">
              <ConfidenceNote value={data.confidence} />
              {data.hr_max.value && (
                <span className="font-mono text-[10px] text-faint">
                  HRmax {data.hr_max.value} ({HR_MAX_SOURCE[data.hr_max.source ?? ""] ?? data.hr_max.source})
                </span>
              )}
            </div>
          </Card>

          <Card
            title="Time in heart-rate zones"
            sub="your device's personal zones"
            right={
              <InfoTip
                label="What are heart-rate zones?"
                text="Ranges of your heart rate from light to peak. They show how intense your day was — the strain value itself is computed independently."
              />
            }
          >
            {Object.keys(zoneMinutes).length === 0 ? (
              <EmptyNote>no zone data</EmptyNote>
            ) : (
              <div className="flex flex-col gap-2.5">
                {ZONE_ORDER.filter((z) => zoneMinutes[z] != null).map((z) => {
                  const max = Math.max(1, ...Object.values(zoneMinutes));
                  return (
                    <div key={z} className="flex items-center gap-3">
                      <span className="w-20 font-disp text-xs font-medium text-muted">{ZONE_LABEL[z]}</span>
                      <div className="h-6 flex-1 overflow-hidden rounded bg-surface-2">
                        <div
                          className="h-full rounded"
                          style={{ width: `${(zoneMinutes[z] / max) * 100}%`, background: ZONE_COLOR[z], opacity: 0.85 }}
                        />
                      </div>
                      <span className="w-16 text-right font-mono text-xs">{fmtMinutes(zoneMinutes[z])}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        </div>
        </>
      )}

      <Card title="Heart-rate trace" sub={`Day · ${data?.date ?? ""}`}>
        {hr.loading || !hr.data ? (
          <Skeleton className="h-64" />
        ) : hr.data.sample_count === 0 ? (
          <EmptyNote>No heart-rate data for this day.</EmptyNote>
        ) : (
          <>
            <HeartRateChart minutes={hr.data.minutes} zones={data?.zones ?? []} />
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[10px] text-faint">
              <span>Coverage {Math.round(hr.data.coverage * 100)}%</span>
              {hr.data.gaps.length > 0 && <span>{hr.data.gaps.length} data gap(s)</span>}
              {Object.entries(ZONE_COLOR).map(([z, c]) => (
                <span key={z} className="inline-flex items-center gap-1">
                  <span className="h-2 w-2 rounded-sm" style={{ background: c }} /> {ZONE_LABEL[z]}
                </span>
              ))}
            </div>
          </>
        )}
      </Card>

      <Card title="Workouts">
        {!data || data.activities.length === 0 ? (
          <EmptyNote>No workouts on this day.</EmptyNote>
        ) : (
          <div className="divide-y divide-line">
            {data.activities.map((a, i) => (
              <div key={i} className="flex flex-wrap items-center justify-between gap-2 py-3">
                <div>
                  <div className="font-disp text-sm font-semibold">{a.type}</div>
                  <div className="font-mono text-[11px] text-faint">
                    {new Date(a.start).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })} –{" "}
                    {new Date(a.end).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}
                  </div>
                </div>
                <div className="flex gap-5 font-mono text-xs text-muted">
                  <span>{fmtMinutes(a.duration_minutes)}</span>
                  {a.avg_hr && <span>Ø {a.avg_hr}</span>}
                  {a.max_hr && <span>max {a.max_hr}</span>}
                  {a.calories != null && <span>{a.calories} kcal</span>}
                  {a.strain != null && (
                    <span className="text-move">Strain {a.strain.toFixed(1)}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="History" right={<RangeToggle value={range} onChange={setRange} />}>
        {hist.loading || !hist.data ? (
          <Skeleton className="h-64" />
        ) : hist.data.filter((d) => d.score != null).length < 2 ? (
          <EmptyNote>Not enough history yet.</EmptyNote>
        ) : (
          <TimeSeriesChart
            labels={hist.data.map((d) => d.date)}
            series={[
              { name: "Strain", data: hist.data.map((d) => d.score), color: "var(--accent)", type: "bar" },
            ]}
            yAxes={[{ min: 0, max: 21 }]}
            zoom={range >= 90}
            height={280}
          />
        )}
      </Card>
    </div>
  );
}
