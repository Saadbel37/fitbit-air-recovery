"""Wearable Provider abstraction (see CONTEXT.md).

The analytics engine only ever sees these normalized DTOs — it is fully
independent of Google Health, demo data, or any future source. Every field
here is backed by a verified source field; nothing is invented:

  - HeartRateSample   <- heart-rate:  heartRate.beatsPerMinute @ sampleTime.physicalTime
  - DailyVitals       <- daily-resting-heart-rate / daily-heart-rate-variability /
                         daily-oxygen-saturation / daily-respiratory-rate /
                         daily-sleep-temperature-derivations
  - SleepSession      <- sleep: interval + stages[]
  - Activity          <- exercise: exerciseType, interval, metricsSummary
                         (NOTE: the API has no max HR for activities — max_hr is
                         derived later from HeartRateSamples inside the interval)
  - DailyActivity     <- dailyRollUp of steps / distance / active-energy-burned /
                         active-zone-minutes
  - HeartRateZoneDay  <- daily-heart-rate-zones (display-only per ADR 0001)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class HeartRateSample:
    ts: datetime          # UTC
    bpm: int


@dataclass(frozen=True)
class SleepStageSegment:
    stage: str            # AWAKE | LIGHT | DEEP | REM
    start: datetime       # UTC
    end: datetime


@dataclass(frozen=True)
class SleepSession:
    start: datetime       # UTC
    end: datetime
    utc_offset_seconds: int                     # for civil bed/wake times
    stages: Tuple[SleepStageSegment, ...] = field(default_factory=tuple)

    def minutes_by_stage(self) -> dict:
        out: dict = {}
        for s in self.stages:
            out[s.stage] = out.get(s.stage, 0.0) + (s.end - s.start).total_seconds() / 60
        return out


@dataclass(frozen=True)
class Activity:
    external_id: str
    activity_type: str    # e.g. BIKING, RUN, WALK
    start: datetime       # UTC
    end: datetime
    avg_hr: Optional[int]
    calories: Optional[int]
    azm: int


@dataclass(frozen=True)
class DailyActivity:
    day: date
    steps: Optional[int]
    distance_km: Optional[float]
    active_calories: Optional[float]
    azm: Optional[int]


@dataclass(frozen=True)
class DailyVitals:
    day: date
    resting_hr: Optional[int] = None
    hrv_rmssd: Optional[float] = None           # averageHeartRateVariabilityMilliseconds
    spo2_avg: Optional[float] = None
    respiratory_rate: Optional[float] = None
    skin_temp_delta: Optional[float] = None     # nightly - baseline (°C)


@dataclass(frozen=True)
class HeartRateZone:
    name: str             # LIGHT | MODERATE | VIGOROUS | PEAK
    min_bpm: int
    max_bpm: int


@dataclass(frozen=True)
class HeartRateZoneDay:
    day: date
    zones: Tuple[HeartRateZone, ...]


class WearableProvider(ABC):
    """Supplies wearable data to the analytics engine. Date ranges are inclusive."""

    name: str = "abstract"

    @abstractmethod
    async def get_heart_rate(self, start: date, end: date) -> List[HeartRateSample]: ...

    @abstractmethod
    async def get_daily_vitals(self, start: date, end: date) -> List[DailyVitals]: ...

    @abstractmethod
    async def get_sleep(self, start: date, end: date) -> List[SleepSession]: ...

    @abstractmethod
    async def get_activities(self, start: date, end: date) -> List[Activity]: ...

    @abstractmethod
    async def get_daily_activity(self, start: date, end: date) -> List[DailyActivity]: ...

    @abstractmethod
    async def get_heart_rate_zones(self, start: date, end: date) -> List[HeartRateZoneDay]: ...
