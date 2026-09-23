"""Pure scoring engine. Numeric order matches spec/reference_scoring.py."""

from __future__ import annotations

from app.engine.units import natural_values
from app.engine.validator import Plan, cost, validate


def simulate(data: dict, plan: Plan, *, event_id: str | None = None,
             buy_response: bool = False, check: bool = True) -> dict:
    if check:
        error = validate(data, plan)
        if error:
            return {"valid": False, "error_code": error[0], "error": error[1]}
    measures = {m["id"]: m for m in data["measures"]}
    codes = [item["code"] for item in data["indicators"]]
    weights = {item["code"]: item["weight"] for item in data["indicators"]}
    horizon = data["rules"]["horizon_quarters"]
    before = {d["id"]: dict(d["indicators"]) for d in data["districts"]}
    values = {district: dict(row) for district, row in before.items()}
    contributions = []

    def targets(measure: dict, district: str | None) -> list[str]:
        return [d["id"] for d in data["districts"]] if measure["type"] == "city" else [district]

    for measure_id, district in plan:
        measure = measures[measure_id]
        share = (horizon - measure["lag"]) / horizon
        for target in targets(measure, district):
            for code, effect in measure["effects"].items():
                delta = effect * share
                values[target][code] += delta
                contributions.append({"source": measure_id, "district": target, "indicator": code, "delta": round(delta, 4)})
    chosen = dict(plan)
    for synergy in data["synergies"]:
        left, right = synergy["pair"]
        if left in chosen and right in chosen:
            for target in targets(measures[left], chosen[left]):
                values[target][synergy["indicator"]] += synergy["bonus"]
                contributions.append({"source": f"{left}+{right}", "district": target,
                                      "indicator": synergy["indicator"], "delta": synergy["bonus"]})

    event_info = None
    if event_id:
        event = next((e for e in data["events"]["catalog"] if e["id"] == event_id), None)
        if event is None:
            return {"valid": False, "error_code": "UNKNOWN_EVENT", "error": f"Неизвестное событие {event_id}"}
        reserve = data["rules"]["budget"] - cost(data, plan)
        response = 0.0
        if buy_response:
            if event["response"]["cost"] > reserve:
                return {"valid": False, "error_code": "RESPONSE_OVER_BUDGET",
                        "error": f"Реакция стоит {event['response']['cost']}, резерв {reserve}"}
            response = event["response"]["reduction"]
        all_districts = [d["id"] for d in data["districts"]]
        fired = []
        for impact in event["impacts"]:
            impacted = all_districts if impact["districts"] == "all" else impact["districts"]
            for target in impacted:
                for code, damage in impact["effects"].items():
                    protection = 0.0
                    protecting_measure = None
                    for mitigation in event["mitigations"]:
                        measure_id = mitigation["measure"]
                        if measure_id not in chosen:
                            continue
                        if measures[measure_id]["type"] == "district" and chosen[measure_id] != target:
                            continue
                        if "indicators" in mitigation and code not in mitigation["indicators"]:
                            continue
                        if mitigation["reduction"] > protection:
                            protection = mitigation["reduction"]
                            protecting_measure = measure_id
                    delta = damage * (1 - protection) * (1 - response)
                    values[target][code] += delta
                    contributions.append({"source": event_id, "district": target, "indicator": code, "delta": round(delta, 4)})
                    if protecting_measure:
                        fired.append({"measure": protecting_measure, "district": target, "indicator": code,
                                      "reduction": protection})
        event_info = {"id": event_id, "reserve": reserve, "response_bought": buy_response,
                      "mitigations_fired": fired}

    for target in values:
        for code in codes:
            values[target][code] = max(0.0, min(100.0, values[target][code]))
    district_scores = {target: sum(weights[code] * values[target][code] for code in codes) for target in values}
    population = {d["id"]: d["pop_share"] for d in data["districts"]}
    d_avg = sum(population[target] * district_scores[target] for target in district_scores)
    critical = [(target, code) for target in values for code in codes
                if values[target][code] < data["rules"]["critical_threshold"]]
    score = 0.7 * d_avg + 0.3 * min(district_scores.values()) - data["rules"]["critical_penalty"] * len(critical)
    total = cost(data, plan)
    return {
        "valid": True, "score": score, "d_avg": d_avg,
        "district_scores": district_scores,
        "weakest_district": min(district_scores, key=district_scores.get),
        "critical": critical, "indicators_before": before, "indicators_after": values,
        "natural_units": natural_values(data, before, values),
        "cost": total, "remaining": data["rules"]["budget"] - total,
        "contributions": contributions, "event": event_info,
    }
