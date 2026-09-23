from __future__ import annotations

from app.engine.dataset import load
from app.engine.validate import normalize, total_cost

SCORE_AVG = 0.7
SCORE_MIN = 0.3
SCORE_CRIT = 1.0
CRIT_THRESHOLD = 40.0


def clip(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def score_plan(decisions: list) -> dict:
    data = load()
    decs = normalize(decisions)
    measures = {m["id"]: m for m in data["measures"]}
    districts = data["districts"]
    indicator_ids = [item["id"] for item in data["indicators"]]
    indicator_names = {item["id"]: item["name"] for item in data["indicators"]}
    weights = {item["id"]: item["weight"] for item in data["indicators"]}
    horizon = data["horizon"]

    base = {
        district["id"]: {key: float(district["indicators"][key]) for key in indicator_ids}
        for district in districts
    }
    state = {district_id: dict(values) for district_id, values in base.items()}
    contributions = []

    for dec in decs:
        measure = measures[dec["measure_id"]]
        fraction = (horizon - measure["lag"]) / horizon
        targets = [dec["district"]] if measure["type"] == "district" else [d["id"] for d in districts]
        effects = []
        for district_id in targets:
            for indicator, raw in measure["effects"].items():
                delta = float(raw) * fraction
                state[district_id][indicator] += delta
                effects.append({"district": district_id, "indicator": indicator, "delta": delta})
        contributions.append({
            "measure_id": measure["id"],
            "name": measure["name"],
            "district": dec["district"] if measure["type"] == "district" else None,
            "cost": measure["cost"],
            "lag": measure["lag"],
            "realized_fraction": fraction,
            "effects": effects,
        })

    by_id = {dec["measure_id"]: dec for dec in decs}
    synergies = []
    for synergy in data["synergies"]:
        left, right = synergy["measures"]
        if left not in by_id or right not in by_id:
            continue
        district_id = by_id[synergy["anchor"]]["district"]
        indicator = synergy["indicator"]
        delta = float(synergy["delta"])
        state[district_id][indicator] += delta
        synergies.append({
            "measures": [left, right],
            "indicator": indicator,
            "delta": delta,
            "district": district_id,
        })

    for values in state.values():
        for indicator in values:
            values[indicator] = clip(values[indicator])

    def index(values: dict[str, float]) -> float:
        return sum(weights[key] * values[key] for key in indicator_ids)

    district_out = {}
    d_values = {}
    crits = []
    for district in districts:
        district_id = district["id"]
        before = base[district_id]
        after = state[district_id]
        d_before = index(before)
        d_after = index(after)
        d_values[district_id] = d_after
        indicators = {}
        for indicator in indicator_ids:
            indicators[indicator] = {
                "name": indicator_names[indicator],
                "before": before[indicator],
                "after": after[indicator],
            }
            if after[indicator] < CRIT_THRESHOLD:
                crits.append({
                    "district": district_id,
                    "district_name": district["name"],
                    "indicator": indicator,
                    "indicator_name": indicator_names[indicator],
                    "value": after[indicator],
                })
        district_out[district_id] = {
            "name": district["name"],
            "pop": district["pop"],
            "d_before": d_before,
            "d_after": d_after,
            "indicators": indicators,
        }

    d_avg = sum(district["pop"] * d_values[district["id"]] for district in districts)
    d_min = min(d_values.values())
    weakest = min(d_values, key=lambda district_id: (d_values[district_id], district_id))
    n_crit = len(crits)
    return {
        "cost": total_cost(decs),
        "score": SCORE_AVG * d_avg + SCORE_MIN * d_min - SCORE_CRIT * n_crit,
        "d_avg": d_avg,
        "d_min": d_min,
        "n_crit": n_crit,
        "weakest_district": weakest,
        "weakest_district_name": district_out[weakest]["name"],
        "districts": district_out,
        "measure_contributions": contributions,
        "synergies_applied": synergies,
        "crits": crits,
    }
