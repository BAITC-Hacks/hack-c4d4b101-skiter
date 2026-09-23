from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.engine.dataset import load
from app.engine.simulator import simulate

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((ROOT / "spec" / "test_cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_golden(case: dict) -> None:
    plan = [(item["measure"], item.get("district")) for item in case["plan"]]
    result = simulate(load(), plan, event_id=case.get("event"),
                      buy_response=case.get("buy_response", False), check=case.get("check", True))
    expected = case["expected"]
    assert result["valid"] == expected["valid"]
    if not expected["valid"]:
        assert result["error_code"] == expected["error_code"]
        assert result["error"] == expected["error"]
        return
    assert round(result["score"], 2) == expected["score"]
    assert result["cost"] == expected["cost"]
    assert result["weakest_district"] == expected["weakest_district"]
    assert len(result["critical"]) == expected["n_critical"]
    for district, score in expected["district_scores"].items():
        assert round(result["district_scores"][district], 2) == score
    if case["id"] == "TC02":
        assert result["natural_units"]["nura"]["S1"]["before"] == 69
        assert result["natural_units"]["nura"]["S1"]["after"] == 74
