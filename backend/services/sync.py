"""Sync service: provider -> normalize -> dedupe -> store raw -> score -> state.

Idempotent: every upsert is keyed on natural keys (day, timestamp, external
id) — running a sync twice imports nothing twice.

Error taxonomy (CONTEXT.md): a Sync Failure (API unreachable, transient) and
an Auth Failure (invalid/expired credentials) are modeled separately — only
an Auth Failure may trigger the reconnect flow in the UI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from fitbit_mcp.auth import FitbitAuthError
from fitbit_mcp.client import FitbitAPIError

from backend.config import get_config
from backend.database import DataMode, get_session
from backend.models import (
    ActivityRow,
    DailyMetric,
    HeartRateSampleRow,
    HrZoneDayRow,
    SleepSessionRow,
    SyncState,
)
from backend.services import scoring
from backend.services.analytics.sleep import analyze_session
from backend.services.analytics.strain import calculate_activity_strain, estimate_hr_max
from backend.services.wearable.base import WearableProvider
from backend.services.wearable.demo import DemoProvider
from backend.services.wearable.googlehealth import GoogleHealthProvider


@dataclass
class SyncReport:
    status: str               # ok | sync_error | auth_error
    records_imported: int = 0
    days_scored: int = 0
    error: Optional[str] = None


def _provider(mode: DataMode) -> WearableProvider:
    return DemoProvider() if mode == DataMode.DEMO else GoogleHealthProvider()


def _naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


async def _import_window(
    session: Session, provider: WearableProvider, start: date, end: date
) -> tuple[int, list[str]]:
    """Import all endpoints; a failing endpoint is recorded, not fatal (spec §25).

    Auth failures still abort — they are raised by the token layer before any
    endpoint distinction matters.
    """
    imported = 0
    partial_errors: list[str] = []

    # --- daily vitals + daily activity -> daily_metrics -------------------
    try:
        vitals = {v.day: v for v in await provider.get_daily_vitals(start, end)}
    except FitbitAPIError as e:
        vitals = {}
        partial_errors.append(f"daily_vitals: {e}")
    try:
        activity = {a.day: a for a in await provider.get_daily_activity(start, end)}
    except FitbitAPIError as e:
        activity = {}
        partial_errors.append(f"daily_activity: {e}")
    for day in sorted(set(vitals) | set(activity)):
        v, a = vitals.get(day), activity.get(day)
        row = session.get(DailyMetric, day) or DailyMetric(day=day)
        if v:
            row.resting_hr = v.resting_hr
            row.hrv_rmssd = v.hrv_rmssd
            row.spo2_avg = v.spo2_avg
            row.respiratory_rate = v.respiratory_rate
            row.skin_temp_delta = v.skin_temp_delta
        if a:
            row.steps = a.steps
            row.distance_km = a.distance_km
            row.active_calories = a.active_calories
            row.azm = a.azm
        session.merge(row)
        imported += 1

    # --- heart-rate samples ------------------------------------------------
    existing_ts = {
        r
        for r in session.execute(
            select(HeartRateSampleRow.ts).where(
                HeartRateSampleRow.ts >= datetime.combine(start, datetime.min.time()) - timedelta(days=1)
            )
        ).scalars()
    }
    try:
        hr_samples = await provider.get_heart_rate(start, end)
    except FitbitAPIError as e:
        hr_samples = []
        partial_errors.append(f"heart_rate: {e}")
    for s in hr_samples:
        ts = _naive_utc(s.ts)
        if ts not in existing_ts:
            session.add(HeartRateSampleRow(ts=ts, bpm=s.bpm, source=provider.name))
            existing_ts.add(ts)
            imported += 1
    session.flush()

    # --- sleep --------------------------------------------------------------
    try:
        sleep_sessions = await provider.get_sleep(start, end)
    except FitbitAPIError as e:
        sleep_sessions = []
        partial_errors.append(f"sleep: {e}")
    for sl in sleep_sessions:
        night = analyze_session(sl)
        end_local = sl.end.astimezone(timezone(timedelta(seconds=sl.utc_offset_seconds)))
        row = SleepSessionRow(
            start_time=_naive_utc(sl.start),
            end_time=_naive_utc(sl.end),
            utc_offset_seconds=sl.utc_offset_seconds,
            day=end_local.date(),
            time_in_bed_minutes=night.time_in_bed_minutes,
            sleep_minutes=night.sleep_minutes,
            awake_minutes=night.awake_minutes,
            light_minutes=night.light_minutes,
            deep_minutes=night.deep_minutes,
            rem_minutes=night.rem_minutes,
            awakenings=night.awakenings,
            sleep_efficiency=night.efficiency,
            stages_json=json.dumps([
                {"stage": st.stage, "start": st.start.isoformat(), "end": st.end.isoformat()}
                for st in sl.stages
            ]),
        )
        dup = session.execute(
            select(SleepSessionRow).where(
                SleepSessionRow.start_time == row.start_time,
                SleepSessionRow.end_time == row.end_time,
            )
        ).scalar_one_or_none()
        if dup:
            row.id = dup.id
        session.merge(row)
        imported += 1

    # --- zones (display-only) ----------------------------------------------
    try:
        zone_days = await provider.get_heart_rate_zones(start, end)
    except FitbitAPIError as e:
        zone_days = []
        partial_errors.append(f"heart_rate_zones: {e}")
    for z in zone_days:
        session.merge(HrZoneDayRow(
            day=z.day,
            zones_json=json.dumps([
                {"name": x.name, "min_bpm": x.min_bpm, "max_bpm": x.max_bpm} for x in z.zones
            ]),
        ))
        imported += 1

    # --- activities (max_hr + strain derived from HR samples) ---------------
    cfg = get_config()
    all_bpm = [s.bpm for s in hr_samples]
    state = session.get(SyncState, 1)
    hr_max = estimate_hr_max(
        all_bpm, history_days=(end - start).days + 1,
        birth_year=state.birth_year if state else None, day=end, cfg=cfg,
    )
    try:
        acts = await provider.get_activities(start, end)
    except FitbitAPIError as e:
        acts = []
        partial_errors.append(f"activities: {e}")
    for a in acts:
        in_window = [s for s in hr_samples if a.start <= s.ts <= a.end]
        # resample the window to per-minute means (ADR 0001) — raw may be 3 s samples
        sums: dict[int, tuple[float, int]] = {}
        for s in in_window:
            k = int(s.ts.timestamp() // 60)
            t, n = sums.get(k, (0.0, 0))
            sums[k] = (t + s.bpm, n + 1)
        window = {k: t / n for k, (t, n) in sums.items()}
        day_metric = session.get(DailyMetric, a.start.astimezone(timezone.utc).date())
        rhr = float(day_metric.resting_hr) if (day_metric and day_metric.resting_hr) else None
        session.merge(ActivityRow(
            external_id=a.external_id,
            activity_type=a.activity_type,
            start_time=_naive_utc(a.start),
            end_time=_naive_utc(a.end),
            duration_minutes=round((a.end - a.start).total_seconds() / 60, 1),
            avg_hr=a.avg_hr,
            max_hr=max(s.bpm for s in in_window) if in_window else None,  # derived — API has no max HR
            calories=a.calories,
            azm=a.azm,
            strain=calculate_activity_strain(window, rhr, hr_max, cfg) if rhr else None,
        ))
        imported += 1

    session.commit()
    return imported, partial_errors


async def run_sync(mode: DataMode, days: int = 30) -> SyncReport:
    """Full sync for `mode`. Demo always regenerates 60 deterministic days."""
    if mode == DataMode.DEMO:
        days = 60
    session = get_session(mode)
    try:
        state = session.get(SyncState, 1)
        if state is None:
            state = SyncState(id=1)
            session.add(state)
            session.commit()

        end = date.today()
        if mode == DataMode.REAL and state.last_sync:
            # incremental with a 2-day overlap buffer
            since = state.last_sync.date() - timedelta(days=2)
            start = max(since, end - timedelta(days=days - 1))
        else:
            start = end - timedelta(days=days - 1)

        provider = _provider(mode)
        imported, partial_errors = await _import_window(session, provider, start, end)
        scored = scoring.compute_range(session, start, end)

        if partial_errors and imported == 0:
            _mark_error(session, "sync_error", "; ".join(partial_errors)[:800])
            return SyncReport(status="sync_error", error="; ".join(partial_errors)[:800])

        state.last_sync = datetime.now(timezone.utc).replace(tzinfo=None)
        state.status = "ok"
        state.records_imported = imported
        state.error = ("Teilweise: " + "; ".join(partial_errors)[:700]) if partial_errors else None
        session.commit()
        return SyncReport(
            status="ok", records_imported=imported, days_scored=scored,
            error=state.error,
        )

    except FitbitAuthError as e:                      # Auth Failure -> reconnect flow
        _mark_error(session, "auth_error", str(e))
        return SyncReport(status="auth_error", error=str(e))
    except FitbitAPIError as e:                       # transient Sync Failure
        msg = str(e)
        status = "auth_error" if "Unauthorized" in msg else "sync_error"
        _mark_error(session, status, msg)
        return SyncReport(status=status, error=msg)
    except Exception as e:  # noqa: BLE001 — a sync must never crash the app
        _mark_error(session, "sync_error", f"{type(e).__name__}: {e}")
        return SyncReport(status="sync_error", error=f"{type(e).__name__}: {e}")
    finally:
        session.close()


def _mark_error(session: Session, status: str, message: str) -> None:
    try:
        session.rollback()
        state = session.get(SyncState, 1) or SyncState(id=1)
        state.status = status
        state.error = message
        session.merge(state)
        session.commit()
    except Exception:  # noqa: BLE001
        pass
