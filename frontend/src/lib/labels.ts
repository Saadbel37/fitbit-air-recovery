/** Display labels + units for metric/contributor keys. */

export const METRIC_LABEL: Record<string, string> = {
  hrv: "HRV",
  resting_hr: "Resting HR",
  sleep: "Sleep",
  respiratory_rate: "Respiratory rate",
  skin_temp: "Skin temp",
  spo2: "SpO₂",
  recovery: "Recovery",
  strain: "Strain",
  steps: "Steps",
};

export const METRIC_UNIT: Record<string, string> = {
  hrv: "ms",
  resting_hr: "bpm",
  respiratory_rate: "/min",
  spo2: "%",
  skin_temp: "°C",
  steps: "",
};

// Monochrome by default; the page's primary series uses the violet accent.
export const SYSTEM_COLOR: Record<string, string> = {
  hrv: "var(--ink)",
  resting_hr: "var(--ink)",
  recovery: "var(--accent)",
  strain: "var(--ink)",
  steps: "var(--ink)",
  sleep: "var(--ink)",
  respiratory_rate: "var(--ink)",
  skin_temp: "var(--ink)",
  spo2: "var(--ink)",
};

/** Restrained multi-series palette for Trends (violet accent + neutrals). */
export const TREND_PALETTE: Record<string, string> = {
  recovery: "#4a53ff",
  hrv: "#111111",
  strain: "#808080",
  sleep: "#9aa0ff",
  resting_hr: "#4a4a4a",
  steps: "#b8bcc4",
  spo2: "#6b74ff",
};

export function label(key: string): string {
  return METRIC_LABEL[key] ?? key;
}
