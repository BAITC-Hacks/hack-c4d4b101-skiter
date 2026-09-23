"""Bounded advisor: every candidate is checked by the deterministic engine."""

from __future__ import annotations

import json

import httpx

from app.ai.explainer import explain
from app.ai.llm import available, chat, metadata, add_usage, LLMError
from app.ai.prompts import ADVISOR_PROMPT
from app.engine.events import stress_test
from app.engine.simulator import simulate
from app.engine.space import best_single_swap
from app.engine.validator import Plan, normalize, validation_result

TOOLS = [{"type": "function", "function": {"name": name,
          "description": "Validate or score a complete city plan with the deterministic engine",
          "parameters": {"type": "object", "properties": {"plan": {"type": "array", "items": {
              "type": "object", "properties": {"measure": {"type": "string"},
              "district": {"type": ["string", "null"]}}, "required": ["measure"]}}},
              "required": ["plan"]}}} for name in ("validate", "simulate")]


def advise(data: dict, plan: Plan) -> dict:
    original = simulate(data, plan)
    if not original["valid"]:
        return original
    best_plan, best_result = list(plan), original
    trace = [{"plan": [{"measure": m, "district": d} for m, d in plan],
              "valid": True, "score": original["score"], "source": "original"}]
    usage = metadata()
    usage["message"] = "Поиск ближайшей допустимой альтернативы движком."
    neighbor = best_single_swap(data, plan)
    if neighbor["score"] > best_result["score"]:
        best_plan = normalize(neighbor["plan"])
        best_result = simulate(data, best_plan)
        trace.append({"plan": neighbor["plan"], "valid": True, "score": best_result["score"], "source": "verified_swap"})
    if available():
        messages = [{"role": "system", "content": ADVISOR_PROMPT},
            {"role": "user", "content": json.dumps({"plan": trace[0]["plan"],
                "initial_result": original, "verified_neighbor": neighbor,
                "rules": data["rules"], "measures": data["measures"], "districts": data["districts"],
                "indicators": data["indicators"], "incompatibilities": data["incompatibilities"],
                "synergies": data["synergies"], "events": data["events"]}, ensure_ascii=False)}]
        try:
            calls = 0
            while calls < 6:
                response = chat(messages, tools=TOOLS)
                add_usage(usage, response)
                usage.update(mode="live", message="API ответил на запрос поиска; результаты проверок приведены в ходе проверки.")
                tool_calls = response.get("tool_calls") or []
                if not tool_calls:
                    break
                messages.append(response)
                for tool_call in tool_calls:
                    if calls >= 6:
                        break
                    calls += 1
                    name = tool_call["function"]["name"]
                    try:
                        if name not in ("validate", "simulate"):
                            raise ValueError("Unknown tool")
                        candidate = normalize(json.loads(tool_call["function"]["arguments"])["plan"])
                        checked = validation_result(data, candidate)
                    except (ValueError, TypeError, KeyError, AttributeError):
                        entry = {"valid": False, "error": "Передайте полный план в simulate или validate.", "source": "tool"}
                        trace.append(entry)
                        messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": json.dumps(entry)})
                        continue
                    if name == "simulate" and checked["valid"]:
                        result = simulate(data, candidate, check=False)
                        entry = {"plan": [{"measure": m, "district": d} for m, d in candidate],
                                 "valid": True, "score": result["score"], "source": "tool",
                                 "cost": result["cost"], "remaining": result["remaining"],
                                 "critical": result["critical"], "district_scores": result["district_scores"],
                                 "stress": stress_test(data, candidate)}
                        if result["score"] > best_result["score"]:
                            best_plan, best_result = candidate, result
                    else:
                        entry = {"plan": [{"measure": m, "district": d} for m, d in candidate],
                                 **checked, "source": "tool"}
                    trace.append(entry)
                    messages.append({"role": "tool", "tool_call_id": tool_call["id"],
                                     "content": json.dumps(entry, ensure_ascii=False)})
        except LLMError as error:
            add_usage(usage, {"_usage": error.usage})
            usage.update(mode="fallback", error_code=error.code, message=str(error))
        except (KeyError, TypeError, ValueError, RuntimeError, OSError, httpx.HTTPError):
            usage.update(mode="fallback", error_code="invalid_output", message="Поиск ИИ прерван; выбрана проверенная альтернатива.")
    # Re-simulate the chosen plan so the returned score never depends on an LLM response.
    verified = simulate(data, best_plan)
    original_stress, proposed_stress = stress_test(data, plan), stress_test(data, best_plan)
    comparison = [{"label": label, "before": before, "after": after} for label, before, after in [
        ("Официальный балл", original["score"], verified["score"]),
        ("Стоимость", original["cost"], verified["cost"]),
        ("Резерв", original["remaining"], verified["remaining"]),
        ("Критические показатели", len(original["critical"]), len(verified["critical"])),
        ("Средний стресс-балл", original_stress["average"], proposed_stress["average"]),
        ("Худший стресс-балл", original_stress["worst"], proposed_stress["worst"])]]
    report = explain(data, best_plan, verified, original_result=original, original_plan=plan,
                     use_ai=not usage.get("error_code"))
    return {"valid": True, "trace": trace, "search_ai": usage, "comparison": comparison,
            "removed": [{"measure": m, "district": d} for m, d in plan if (m, d) not in best_plan],
            "added": [{"measure": m, "district": d} for m, d in best_plan if (m, d) not in plan],
            "best_plan": [{"measure": m, "district": d} for m, d in best_plan],
            "best_score": verified["score"], "improvement": verified["score"] - original["score"],
            "explanation": report}
