"""Insight engine (CONTEXT.md: "Insight").

Ten deterministic rules, thresholds from scores.toml. Every text is an
observation or measurement note — never a medical warning, diagnosis, or
causal claim. No LLM involved.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from backend.config import ScoresConfig


@dataclass(frozen=True)
class Insight:
    type: str      # positive | negative | neutral | info
    metric: str
    title: str
    description: str


@dataclass(frozen=True)
class InsightContext:
    """Everything the rules may look at. All fields optional — rules skip gaps."""

    hrv: Optional[float] = None
    hrv_baseline: Optional[float] = None
    resting_hr: Optional[float] = None
    resting_hr_baseline: Optional[float] = None
    sleep_minutes: Optional[float] = None
    sleep_need_minutes: Optional[float] = None
    yesterday_strain: Optional[float] = None
    recovery_today: Optional[int] = None
    recovery_7d_avg: Optional[float] = None
    skin_temp_delta: Optional[float] = None
    spo2_avg: Optional[float] = None
    bedtime_stddev_minutes: Optional[float] = None
    weekly_azm: Optional[int] = None
    hr_coverage: Optional[float] = None        # 0..1 minute coverage of the day
    vitals_missing: bool = False


def _fmt_min(minutes: float) -> str:
    h, m = divmod(int(round(abs(minutes))), 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def generate(ctx: InsightContext, cfg: ScoresConfig) -> List[Insight]:
    t = cfg.insights
    out: List[Insight] = []

    # 1 — HRV vs. baseline
    if ctx.hrv is not None and ctx.hrv_baseline:
        pct = (ctx.hrv - ctx.hrv_baseline) / ctx.hrv_baseline * 100
        if abs(pct) >= t.hrv_notable_pct:
            up = pct > 0
            out.append(Insight(
                type="positive" if up else "negative", metric="hrv",
                title="HRV above baseline" if up else "HRV below baseline",
                description=f"Your HRV is {abs(pct):.0f}% {'above' if up else 'below'} your personal baseline ({ctx.hrv_baseline:.0f} ms).",
            ))

    # 2 — Resting heart rate vs. baseline
    if ctx.resting_hr is not None and ctx.resting_hr_baseline:
        diff = ctx.resting_hr - ctx.resting_hr_baseline
        if abs(diff) >= t.rhr_notable_bpm:
            low = diff < 0
            out.append(Insight(
                type="positive" if low else "negative", metric="resting_hr",
                title="Resting heart rate lower than usual" if low else "Resting heart rate elevated",
                description=f"Your resting heart rate is {abs(diff):.0f} bpm {'below' if low else 'above'} your baseline ({ctx.resting_hr_baseline:.0f} bpm).",
            ))

    # 3 — Sleep vs. need
    if ctx.sleep_minutes is not None and ctx.sleep_need_minutes:
        gap = ctx.sleep_need_minutes - ctx.sleep_minutes
        if gap >= t.sleep_shortfall_notable_min:
            out.append(Insight(
                type="negative", metric="sleep", title="Below sleep need",
                description=f"You slept {_fmt_min(gap)} less than your calculated need ({_fmt_min(ctx.sleep_need_minutes)}).",
            ))
        elif gap <= -15:
            out.append(Insight(
                type="positive", metric="sleep", title="Sleep need met",
                description=f"You exceeded your calculated sleep need by {_fmt_min(-gap)}.",
            ))

    # 4 — Yesterday's strain ↔ today's recovery (observation, not causation)
    if (
        ctx.yesterday_strain is not None and ctx.yesterday_strain >= t.strain_high_threshold
        and ctx.recovery_today is not None and ctx.recovery_7d_avg
        and ctx.recovery_today < ctx.recovery_7d_avg
    ):
        out.append(Insight(
            type="neutral", metric="strain",
            title="High strain yesterday",
            description=f"Yesterday your strain was {ctx.yesterday_strain:.1f}. Today's recovery is below your 7-day average — the two often occur together after heavy load.",
        ))

    # 5 — Skin temperature deviation (measurement note, not a warning)
    if ctx.skin_temp_delta is not None and abs(ctx.skin_temp_delta) >= t.skin_temp_notable_celsius:
        out.append(Insight(
            type="neutral", metric="skin_temp", title="Skin temperature deviating",
            description=f"Your nightly skin temperature was {abs(ctx.skin_temp_delta):.1f} °C {'above' if ctx.skin_temp_delta > 0 else 'below'} your baseline.",
        ))

    # 6 — SpO2 deviation (measurement note)
    if ctx.spo2_avg is not None and ctx.spo2_avg < t.spo2_notable:
        out.append(Insight(
            type="neutral", metric="spo2", title="SpO₂ measured lower",
            description=f"Your average oxygen saturation was measured at {ctx.spo2_avg:.1f}% — lower than usual for you.",
        ))

    # 7 — Sleep consistency
    if ctx.bedtime_stddev_minutes is not None and ctx.bedtime_stddev_minutes >= t.bedtime_stddev_notable_min:
        out.append(Insight(
            type="negative", metric="sleep_consistency", title="Irregular bedtimes",
            description=f"Your bedtime varied by ±{ctx.bedtime_stddev_minutes:.0f} min recently. More consistent times tend to go with better sleep scores for you.",
        ))

    # 8 — Weekly AZM vs. the 150-min guideline
    if ctx.weekly_azm is not None:
        if ctx.weekly_azm >= t.weekly_azm_target:
            out.append(Insight(
                type="positive", metric="azm", title="Weekly activity goal reached",
                description=f"{ctx.weekly_azm} active zone minutes this week — above the WHO guideline of 150 min.",
            ))
        elif ctx.weekly_azm < t.weekly_azm_target * 0.5:
            out.append(Insight(
                type="neutral", metric="azm", title="Few active zone minutes",
                description=f"{ctx.weekly_azm} of {t.weekly_azm_target} active zone minutes this week (WHO guideline).",
            ))

    # 9 — Data gaps
    if ctx.vitals_missing or (ctx.hr_coverage is not None and ctx.hr_coverage < 0.5):
        detail = "Vitals are missing for this day." if ctx.vitals_missing else f"Only {ctx.hr_coverage:.0%} of the day has heart-rate data."
        out.append(Insight(
            type="info", metric="data", title="Sparse data",
            description=f"{detail} Scores for this day have reduced confidence.",
        ))

    # 10 — Recovery vs. 7-day average
    if ctx.recovery_today is not None and ctx.recovery_7d_avg:
        pct = (ctx.recovery_today - ctx.recovery_7d_avg) / ctx.recovery_7d_avg * 100
        if abs(pct) >= t.recovery_vs_week_notable_pct:
            up = pct > 0
            out.append(Insight(
                type="positive" if up else "neutral", metric="recovery",
                title="Recovery above weekly average" if up else "Recovery below weekly average",
                description=f"Your recovery is {abs(pct):.0f}% {'above' if up else 'below'} your 7-day average.",
            ))

    return out


def insights_to_dicts(insights: List[Insight]) -> List[Dict[str, str]]:
    return [vars(i) for i in insights]
