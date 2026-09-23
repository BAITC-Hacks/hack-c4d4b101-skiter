from __future__ import annotations

import random

from app.engine.dataset import load
from app.engine.simulator import simulate
from app.engine.space import options
from app.engine.validator import validate
from spec.reference_scoring import simulate as reference_simulate


def test_reference_parity_on_10000_seeded_valid_plans() -> None:
    data = load()
    rng = random.Random(20260923)
    choices = options(data)
    checked = 0
    while checked < 10_000:
        plan = rng.sample(choices, data["rules"]["decisions_exact"])
        if validate(data, plan):
            continue
        actual = simulate(data, plan)
        expected = reference_simulate(data, plan)
        assert abs(actual["score"] - expected["score"]) < 1e-9
        assert actual["district_scores"] == expected["district_scores"]
        checked += 1
