from backend.config import get_config
from backend.services.analytics.baseline import BaselineResult
from backend.services.analytics.recovery import (
    RecoveryBaselines,
    RecoveryInputs,
    calculate_recovery,
)

CFG = get_config()

FULL_BASE = RecoveryBaselines(
    hrv=BaselineResult(50.0, 1.0, 28),
    resting_hr=BaselineResult(57.0, 1.0, 28),
    respiratory_rate=BaselineResult(13.5, 1.0, 28),
)


def _inputs(**kw) -> RecoveryInputs:
    defaults = dict(hrv_rmssd=50.0, resting_hr=57.0, sleep_score=80,
                    respiratory_rate=13.5, skin_temp_delta=0.0, spo2_avg=97.0)
    defaults.update(kw)
    return RecoveryInputs(**defaults)


def test_hrv_above_baseline_raises_score():
    base = calculate_recovery(_inputs(), FULL_BASE, CFG)
    up = calculate_recovery(_inputs(hrv_rmssd=60.0), FULL_BASE, CFG)
    assert up.score > base.score
    assert "hrv" in up.positive_factors


def test_hrv_drop_lowers_score():
    base = calculate_recovery(_inputs(), FULL_BASE, CFG)
    down = calculate_recovery(_inputs(hrv_rmssd=38.0), FULL_BASE, CFG)
    assert down.score < base.score
    assert "hrv" in down.negative_factors


def test_elevated_resting_hr_lowers_score():
    base = calculate_recovery(_inputs(), FULL_BASE, CFG)
    up = calculate_recovery(_inputs(resting_hr=64.0), FULL_BASE, CFG)
    assert up.score < base.score
    assert "resting_hr" in up.negative_factors


def test_missing_hrv_reduces_confidence_not_score_to_none():
    full = calculate_recovery(_inputs(), FULL_BASE, CFG)
    no_hrv = calculate_recovery(_inputs(hrv_rmssd=None), FULL_BASE, CFG)
    assert no_hrv.score is not None
    assert no_hrv.confidence < full.confidence
    assert "hrv" not in no_hrv.contributors


def test_missing_sleep_reduces_confidence():
    full = calculate_recovery(_inputs(), FULL_BASE, CFG)
    no_sleep = calculate_recovery(_inputs(sleep_score=None), FULL_BASE, CFG)
    assert no_sleep.score is not None
    assert no_sleep.confidence < full.confidence


def test_all_primary_metrics_missing_gives_no_score():
    r = calculate_recovery(
        RecoveryInputs(skin_temp_delta=0.1, spo2_avg=97.0),
        RecoveryBaselines(), CFG,
    )
    assert r.score is None and r.confidence == 0.0


def test_abnormal_temperature_is_negative_factor():
    r = calculate_recovery(_inputs(skin_temp_delta=1.0), FULL_BASE, CFG)
    assert "skin_temp" in r.negative_factors


def test_insufficient_baseline_skips_component():
    no_base = RecoveryBaselines(
        hrv=BaselineResult(None, 0.2, 5),          # too little history
        resting_hr=BaselineResult(57.0, 1.0, 28),
        respiratory_rate=BaselineResult(13.5, 1.0, 28),
    )
    r = calculate_recovery(_inputs(), no_base, CFG)
    assert "hrv" not in r.contributors
    assert r.score is not None


def test_score_bounds_and_status():
    great = calculate_recovery(
        _inputs(hrv_rmssd=70.0, resting_hr=51.0, sleep_score=98), FULL_BASE, CFG
    )
    bad = calculate_recovery(
        _inputs(hrv_rmssd=30.0, resting_hr=68.0, sleep_score=25,
                skin_temp_delta=1.2, spo2_avg=91.0), FULL_BASE, CFG
    )
    assert 0 <= bad.score < great.score <= 100
    assert great.status == "high" and bad.status == "low"
