from datetime import date, timedelta

from backend.services.analytics.baseline import BaselineResult, rolling_median

D0 = date(2026, 9, 11)


def _history(days: int, value: float = 50.0) -> dict:
    return {D0 - timedelta(days=i): value for i in range(1, days + 1)}


def test_insufficient_history_gives_no_baseline():
    r = rolling_median(_history(6), D0)
    assert r.value is None and r.n == 6
    assert 0 < r.coverage < 1


def test_min_days_boundary():
    r = rolling_median(_history(7), D0)
    assert r.value == 50.0 and r.n == 7


def test_expanding_window_coverage_grows():
    r10 = rolling_median(_history(10), D0)
    r28 = rolling_median(_history(28), D0)
    assert r10.coverage < r28.coverage == 1.0


def test_scored_day_is_excluded():
    hist = _history(10)
    hist[D0] = 999.0  # today must not feed its own baseline
    assert rolling_median(hist, D0).value == 50.0


def test_median_is_robust_to_outlier():
    hist = _history(9, 50.0)
    hist[D0 - timedelta(days=10)] = 500.0  # single spike
    assert rolling_median(hist, D0).value == 50.0


def test_window_limits_to_28_days():
    hist = {D0 - timedelta(days=i): (10.0 if i > 28 else 50.0) for i in range(1, 60)}
    assert rolling_median(hist, D0).value == 50.0
