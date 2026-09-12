from datetime import datetime, timedelta, timezone

from backend.config import get_config
from backend.services.analytics.sleep import analyze_session, calculate_sleep
from backend.services.wearable.base import SleepSession, SleepStageSegment

CFG = get_config()
TZ = timezone(timedelta(hours=2))


def _session(start_h=23, start_m=30, hours=8.0, fragmented=False, with_stages=True) -> SleepSession:
    start = datetime(2026, 9, 10, start_h, start_m, tzinfo=TZ).astimezone(timezone.utc)
    end = start + timedelta(hours=hours)
    stages = []
    if with_stages:
        cursor = start
        pattern = (
            [("AWAKE", 8), ("LIGHT", 25), ("DEEP", 18), ("LIGHT", 30), ("REM", 20)]
            if not fragmented
            else [("AWAKE", 15), ("LIGHT", 20), ("AWAKE", 10), ("LIGHT", 20), ("AWAKE", 12), ("DEEP", 8), ("AWAKE", 8), ("REM", 8)]
        )
        while cursor < end:
            for stage, mins in pattern:
                seg_end = min(cursor + timedelta(minutes=mins), end)
                stages.append(SleepStageSegment(stage, cursor, seg_end))
                cursor = seg_end
                if cursor >= end:
                    break
    return SleepSession(start=start, end=end, utc_offset_seconds=7200, stages=tuple(stages))


def _history(n=14, hours=8.0):
    return [analyze_session(_session(hours=hours)) for _ in range(n)]


def test_perfect_night_scores_high():
    r = calculate_sleep(analyze_session(_session(hours=8.2)), _history(), CFG)
    assert r.score is not None and r.score >= 80
    assert r.status in ("solid", "optimal")
    assert r.confidence == 1.0


def test_short_sleep_scores_lower():
    good = calculate_sleep(analyze_session(_session(hours=8.2)), _history(), CFG)
    short = calculate_sleep(analyze_session(_session(hours=4.5)), _history(), CFG)
    assert short.score < good.score
    assert short.parts["duration"] < good.parts["duration"]


def test_fragmented_sleep_scores_lower():
    calm = calculate_sleep(analyze_session(_session(hours=8.0)), _history(), CFG)
    frag = calculate_sleep(analyze_session(_session(hours=8.0, fragmented=True)), _history(), CFG)
    assert frag.score < calm.score
    assert frag.parts["efficiency"] < calm.parts["efficiency"]


def test_missing_stages_renormalizes_and_lowers_confidence():
    r = calculate_sleep(analyze_session(_session(with_stages=False)), _history(), CFG)
    assert r.score is not None
    assert "stages" not in r.parts
    assert r.confidence < 1.0


def test_overnight_session_crossing_midnight():
    night = analyze_session(_session(start_h=23, start_m=40, hours=7.5))
    assert night.time_in_bed_minutes == 450
    assert night.bedtime_local_minutes == 23 * 60 + 40
    r = calculate_sleep(night, _history(), CFG)
    assert r.score is not None


def test_no_night_gives_no_score_but_need_and_debt():
    r = calculate_sleep(None, _history(hours=7.0), CFG)
    assert r.score is None and r.confidence == 0.0
    assert r.need_minutes >= CFG.sleep.need_default_minutes
    assert r.debt_minutes > 0  # 7 h nights vs 8 h need accumulate debt


def test_sleep_debt_raises_need():
    rested = calculate_sleep(analyze_session(_session(hours=8.0)), _history(hours=8.3), CFG)
    deprived = calculate_sleep(analyze_session(_session(hours=8.0)), _history(hours=6.0), CFG)
    assert deprived.need_minutes > rested.need_minutes
    cap = CFG.sleep.need_default_minutes + CFG.sleep.debt_need_cap_minutes
    assert deprived.need_minutes <= cap


def test_performance_is_named_input_not_score():
    r = calculate_sleep(analyze_session(_session(hours=8.0)), _history(), CFG)
    assert r.performance is not None
    assert r.performance != r.score  # distinct concepts (CONTEXT.md)
