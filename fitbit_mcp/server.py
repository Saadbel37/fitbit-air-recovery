#!/usr/bin/env python3
"""MCP server for the Google Health API (Fitbit / Pixel Watch data).

Exposes health data (activity, sleep, heart rate, body, SpO2, breathing rate,
HRV, temperature, VO2 max, nutrition, devices) as MCP tools. Requires a
one-time OAuth sign-in via `python authorize.py`.

Design: two generic tools cover every data type:
  - googlehealth_daily_rollup  -> daily-aggregated values over a range (trends)
  - googlehealth_list_data_points -> raw/detailed records (sleep, exercise, ecg…)
plus identity, devices, a one-day summary helper, and a data-type catalog.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mcp.server.fastmcp import FastMCP

try:
    from .client import FitbitAPIError, health_get, health_post
except ImportError:  # pragma: no cover
    from fitbit_mcp.client import FitbitAPIError, health_get, health_post

mcp = FastMCP("googlehealth_mcp")

READ_ONLY = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}

# --- Data type registry ---------------------------------------------------
# kind: "interval" -> filter on <snake>.interval.civil_start_time (ISO date)
#       "sample"   -> filter on <snake>.sample_time.physical_time (RFC-3339 Z)
# sleep is special-cased to filter on interval.civil_end_time.
_SAMPLE_TYPES = {
    "heart-rate", "oxygen-saturation", "blood-glucose", "body-fat", "weight",
    "height", "core-body-temperature", "heart-rate-variability", "altitude",
    "activity-level", "electrocardiogram",
}

# All data types that support the List operation.
_LISTABLE = {
    "active-energy-burned", "active-minutes", "active-zone-minutes", "activity-level",
    "altitude", "blood-glucose", "body-fat", "core-body-temperature",
    "daily-heart-rate-variability", "daily-heart-rate-zones", "daily-oxygen-saturation",
    "daily-respiratory-rate", "daily-resting-heart-rate", "daily-sleep-temperature-derivations",
    "daily-vo2-max", "distance", "electrocardiogram", "exercise", "food",
    "food-measurement-unit", "heart-rate", "heart-rate-variability", "height",
    "hydration-log", "irregular-rhythm-notification", "nutrition-log", "oxygen-saturation",
    "respiratory-rate-sleep-summary", "run-vo2-max", "sedentary-period", "sleep", "steps",
    "swim-lengths-data", "time-in-heart-rate-zone", "vo2-max", "weight",
}

# Data types that support daily aggregation (dailyRollUp).
_ROLLUPABLE = {
    "active-energy-burned", "active-minutes", "active-zone-minutes", "altitude",
    "blood-glucose", "body-fat", "calories-in-heart-rate-zone", "core-body-temperature",
    "distance", "floors", "heart-rate", "hydration-log", "nutrition-log", "run-vo2-max",
    "sedentary-period", "steps", "swim-lengths-data", "time-in-heart-rate-zone",
    "total-calories", "weight",
}

_ALL_SOURCES = "users/me/dataSourceFamilies/all-sources"


def _civil_range(start: date, end: date) -> Dict[str, Any]:
    """Build a CivilTimeInterval body for dailyRollUp (closed-open range)."""
    return {
        "start": {"date": {"year": start.year, "month": start.month, "day": start.day}},
        "end": {"date": {"year": end.year, "month": end.month, "day": end.day}},
    }


class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


# --- date helpers ---------------------------------------------------------

def _resolve_date(value: str) -> date:
    """Turn 'today'/'yesterday'/'YYYY-MM-DD' into a date object."""
    v = value.strip().lower()
    if v == "today":
        return date.today()
    if v == "yesterday":
        return date.today() - timedelta(days=1)
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def _build_time_filter(data_type: str, start: date, end_exclusive: date) -> str:
    """Build an AIP-160 filter string for a date range on this data type.

    Field path varies by data type:
      - daily-* aggregates          -> <snake>.date (civil date)
      - sample (point) measurements -> <snake>.sample_time.physical_time (RFC-3339 Z)
      - sleep                       -> <snake>.interval.civil_end_time
      - other interval types        -> <snake>.interval.civil_start_time
    """
    snake = data_type.replace("-", "_")
    lo, hi = start.isoformat(), end_exclusive.isoformat()
    if data_type.startswith("daily-"):
        field = f"{snake}.date"
        return f'{field} >= "{lo}" AND {field} < "{hi}"'
    if data_type == "sleep":
        field = f"{snake}.interval.civil_end_time"
        return f'{field} >= "{lo}" AND {field} < "{hi}"'
    if data_type in _SAMPLE_TYPES:
        field = f"{snake}.sample_time.physical_time"
        return f'{field} >= "{lo}T00:00:00Z" AND {field} < "{hi}T00:00:00Z"'
    field = f"{snake}.interval.civil_start_time"
    return f'{field} >= "{lo}" AND {field} < "{hi}"'


def _dumps(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def _err(e: FitbitAPIError) -> str:
    return str(e)


# --- input models ---------------------------------------------------------

class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    data_type: str = Field(
        ...,
        description="Data type ID, e.g. 'sleep', 'heart-rate', 'steps', 'exercise', "
        "'oxygen-saturation', 'daily-resting-heart-rate', 'electrocardiogram'. "
        "Call googlehealth_list_data_types for the full catalog.",
    )
    start_date: str = Field(default="yesterday", description="Start date 'YYYY-MM-DD'/'today'/'yesterday'.")
    end_date: str = Field(default="today", description="End date (inclusive) 'YYYY-MM-DD'/'today'/'yesterday'.")
    page_size: int = Field(default=100, description="Max data points to return.", ge=1, le=1000)
    filter: Optional[str] = Field(
        default=None,
        description="Optional raw AIP-160 filter to override the auto date filter "
        "(e.g. 'heart_rate.sample_time.physical_time >= \"2026-09-01T00:00:00Z\"').",
    )

    @field_validator("data_type")
    @classmethod
    def _valid(cls, v: str) -> str:
        if v not in _LISTABLE:
            raise ValueError(f"'{v}' does not support list. Listable types: {sorted(_LISTABLE)}")
        return v


class RollUpInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    data_type: str = Field(
        ...,
        description="Aggregatable data type ID, e.g. 'steps', 'distance', 'heart-rate', "
        "'active-zone-minutes', 'total-calories', 'weight'. See googlehealth_list_data_types.",
    )
    start_date: str = Field(default="today", description="Start date 'YYYY-MM-DD'/'today'/'yesterday'.")
    end_date: str = Field(default="today", description="End date (inclusive) 'YYYY-MM-DD'/'today'/'yesterday'.")
    window_size_days: int = Field(default=1, description="Aggregation window in days (1 = per day).", ge=1, le=365)

    @field_validator("data_type")
    @classmethod
    def _valid(cls, v: str) -> str:
        if v not in _ROLLUPABLE:
            raise ValueError(f"'{v}' does not support dailyRollUp. Aggregatable types: {sorted(_ROLLUPABLE)}")
        return v


class DateInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    date: str = Field(default="today", description="Date 'YYYY-MM-DD'/'today'/'yesterday'.")


# --- tools ----------------------------------------------------------------

@mcp.tool(name="googlehealth_list_data_types", annotations={"title": "List Supported Data Types", **READ_ONLY})
async def googlehealth_list_data_types(params: EmptyInput) -> str:
    """List every supported data type ID and which operations it supports.

    Use this to discover valid `data_type` values for the list/rollup tools.

    Returns:
        str: JSON with 'listable' and 'aggregatable' arrays of data-type IDs.
    """
    return _dumps({
        "listable": sorted(_LISTABLE),
        "aggregatable": sorted(_ROLLUPABLE),
        "hint": "Use googlehealth_daily_rollup for trends/totals, "
                "googlehealth_list_data_points for detailed records like sleep/exercise/ecg.",
    })


@mcp.tool(name="googlehealth_get_identity", annotations={"title": "Get User Identity", **READ_ONLY})
async def googlehealth_get_identity(params: EmptyInput) -> str:
    """Get the user's Google Health ID and legacy Fitbit ID.

    Returns:
        str: JSON with the identity object.
    """
    try:
        return _dumps(await health_get("/users/me/identity"))
    except FitbitAPIError as e:
        return _err(e)


@mcp.tool(name="googlehealth_get_devices", annotations={"title": "Get Paired Devices", **READ_ONLY})
async def googlehealth_get_devices(params: EmptyInput) -> str:
    """List devices paired to the account, with battery level and last sync time.

    Returns:
        str: JSON with a 'pairedDevices' array.
    """
    try:
        return _dumps(await health_get("/users/me/pairedDevices"))
    except FitbitAPIError as e:
        return _err(e)


@mcp.tool(name="googlehealth_list_data_points", annotations={"title": "List Data Points", **READ_ONLY})
async def googlehealth_list_data_points(params: ListInput) -> str:
    """List raw/detailed data points for one data type over a date range.

    Best for detailed records: sleep stages, individual exercises, ECG readings,
    HRV, daily-* summaries, SpO2, respiratory rate. For simple daily totals/trends
    (steps, distance, calories) prefer googlehealth_daily_rollup.

    Args:
        params (ListInput): data_type, start_date, end_date, page_size, optional filter.

    Returns:
        str: JSON with 'dataPoints' array and optional 'nextPageToken'. Data point
        value fields vary per data type (union field). On failure, an 'Error: ...' string.
    """
    try:
        start = _resolve_date(params.start_date)
        end_inclusive = _resolve_date(params.end_date)
    except ValueError as e:
        return f"Error: Invalid date: {e}"
    end_exclusive = end_inclusive + timedelta(days=1)

    query = {"pageSize": params.page_size}
    query["filter"] = params.filter or _build_time_filter(params.data_type, start, end_exclusive)

    try:
        data = await health_get(f"/users/me/dataTypes/{params.data_type}/dataPoints", params=query)
        return _dumps(data)
    except FitbitAPIError as e:
        return _err(e)


@mcp.tool(name="googlehealth_daily_rollup", annotations={"title": "Daily Roll-Up (Aggregate)", **READ_ONLY})
async def googlehealth_daily_rollup(params: RollUpInput) -> str:
    """Get daily-aggregated values for one data type over a range (trends, totals).

    Ideal for questions like "steps per day last week" or "average resting heart
    rate this month". Aggregates in windows of `window_size_days` days.

    Args:
        params (RollUpInput): data_type, start_date, end_date, window_size_days.

    Returns:
        str: JSON with a 'rollupDataPoints' array; each has civilStartTime,
        civilEndTime, and a per-type value object (e.g. steps: {count_sum}).
        On failure, an 'Error: ...' string.
    """
    try:
        start = _resolve_date(params.start_date)
        end = _resolve_date(params.end_date)
    except ValueError as e:
        return f"Error: Invalid date: {e}"

    # Range is closed-open [start, end); add a day so end_date is included.
    body = {
        "range": _civil_range(start, end + timedelta(days=1)),
        "windowSizeDays": params.window_size_days,
        "dataSourceFamily": _ALL_SOURCES,
    }
    try:
        data = await health_post(
            f"/users/me/dataTypes/{params.data_type}/dataPoints:dailyRollUp", json_body=body
        )
        return _dumps(data)
    except FitbitAPIError as e:
        return _err(e)


@mcp.tool(name="googlehealth_daily_summary", annotations={"title": "One-Day Health Summary", **READ_ONLY})
async def googlehealth_daily_summary(params: DateInput) -> str:
    """Get a combined one-day snapshot: steps, resting HR, and sleep.

    A convenience tool that gathers the most common daily metrics in one call.

    Args:
        params (DateInput): the date to summarize.

    Returns:
        str: JSON with 'steps', 'resting_heart_rate', and 'sleep' sections
        (each may contain an 'Error: ...' string if that metric is unavailable).
    """
    try:
        day = _resolve_date(params.date)
    except ValueError as e:
        return f"Error: Invalid date: {e}"
    next_day = day + timedelta(days=1)

    result: Dict[str, Any] = {"date": day.isoformat()}

    # Steps (aggregate)
    try:
        steps = await health_post(
            "/users/me/dataTypes/steps/dataPoints:dailyRollUp",
            json_body={
                "range": _civil_range(day, next_day),
                "windowSizeDays": 1,
                "dataSourceFamily": _ALL_SOURCES,
            },
        )
        result["steps"] = steps.get("rollupDataPoints", steps)
    except FitbitAPIError as e:
        result["steps"] = _err(e)

    # Resting heart rate (daily list)
    try:
        rhr = await health_get(
            "/users/me/dataTypes/daily-resting-heart-rate/dataPoints",
            params={
                "pageSize": 5,
                "filter": _build_time_filter("daily-resting-heart-rate", day, next_day),
            },
        )
        result["resting_heart_rate"] = rhr.get("dataPoints", rhr)
    except FitbitAPIError as e:
        result["resting_heart_rate"] = _err(e)

    # Sleep (list, filtered on end time)
    try:
        sleep = await health_get(
            "/users/me/dataTypes/sleep/dataPoints",
            params={"pageSize": 10, "filter": _build_time_filter("sleep", day, next_day)},
        )
        result["sleep"] = sleep.get("dataPoints", sleep)
    except FitbitAPIError as e:
        result["sleep"] = _err(e)

    return _dumps(result)


if __name__ == "__main__":
    mcp.run()
