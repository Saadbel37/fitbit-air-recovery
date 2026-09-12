"""End-to-end: demo sync -> scored DB -> API responses. Uses the real demo.db
(deterministic demo data is the intended content of that file)."""

import asyncio
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.database import DataMode, get_session
from backend.models import DailyScoreRow, HeartRateSampleRow
from backend.services.sync import run_sync
from sqlalchemy import func, select

client = TestClient(app)


@pytest.fixture(scope="module")
def synced():
    report = asyncio.run(run_sync(DataMode.DEMO))
    assert report.status == "ok", report.error
    return report


def test_sync_imports_and_scores(synced):
    # fresh DB: HR minutes dominate (>80k); warm DB: only daily upserts (~200)
    assert synced.records_imported > 100
    assert synced.days_scored == 60


def test_sync_is_idempotent(synced):
    s = get_session(DataMode.DEMO)
    before = s.execute(select(func.count(HeartRateSampleRow.ts))).scalar()
    s.close()
    second = asyncio.run(run_sync(DataMode.DEMO))
    assert second.status == "ok"
    s = get_session(DataMode.DEMO)
    after = s.execute(select(func.count(HeartRateSampleRow.ts))).scalar()
    s.close()
    assert after == before  # no duplicates on re-run


def test_dashboard_endpoint(synced):
    r = client.get("/api/dashboard/yesterday", params={"mode": "demo"})
    assert r.status_code == 200
    body = r.json()
    assert body["recovery"]["score"] is not None
    assert body["sleep"]["score"] is not None
    assert 0 <= body["recovery"]["confidence"] <= 1
    assert isinstance(body["insights"], list)


def test_scripted_missing_day_reduces_confidence(synced):
    missing_day = (date.today() - timedelta(days=25)).isoformat()
    r = client.get(f"/api/recovery/{missing_day}", params={"mode": "demo"})
    body = r.json()
    # vitals are missing that day -> hrv/rhr not in contributors
    assert body["inputs"]["hrv"] is None
    assert body["score"] is None or body["confidence"] < 0.6


def test_strain_detail_has_provenance(synced):
    d = (date.today() - timedelta(days=12)).isoformat()  # scripted hard day
    body = client.get(f"/api/strain/{d}", params={"mode": "demo"}).json()
    assert body["hr_max"]["source"] in ("age_formula", "blended", "observed_p999")
    assert body["detail"]["zone_minutes"]  # display zones present
    assert body["score"] and body["score"] > 8


def test_sleep_detail_timeline(synced):
    d = (date.today() - timedelta(days=3)).isoformat()
    body = client.get(f"/api/sleep/{d}", params={"mode": "demo"}).json()
    assert body["sessions"] and body["sessions"][0]["stages"]
    assert body["detail"]["need_minutes"] > 0
    assert len(body["consistency"]) >= 7


def test_trends_correlation_gate(synced):
    body = client.get(
        "/api/trends", params={"mode": "demo", "metrics": "recovery,hrv,strain", "days": 60}
    ).json()
    assert set(body["series"]) == {"recovery", "hrv", "strain"}
    for c in body["correlations"]:
        assert "n" in c and "coverage" in c
        if c["n"] >= body["correlation_gate_days"]:
            assert c["r"] is not None and -1 <= c["r"] <= 1
        else:
            assert c["r"] is None  # never show an uncertain coefficient
    lag = {x["name"]: x for x in body["lag_analyses"]}
    assert "strain_yesterday_vs_recovery" in lag


def test_heart_rate_endpoint_reports_gaps_and_coverage(synced):
    d = (date.today() - timedelta(days=1)).isoformat()
    body = client.get("/api/heart-rate", params={"mode": "demo", "day": d}).json()
    assert body["sample_count"] > 0
    assert 0 < body["coverage"] <= 1
    assert isinstance(body["gaps"], list)


def test_status_endpoint(synced):
    body = client.get("/api/status").json()
    assert body["modes"]["demo"]["days_scored"] >= 60
    assert body["modes"]["demo"]["sync_status"] == "ok"


def test_activities_have_derived_max_hr(synced):
    body = client.get("/api/activities", params={"mode": "demo", "days": 60}).json()
    assert len(body) >= 20
    with_hr = [a for a in body if a["max_hr"] is not None]
    assert with_hr, "max_hr should be derived from HR samples"
    assert all(a["max_hr"] >= (a["avg_hr"] or 0) * 0.85 for a in with_hr)
