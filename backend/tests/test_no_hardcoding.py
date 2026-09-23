from __future__ import annotations

import json

from app.engine.dataset import load
from app.engine.simulator import simulate
from app.engine.validator import cost


def test_modified_dataset_drives_engine(tmp_path) -> None:
    data = json.loads(json.dumps(load()))
    clone = json.loads(json.dumps(data["districts"][0]))
    clone["id"] = "sixth"
    clone["name"] = "Шестой"
    clone["pop_share"] = 0.01
    data["districts"].append(clone)
    data["districts"][0]["pop_share"] -= 0.01
    data["measures"][0]["cost"] += 1
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    changed = load(path)
    plan = [("M1", "sixth"), ("M8", "nura"), ("M10", "nura"),
            ("M12", None), ("M14", None)]
    result = simulate(changed, plan)
    assert result["valid"]
    assert "sixth" in result["district_scores"]
    assert cost(changed, plan) == cost(data, plan)
    assert cost(changed, plan) == cost(load(), plan) + 1
