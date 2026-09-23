"""Run the seven catalog events without changing the official plan score."""

from __future__ import annotations

from app.engine.simulator import simulate
from app.engine.validator import Plan


def stress_test(data: dict, plan: Plan, buy_responses: set[str] | None = None) -> dict:
    bought = buy_responses or set()
    official = simulate(data, plan)
    if not official["valid"]:
        return official
    known = {event["id"] for event in data["events"]["catalog"]}
    unknown = bought - known
    if unknown:
        return {"valid": False, "error_code": "UNKNOWN_EVENT", "error": f"Неизвестное событие {sorted(unknown)[0]}"}
    events = []
    for event in data["events"]["catalog"]:
        result = simulate(data, plan, event_id=event["id"], buy_response=event["id"] in bought)
        if not result["valid"]:
            return result
        events.append({"id": event["id"], "name": event["name"], "score": result["score"],
                       "delta": result["score"] - official["score"],
                       "n_critical": len(result["critical"]),
                       "response_bought": event["id"] in bought,
                       "mitigations_fired": result["event"]["mitigations_fired"]})
    return {"valid": True, "official_score": official["score"], "events": events,
            "average": sum(item["score"] for item in events) / len(events),
            "worst": min(item["score"] for item in events)}
