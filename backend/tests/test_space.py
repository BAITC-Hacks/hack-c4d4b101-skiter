from __future__ import annotations

from app.engine.dataset import load
from app.engine.simulator import simulate
from app.engine.space import best_single_swap, context, load_scores


def test_space_and_example_rank() -> None:
    scores = load_scores()
    assert len(scores) == 694_395
    assert round(float(scores[0]), 2) == 52.04
    assert round(float(scores[-1]), 2) == 57.24
    plan = [("M7", "nura"), ("M8", "nura"), ("M10", "nura"),
            ("M12", None), ("M5", "saryarka")]
    score = simulate(load(), plan)["score"]
    ranked = context(score, scores)
    assert ranked["rank"] == 566
    assert ranked["percentile"] == 100 * 693_829 / 694_395
    assert round(ranked["gap"], 2) == 0.69
    swap = best_single_swap(load(), plan)
    assert swap["score"] >= score
