"""Baseline engine (CONTEXT.md: "Baseline").

Rolling robust statistic (median) over the days strictly BEFORE the scored
day. Target window 28 days; with shorter history an expanding window of at
least `min_days` real values is used. Below that: no Baseline, no score.
Coverage (window fill, 0..1) feeds Confidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median
from typing import Mapping, Optional


@dataclass(frozen=True)
class BaselineResult:
    value: Optional[float]   # None when history is too short
    coverage: float          # available days / window_days, 0..1
    n: int                   # days actually used


def rolling_median(
    history: Mapping[date, float],
    day: date,
    window_days: int = 28,
    min_days: int = 7,
) -> BaselineResult:
    """Median of `history` values in the `window_days` before `day` (exclusive)."""
    values = [
        v
        for d, v in history.items()
        if day - timedelta(days=window_days) <= d < day and v is not None
    ]
    n = len(values)
    coverage = min(1.0, n / window_days)
    if n < min_days:
        return BaselineResult(value=None, coverage=coverage, n=n)
    return BaselineResult(value=float(median(values)), coverage=coverage, n=n)


def deviation_fraction(current: float, baseline: float) -> float:
    """Relative deviation of current vs baseline (e.g. +0.12 = 12 % above)."""
    if baseline == 0:
        return 0.0
    return (current - baseline) / baseline
