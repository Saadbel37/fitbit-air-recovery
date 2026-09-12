"""Recovery engine (CONTEXT.md: Recovery Score, Confidence).

Explainable 0..100 score from deviations against personal Baselines. Weights
live in scores.toml and renormalize over the components actually present —
a missing sensor lowers Confidence, it never silently substitutes a value.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from backend.config import ScoresConfig
from backend.services.analytics.baseline import BaselineResult, deviation_fraction


@dataclass(frozen=True)
class RecoveryInputs:
    """Today's measured values (None = sensor missing)."""

    hrv_rmssd: Optional[float] = None
    resting_hr: Optional[float] = None
    sleep_score: Optional[int] = None
    respiratory_rate: Optional[float] = None
    skin_temp_delta: Optional[float] = None
    spo2_avg: Optional[float] = None


@dataclass(frozen=True)
class RecoveryBaselines:
    hrv: BaselineResult = BaselineResult(None, 0.0, 0)
    resting_hr: BaselineResult = BaselineResult(None, 0.0, 0)
    respiratory_rate: BaselineResult = BaselineResult(None, 0.0, 0)


@dataclass(frozen=True)
class RecoveryResult:
    score: Optional[int]
    status: Optional[str]                       # niedrig | moderat | hoch
    confidence: float
    contributors: Dict[str, float] = field(default_factory=dict)   # component -> 0..1
    positive_factors: List[str] = field(default_factory=list)
    negative_factors: List[str] = field(default_factory=list)
    deviations: Dict[str, float] = field(default_factory=dict)     # for explanations ("+12 %")


def _directional(dev: float, strong: float, higher_is_better: bool) -> float:
    """Map a relative deviation to 0..1 (0.5 = at baseline) via tanh."""
    signed = dev if higher_is_better else -dev
    return 0.5 + 0.5 * math.tanh(signed / strong)


def _stability(dev: float, strong: float) -> float:
    """1.0 at baseline, falling toward 0 with deviation in either direction."""
    return max(0.0, 1.0 - abs(dev) / strong)


def _status(score: int, cfg: ScoresConfig) -> str:
    if score <= cfg.recovery.status.low_max:
        return "low"
    if score <= cfg.recovery.status.moderate_max:
        return "moderate"
    return "high"


def calculate_recovery(
    inputs: RecoveryInputs, baselines: RecoveryBaselines, cfg: ScoresConfig
) -> RecoveryResult:
    sc = cfg.recovery.scaling
    weights = dict(cfg.recovery.weights)
    contributors: Dict[str, float] = {}
    deviations: Dict[str, float] = {}
    coverages: List[float] = []

    if inputs.hrv_rmssd is not None and baselines.hrv.value:
        dev = deviation_fraction(inputs.hrv_rmssd, baselines.hrv.value)
        deviations["hrv"] = dev
        contributors["hrv"] = _directional(dev, sc.hrv_strong_deviation, higher_is_better=True)
        coverages.append(baselines.hrv.coverage)

    if inputs.resting_hr is not None and baselines.resting_hr.value:
        dev = deviation_fraction(inputs.resting_hr, baselines.resting_hr.value)
        deviations["resting_hr"] = dev
        contributors["resting_hr"] = _directional(dev, sc.resting_hr_strong_deviation, higher_is_better=False)
        coverages.append(baselines.resting_hr.coverage)

    if inputs.sleep_score is not None:
        contributors["sleep"] = inputs.sleep_score / 100.0
        coverages.append(1.0)

    if inputs.respiratory_rate is not None and baselines.respiratory_rate.value:
        dev = deviation_fraction(inputs.respiratory_rate, baselines.respiratory_rate.value)
        deviations["respiratory_rate"] = dev
        contributors["respiratory_rate"] = _stability(dev, sc.respiratory_strong_deviation)
        coverages.append(baselines.respiratory_rate.coverage)

    if inputs.skin_temp_delta is not None:
        deviations["skin_temp"] = inputs.skin_temp_delta
        contributors["skin_temp"] = _stability(
            inputs.skin_temp_delta / sc.skin_temp_strong_delta_celsius, 1.0
        )
        coverages.append(1.0)

    if inputs.spo2_avg is not None:
        span = sc.spo2_normal - sc.spo2_low
        contributors["spo2"] = max(0.0, min(1.0, (inputs.spo2_avg - sc.spo2_low) / span))
        coverages.append(1.0)

    # Core requirement: at least one primary signal (hrv / resting_hr / sleep)
    if not any(k in contributors for k in ("hrv", "resting_hr", "sleep")):
        return RecoveryResult(score=None, status=None, confidence=0.0)

    used_weight = sum(weights[k] for k in contributors)
    score = int(round(100 * sum(weights[k] * v for k, v in contributors.items()) / used_weight))
    score = max(0, min(100, score))

    weight_share = used_weight / sum(weights.values())
    baseline_cov = sum(coverages) / len(coverages) if coverages else 0.0
    confidence = round(weight_share * baseline_cov, 3)

    positive = [k for k, v in contributors.items() if v >= 0.62]
    negative = [k for k, v in contributors.items() if v <= 0.38]

    return RecoveryResult(
        score=score,
        status=_status(score, cfg),
        confidence=confidence,
        contributors={k: round(v, 3) for k, v in contributors.items()},
        positive_factors=positive,
        negative_factors=negative,
        deviations={k: round(v, 4) for k, v in deviations.items()},
    )
