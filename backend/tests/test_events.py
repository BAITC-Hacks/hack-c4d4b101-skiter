from __future__ import annotations

from app.engine.dataset import load
from app.engine.events import stress_test
from app.engine.simulator import simulate

EXAMPLE = [("M7", "nura"), ("M8", "nura"), ("M10", "nura"),
           ("M12", None), ("M5", "saryarka")]


def test_events_do_not_change_official_score() -> None:
    data = load()
    official = simulate(data, EXAMPLE)["score"]
    result = stress_test(data, EXAMPLE)
    assert result["valid"]
    assert result["official_score"] == official
    assert len(result["events"]) == len(data["events"]["catalog"])
    assert simulate(data, EXAMPLE)["score"] == official


def test_response_uses_only_remaining_budget() -> None:
    result = stress_test(load(), EXAMPLE, {"EV2"})
    assert not result["valid"]
    assert result["error_code"] == "RESPONSE_OVER_BUDGET"
