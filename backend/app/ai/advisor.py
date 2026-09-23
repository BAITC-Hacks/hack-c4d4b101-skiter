"""Bounded advisor: every candidate is checked by the deterministic engine."""

from __future__ import annotations

import json

import httpx

from app.ai.explainer import explain
from app.ai.llm import available, chat
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
    if available():
        messages = [{"role": "system", "content": (
            "Find a valid higher-scoring plan. Numbers come only from the simulate/validate tools; "
            "never calculate or invent them. Call tools for every proposal. Use at most six tool calls.")},
            {"role": "user", "content": json.dumps({"plan": trace[0]["plan"],
                                                       "score": original["score"]}, ensure_ascii=False)}]
        try:
            calls = 0
            while calls < 6:
                response = chat(messages, tools=TOOLS)
                tool_calls = response.get("tool_calls") or []
                if not tool_calls:
                    break
                messages.append(response)
                for tool_call in tool_calls:
                    if calls >= 6:
                        break
                    calls += 1
                    name = tool_call["function"]["name"]
                    candidate = normalize(json.loads(tool_call["function"]["arguments"])["plan"])
                    checked = validation_result(data, candidate)
                    if name == "simulate" and checked["valid"]:
                        result = simulate(data, candidate, check=False)
                        entry = {"plan": [{"measure": m, "district": d} for m, d in candidate],
                                 "valid": True, "score": result["score"], "source": "tool"}
                        if result["score"] > best_result["score"]:
                            best_plan, best_result = candidate, result
                    else:
                        entry = {"plan": [{"measure": m, "district": d} for m, d in candidate],
                                 **checked, "source": "tool"}
                    trace.append(entry)
                    messages.append({"role": "tool", "tool_call_id": tool_call["id"],
                                     "content": json.dumps(entry, ensure_ascii=False)})
        except (KeyError, TypeError, ValueError, RuntimeError, OSError, httpx.HTTPError):
            pass
    fallback = best_single_swap(data, plan)
    if fallback["score"] > best_result["score"]:
        best_plan = normalize(fallback["plan"])
        best_result = simulate(data, best_plan)
        trace.append({"plan": fallback["plan"], "valid": True,
                      "score": best_result["score"], "source": "verified_swap"})
    # Re-simulate the chosen plan so the returned score never depends on an LLM response.
    verified = simulate(data, best_plan)
    return {"valid": True, "trace": trace,
            "best_plan": [{"measure": m, "district": d} for m, d in best_plan],
            "best_score": verified["score"], "improvement": verified["score"] - original["score"],
            "explanation": explain(data, best_plan, verified)}
