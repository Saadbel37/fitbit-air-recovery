"""Signals API — FastAPI app (localhost-only personal tool).

Routes follow the agreed API design (spec §27). Every data route takes
?mode=real|demo and reads from that mode's own database file. Partial data
never breaks a response: missing pieces are null with explicit confidence.
Run:  python -m backend.api.main   (binds 127.0.0.1:8000)
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select

from backend.config import get_config
from backend.database import DataMode, get_session
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
from backend.services.scoring import _local_offset_seconds
from backend.services.sync import run_sync

app = FastAPI(title="Signals API", version=get_config().algorithm_version)

app.add_middleware(  # vite dev server during development
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- authentication -------------------------------------------------------
# HTTP Basic gate, active whenever SIGNALS_PASSWORD is set (required for any
# public/hosted deployment — the app holds personal health data). Left unset
# locally so localhost stays open. Serve only over HTTPS in the cloud.
import base64
import secrets as _secrets

from starlette.requests import Request as _Request
from starlette.responses import Response as _Response

_AUTH_USER = os.environ.get("SIGNALS_USER", "signals").strip()
_AUTH_PASSWORD = os.environ.get("SIGNALS_PASSWORD", "").strip()


@app.middleware("http")
async def _basic_auth(request: _Request, call_next):
    if not _AUTH_PASSWORD:
        return await call_next(request)  # open (local dev)
    header = request.headers.get("Authorization", "")
    ok = False
    if header.startswith("Basic "):
        try:
            user, _, pw = base64.b64decode(header[6:]).decode("utf-8").partition(":")
            ok = _secrets.compare_digest(user, _AUTH_USER) and _secrets.compare_digest(pw, _AUTH_PASSWORD)
        except Exception:  # noqa: BLE001 — malformed header ⇒ unauthorized
            ok = False
    if not ok:
        return _Response(
            "Anmeldung erforderlich",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="Signals"'},
        )
    return await call_next(request)


def _mode(mode: str) -> DataMode:
    try:
        return DataMode(mode)
    except ValueError:
        raise HTTPException(422, f"mode must be 'real' or 'demo', got '{mode}'")


def _resolve_day(d: str) -> date:
    if d == "today":
        return date.today()
    if d == "yesterday":
        return date.today() - timedelta(days=1)
    try:
        return date.fromisoformat(d)
    except ValueError:
        raise HTTPException(422, f"invalid date '{d}' (use YYYY-MM-DD, 'today' or 'yesterday')")


def _score_row(session, day: date) -> Optional[DailyScoreRow]:
    return session.get(DailyScoreRow, day)


def _latest_day_with(session, column) -> Optional[date]:
    """Most recent day whose given score column is non-null."""
    return session.execute(
        select(func.max(DailyScoreRow.day)).where(column.isnot(None))
    ).scalar()


def _resolve_or_latest(session, day: str, column) -> date:
    """Resolve 'latest' to the most recent day carrying that score; else parse."""
    if day == "latest":
        d = _latest_day_with(session, column)
        if d is None:
            raise HTTPException(404, "Noch keine Scores vorhanden.")
        return d
    return _resolve_day(day)


def _js(raw: Optional[str]) -> Any:
    return json.loads(raw) if raw else None


# ------------------------------- status ---------------------------------

@app.get("/api/status")
def status() -> Dict[str, Any]:
    out: Dict[str, Any] = {"algorithm_version": get_config().algorithm_version, "modes": {}}
    for m in DataMode:
        s = get_session(m)
        try:
            days = s.execute(select(func.count(DailyScoreRow.day))).scalar() or 0
            first = s.execute(select(func.min(DailyScoreRow.day))).scalar()
            last = s.execute(select(func.max(DailyScoreRow.day))).scalar()
            state = s.get(SyncState, 1)
            out["modes"][m.value] = {
                "days_scored": days,
                "first_day": str(first) if first else None,
                "last_day": str(last) if last else None,
                "last_sync": state.last_sync.isoformat() + "Z" if state and state.last_sync else None,
                "sync_status": state.status if state else "never",
                "sync_error": state.error if state else None,
            }
        finally:
            s.close()
    return out


@app.post("/api/sync")
async def sync(mode: str = Query("real")) -> Dict[str, Any]:
    report = await run_sync(_mode(mode))
    return vars(report)


# ------------------------------ dashboard --------------------------------

@app.get("/api/dashboard/{day}")
def dashboard(day: str, mode: str = Query("real")) -> Dict[str, Any]:
    d = _resolve_day(day)
    session = get_session(_mode(mode))
    try:
        row = _score_row(session, d)
        prev = _score_row(session, d - timedelta(days=1))
        m = session.get(DailyMetric, d)
        bl = session.get(BaselineRow, d)
        sleep_detail = _js(row.sleep_detail_json) if row else None
        return {
            "date": d.isoformat(),
            "recovery": {
                "score": row.recovery_score if row else None,
                "status": row.recovery_status if row else None,
                "confidence": row.recovery_confidence if row else None,
                "vs_yesterday": (
                    row.recovery_score - prev.recovery_score
                    if row and prev and row.recovery_score is not None and prev.recovery_score is not None
                    else None
                ),
            },
            "strain": {
                "score": row.strain_score if row else None,
                "status": row.strain_status if row else None,
                "confidence": row.strain_confidence if row else None,
            },
            "sleep": {
                "score": row.sleep_score if row else None,
                "status": row.sleep_status if row else None,
                "confidence": row.sleep_confidence if row else None,
                "duration_minutes": (sleep_detail or {}).get("night", {}).get("sleep_minutes")
                if sleep_detail and sleep_detail.get("night") else None,
                "need_minutes": (sleep_detail or {}).get("need_minutes"),
                "performance": (sleep_detail or {}).get("performance"),
            },
            "health": {
                "hrv": m.hrv_rmssd if m else None,
                "hrv_baseline": bl.hrv_baseline if bl else None,
                "resting_hr": m.resting_hr if m else None,
                "resting_hr_baseline": bl.resting_hr_baseline if bl else None,
                "spo2": m.spo2_avg if m else None,
                "respiratory_rate": m.respiratory_rate if m else None,
                "respiratory_rate_baseline": bl.respiratory_rate_baseline if bl else None,
                "temperature_delta": m.skin_temp_delta if m else None,
                "steps": m.steps if m else None,
                "azm": m.azm if m else None,
            },
            "insights": _js(row.insights_json) if row else [],
        }
    finally:
        session.close()


# --------------------------- score histories ------------------------------

def _history(session, days: int, fields: Dict[str, Any]) -> List[Dict[str, Any]]:
    since = date.today() - timedelta(days=days - 1)
    rows = session.execute(
        select(DailyScoreRow).where(DailyScoreRow.day >= since).order_by(DailyScoreRow.day)
    ).scalars()
    return [{"date": r.day.isoformat(), **{k: getattr(r, v) for k, v in fields.items()}} for r in rows]


@app.get("/api/recovery")
def recovery_history(days: int = Query(30, ge=1, le=365), mode: str = Query("real")):
    session = get_session(_mode(mode))
    try:
        return _history(session, days, {"score": "recovery_score", "status": "recovery_status", "confidence": "recovery_confidence"})
    finally:
        session.close()


@app.get("/api/recovery/{day}")
def recovery_detail(day: str, mode: str = Query("real")):
    session = get_session(_mode(mode))
    try:
        d = _resolve_or_latest(session, day, DailyScoreRow.recovery_score)
        row = _score_row(session, d)
        if not row:
            raise HTTPException(404, f"No scores for {d.isoformat()}.")
        bl = session.get(BaselineRow, d)
        m = session.get(DailyMetric, d)
        return {
            "date": d.isoformat(),
            "score": row.recovery_score,
            "status": row.recovery_status,
            "confidence": row.recovery_confidence,
            "detail": _js(row.recovery_detail_json),
            "inputs": {
                "hrv": m.hrv_rmssd if m else None,
                "resting_hr": m.resting_hr if m else None,
                "spo2": m.spo2_avg if m else None,
                "respiratory_rate": m.respiratory_rate if m else None,
                "skin_temp_delta": m.skin_temp_delta if m else None,
                "sleep_score": row.sleep_score,
            },
            "baselines": {
                "hrv": bl.hrv_baseline if bl else None,
                "resting_hr": bl.resting_hr_baseline if bl else None,
                "respiratory_rate": bl.respiratory_rate_baseline if bl else None,
                "coverage": bl.coverage if bl else None,
            },
        }
    finally:
        session.close()


@app.get("/api/strain")
def strain_history(days: int = Query(30, ge=1, le=365), mode: str = Query("real")):
    session = get_session(_mode(mode))
    try:
        return _history(session, days, {"score": "strain_score", "status": "strain_status", "confidence": "strain_confidence"})
    finally:
        session.close()


@app.get("/api/strain/{day}")
def strain_detail(day: str, mode: str = Query("real")):
    session = get_session(_mode(mode))
    try:
        d = _resolve_or_latest(session, day, DailyScoreRow.strain_score)
        row = _score_row(session, d)
        if not row:
            raise HTTPException(404, f"No scores for {d.isoformat()}.")
        acts = session.execute(
            select(ActivityRow).where(
                ActivityRow.start_time >= datetime.combine(d, time.min) - timedelta(hours=12),
                ActivityRow.start_time < datetime.combine(d, time.max),
            ).order_by(ActivityRow.start_time)
        ).scalars()
        zone_row = session.get(HrZoneDayRow, d)
        zones = _js(zone_row.zones_json) if zone_row else []
        return {
            "date": d.isoformat(),
            "score": row.strain_score,
            "status": row.strain_status,
            "confidence": row.strain_confidence,
            "detail": _js(row.strain_detail_json),
            "hr_max": {"value": row.hr_max_value, "source": row.hr_max_source},
            "zones": zones,  # display-only boundaries (ADR 0001)
            "activities": [
                {
                    "type": a.activity_type,
                    "start": a.start_time.isoformat() + "Z",
                    "end": a.end_time.isoformat() + "Z",
                    "duration_minutes": a.duration_minutes,
                    "avg_hr": a.avg_hr,
                    "max_hr": a.max_hr,
                    "calories": a.calories,
                    "azm": a.azm,
                    "strain": a.strain,
                }
                for a in acts
            ],
        }
    finally:
        session.close()


@app.get("/api/sleep")
def sleep_history(days: int = Query(30, ge=1, le=365), mode: str = Query("real")):
    session = get_session(_mode(mode))
    try:
        return _history(session, days, {"score": "sleep_score", "status": "sleep_status", "confidence": "sleep_confidence"})
    finally:
        session.close()


@app.get("/api/sleep/{day}")
def sleep_detail(day: str, mode: str = Query("real")):
    session = get_session(_mode(mode))
    try:
        d = _resolve_or_latest(session, day, DailyScoreRow.sleep_score)
        row = _score_row(session, d)
        sess = session.execute(
            select(SleepSessionRow).where(SleepSessionRow.day == d).order_by(SleepSessionRow.start_time)
        ).scalars().all()
        if not row and not sess:
            raise HTTPException(404, f"No sleep data for {d.isoformat()}.")
        # bedtime/wake scatter for the last 14 nights (consistency panel)
        recent = session.execute(
            select(SleepSessionRow).where(SleepSessionRow.day > d - timedelta(days=14), SleepSessionRow.day <= d)
            .order_by(SleepSessionRow.day)
        ).scalars()
        consistency = [
            {
                "date": r.day.isoformat(),
                "bed_local": (r.start_time.replace(tzinfo=timezone.utc)
                              .astimezone(timezone(timedelta(seconds=r.utc_offset_seconds or 0))).strftime("%H:%M")),
                "wake_local": (r.end_time.replace(tzinfo=timezone.utc)
                               .astimezone(timezone(timedelta(seconds=r.utc_offset_seconds or 0))).strftime("%H:%M")),
            }
            for r in recent
        ]
        return {
            "date": d.isoformat(),
            "score": row.sleep_score if row else None,
            "status": row.sleep_status if row else None,
            "confidence": row.sleep_confidence if row else None,
            "detail": _js(row.sleep_detail_json) if row else None,
            "sessions": [
                {
                    "start": s.start_time.isoformat() + "Z",
                    "end": s.end_time.isoformat() + "Z",
                    "utc_offset_seconds": s.utc_offset_seconds,
                    "time_in_bed_minutes": s.time_in_bed_minutes,
                    "sleep_minutes": s.sleep_minutes,
                    "efficiency": s.sleep_efficiency,
                    "awakenings": s.awakenings,
                    "stages": _js(s.stages_json) or [],
                }
                for s in sess
            ],
            "consistency": consistency,
        }
    finally:
        session.close()


# ------------------------------- health -----------------------------------

@app.get("/api/health")
def health(days: int = Query(30, ge=1, le=365), mode: str = Query("real")):
    session = get_session(_mode(mode))
    try:
        since = date.today() - timedelta(days=days - 1)
        metrics = session.execute(
            select(DailyMetric).where(DailyMetric.day >= since).order_by(DailyMetric.day)
        ).scalars().all()
        baselines = {
            b.day: b
            for b in session.execute(select(BaselineRow).where(BaselineRow.day >= since)).scalars()
        }
        return [
            {
                "date": m.day.isoformat(),
                "hrv": m.hrv_rmssd,
                "resting_hr": m.resting_hr,
                "spo2": m.spo2_avg,
                "respiratory_rate": m.respiratory_rate,
                "skin_temp_delta": m.skin_temp_delta,
                "steps": m.steps,
                "distance_km": m.distance_km,
                "active_calories": m.active_calories,
                "azm": m.azm,
                "baselines": {
                    "hrv": baselines[m.day].hrv_baseline if m.day in baselines else None,
                    "resting_hr": baselines[m.day].resting_hr_baseline if m.day in baselines else None,
                    "respiratory_rate": baselines[m.day].respiratory_rate_baseline if m.day in baselines else None,
                    "skin_temp": baselines[m.day].temperature_baseline if m.day in baselines else None,
                    "coverage": baselines[m.day].coverage if m.day in baselines else None,
                } if m.day in baselines else None,
            }
            for m in metrics
        ]
    finally:
        session.close()


# ------------------------------- trends -----------------------------------

_TREND_SOURCES = {
    "recovery": ("scores", "recovery_score"),
    "strain": ("scores", "strain_score"),
    "sleep": ("scores", "sleep_score"),
    "hrv": ("metrics", "hrv_rmssd"),
    "resting_hr": ("metrics", "resting_hr"),
    "steps": ("metrics", "steps"),
    "spo2": ("metrics", "spo2_avg"),
}


@app.get("/api/trends")
def trends(
    metrics: str = Query("recovery,hrv"),
    days: int = Query(30, ge=7, le=365),
    mode: str = Query("real"),
):
    wanted = [m.strip() for m in metrics.split(",") if m.strip() in _TREND_SOURCES]
    if not wanted:
        raise HTTPException(422, f"metrics must be some of {sorted(_TREND_SOURCES)}")
    cfg = get_config()
    session = get_session(_mode(mode))
    try:
        since = date.today() - timedelta(days=days - 1)
        score_rows = {r.day: r for r in session.execute(
            select(DailyScoreRow).where(DailyScoreRow.day >= since)).scalars()}
        metric_rows = {r.day: r for r in session.execute(
            select(DailyMetric).where(DailyMetric.day >= since)).scalars()}
        labels = [since + timedelta(days=i) for i in range(days)]

        series: Dict[str, List[Optional[float]]] = {}
        for name in wanted:
            table, attr = _TREND_SOURCES[name]
            src = score_rows if table == "scores" else metric_rows
            series[name] = [
                (getattr(src[d], attr) if d in src and getattr(src[d], attr) is not None else None)
                for d in labels
            ]

        # pairwise correlations — n >= gate or NO coefficient at all (settled Q17)
        gate = cfg.trends.min_days_for_correlation
        correlations = []
        for i, a in enumerate(wanted):
            for b_name in wanted[i + 1:]:
                pairs = [
                    (x, y) for x, y in zip(series[a], series[b_name])
                    if x is not None and y is not None
                ]
                n = len(pairs)
                coverage = round(n / days, 2)
                entry: Dict[str, Any] = {"a": a, "b": b_name, "n": n, "coverage": coverage}
                if n >= gate:
                    xs, ys = zip(*pairs)
                    entry["r"] = round(float(np.corrcoef(xs, ys)[0, 1]), 2)
                else:
                    entry["r"] = None
                    entry["needs_days"] = gate - n
                correlations.append(entry)

        # fixed lag analyses: Strain[t-1] -> Recovery[t]; Sleep[t] -> Recovery[t]
        lag = []
        for name, (sa, sb, shift) in {
            "strain_yesterday_vs_recovery": ("strain", "recovery", 1),
            "sleep_vs_recovery": ("sleep", "recovery", 0),
        }.items():
            va = [
                (getattr(score_rows[d - timedelta(days=shift)], _TREND_SOURCES[sa][1])
                 if (d - timedelta(days=shift)) in score_rows else None)
                for d in labels
            ]
            vb = [
                (getattr(score_rows[d], _TREND_SOURCES[sb][1]) if d in score_rows else None)
                for d in labels
            ]
            pairs = [(x, y) for x, y in zip(va, vb) if x is not None and y is not None]
            n = len(pairs)
            entry = {"name": name, "n": n, "coverage": round(n / days, 2)}
            if n >= gate:
                xs, ys = zip(*pairs)
                entry["r"] = round(float(np.corrcoef(xs, ys)[0, 1]), 2)
            else:
                entry["r"] = None
                entry["needs_days"] = gate - n
            lag.append(entry)

        return {
            "days": days,
            "labels": [d.isoformat() for d in labels],
            "series": series,
            "correlations": correlations,
            "lag_analyses": lag,
            "correlation_gate_days": gate,
        }
    finally:
        session.close()


# ---------------------------- raw data (explorer) --------------------------

@app.get("/api/heart-rate")
def heart_rate(day: str = Query("today"), mode: str = Query("real")):
    d = _resolve_day(day)
    offset_s = _local_offset_seconds(d)
    tz = timezone(timedelta(seconds=offset_s))
    start_utc = datetime.combine(d, time.min, tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)
    session = get_session(_mode(mode))
    try:
        rows = session.execute(
            select(HeartRateSampleRow)
            .where(HeartRateSampleRow.ts >= start_utc, HeartRateSampleRow.ts < start_utc + timedelta(days=1))
            .order_by(HeartRateSampleRow.ts)
        ).scalars().all()
        # minute means + explicit gap list (Data Explorer requirement)
        sums: Dict[int, tuple] = {}
        for r in rows:
            local = r.ts.replace(tzinfo=timezone.utc).astimezone(tz)
            k = local.hour * 60 + local.minute
            t, n = sums.get(k, (0.0, 0))
            sums[k] = (t + r.bpm, n + 1)
        minutes = [{"minute": k, "bpm": round(t / n, 1)} for k, (t, n) in sorted(sums.items())]
        gaps, prev = [], None
        for k in sorted(sums):
            if prev is not None and k - prev > 5:
                gaps.append({"from_minute": prev + 1, "to_minute": k - 1, "missing_minutes": k - prev - 1})
            prev = k
        return {
            "date": d.isoformat(),
            "utc_offset_seconds": offset_s,
            "sample_count": len(rows),
            "minutes": minutes,
            "gaps": gaps,
            "coverage": round(len(sums) / 1440, 3),
        }
    finally:
        session.close()


@app.get("/api/activities")
def activities(days: int = Query(30, ge=1, le=365), mode: str = Query("real")):
    session = get_session(_mode(mode))
    try:
        since = datetime.combine(date.today() - timedelta(days=days - 1), time.min)
        rows = session.execute(
            select(ActivityRow).where(ActivityRow.start_time >= since).order_by(ActivityRow.start_time.desc())
        ).scalars()
        return [
            {
                "type": a.activity_type,
                "start": a.start_time.isoformat() + "Z",
                "end": a.end_time.isoformat() + "Z",
                "duration_minutes": a.duration_minutes,
                "avg_hr": a.avg_hr,
                "max_hr": a.max_hr,
                "calories": a.calories,
                "azm": a.azm,
                "strain": a.strain,
            }
            for a in rows
        ]
    finally:
        session.close()


# --------------------------- static frontend -------------------------------
# After `npm run build`, FastAPI serves the SPA (single-server deployment).
# Assets are served directly; all non-API paths fall back to index.html so
# client-side routes (/recovery, /sleep, …) work on direct load / refresh.

_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404, "Unknown API route.")
        candidate = _DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")


if __name__ == "__main__":
    import uvicorn

    # Cloud platforms inject $PORT and need 0.0.0.0; default to localhost dev.
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
