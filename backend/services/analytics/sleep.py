"""Sleep engine (CONTEXT.md: Sleep Score, Sleep Performance, Sleep Need, Sleep Debt).

Sleep Score (0..100, the headline) = weighted composite of duration,
efficiency, consistency and stage quality. Sleep Performance (achieved/Need)
is a clearly named input, never the headline. Need starts from a configured
default and grows with accumulated Debt (capped); personalization comes later
with more history (settled in grilling Q12).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta, timezone
from statistics import pstdev
from typing import Dict, List, Optional, Sequence

from backend.config import ScoresConfig
from backend.services.wearable.base import SleepSession


@dataclass(frozen=True)
class SleepNight:
    """Normalized facts about one night (pure feature extraction, no scoring)."""

    time_in_bed_minutes: float
    sleep_minutes: float
    awake_minutes: float
    light_minutes: float
    deep_minutes: float
    rem_minutes: float
    awakenings: int
    efficiency: float                 # sleep / time in bed, 0..1
    bedtime_local_minutes: int        # minutes since local midnight, may exceed 1440 handling wrap
    has_stages: bool


@dataclass(frozen=True)
class SleepResult:
    score: Optional[int]
    status: Optional[str]             # schwach | solide | optimal
    confidence: float
    performance: Optional[float]      # 0..1+, sleep / need
    need_minutes: float
    debt_minutes: float
    parts: Dict[str, float]           # per-component 0..1 (for the waterfall/why view)


def analyze_session(session: SleepSession) -> SleepNight:
    tib = (session.end - session.start).total_seconds() / 60
    by_stage = session.minutes_by_stage()
    awake = by_stage.get("AWAKE", 0.0)
    light = by_stage.get("LIGHT", 0.0)
    deep = by_stage.get("DEEP", 0.0)
    rem = by_stage.get("REM", 0.0)
    has_stages = bool(session.stages)
    asleep = (light + deep + rem) if has_stages else tib  # without stages: bed time is the best estimate
    awakenings = sum(1 for s in session.stages if s.stage == "AWAKE") - (1 if has_stages else 0)

    tz = timezone(timedelta(seconds=session.utc_offset_seconds))
    local_start = session.start.astimezone(tz)
    bed_min = local_start.hour * 60 + local_start.minute

    return SleepNight(
        time_in_bed_minutes=round(tib, 1),
        sleep_minutes=round(asleep, 1),
        awake_minutes=round(awake, 1),
        light_minutes=round(light, 1),
        deep_minutes=round(deep, 1),
        rem_minutes=round(rem, 1),
        awakenings=max(0, awakenings),
        efficiency=round(asleep / tib, 3) if tib > 0 else 0.0,
        bedtime_local_minutes=bed_min,
        has_stages=has_stages,
    )


def _bedtime_stddev(nights: Sequence[SleepNight]) -> Optional[float]:
    """Std deviation of bedtime in minutes, unwrapped around midnight."""
    if len(nights) < 3:
        return None
    # Shift so that times after midnight (< 12:00) count as >24:00 — keeps 23:50 and 00:10 close.
    vals = [n.bedtime_local_minutes + (1440 if n.bedtime_local_minutes < 720 else 0) for n in nights]
    return pstdev(vals)


def calculate_need_and_debt(
    recent_nights: Sequence[SleepNight], cfg: ScoresConfig
) -> tuple[float, float]:
    """Need = default + capped share of the average nightly shortfall (Debt)."""
    base = float(cfg.sleep.need_default_minutes)
    window = recent_nights[-cfg.sleep.debt_window_days :]
    if not window:
        return base, 0.0
    shortfalls = [max(0.0, base - n.sleep_minutes) for n in window]
    debt = sum(shortfalls)
    avg_shortfall = debt / len(window)
    need = base + min(cfg.sleep.debt_need_cap_minutes, cfg.sleep.debt_need_factor * avg_shortfall)
    return round(need, 0), round(debt, 0)


def _status(score: int, cfg: ScoresConfig) -> str:
    if score <= cfg.sleep.status.weak_max:
        return "poor"
    if score <= cfg.sleep.status.solid_max:
        return "solid"
    return "optimal"


def calculate_sleep(
    night: Optional[SleepNight],
    recent_nights: Sequence[SleepNight],  # previous nights, oldest→newest, excluding `night`
    cfg: ScoresConfig,
) -> SleepResult:
    need, debt = calculate_need_and_debt(list(recent_nights), cfg)

    if night is None:
        return SleepResult(
            score=None, status=None, confidence=0.0, performance=None,
            need_minutes=need, debt_minutes=debt, parts={},
        )

    weights = dict(cfg.sleep.weights)
    parts: Dict[str, float] = {}

    performance = night.sleep_minutes / need if need else 0.0
    parts["duration"] = min(1.0, performance)

    eff_span = cfg.sleep.efficiency_full - cfg.sleep.efficiency_zero
    parts["efficiency"] = max(0.0, min(1.0, (night.efficiency - cfg.sleep.efficiency_zero) / eff_span))

    consistency_nights = list(recent_nights[-cfg.sleep.consistency_window_days :]) + [night]
    std = _bedtime_stddev(consistency_nights)
    if std is None:
        weights.pop("consistency", None)  # not enough history — renormalize, don't fake
    else:
        parts["consistency"] = max(0.0, 1.0 - std / cfg.sleep.consistency_strong_stddev_minutes)

    if night.has_stages and night.sleep_minutes > 0:
        deep_share = night.deep_minutes / night.sleep_minutes
        rem_share = night.rem_minutes / night.sleep_minutes
        deep_part = max(0.0, 1.0 - abs(deep_share - cfg.sleep.deep_target_share) / cfg.sleep.deep_target_share)
        rem_part = max(0.0, 1.0 - abs(rem_share - cfg.sleep.rem_target_share) / cfg.sleep.rem_target_share)
        parts["stages"] = 0.5 * deep_part + 0.5 * rem_part
    else:
        weights.pop("stages", None)  # missing sensor lowers confidence, never the score directly

    used_weight = sum(w for k, w in weights.items() if k in parts)
    if used_weight == 0:
        return SleepResult(
            score=None, status=None, confidence=0.0, performance=round(performance, 3),
            need_minutes=need, debt_minutes=debt, parts=parts,
        )
    score = int(round(100 * sum(weights[k] * parts[k] for k in parts if k in weights) / used_weight))
    score = max(0, min(100, score))
    confidence = round(used_weight / sum(cfg.sleep.weights.values()), 3)

    return SleepResult(
        score=score, status=_status(score, cfg), confidence=confidence,
        performance=round(performance, 3), need_minutes=need, debt_minutes=debt,
        parts={k: round(v, 3) for k, v in parts.items()},
    )
