"""Strain engine — ADR 0001.

Load is computed from continuous Heart Rate Reserve Intensity on 1-minute
means; Fitbit zones are display-only. Missing minutes reduce Confidence and
are never counted as rest. Every result carries hr_max provenance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from backend.config import ScoresConfig
from backend.services.wearable.base import HeartRateSample, HeartRateZone


@dataclass(frozen=True)
class HrMaxEstimate:
    value: int
    source: str  # observed_p999 | age_formula | blended


@dataclass(frozen=True)
class StrainResult:
    score: Optional[float]        # 0..21, None when coverage is insufficient
    status: Optional[str]         # leicht | moderat | hoch | maximal
    confidence: float             # 0..1 (minute coverage)
    load: float
    minutes_covered: int
    hr_max: HrMaxEstimate
    zone_minutes: Dict[str, int] = field(default_factory=dict)  # display-only


def estimate_hr_max(
    all_samples_bpm: Sequence[int],
    history_days: int,
    birth_year: Optional[int],
    day: date,
    cfg: ScoresConfig,
) -> HrMaxEstimate:
    """Estimate HRmax with per-day provenance (ADR 0001) — never blindly p99.9.

    The observed percentile is a LOWER bound of true HRmax (heart rate above
    one's maximum cannot be observed), so observation may only revise the
    estimate UPWARD: if observed >= age formula, blend toward it as history
    grows; if observed is below, absence of a max effort is no evidence of a
    lower HRmax and the age formula stands.
    """
    age_hr: Optional[int] = None
    if birth_year:
        age_hr = cfg.strain.hr_max_age_formula_base - (day.year - birth_year)

    observed: Optional[int] = None
    if all_samples_bpm:
        s = sorted(all_samples_bpm)
        idx = min(len(s) - 1, int(len(s) * cfg.strain.hr_max_observed_percentile / 100))
        observed = s[idx]

    if observed is None and age_hr is None:
        return HrMaxEstimate(value=190, source="age_formula")  # last-resort default
    if observed is None:
        return HrMaxEstimate(value=int(age_hr), source="age_formula")
    if age_hr is None:
        return HrMaxEstimate(value=int(observed), source="observed_p999")
    if observed < age_hr:
        return HrMaxEstimate(value=int(age_hr), source="age_formula")

    w = min(1.0, history_days / cfg.strain.hr_max_blend_full_days)
    value = int(round(w * observed + (1 - w) * age_hr))
    source = "observed_p999" if w >= 1.0 else ("age_formula" if w == 0 else "blended")
    return HrMaxEstimate(value=value, source=source)


def resample_to_minutes(
    samples: Sequence[HeartRateSample], day: date, utc_offset_seconds: int
) -> Dict[int, float]:
    """Mean bpm per civil minute of `day` (0..1439). Sparse: gaps stay absent."""
    tz = timezone(timedelta(seconds=utc_offset_seconds))
    day_start = datetime.combine(day, datetime.min.time(), tzinfo=tz)
    day_end = day_start + timedelta(days=1)
    sums: Dict[int, Tuple[float, int]] = {}
    for s in samples:
        local = s.ts.astimezone(tz)
        if not (day_start <= local < day_end):
            continue
        m = local.hour * 60 + local.minute
        total, n = sums.get(m, (0.0, 0))
        sums[m] = (total + s.bpm, n + 1)
    return {m: total / n for m, (total, n) in sums.items()}


def _minute_weight(bpm: float, resting_hr: float, hr_max: float, cfg: ScoresConfig) -> float:
    hrr = hr_max - resting_hr
    if hrr <= 0:
        return 0.0
    intensity = (bpm - resting_hr) / hrr
    floor = cfg.strain.intensity_floor
    if intensity <= floor:
        return 0.0
    return ((min(intensity, 1.0) - floor) / (1.0 - floor)) ** cfg.strain.intensity_gamma


def _load_to_strain(load: float, cfg: ScoresConfig) -> float:
    return cfg.strain.max_strain * (1.0 - math.exp(-load / cfg.strain.load_k))


def _status(score: float, cfg: ScoresConfig) -> str:
    s = cfg.strain.status
    if score <= s.light_max:
        return "light"
    if score <= s.moderate_max:
        return "moderate"
    if score <= s.high_max:
        return "high"
    return "all-out"


def zone_minutes_display(
    minute_hr: Mapping[int, float], zones: Sequence[HeartRateZone]
) -> Dict[str, int]:
    """Time in Fitbit zones — display only, never part of score math (ADR 0001)."""
    out = {z.name: 0 for z in zones}
    for bpm in minute_hr.values():
        for z in zones:
            if z.min_bpm <= bpm <= z.max_bpm:
                out[z.name] += 1
                break
    return out


def calculate_daily_strain(
    minute_hr: Mapping[int, float],
    resting_hr: Optional[float],
    hr_max: HrMaxEstimate,
    cfg: ScoresConfig,
    zones: Optional[Sequence[HeartRateZone]] = None,
) -> StrainResult:
    covered = len(minute_hr)
    confidence = covered / 1440.0
    zm = zone_minutes_display(minute_hr, zones) if zones else {}

    if resting_hr is None or covered < cfg.strain.min_minutes_for_score:
        return StrainResult(
            score=None, status=None, confidence=confidence, load=0.0,
            minutes_covered=covered, hr_max=hr_max, zone_minutes=zm,
        )

    load = sum(
        _minute_weight(bpm, resting_hr, hr_max.value, cfg) for bpm in minute_hr.values()
    )
    score = round(min(cfg.strain.max_strain, _load_to_strain(load, cfg)), 1)
    return StrainResult(
        score=score, status=_status(score, cfg), confidence=round(confidence, 3),
        load=round(load, 2), minutes_covered=covered, hr_max=hr_max, zone_minutes=zm,
    )


def calculate_activity_strain(
    minute_hr: Mapping[int, float],
    resting_hr: Optional[float],
    hr_max: HrMaxEstimate,
    cfg: ScoresConfig,
) -> Optional[float]:
    """Strain contribution of a single activity window (same load model)."""
    if resting_hr is None or not minute_hr:
        return None
    load = sum(_minute_weight(bpm, resting_hr, hr_max.value, cfg) for bpm in minute_hr.values())
    return round(min(cfg.strain.max_strain, _load_to_strain(load, cfg)), 1)
