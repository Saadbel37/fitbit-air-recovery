"""Typed access to scores.toml — the single home of all scoring parameters."""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel

CONFIG_PATH = Path(__file__).parent / "scores.toml"


class BaselineCfg(BaseModel):
    window_days: int
    min_days: int
    metrics: List[str]


class RecoveryStatusCfg(BaseModel):
    low_max: int
    moderate_max: int


class RecoveryScalingCfg(BaseModel):
    hrv_strong_deviation: float
    resting_hr_strong_deviation: float
    respiratory_strong_deviation: float
    skin_temp_strong_delta_celsius: float
    spo2_normal: float
    spo2_low: float


class RecoveryCfg(BaseModel):
    weights: Dict[str, float]
    scaling: RecoveryScalingCfg
    status: RecoveryStatusCfg


class StrainStatusCfg(BaseModel):
    light_max: float
    moderate_max: float
    high_max: float


class StrainCfg(BaseModel):
    resample_minutes: int
    intensity_floor: float
    intensity_gamma: float
    load_k: float
    max_strain: float
    hr_max_age_formula_base: int
    hr_max_observed_percentile: float
    hr_max_blend_full_days: int
    min_minutes_for_score: int
    status: StrainStatusCfg


class SleepStatusCfg(BaseModel):
    weak_max: int
    solid_max: int


class SleepCfg(BaseModel):
    need_default_minutes: int
    debt_window_days: int
    debt_need_factor: float
    debt_need_cap_minutes: int
    consistency_window_days: int
    consistency_strong_stddev_minutes: int
    efficiency_full: float
    efficiency_zero: float
    deep_target_share: float
    rem_target_share: float
    weights: Dict[str, float]
    status: SleepStatusCfg


class InsightsCfg(BaseModel):
    hrv_notable_pct: float
    rhr_notable_bpm: float
    sleep_shortfall_notable_min: int
    strain_high_threshold: float
    skin_temp_notable_celsius: float
    spo2_notable: float
    bedtime_stddev_notable_min: int
    weekly_azm_target: int
    recovery_vs_week_notable_pct: float


class TrendsCfg(BaseModel):
    min_days_for_correlation: int


class ScoresConfig(BaseModel):
    algorithm_version: str
    baseline: BaselineCfg
    recovery: RecoveryCfg
    strain: StrainCfg
    sleep: SleepCfg
    insights: InsightsCfg
    trends: TrendsCfg


@lru_cache(maxsize=1)
def get_config() -> ScoresConfig:
    with open(CONFIG_PATH, "rb") as f:
        raw = tomllib.load(f)
    return ScoresConfig.model_validate(raw)
