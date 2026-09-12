from datetime import date

from backend.config import get_config
from backend.services.analytics.strain import (
    HrMaxEstimate,
    calculate_activity_strain,
    calculate_daily_strain,
    estimate_hr_max,
)
from backend.services.wearable.base import HeartRateZone

CFG = get_config()
HR_MAX = HrMaxEstimate(value=190, source="age_formula")
RHR = 57.0
ZONES = (
    HeartRateZone("LIGHT", 30, 113),
    HeartRateZone("MODERATE", 114, 141),
    HeartRateZone("VIGOROUS", 142, 176),
    HeartRateZone("PEAK", 177, 220),
)


def _day(base_bpm: int, workout_bpm: int = 0, workout_minutes: int = 0) -> dict:
    minutes = {m: float(base_bpm) for m in range(1440)}
    for m in range(600, 600 + workout_minutes):
        minutes[m] = float(workout_bpm)
    return minutes


def test_resting_day_has_low_strain():
    r = calculate_daily_strain(_day(base_bpm=65), RHR, HR_MAX, CFG, ZONES)
    assert r.score is not None and r.score < 4


def test_moderate_activity_raises_strain():
    rest = calculate_daily_strain(_day(65), RHR, HR_MAX, CFG, ZONES)
    moderate = calculate_daily_strain(_day(65, workout_bpm=145, workout_minutes=45), RHR, HR_MAX, CFG, ZONES)
    assert moderate.score > rest.score


def test_high_intensity_beats_moderate():
    moderate = calculate_daily_strain(_day(65, 145, 45), RHR, HR_MAX, CFG, ZONES)
    hard = calculate_daily_strain(_day(65, 175, 90), RHR, HR_MAX, CFG, ZONES)
    assert hard.score > moderate.score
    assert hard.status in ("high", "all-out", "moderate")


def test_strain_never_exceeds_21():
    extreme = calculate_daily_strain(_day(120, 188, 600), RHR, HR_MAX, CFG, ZONES)
    assert extreme.score <= 21.0


def test_no_samples_gives_no_score_zero_confidence():
    r = calculate_daily_strain({}, RHR, HR_MAX, CFG, ZONES)
    assert r.score is None and r.confidence == 0.0


def test_sparse_coverage_gives_no_score_but_reports_coverage():
    sparse = {m: 70.0 for m in range(0, 200)}  # under min_minutes_for_score
    r = calculate_daily_strain(sparse, RHR, HR_MAX, CFG, ZONES)
    assert r.score is None
    assert 0 < r.confidence < 0.2
    assert r.minutes_covered == 200


def test_missing_minutes_are_not_counted_as_rest():
    """ADR 0001: a half-covered active day must not out-load a fully covered one
    just by treating gaps as rest — load counts only covered minutes."""
    full_active = calculate_daily_strain(_day(110), RHR, HR_MAX, CFG, ZONES)
    half = {m: 110.0 for m in range(0, 720)}
    half_active = calculate_daily_strain(half, RHR, HR_MAX, CFG, ZONES)
    assert half_active.load < full_active.load
    assert half_active.confidence < full_active.confidence


def test_zone_minutes_are_display_only_and_counted():
    r = calculate_daily_strain(_day(65, 150, 30), RHR, HR_MAX, CFG, ZONES)
    assert r.zone_minutes["VIGOROUS"] == 30
    assert r.zone_minutes["LIGHT"] == 1410


def test_activity_strain_scores_a_window():
    window = {m: 150.0 for m in range(60)}
    s = calculate_activity_strain(window, RHR, HR_MAX, CFG)
    assert s is not None and 0 < s <= 21


def test_hr_max_observation_only_revises_upward():
    d = date(2026, 9, 11)  # age formula: 220 - 31 = 189
    # observed above the formula: blend toward it as history grows
    high = [150] * 1000 + [196] * 5
    early = estimate_hr_max(high, history_days=5, birth_year=1995, day=d, cfg=CFG)
    late = estimate_hr_max(high, history_days=28, birth_year=1995, day=d, cfg=CFG)
    assert early.source == "blended" and 189 <= early.value < late.value
    assert late.source == "observed_p999" and late.value == 196
    # observed below the formula: no max effort seen — the formula stands
    low = [150] * 1000 + [170] * 5
    r = estimate_hr_max(low, history_days=60, birth_year=1995, day=d, cfg=CFG)
    assert r.source == "age_formula" and r.value == 189
    no_data = estimate_hr_max([], history_days=0, birth_year=1995, day=d, cfg=CFG)
    assert no_data.source == "age_formula"
