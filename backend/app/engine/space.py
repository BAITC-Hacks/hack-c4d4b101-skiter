"""Enumerate valid plans once and cache their scores by dataset hash."""

from __future__ import annotations

from itertools import combinations
from pathlib import Path

import numpy as np

from app.engine.dataset import dataset_hash, load
from app.engine.simulator import simulate
from app.engine.validator import Plan, validate

CACHE_DIR = Path(__file__).resolve().parents[1] / "cache"


def options(data: dict) -> list[tuple[str, str | None]]:
    districts = [d["id"] for d in data["districts"]]
    return [(m["id"], district) for m in data["measures"]
            for district in (districts if m["type"] == "district" else [None])]


def enumerate_scores(data: dict) -> np.ndarray:
    """Apply cheap dataset-driven filters before invoking the full engine."""
    choices = options(data)
    measures = {m["id"]: m for m in data["measures"]}
    incompatible = data["incompatibilities"]
    budget = data["rules"]["budget"]
    max_direction = data["rules"]["max_per_direction"]
    count = data["rules"]["decisions_exact"]
    scores = []
    for plan_tuple in combinations(choices, count):
        ids = [measure for measure, _ in plan_tuple]
        if len(set(ids)) != count:
            continue
        if sum(measures[measure]["cost"] for measure in ids) > budget:
            continue
        directions = [measures[measure]["direction"] for measure in ids]
        if any(directions.count(direction) > max_direction for direction in set(directions)):
            continue
        chosen = dict(plan_tuple)
        if any(left in chosen and right in chosen and (rule["scope"] == "any" or chosen[left] == chosen[right])
               for rule in incompatible for left, right in [rule["pair"]]):
            continue
        scores.append(simulate(data, list(plan_tuple), check=False)["score"])
    return np.sort(np.asarray(scores, dtype=np.float64))


def cache_path(cache_dir: Path | None = None) -> Path:
    return (cache_dir or CACHE_DIR) / f"space_{dataset_hash()[:12]}.npy"


def load_scores(data: dict | None = None, cache_dir: Path | None = None) -> np.ndarray:
    path = cache_path(cache_dir)
    if path.exists():
        return np.load(path, allow_pickle=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    scores = enumerate_scores(data or load())
    np.save(path, scores)
    return scores


def context(score: float, scores: np.ndarray) -> dict:
    below = int(np.searchsorted(scores, score - 1e-9, side="left"))
    higher = len(scores) - int(np.searchsorted(scores, score + 1e-9, side="right"))
    best = float(scores[-1])
    return {"valid_plans": len(scores), "percentile": 100 * below / len(scores),
            "rank": 1 + higher, "best_score": best, "gap": best - score}


def best_single_swap(data: dict, plan: Plan) -> dict:
    """Try every one-slot replacement, including a different district for that measure."""
    current = simulate(data, plan)
    if not current["valid"]:
        return current
    best_plan = list(plan)
    best_score = current["score"]
    for index in range(len(plan)):
        for option in options(data):
            candidate = list(plan)
            candidate[index] = option
            if validate(data, candidate):
                continue
            score = simulate(data, candidate, check=False)["score"]
            if score > best_score + 1e-9:
                best_plan, best_score = candidate, score
    return {"plan": [{"measure": measure, "district": district} for measure, district in best_plan],
            "score": best_score, "improvement": best_score - current["score"]}
