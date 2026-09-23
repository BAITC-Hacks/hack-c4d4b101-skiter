"""Engine-owned facts that explanations may reference."""

from __future__ import annotations

from app.engine.simulator import simulate
from app.engine.validator import Plan


def build_facts(data: dict, plan: Plan, result: dict, *, context: dict | None = None,
                events: dict | None = None) -> dict[str, str]:
    baseline = simulate(data, [], check=False)
    facts = {
        "score": f"{result['score']:.2f}",
        "score_delta_vs_base": f"{result['score'] - baseline['score']:+.2f}",
        "cost": str(result["cost"]),
        "remaining": str(result["remaining"]),
        "critical_count": str(len(result["critical"])),
        "weakest_district": next(d["name"] for d in data["districts"] if d["id"] == result["weakest_district"]),
    }
    for district in data["districts"]:
        district_id = district["id"]
        facts[f"district.{district_id}.score_after"] = f"{result['district_scores'][district_id]:.2f}"
        for code, values in result["natural_units"][district_id].items():
            facts[f"district.{district_id}.{code}.raw_before"] = f"{values['before']:.1f} {values['unit']}"
            facts[f"district.{district_id}.{code}.raw_after"] = f"{values['after']:.1f} {values['unit']}"
    measures = {m["id"]: m for m in data["measures"]}
    for measure_id, _ in plan:
        facts[f"measure.{measure_id}.cost"] = str(measures[measure_id]["cost"])
    if context:
        facts.update({"percentile": f"{context['percentile']:.2f}%", "rank": str(context["rank"]),
                      "best_score": f"{context['best_score']:.2f}", "gap": f"{context['gap']:.2f}"})
    if events:
        for event in events["events"]:
            facts[f"event.{event['id']}.score"] = f"{event['score']:.2f}"
    return facts
