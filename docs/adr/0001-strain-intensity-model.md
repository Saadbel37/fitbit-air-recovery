# Strain uses continuous HRR intensity; Fitbit zones are display-only

Fitbit delivers 4 personalized heart-rate zones per day, but its "Light" zone starts at 30 bpm and therefore covers resting time — a zone-minute-weighted load formula would produce a huge idle base load. We decided: cardiovascular load is computed from **continuous Heart Rate Reserve intensity** (`(HR − resting HR) / (HRmax − resting HR)` with a smooth weight function), resampled to **1-minute means** from the ~3 s raw samples; Fitbit's own zone boundaries are used **exclusively for display** ("time in zones", chart coloring), so the UI stays consistent with what the device app shows.

## Consequences

- `HRmax` is an estimate, never blindly the observed maximum: we store `hr_max_value`, `hr_max_source` (`observed_p999 | age_formula | blended`) and `algorithm_version` **per day**. The observed p99.9 is a *lower bound* of true HRmax (heart rate above one's maximum cannot be observed), so observation only revises the estimate **upward**: above the age formula it blends in as history grows toward `hr_max_blend_full_days`; below it, the age formula (220 − age) stands. Historical strain stays reproducible because every day carries the parameters it was scored with.
- Missing minutes reduce the day's Confidence and are **never** counted as rest/zero intensity.
- Raw heart-rate samples are stored untouched; resampling happens at scoring time.

## Considered options

- **Fitbit zones for everything** — consistent with the device but a black box, and the 30-bpm Light zone breaks daily-load math.
- **Own 5 HRR zones (spec §7)** — transparent, but a stepped function diverges from the device's zone display and adds a second, competing zone definition.
