"""GoogleHealthProvider — real wearable data via the Google Health API.

Built on the existing, verified integration in fitbit_mcp/ (OAuth incl. token
refresh, request client). All endpoint paths, filter syntax and field names
were verified against the live API; see also fitbit_mcp/server.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import asyncio

from fitbit_mcp.client import FitbitAPIError
from fitbit_mcp.client import health_get as _raw_get
from fitbit_mcp.client import health_post as _raw_post

_TRANSIENT_MARKERS = ("503", "502", "504", "UNAVAILABLE", "timed out", "Network error")
_RETRY_DELAYS = (2.0, 5.0, 12.0)


def _is_transient(err: FitbitAPIError) -> bool:
    msg = str(err)
    return any(m in msg for m in _TRANSIENT_MARKERS)


async def health_get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """health_get with retry/backoff on transient failures (503 etc.).

    Kept here rather than in fitbit_mcp/ so the MCP server stays untouched.
    """
    for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
        try:
            return await _raw_get(endpoint, params)
        except FitbitAPIError as e:
            if delay is None or not _is_transient(e):
                raise
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")


async def health_post(endpoint: str, json_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """health_post with the same transient-retry policy as health_get."""
    for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
        try:
            return await _raw_post(endpoint, json_body)
        except FitbitAPIError as e:
            if delay is None or not _is_transient(e):
                raise
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")

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

_ALL_SOURCES = "users/me/dataSourceFamilies/all-sources"


def _civil(d: date) -> Dict[str, int]:
    return {"year": d.year, "month": d.month, "day": d.day}


def _iso_z(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))


def _date_of(d: Dict[str, int]) -> date:
    return date(d["year"], d["month"], d["day"])


def _daily_filter(snake: str, start: date, end: date) -> str:
    end_excl = end + timedelta(days=1)
    return f'{snake}.date >= "{start.isoformat()}" AND {snake}.date < "{end_excl.isoformat()}"'


async def _list_all(data_type: str, filter_str: str, page_size: int = 1000) -> List[Dict[str, Any]]:
    """List data points, following pageToken until exhausted."""
    out: List[Dict[str, Any]] = []
    params: Dict[str, Any] = {"pageSize": page_size, "filter": filter_str}
    while True:
        data = await health_get(f"/users/me/dataTypes/{data_type}/dataPoints", params=params)
        out.extend(data.get("dataPoints", []))
        token = data.get("nextPageToken")
        if not token:
            return out
        params = {"pageSize": page_size, "filter": filter_str, "pageToken": token}


class GoogleHealthProvider(WearableProvider):
    name = "googlehealth"

    async def get_heart_rate(self, start: date, end: date) -> List[HeartRateSample]:
        end_excl = end + timedelta(days=1)
        f = (
            f'heart_rate.sample_time.physical_time >= "{start.isoformat()}T00:00:00Z" '
            f'AND heart_rate.sample_time.physical_time < "{end_excl.isoformat()}T00:00:00Z"'
        )
        points = await _list_all("heart-rate", f, page_size=10000)
        samples = []
        for p in points:
            hr = p.get("heartRate", {})
            ts = hr.get("sampleTime", {}).get("physicalTime")
            bpm = hr.get("beatsPerMinute")
            if ts and bpm is not None:
                samples.append(HeartRateSample(ts=_iso_z(ts), bpm=int(bpm)))
        samples.sort(key=lambda s: s.ts)
        return samples

    async def get_daily_vitals(self, start: date, end: date) -> List[DailyVitals]:
        by_day: Dict[date, Dict[str, Any]] = {}

        def _set(day: date, key: str, value: Any) -> None:
            by_day.setdefault(day, {})[key] = value

        for p in await _list_all("daily-resting-heart-rate", _daily_filter("daily_resting_heart_rate", start, end)):
            r = p.get("dailyRestingHeartRate", {})
            if "date" in r and r.get("beatsPerMinute") is not None:
                _set(_date_of(r["date"]), "resting_hr", int(r["beatsPerMinute"]))

        for p in await _list_all("daily-heart-rate-variability", _daily_filter("daily_heart_rate_variability", start, end)):
            r = p.get("dailyHeartRateVariability", {})
            v = r.get("averageHeartRateVariabilityMilliseconds")
            if "date" in r and v is not None:
                _set(_date_of(r["date"]), "hrv_rmssd", float(v))

        for p in await _list_all("daily-oxygen-saturation", _daily_filter("daily_oxygen_saturation", start, end)):
            r = p.get("dailyOxygenSaturation", {})
            v = r.get("averagePercentage")
            if "date" in r and v is not None:
                _set(_date_of(r["date"]), "spo2_avg", float(v))

        for p in await _list_all("daily-respiratory-rate", _daily_filter("daily_respiratory_rate", start, end)):
            r = p.get("dailyRespiratoryRate", {})
            v = r.get("breathsPerMinute")
            if "date" in r and v is not None:
                _set(_date_of(r["date"]), "respiratory_rate", float(v))

        for p in await _list_all(
            "daily-sleep-temperature-derivations", _daily_filter("daily_sleep_temperature_derivations", start, end)
        ):
            r = p.get("dailySleepTemperatureDerivations", {})
            nightly, base = r.get("nightlyTemperatureCelsius"), r.get("baselineTemperatureCelsius")
            if "date" in r and nightly is not None and base is not None:
                delta = float(nightly) - float(base)
                if delta == delta:  # NaN guard (learned the hard way)
                    _set(_date_of(r["date"]), "skin_temp_delta", round(delta, 2))

        return [DailyVitals(day=d, **vals) for d, vals in sorted(by_day.items())]

    async def get_sleep(self, start: date, end: date) -> List[SleepSession]:
        end_excl = end + timedelta(days=1)
        f = (
            f'sleep.interval.civil_end_time >= "{start.isoformat()}" '
            f'AND sleep.interval.civil_end_time < "{end_excl.isoformat()}"'
        )
        sessions = []
        for p in await _list_all("sleep", f, page_size=25):
            sl = p.get("sleep", {})
            iv = sl.get("interval", {})
            if not (iv.get("startTime") and iv.get("endTime")):
                continue
            stages = tuple(
                SleepStageSegment(stage=s["type"], start=_iso_z(s["startTime"]), end=_iso_z(s["endTime"]))
                for s in sl.get("stages", [])
                if s.get("startTime") and s.get("endTime") and s.get("type")
            )
            offset = int(str(iv.get("endUtcOffset", "0s")).rstrip("s") or 0)
            sessions.append(
                SleepSession(start=_iso_z(iv["startTime"]), end=_iso_z(iv["endTime"]),
                             utc_offset_seconds=offset, stages=stages)
            )
        sessions.sort(key=lambda s: s.start)
        return sessions

    async def get_activities(self, start: date, end: date) -> List[Activity]:
        end_excl = end + timedelta(days=1)
        f = (
            f'exercise.interval.civil_start_time >= "{start.isoformat()}" '
            f'AND exercise.interval.civil_start_time < "{end_excl.isoformat()}"'
        )
        out = []
        for p in await _list_all("exercise", f, page_size=25):
            ex = p.get("exercise", {})
            iv = ex.get("interval", {})
            if not (iv.get("startTime") and iv.get("endTime")):
                continue
            m = ex.get("metricsSummary", {})
            avg_hr = m.get("averageHeartRateBeatsPerMinute")
            cal = m.get("caloriesKcal")
            out.append(
                Activity(
                    external_id=p.get("name", f"{ex.get('exerciseType','?')}-{iv['startTime']}"),
                    activity_type=ex.get("exerciseType", "WORKOUT"),
                    start=_iso_z(iv["startTime"]),
                    end=_iso_z(iv["endTime"]),
                    avg_hr=int(avg_hr) if avg_hr is not None else None,
                    calories=int(cal) if cal is not None else None,
                    azm=int(m.get("activeZoneMinutes", 0) or 0),
                )
            )
        out.sort(key=lambda a: a.start)
        return out

    async def get_daily_activity(self, start: date, end: date) -> List[DailyActivity]:
        async def rollup(data_type: str) -> List[Dict[str, Any]]:
            body = {
                "range": {"start": {"date": _civil(start)}, "end": {"date": _civil(end + timedelta(days=1))}},
                "windowSizeDays": 1,
                "dataSourceFamily": _ALL_SOURCES,
                # NOTE: no pageSize here — it triggers a spurious duration error
            }
            data = await health_post(f"/users/me/dataTypes/{data_type}/dataPoints:dailyRollUp", json_body=body)
            return data.get("rollupDataPoints", [])

        by_day: Dict[date, Dict[str, Any]] = {}
        for p in await rollup("steps"):
            d = _date_of(p["civilStartTime"]["date"])
            by_day.setdefault(d, {})["steps"] = int(p.get("steps", {}).get("countSum", 0))
        for p in await rollup("distance"):
            d = _date_of(p["civilStartTime"]["date"])
            mm = float(p.get("distance", {}).get("millimetersSum", 0))
            by_day.setdefault(d, {})["distance_km"] = round(mm / 1_000_000, 2)
        for p in await rollup("active-energy-burned"):
            d = _date_of(p["civilStartTime"]["date"])
            by_day.setdefault(d, {})["active_calories"] = round(float(p.get("activeEnergyBurned", {}).get("kcalSum", 0)), 1)
        for p in await rollup("active-zone-minutes"):
            d = _date_of(p["civilStartTime"]["date"])
            z = p.get("activeZoneMinutes", {})
            fb = int(z.get("sumInFatBurnHeartZone", 0))
            cardio = int(z.get("sumInCardioHeartZone", 0))
            peak = int(z.get("sumInPeakHeartZone", 0))
            by_day.setdefault(d, {})["azm"] = fb + 2 * (cardio + peak)  # Fitbit AZM weighting

        return [
            DailyActivity(
                day=d,
                steps=vals.get("steps"),
                distance_km=vals.get("distance_km"),
                active_calories=vals.get("active_calories"),
                azm=vals.get("azm"),
            )
            for d, vals in sorted(by_day.items())
        ]

    async def get_heart_rate_zones(self, start: date, end: date) -> List[HeartRateZoneDay]:
        out = []
        for p in await _list_all("daily-heart-rate-zones", _daily_filter("daily_heart_rate_zones", start, end)):
            r = p.get("dailyHeartRateZones", {})
            if "date" not in r:
                continue
            zones = tuple(
                HeartRateZone(
                    name=z["heartRateZoneType"],
                    min_bpm=int(z["minBeatsPerMinute"]),
                    max_bpm=int(z["maxBeatsPerMinute"]),
                )
                for z in r.get("heartRateZones", [])
                if z.get("heartRateZoneType")
            )
            if zones:
                out.append(HeartRateZoneDay(day=_date_of(r["date"]), zones=zones))
        # multiple sources may report zones per day — keep the last per day
        dedup: Dict[date, HeartRateZoneDay] = {z.day: z for z in sorted(out, key=lambda z: z.day)}
        return list(dedup.values())
