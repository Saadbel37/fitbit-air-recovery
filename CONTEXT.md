# Fitbit Air Health Analytics

Personal (single-user) health analytics for one Fitbit Air tracker: raw wearable data from the Google Health API is turned into personalized daily scores with transparent, explainable algorithms. UI language is German; code, API, and model names are English.

## Language

### Scores

**Recovery Score**:
A 0–100 daily score expressing how ready the body is, computed from deviations of cardiac and rest metrics against the personal Baseline.
_Avoid_: readiness, recovery percentage

**Strain**:
A 0–21 daily score of accumulated cardiovascular load (workouts plus everyday load).
_Avoid_: exertion, training load (as a score name)

**Sleep Score**:
The primary 0–100 sleep quality score, a weighted composite (duration, efficiency, consistency, stages). This is the headline sleep number.
_Avoid_: using "sleep performance" for this number

**Sleep Performance**:
The ratio of sleep achieved to Sleep Need, in percent. One input of the Sleep Score, never the headline.
_Avoid_: sleep score (for this ratio)

**Sleep Need**:
The nightly sleep duration the user should reach; basis for Sleep Performance and Sleep Debt.

**Sleep Debt**:
Rolling accumulated shortfall of sleep achieved versus Sleep Need.

### Statistics

**Baseline**:
A rolling robust statistic (median) of a metric over a personal history window, target 28 days. With shorter history it is computed from an expanding window of at least 7 real days; synthetic data never feeds a Baseline.
_Avoid_: average, norm

**Confidence**:
A 0–1 value attached to every derived score expressing how complete its input data was (sensor coverage and Baseline window coverage). Missing sensors lower Confidence; they never silently substitute values.
_Avoid_: accuracy, quality score

### Strain model

**Intensity**:
The continuous fraction of Heart Rate Reserve at a moment: (HR − resting HR) / (HRmax − resting HR). The basis of Load; never a discrete zone.

**Load**:
Minute-weighted accumulation of Intensity over a day (workouts plus everyday activity). Mapped non-linearly to Strain.

**HR Max**:
The estimated maximal heart rate used for Intensity. Always carries its source (observed, age formula, or blended); never assumed to be the raw observed maximum.

**Zone**:
One of Fitbit's personalized heart-rate bands (Light/Moderate/Vigorous/Peak). Display-only; Zones never enter score math.

### Sync

**Sync Failure**:
The wearable API could not be reached or returned an error; transient, resolved by retrying. Distinct from an Auth Failure.

**Auth Failure**:
The stored credentials are no longer valid (e.g. expired refresh token); resolved only by the user reconnecting. Never conflated with a Sync Failure.

### Data

**Demo Mode**:
An explicit, visible mode that serves realistic generated data instead of real measurements. Demo data is strictly separated from real data and is never mixed into Baselines or scores of the real mode.
_Avoid_: mock mode (in UI), test data

**Wearable Provider**:
The abstraction that supplies wearable data to the analytics engine; implementations exist for the Google Health API and for Demo Mode.
_Avoid_: integration, connector

### Explanations

**Insight**:
A deterministic, rule-based observation about the user's data (e.g. a deviation from Baseline). Always phrased as an observation or measurement note — never a medical warning, diagnosis, or causal claim.
_Avoid_: alert, warning, diagnosis

**Correlation**:
A pairwise statistical association between two metrics, always reported with its coefficient, sample size n, and data coverage. Below n = 14 no coefficient is shown at all.
_Avoid_: showing "uncertain" coefficients, causal language

### Design

**Signals**:
The project's own design identity (dark plum base, three semantic system accents — heart, movement, rest — monospaced readouts). Evolved for the app; not a WHOOP copy.
