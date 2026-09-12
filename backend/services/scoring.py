"""Scoring pipeline: DB rows -> Baselines -> Scores -> persisted daily_scores.

Pure orchestration over the analytics modules. Raw tables are read-only here;
results land exclusively in baseline_metrics / daily_scores (never back into
raw data). Timestamps in the DB are naive UTC.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from statistics import pstdev
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import ScoresConfig, get_config
from backend.models import (
    ActivityRow,
    BaselineRow,
    DailyMetric,
    DailyScoreRow,
    HeartRateSampleRow,
    HrZoneDayRow,
    SleepSessionRow,
    SyncState,
)
from backend.services.analytics.baseline import rolling_median
from backend.services.analytics.insights import InsightContext, generate, insights_to_dicts
from backend.services.analytics.recovery import (
    RecoveryBaselines,
    RecoveryInputs,
    calculate_recovery,
)
from backend.services.analytics.sleep import SleepNight, calculate_sleep
from backend.services.analytics.strain import (
    calculate_daily_strain,
    estimate_hr_max,
    resample_to_minutes,
)
from backend.services.wearable.base import HeartRateSample, HeartRateZone


def _local_offset_seconds(day: date) -> int:
    """UTC offset of the system timezone on that day (handles DST)."""
    probe = datetime.combine(day, time(12)).astimezone()
    off = probe.utcoffset()
    return int(off.total_seconds()) if off else 0


def _night_from_row(row: SleepSessionRow) -> SleepNight:
    return SleepNight(
        time_in_bed_minutes=row.time_in_bed_minutes or 0.0,
        sleep_minutes=row.sleep_minutes or 0.0,
        awake_minutes=row.awake_minutes or 0.0,
        light_minutes=row.light_minutes or 0.0,
        deep_minutes=row.deep_minutes or 0.0,
        rem_minutes=row.rem_minutes or 0.0,
        awakenings=row.awakenings or 0,
        efficiency=row.sleep_efficiency or 0.0,
        bedtime_local_minutes=_bedtime_minutes(row),
        has_stages=bool(row.stages_json and row.stages_json != "[]"),
    )


def _bedtime_minutes(row: SleepSessionRow) -> int:
    local = row.start_time.replace(tzinfo=timezone.utc).astimezone(
        timezone(timedelta(seconds=row.utc_offset_seconds or 0))
    )
    return local.hour * 60 + local.minute


def _day_samples(session: Session, day: date, offset_s: int) -> List[HeartRateSample]:
    tz = timezone(timedelta(seconds=offset_s))
    start_local = datetime.combine(day, time.min, tzinfo=tz)
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = start_utc + timedelta(days=1)
    rows = session.execute(
        select(HeartRateSampleRow).where(
            HeartRateSampleRow.ts >= start_utc, HeartRateSampleRow.ts < end_utc
        )
    ).scalars()
    return [HeartRateSample(ts=r.ts.replace(tzinfo=timezone.utc), bpm=r.bpm) for r in rows]


def _observed_hr_stats(session: Session) -> tuple[List[int], int]:
    """Per-day max bpm across all history + number of covered days."""
    rows = session.execute(
        select(func.date(HeartRateSampleRow.ts), func.max(HeartRateSampleRow.bpm)).group_by(
            func.date(HeartRateSampleRow.ts)
        )
    ).all()
    return [int(r[1]) for r in rows], len(rows)


def compute_range(session: Session, start: date, end: date, cfg: Optional[ScoresConfig] = None) -> int:
    """(Re)compute baselines + scores for [start, end]. Returns days scored."""
    cfg = cfg or get_config()
    state = session.get(SyncState, 1)
    birth_year = state.birth_year if state else None

    metrics: Dict[date, DailyMetric] = {
        m.day: m for m in session.execute(select(DailyMetric)).scalars()
    }
    hrv_hist = {d: m.hrv_rmssd for d, m in metrics.items() if m.hrv_rmssd is not None}
    rhr_hist = {d: float(m.resting_hr) for d, m in metrics.items() if m.resting_hr is not None}
    resp_hist = {d: m.respiratory_rate for d, m in metrics.items() if m.respiratory_rate is not None}
    temp_hist = {d: m.skin_temp_delta for d, m in metrics.items() if m.skin_temp_delta is not None}

    sleep_rows = list(
        session.execute(select(SleepSessionRow).order_by(SleepSessionRow.day)).scalars()
    )
    nights_by_day: Dict[date, SleepNight] = {r.day: _night_from_row(r) for r in sleep_rows}
    sleep_hist = {d: n.sleep_minutes for d, n in nights_by_day.items()}

    zones_by_day: Dict[date, List[HeartRateZone]] = {}
    for z in session.execute(select(HrZoneDayRow)).scalars():
        zones_by_day[z.day] = [HeartRateZone(**j) for j in json.loads(z.zones_json)]

    observed_maxes, hr_history_days = _observed_hr_stats(session)

    b = cfg.baseline
    scored = 0
    computed_recovery: Dict[date, int] = {
        r.day: r.recovery_score
        for r in session.execute(select(DailyScoreRow)).scalars()
        if r.recovery_score is not None
    }
    computed_strain: Dict[date, float] = {
        r.day: r.strain_score
        for r in session.execute(select(DailyScoreRow)).scalars()
        if r.strain_score is not None
    }

    day = start
    while day <= end:
        m = metrics.get(day)
        offset_s = _local_offset_seconds(day)

        # --- baselines (persisted for transparency/Health page) ---
        bl_hrv = rolling_median(hrv_hist, day, b.window_days, b.min_days)
        bl_rhr = rolling_median(rhr_hist, day, b.window_days, b.min_days)
        bl_resp = rolling_median(resp_hist, day, b.window_days, b.min_days)
        bl_temp = rolling_median(temp_hist, day, b.window_days, b.min_days)
        bl_sleep = rolling_median(sleep_hist, day, b.window_days, b.min_days)
        session.merge(BaselineRow(
            day=day,
            hrv_baseline=bl_hrv.value,
            resting_hr_baseline=bl_rhr.value,
            respiratory_rate_baseline=bl_resp.value,
            temperature_baseline=bl_temp.value,
            sleep_duration_baseline=bl_sleep.value,
            coverage=bl_hrv.coverage,
        ))

        # --- sleep ---
        night = nights_by_day.get(day)
        prior_nights = [n for d, n in sorted(nights_by_day.items()) if d < day]
        sleep_res = calculate_sleep(night, prior_nights, cfg)

        # --- strain ---
        samples = _day_samples(session, day, offset_s)
        minute_hr = resample_to_minutes(samples, day, offset_s)
        hr_max = estimate_hr_max(observed_maxes, hr_history_days, birth_year, day, cfg)
        rhr_today = float(m.resting_hr) if (m and m.resting_hr is not None) else (bl_rhr.value)
        strain_res = calculate_daily_strain(
            minute_hr, rhr_today, hr_max, cfg, zones_by_day.get(day)
        )

        # --- recovery ---
        rec_res = calculate_recovery(
            RecoveryInputs(
                hrv_rmssd=m.hrv_rmssd if m else None,
                resting_hr=float(m.resting_hr) if (m and m.resting_hr is not None) else None,
                sleep_score=sleep_res.score,
                respiratory_rate=m.respiratory_rate if m else None,
                skin_temp_delta=m.skin_temp_delta if m else None,
                spo2_avg=m.spo2_avg if m else None,
            ),
            RecoveryBaselines(hrv=bl_hrv, resting_hr=bl_rhr, respiratory_rate=bl_resp),
            cfg,
        )

        # --- insights ---
        week = [computed_recovery[d] for d in computed_recovery if day - timedelta(days=7) <= d < day]
        recent_beds = [
            n.bedtime_local_minutes + (1440 if n.bedtime_local_minutes < 720 else 0)
            for d, n in sorted(nights_by_day.items())
            if day - timedelta(days=cfg.sleep.consistency_window_days) <= d <= day
        ]
        weekly_azm = sum(
            metrics[d].azm or 0 for d in metrics if day - timedelta(days=6) <= d <= day
        )
        ctx = InsightContext(
            hrv=m.hrv_rmssd if m else None,
            hrv_baseline=bl_hrv.value,
            resting_hr=float(m.resting_hr) if (m and m.resting_hr is not None) else None,
            resting_hr_baseline=bl_rhr.value,
            sleep_minutes=night.sleep_minutes if night else None,
            sleep_need_minutes=sleep_res.need_minutes,
            yesterday_strain=computed_strain.get(day - timedelta(days=1)),
            recovery_today=rec_res.score,
            recovery_7d_avg=(sum(week) / len(week)) if week else None,
            skin_temp_delta=m.skin_temp_delta if m else None,
            spo2_avg=m.spo2_avg if m else None,
            bedtime_stddev_minutes=pstdev(recent_beds) if len(recent_beds) >= 3 else None,
            weekly_azm=weekly_azm or None,
            hr_coverage=strain_res.confidence,
            vitals_missing=m is None,
        )
        insights = generate(ctx, cfg)

        session.merge(DailyScoreRow(
            day=day,
            recovery_score=rec_res.score,
            recovery_status=rec_res.status,
            recovery_confidence=rec_res.confidence,
            recovery_detail_json=json.dumps({
                "contributors": rec_res.contributors,
                "positive_factors": rec_res.positive_factors,
                "negative_factors": rec_res.negative_factors,
                "deviations": rec_res.deviations,
            }),
            strain_score=strain_res.score,
            strain_status=strain_res.status,
            strain_confidence=strain_res.confidence,
            strain_detail_json=json.dumps({
                "load": strain_res.load,
                "minutes_covered": strain_res.minutes_covered,
                "zone_minutes": strain_res.zone_minutes,
            }),
            hr_max_value=strain_res.hr_max.value,
            hr_max_source=strain_res.hr_max.source,
            sleep_score=sleep_res.score,
            sleep_status=sleep_res.status,
            sleep_confidence=sleep_res.confidence,
            sleep_detail_json=json.dumps({
                "performance": sleep_res.performance,
                "need_minutes": sleep_res.need_minutes,
                "debt_minutes": sleep_res.debt_minutes,
                "parts": sleep_res.parts,
                "night": asdict(night) if night else None,
            }),
            insights_json=json.dumps(insights_to_dicts(insights), ensure_ascii=False),
            algorithm_version=cfg.algorithm_version,
            computed_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))

        if rec_res.score is not None:
            computed_recovery[day] = rec_res.score
        if strain_res.score is not None:
            computed_strain[day] = strain_res.score
        scored += 1
        day += timedelta(days=1)

    session.commit()
    return scored
