"""Engine-owned facts that explanations may reference."""

from __future__ import annotations

from app.engine.simulator import simulate
from app.engine.validator import Plan


def build_facts(data: dict, plan: Plan, result: dict, *, context: dict | None = None,
                events: dict | None = None, original_result: dict | None = None) -> dict[str, str]:
    baseline = simulate(data, [], check=False)
    facts = {
        "base_score": f"{baseline['score']:.2f}",
        "threshold": str(data["rules"]["critical_threshold"]),
        "horizon": str(data["rules"]["horizon_quarters"]),
        "score": f"{result['score']:.2f}",
        "score_delta_vs_base": f"{result['score'] - baseline['score']:+.2f}",
        "cost": str(result["cost"]),
        "remaining": str(result["remaining"]),
        "critical_count": str(len(result["critical"])),
        "weakest_district": next(d["name"] for d in data["districts"] if d["id"] == result["weakest_district"]),
    }
    for district in data["districts"]:
        district_id = district["id"]
        facts[f"district.{district_id}.name"] = district["name"]
        facts[f"district.{district_id}.score_before"] = f"{baseline['district_scores'][district_id]:.2f}"
        facts[f"district.{district_id}.score_after"] = f"{result['district_scores'][district_id]:.2f}"
        for code, values in result["natural_units"][district_id].items():
            facts[f"indicator.{code}.name"] = values["name"]
            facts[f"district.{district_id}.{code}.score_after"] = f"{result['indicators_after'][district_id][code]:.2f}"
            facts[f"district.{district_id}.{code}.raw_before"] = f"{values['before']:.1f} {values['unit']}"
            facts[f"district.{district_id}.{code}.raw_after"] = f"{values['after']:.1f} {values['unit']}"
    measures = {m["id"]: m for m in data["measures"]}
    for measure_id, _ in plan:
        for key in ("name", "cost", "lag", "risks"):
            facts[f"measure.{measure_id}.{key}"] = str(measures[measure_id][key])
        facts[f"measure.{measure_id}.realized"] = f"{measures[measure_id]['realized_share'] * 100:g}%"
    for index, contribution in enumerate(result["contributions"]):
        facts[f"contribution.{index}.delta"] = f"{contribution['delta']:+.2f}"
    if context:
        facts.update({"percentile": f"{context['percentile']:.2f}%", "rank": str(context["rank"]),
                      "best_score": f"{context['best_score']:.2f}", "gap": f"{context['gap']:.2f}"})
    if events:
        facts["stress_average"] = f"{events['average']:.2f}"
        facts["stress_worst"] = f"{events['worst']:.2f}"
        for event in events["events"]:
            facts[f"event.{event['id']}.name"] = event["name"]
            facts[f"event.{event['id']}.delta"] = f"{event['delta']:+.2f}"
            facts[f"event.{event['id']}.critical_count"] = str(event["n_critical"])
            facts[f"event.{event['id']}.score"] = f"{event['score']:.2f}"
    if original_result:
        facts["original_score"] = f"{original_result['score']:.2f}"
        facts["improvement"] = f"{result['score'] - original_result['score']:+.2f}"
        facts["original_remaining"] = str(original_result["remaining"])
    return facts
