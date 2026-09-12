"""SQLAlchemy models (SQLite, single user per database file).

Raw/normalized measurements and derived analytics live in separate tables —
raw data is never overwritten by calculated values:
  raw:      heart_rate_samples, sleep_sessions, activities, daily_metrics,
            hr_zone_days
  derived:  baseline_metrics, daily_scores
  state:    sync_state
"""

from __future__ import annotations

from datetime import date, datetime, timezone as _tz
_UTC = _tz.utc
from typing import Optional

from sqlalchemy import Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# --------------------------- raw / normalized ---------------------------

class DailyMetric(Base):
    """One row per day of normalized daily measurements (features, not scores)."""

    __tablename__ = "daily_metrics"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    resting_hr: Mapped[Optional[int]] = mapped_column(Integer)
    hrv_rmssd: Mapped[Optional[float]] = mapped_column(Float)
    spo2_avg: Mapped[Optional[float]] = mapped_column(Float)
    respiratory_rate: Mapped[Optional[float]] = mapped_column(Float)
    skin_temp_delta: Mapped[Optional[float]] = mapped_column(Float)
    steps: Mapped[Optional[int]] = mapped_column(Integer)
    distance_km: Mapped[Optional[float]] = mapped_column(Float)
    active_calories: Mapped[Optional[float]] = mapped_column(Float)
    azm: Mapped[Optional[int]] = mapped_column(Integer)


class HeartRateSampleRow(Base):
    __tablename__ = "heart_rate_samples"

    ts: Mapped[datetime] = mapped_column(DateTime, primary_key=True)  # UTC
    bpm: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="wearable")


class SleepSessionRow(Base):
    __tablename__ = "sleep_sessions"
    __table_args__ = (UniqueConstraint("start_time", "end_time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # UTC
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    utc_offset_seconds: Mapped[int] = mapped_column(Integer, default=0)
    day: Mapped[date] = mapped_column(Date, index=True)  # civil date the night ends on

    time_in_bed_minutes: Mapped[Optional[float]] = mapped_column(Float)
    sleep_minutes: Mapped[Optional[float]] = mapped_column(Float)
    awake_minutes: Mapped[Optional[float]] = mapped_column(Float)
    light_minutes: Mapped[Optional[float]] = mapped_column(Float)
    deep_minutes: Mapped[Optional[float]] = mapped_column(Float)
    rem_minutes: Mapped[Optional[float]] = mapped_column(Float)
    awakenings: Mapped[Optional[int]] = mapped_column(Integer)
    sleep_efficiency: Mapped[Optional[float]] = mapped_column(Float)

    stages_json: Mapped[Optional[str]] = mapped_column(Text)  # raw stage segments for the timeline


class ActivityRow(Base):
    __tablename__ = "activities"

    external_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    activity_type: Mapped[str] = mapped_column(String(64))
    start_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime)
    duration_minutes: Mapped[float] = mapped_column(Float)
    avg_hr: Mapped[Optional[int]] = mapped_column(Integer)
    max_hr: Mapped[Optional[int]] = mapped_column(Integer)  # derived from HR samples (API has none)
    calories: Mapped[Optional[int]] = mapped_column(Integer)
    azm: Mapped[Optional[int]] = mapped_column(Integer)
    strain: Mapped[Optional[float]] = mapped_column(Float)  # derived


class HrZoneDayRow(Base):
    __tablename__ = "hr_zone_days"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    zones_json: Mapped[str] = mapped_column(Text)  # [{name,min,max}] — display-only (ADR 0001)


# ------------------------------ derived ---------------------------------

class BaselineRow(Base):
    __tablename__ = "baseline_metrics"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    hrv_baseline: Mapped[Optional[float]] = mapped_column(Float)
    resting_hr_baseline: Mapped[Optional[float]] = mapped_column(Float)
    respiratory_rate_baseline: Mapped[Optional[float]] = mapped_column(Float)
    temperature_baseline: Mapped[Optional[float]] = mapped_column(Float)
    sleep_duration_baseline: Mapped[Optional[float]] = mapped_column(Float)
    coverage: Mapped[Optional[float]] = mapped_column(Float)  # window fill 0..1


class DailyScoreRow(Base):
    __tablename__ = "daily_scores"

    day: Mapped[date] = mapped_column(Date, primary_key=True)

    recovery_score: Mapped[Optional[int]] = mapped_column(Integer)
    recovery_status: Mapped[Optional[str]] = mapped_column(String(16))
    recovery_confidence: Mapped[Optional[float]] = mapped_column(Float)
    recovery_detail_json: Mapped[Optional[str]] = mapped_column(Text)  # contributors, factors

    strain_score: Mapped[Optional[float]] = mapped_column(Float)
    strain_status: Mapped[Optional[str]] = mapped_column(String(16))
    strain_confidence: Mapped[Optional[float]] = mapped_column(Float)
    strain_detail_json: Mapped[Optional[str]] = mapped_column(Text)    # load, minutes by zone, coverage
    hr_max_value: Mapped[Optional[int]] = mapped_column(Integer)       # ADR 0001: per-day provenance
    hr_max_source: Mapped[Optional[str]] = mapped_column(String(24))   # observed_p999|age_formula|blended

    sleep_score: Mapped[Optional[int]] = mapped_column(Integer)
    sleep_status: Mapped[Optional[str]] = mapped_column(String(16))
    sleep_confidence: Mapped[Optional[float]] = mapped_column(Float)
    sleep_detail_json: Mapped[Optional[str]] = mapped_column(Text)     # need, performance, debt, parts

    insights_json: Mapped[Optional[str]] = mapped_column(Text)
    algorithm_version: Mapped[str] = mapped_column(String(16), default="0")
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(_UTC).replace(tzinfo=None))


# ------------------------------- state ----------------------------------

class SyncState(Base):
    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_sync: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="never")  # ok|sync_error|auth_error|never
    records_imported: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text)

    # Profile facts needed by analytics (age for the HRmax fallback)
    birth_year: Mapped[Optional[int]] = mapped_column(Integer)
