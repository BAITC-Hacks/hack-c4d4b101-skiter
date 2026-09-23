from __future__ import annotations

from pydantic import BaseModel, Field


class Decision(BaseModel):
    measure_id: str
    district: str | None = None


class SimulateRequest(BaseModel):
    decisions: list[Decision]


class Violation(BaseModel):
    code: str
    message: str


class IndicatorValue(BaseModel):
    name: str
    before: float
    after: float


class DistrictResult(BaseModel):
    name: str
    pop: float
    d_before: float
    d_after: float
    indicators: dict[str, IndicatorValue]


class EffectLine(BaseModel):
    district: str
    indicator: str
    delta: float


class MeasureContribution(BaseModel):
    measure_id: str
    name: str
    district: str | None
    cost: int
    lag: int
    realized_fraction: float
    effects: list[EffectLine]


class SynergyApplied(BaseModel):
    measures: list[str]
    indicator: str
    delta: float
    district: str


class CritCell(BaseModel):
    district: str
    district_name: str
    indicator: str
    indicator_name: str
    value: float


class SimulateResponse(BaseModel):
    valid: bool
    cost: int | None = None
    budget: int
    score: float | None = None
    baseline_score: float | None = None
    delta_vs_baseline: float | None = None
    d_avg: float | None = None
    d_min: float | None = None
    n_crit: int | None = None
    weakest_district: str | None = None
    weakest_district_name: str | None = None
    districts: dict[str, DistrictResult] | None = None
    measure_contributions: list[MeasureContribution] | None = None
    synergies_applied: list[SynergyApplied] | None = None
    crits: list[CritCell] | None = None
    violations: list[Violation] = Field(default_factory=list)
