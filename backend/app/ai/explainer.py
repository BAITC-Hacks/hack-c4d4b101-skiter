"""Render only references to facts; fall back to verified templates."""

from __future__ import annotations

import json
import re

import httpx

from app.ai.facts import build_facts
from app.ai.llm import available, chat
from app.engine.validator import Plan

PLACEHOLDER = re.compile(r"\{\{([A-Za-z0-9_.]+)\}\}")
CODE = re.compile(r"\b(?:M\d+|[TESBC]\d+|EV\d+)\b")
BARE_NUMBER = re.compile(r"\d")
FIELDS = ("summary", "strengths", "risks", "consequences", "main_tradeoff")


def render_text(text: str, facts: dict[str, str]) -> str:
    ids = PLACEHOLDER.findall(text)
    if any(fact_id not in facts for fact_id in ids):
        raise ValueError("Unknown fact placeholder")
    residue = CODE.sub("", PLACEHOLDER.sub("", text))
    if BARE_NUMBER.search(residue):
        raise ValueError("Bare number in explanation")
    return PLACEHOLDER.sub(lambda match: facts[match.group(1)], text)


def render_payload(payload: dict, facts: dict[str, str]) -> dict:
    if not all(key in payload for key in FIELDS):
        raise ValueError("Missing explanation field")
    result = {}
    for key in FIELDS:
        value = payload[key]
        if key in ("strengths", "risks", "consequences"):
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError("Invalid explanation list")
            result[key] = [render_text(item, facts) for item in value]
        elif isinstance(value, str):
            result[key] = render_text(value, facts)
        else:
            raise ValueError("Invalid explanation text")
    result["verified"] = True
    return result


def fallback(data: dict, plan: Plan, result: dict, facts: dict[str, str]) -> dict:
    weakest = result["weakest_district"]
    indicator = next((code for district, code in result["critical"] if district == weakest), None)
    changed_district, changed_code = max(
        ((district, code) for district, values in result["indicators_after"].items() for code in values),
        key=lambda pair: abs(result["indicators_after"][pair[0]][pair[1]] -
                             result["indicators_before"][pair[0]][pair[1]]),
    )
    district_name = next(d["name"] for d in data["districts"] if d["id"] == changed_district)
    indicator_name = next(item["name"] for item in data["indicators"] if item["code"] == changed_code)
    risk = (f"В слабейшем районе остаётся критический показатель {indicator}: "
            f"{{{{district.{weakest}.{indicator}.raw_after}}}}." if indicator else
            "Критических показателей после выбранных мер нет.")
    payload = {
        "summary": "Итоговый балл {{score}}, изменение к базе {{score_delta_vs_base}}.",
        "strengths": ["План укладывается в бюджет: стоимость {{cost}}, резерв {{remaining}}."],
        "risks": [risk],
        "consequences": ["Слабейший район — {{weakest_district}}; критических показателей {{critical_count}}.",
                         f"{district_name}, {indicator_name}: "
                         f"{{{{district.{changed_district}.{changed_code}.raw_before}}}} → "
                         f"{{{{district.{changed_district}.{changed_code}.raw_after}}}}."],
        "main_tradeoff": "Резерв {{remaining}} можно сохранить для реакции на городское событие.",
    }
    return render_payload(payload, facts)


def explain(data: dict, plan: Plan, result: dict, *, context: dict | None = None) -> dict:
    facts = build_facts(data, plan, result, context=context)
    if not available():
        return fallback(data, plan, result, facts)
    district_profiles = [{"name": d["name"], "profile": d["profile"]} for d in data["districts"]]
    cards = [{"id": m["id"], "description": m["description"], "risks": m["risks"]}
             for m in data["measures"] if m["id"] in {p[0] for p in plan}]
    messages = [{"role": "system", "content": (
        "Explain in Russian. Numbers come only from the facts table, never calculate or invent them. "
        "Use {{fact_id}} placeholders for every number except measure and indicator codes. "
        "Return JSON with summary, strengths[], risks[], consequences[], main_tradeoff.")},
        {"role": "user", "content": json.dumps({"plan": plan, "facts": facts, "measures": cards,
                                               "districts": district_profiles}, ensure_ascii=False)}]
    for _ in range(2):
        try:
            message = chat(messages)
            content = message["content"].strip()
            if content.startswith("```"):
                content = content.strip("`").removeprefix("json").strip()
            return render_payload(json.loads(content), facts)
        except (ValueError, KeyError, TypeError, RuntimeError, OSError, httpx.HTTPError) as error:
            messages.append({"role": "user", "content": f"Invalid output: {error}. Retry with fact placeholders only."})
    return fallback(data, plan, result, facts)
