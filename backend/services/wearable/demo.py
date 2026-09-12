"""DemoProvider — 60 days of realistic, correlated demo data (Demo Mode).

Not white noise: a weekly training rhythm drives strain; yesterday's strain
depresses today's HRV and elevates resting HR; sleep varies around a stable
bedtime. Scripted events (relative to the end of the range):
  - day -8:  one night of bad, fragmented sleep
  - day -12: one very high-strain day (long hard ride)
  - day -20: one small skin-temperature deviation
  - day -25: one day with missing vitals (sensor gap)

Deterministic: seeded RNG, same data every run. Demo data never touches the
real database (separate SQLite file — see backend/database.py).
"""

from __future__ import annotations

import math
import random
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List

from .base import (
    Activity,
    DailyActivity,
    DailyVitals,
    HeartRateSample,
    HeartRateZone,
    HeartRateZoneDay,
    SleepSession,
    SleepStageSegment,
    WearableProvider,
)

_SEED = 20260911
_DAYS = 60
_TZ_OFFSET = 7200  # +02:00, matches the user's real timezone

# Physiological anchors for the demo person
_BASE_RHR = 57.0
_BASE_HRV = 55.0
_BASE_RESP = 13.5
_BASE_SPO2 = 96.8
_HR_MAX = 191


def _local(d: date, t: time) -> datetime:
    """Local wall time -> UTC datetime."""
    return datetime.combine(d, t, tzinfo=timezone(timedelta(seconds=_TZ_OFFSET))).astimezone(timezone.utc)


class _Day:
    """One simulated day with all its correlated values."""

    def __init__(self) -> None:
        self.strain_load = 0.0          # yesterday's value feeds today's vitals
        self.rhr = _BASE_RHR
        self.hrv = _BASE_HRV
        self.resp = _BASE_RESP
        self.spo2 = _BASE_SPO2
        self.temp_delta = 0.0
        self.sleep_start: datetime | None = None
        self.sleep_end: datetime | None = None
        self.stages: List[SleepStageSegment] = []
        self.activities: List[Activity] = []
        self.steps = 0
        self.distance = 0.0
        self.calories = 0.0
        self.azm = 0
        self.missing_vitals = False
        self.hr_minutes: List[int] = []  # 1440 bpm values (minute means)


def _simulate() -> Dict[date, _Day]:
    rng = random.Random(_SEED)
    end = date.today()
    days: Dict[date, _Day] = {}
    prev_strain = 0.0
    prev_bedtime_min = 23 * 60 + 15

    for i in range(_DAYS, 0, -1):
        d = end - timedelta(days=i - 1)
        day = _Day()
        idx_from_end = i - 1  # 0 = today

        weekday = d.weekday()  # 0=Mon
        training = weekday in (1, 3, 5)          # Tue/Thu/Sat
        hard_day = idx_from_end == 12            # scripted high-strain day
        bad_night = idx_from_end == 8
        temp_event = idx_from_end == 20
        missing_day = idx_from_end == 25

        # --- vitals respond to yesterday's strain (correlation, not noise) ---
        strain_hangover = max(0.0, prev_strain - 10.0)
        day.rhr = _BASE_RHR + 0.45 * strain_hangover + rng.gauss(0, 1.1)
        day.hrv = _BASE_HRV - 1.6 * strain_hangover + rng.gauss(0, 4.0)
        day.resp = _BASE_RESP + 0.06 * strain_hangover + rng.gauss(0, 0.35)
        day.spo2 = _BASE_SPO2 + rng.gauss(0, 0.5)
        day.temp_delta = rng.gauss(0, 0.15) + (0.8 if temp_event else 0.0)
        if temp_event:
            day.hrv -= 6
            day.rhr += 2

        # --- sleep (night ending on morning of d) ---
        bed_min = int(0.6 * prev_bedtime_min + 0.4 * (23 * 60 + 15) + rng.gauss(0, 25))
        prev_bedtime_min = bed_min
        sleep_len = rng.gauss(7.6, 0.55) * 60
        if bad_night:
            sleep_len = 4.6 * 60
            bed_min += 95
        bed_h, bed_m = divmod(bed_min % 1440, 60)
        bed_date = d - timedelta(days=1) if bed_min < 1440 else d
        start = _local(bed_date, time(bed_h, bed_m))
        end_dt = start + timedelta(minutes=sleep_len + rng.uniform(15, 40))  # incl. awake time
        day.sleep_start, day.sleep_end = start, end_dt
        day.stages = _stages(rng, start, end_dt, fragmented=bad_night)

        # --- activity ---
        if not missing_day:
            base_steps = rng.gauss(9500, 2200)
            if training or hard_day:
                kind = "BIKING" if (weekday in (1, 5) or hard_day) else "RUN"
                dur = rng.uniform(80, 110) if hard_day else rng.uniform(35, 70)
                avg_int = rng.uniform(0.72, 0.82) if hard_day else rng.uniform(0.58, 0.72)
                a_start = _local(d, time(17, rng.randrange(0, 40)))
                avg_hr = int(_BASE_RHR + avg_int * (_HR_MAX - _BASE_RHR))
                day.activities.append(
                    Activity(
                        external_id=f"demo-{d.isoformat()}-{kind}",
                        activity_type=kind,
                        start=a_start,
                        end=a_start + timedelta(minutes=dur),
                        avg_hr=avg_hr,
                        calories=int(dur * (11 if hard_day else 8.5)),
                        azm=int(dur * (1.9 if avg_int > 0.7 else 1.2)),
                    )
                )
                base_steps += 3000 if kind == "RUN" else 800
            day.steps = max(1500, int(base_steps))
            day.distance = round(day.steps * 0.00078, 2)
            day.azm = sum(a.azm for a in day.activities) + rng.randrange(0, 14)
            day.calories = round(120 + day.steps * 0.032 + sum(a.calories or 0 for a in day.activities), 1)
        day.missing_vitals = missing_day

        # --- minute-level heart rate for the whole day ---
        day.hr_minutes = _minute_hr(rng, day)
        prev_strain = _rough_strain(day)
        days[d] = day
    return days


def _stages(rng: random.Random, start: datetime, end: datetime, fragmented: bool) -> List[SleepStageSegment]:
    """Build a plausible stage sequence covering [start, end]."""
    total_min = (end - start).total_seconds() / 60
    segs: List[SleepStageSegment] = []
    cursor = start
    # opening: fall asleep
    first_awake = rng.uniform(4, 12)
    segs.append(SleepStageSegment("AWAKE", cursor, cursor + timedelta(minutes=first_awake)))
    cursor = segs[-1].end
    cycle = ["LIGHT", "DEEP", "LIGHT", "REM"]
    while (end - cursor).total_seconds() / 60 > 8:
        for stage in cycle:
            remaining = (end - cursor).total_seconds() / 60
            if remaining <= 8:
                break
            base = {"LIGHT": rng.uniform(25, 45), "DEEP": rng.uniform(12, 22), "REM": rng.uniform(12, 25)}[stage]
            if fragmented:
                base *= 0.6
            seg_end = cursor + timedelta(minutes=min(base, remaining - 4))
            segs.append(SleepStageSegment(stage, cursor, seg_end))
            cursor = seg_end
            if fragmented and rng.random() < 0.45:
                wake = cursor + timedelta(minutes=rng.uniform(3, 9))
                segs.append(SleepStageSegment("AWAKE", cursor, min(wake, end)))
                cursor = segs[-1].end
    if cursor < end:
        segs.append(SleepStageSegment("LIGHT", cursor, end))
    _ = total_min
    return segs


def _minute_hr(rng: random.Random, day: _Day) -> List[int]:
    """1440 per-minute bpm values consistent with sleep, day load, and workouts."""
    minutes = [0] * 1440
    for m in range(1440):
        # daytime base with a gentle circadian bump
        base = day.rhr + 12 + 6 * math.sin((m - 600) / 1440 * 2 * math.pi)
        minutes[m] = max(42, int(base + rng.gauss(0, 3)))
    # overnight: near resting
    if day.sleep_start and day.sleep_end:
        tz = timezone(timedelta(seconds=_TZ_OFFSET))
        for m in range(1440):
            probe = datetime.combine(day.sleep_end.astimezone(tz).date(), time(m // 60, m % 60), tzinfo=tz)
            if day.sleep_start <= probe.astimezone(timezone.utc) <= day.sleep_end:
                minutes[m] = max(40, int(day.rhr - 4 + rng.gauss(0, 2)))
    # workouts: ramp to target intensity
    tz = timezone(timedelta(seconds=_TZ_OFFSET))
    for a in day.activities:
        s_loc, e_loc = a.start.astimezone(tz), a.end.astimezone(tz)
        s_min, e_min = s_loc.hour * 60 + s_loc.minute, e_loc.hour * 60 + e_loc.minute
        for m in range(s_min, min(e_min, 1439)):
            frac = min(1.0, (m - s_min) / 8)  # 8-minute ramp
            target = (a.avg_hr or 130) + rng.gauss(0, 6)
            minutes[m] = int(minutes[m] * (1 - frac) + target * frac)
    return minutes


def _rough_strain(day: _Day) -> float:
    """Internal feedback signal for next-day vitals (not the real Strain score)."""
    load = 0.0
    for bpm in day.hr_minutes:
        inten = (bpm - day.rhr) / (_HR_MAX - day.rhr)
        if inten > 0.3:
            load += ((inten - 0.3) / 0.7) ** 2
    return 21 * (1 - math.exp(-load / 90))


class DemoProvider(WearableProvider):
    name = "demo"

    def __init__(self) -> None:
        self._days = _simulate()

    def _in_range(self, start: date, end: date):
        return [(d, day) for d, day in sorted(self._days.items()) if start <= d <= end]

    async def get_heart_rate(self, start: date, end: date) -> List[HeartRateSample]:
        out: List[HeartRateSample] = []
        tz = timezone(timedelta(seconds=_TZ_OFFSET))
        for d, day in self._in_range(start, end):
            for m, bpm in enumerate(day.hr_minutes):
                ts = datetime.combine(d, time(m // 60, m % 60), tzinfo=tz).astimezone(timezone.utc)
                out.append(HeartRateSample(ts=ts, bpm=bpm))
        return out

    async def get_daily_vitals(self, start: date, end: date) -> List[DailyVitals]:
        out = []
        for d, day in self._in_range(start, end):
            if day.missing_vitals:
                continue  # the scripted sensor-gap day
            out.append(
                DailyVitals(
                    day=d,
                    resting_hr=round(day.rhr),
                    hrv_rmssd=round(day.hrv, 1),
                    spo2_avg=round(day.spo2, 1),
                    respiratory_rate=round(day.resp, 1),
                    skin_temp_delta=round(day.temp_delta, 2),
                )
            )
        return out

    async def get_sleep(self, start: date, end: date) -> List[SleepSession]:
        out = []
        for _, day in self._in_range(start, end):
            if day.sleep_start and day.sleep_end:
                out.append(
                    SleepSession(
                        start=day.sleep_start,
                        end=day.sleep_end,
                        utc_offset_seconds=_TZ_OFFSET,
                        stages=tuple(day.stages),
                    )
                )
        return out

    async def get_activities(self, start: date, end: date) -> List[Activity]:
        return [a for _, day in self._in_range(start, end) for a in day.activities]

    async def get_daily_activity(self, start: date, end: date) -> List[DailyActivity]:
        return [
            DailyActivity(
                day=d,
                steps=day.steps or None,
                distance_km=day.distance or None,
                active_calories=day.calories or None,
                azm=day.azm,
            )
            for d, day in self._in_range(start, end)
        ]

    async def get_heart_rate_zones(self, start: date, end: date) -> List[HeartRateZoneDay]:
        zones = (
            HeartRateZone("LIGHT", 30, 113),
            HeartRateZone("MODERATE", 114, 141),
            HeartRateZone("VIGOROUS", 142, 176),
            HeartRateZone("PEAK", 177, 220),
        )
        return [HeartRateZoneDay(day=d, zones=zones) for d, _ in self._in_range(start, end)]
