/** Typed API client. Every data call carries the active data mode. */

export type Mode = "real" | "demo";

export interface ScoreBlock {
  score: number | null;
  status: string | null;
  confidence: number | null;
}

export interface DashboardResponse {
  date: string;
  recovery: ScoreBlock & { vs_yesterday: number | null };
  strain: ScoreBlock;
  sleep: ScoreBlock & {
    duration_minutes: number | null;
    need_minutes: number | null;
    performance: number | null;
  };
  health: {
    hrv: number | null;
    hrv_baseline: number | null;
    resting_hr: number | null;
    resting_hr_baseline: number | null;
    spo2: number | null;
    respiratory_rate: number | null;
    respiratory_rate_baseline: number | null;
    temperature_delta: number | null;
    steps: number | null;
    azm: number | null;
  };
  insights: { type: string; metric: string; title: string; description: string }[];
}

export interface HistoryPoint {
  date: string;
  score: number | null;
  status: string | null;
  confidence: number | null;
}

export interface HealthDay {
  date: string;
  hrv: number | null;
  resting_hr: number | null;
  spo2: number | null;
  respiratory_rate: number | null;
  skin_temp_delta: number | null;
  steps: number | null;
  distance_km: number | null;
  active_calories: number | null;
  azm: number | null;
  baselines: {
    hrv: number | null;
    resting_hr: number | null;
    respiratory_rate: number | null;
    skin_temp: number | null;
    coverage: number | null;
  } | null;
}

export interface ModeStatus {
  days_scored: number;
  first_day: string | null;
  last_day: string | null;
  last_sync: string | null;
  sync_status: "ok" | "sync_error" | "auth_error" | "never";
  sync_error: string | null;
}

export interface StatusResponse {
  algorithm_version: string;
  modes: Record<Mode, ModeStatus>;
}

export interface RecoveryDetail {
  date: string;
  score: number | null;
  status: string | null;
  confidence: number | null;
  detail: {
    contributors: Record<string, number>;
    positive_factors: string[];
    negative_factors: string[];
    deviations: Record<string, number>;
  } | null;
  inputs: Record<string, number | null>;
  baselines: { hrv: number | null; resting_hr: number | null; respiratory_rate: number | null; coverage: number | null };
}

export interface StrainActivity {
  type: string;
  start: string;
  end: string;
  duration_minutes: number;
  avg_hr: number | null;
  max_hr: number | null;
  calories: number | null;
  azm: number | null;
  strain: number | null;
}

export interface StrainDetail {
  date: string;
  score: number | null;
  status: string | null;
  confidence: number | null;
  detail: { load: number; minutes_covered: number; zone_minutes: Record<string, number> } | null;
  hr_max: { value: number | null; source: string | null };
  zones: { name: string; min_bpm: number; max_bpm: number }[];
  activities: StrainActivity[];
}

export interface SleepStage {
  stage: string;
  start: string;
  end: string;
}

export interface SleepDetail {
  date: string;
  score: number | null;
  status: string | null;
  confidence: number | null;
  detail: {
    performance: number | null;
    need_minutes: number;
    debt_minutes: number;
    parts: Record<string, number>;
    night: Record<string, number | boolean> | null;
  } | null;
  sessions: {
    start: string;
    end: string;
    utc_offset_seconds: number;
    time_in_bed_minutes: number | null;
    sleep_minutes: number | null;
    efficiency: number | null;
    awakenings: number | null;
    stages: SleepStage[];
  }[];
  consistency: { date: string; bed_local: string; wake_local: string }[];
}

export interface TrendsResponse {
  days: number;
  labels: string[];
  series: Record<string, (number | null)[]>;
  correlations: { a: string; b: string; n: number; coverage: number; r: number | null; needs_days?: number }[];
  lag_analyses: { name: string; n: number; coverage: number; r: number | null; needs_days?: number }[];
  correlation_gate_days: number;
}

export interface HeartRateResponse {
  date: string;
  utc_offset_seconds: number;
  sample_count: number;
  minutes: { minute: number; bpm: number }[];
  gaps: { from_minute: number; to_minute: number; missing_minutes: number }[];
  coverage: number;
}

async function getJSON<T>(path: string, params?: Record<string, string>): Promise<T> {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  const res = await fetch(`/api${path}${qs}`);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body.slice(0, 200)}`);
  }
  return res.json();
}

export const api = {
  status: () => getJSON<StatusResponse>("/status"),
  dashboard: (day: string, mode: Mode) =>
    getJSON<DashboardResponse>(`/dashboard/${day}`, { mode }),
  history: (kind: "recovery" | "strain" | "sleep", days: number, mode: Mode) =>
    getJSON<HistoryPoint[]>(`/${kind}`, { days: String(days), mode }),
  health: (days: number, mode: Mode) =>
    getJSON<HealthDay[]>(`/health`, { days: String(days), mode }),
  recoveryDetail: (day: string, mode: Mode) =>
    getJSON<RecoveryDetail>(`/recovery/${day}`, { mode }),
  strainDetail: (day: string, mode: Mode) =>
    getJSON<StrainDetail>(`/strain/${day}`, { mode }),
  sleepDetail: (day: string, mode: Mode) =>
    getJSON<SleepDetail>(`/sleep/${day}`, { mode }),
  trends: (metrics: string[], days: number, mode: Mode) =>
    getJSON<TrendsResponse>(`/trends`, { metrics: metrics.join(","), days: String(days), mode }),
  activities: (days: number, mode: Mode) =>
    getJSON<StrainActivity[]>(`/activities`, { days: String(days), mode }),
  heartRate: (day: string, mode: Mode) =>
    getJSON<HeartRateResponse>(`/heart-rate`, { day, mode }),
  sync: async (mode: Mode) => {
    const res = await fetch(`/api/sync?mode=${mode}`, { method: "POST" });
    if (!res.ok) throw new Error(`Sync fehlgeschlagen (${res.status})`);
    return res.json() as Promise<{ status: string; records_imported: number; error: string | null }>;
  },
};

export function fmtMinutes(min: number | null): string {
  if (min == null) return "–";
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  return h > 0 ? `${h} h ${String(m).padStart(2, "0")} min` : `${m} min`;
}

export function confidenceWord(c: number | null): string {
  if (c == null) return "–";
  if (c >= 0.8) return "high";
  if (c >= 0.5) return "medium";
  return "low";
}
