"""Render only references to facts; fall back to verified templates."""

from __future__ import annotations

import json
import re

import httpx

from app.ai.facts import build_facts
from app.ai.llm import available, chat, metadata, add_usage, LLMError
from app.ai.prompts import EXPLAINER_PROMPT
from app.engine.events import stress_test
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
    changed_district, changed_code = max(
        ((district, code) for district, values in result["indicators_after"].items() for code in values),
        key=lambda pair: abs(result["indicators_after"][pair[0]][pair[1]] -
                             result["indicators_before"][pair[0]][pair[1]]),
    )
    risks = [f"{{{{district.{d}.name}}}}: {{{{indicator.{code}.name}}}} — "
             f"{{{{district.{d}.{code}.raw_after}}}}; индекс {{{{district.{d}.{code}.score_after}}}} "
             "ниже критического порога {{threshold}}." for d, code in result["critical"]]
    payload = {
        "summary": "Итоговый балл {{score}}, изменение к базе {{score_delta_vs_base}}. "
                   "Стоимость пакета {{cost}}, резерв {{remaining}}. Критических показателей: {{critical_count}}.",
        "strengths": [f"{{{{measure.{m}.name}}}}: реализуется {{{{measure.{m}.realized}}}} эффекта "
                      f"на горизонте {{{{horizon}}}} кварталов; лаг {{{{measure.{m}.lag}}}} кварталов."
                      for m, _ in plan],
        "risks": (risks or ["Критических показателей после выбранных мер нет."]) + [
            f"{{{{measure.{m}.name}}}}: {{{{measure.{m}.risks}}}}" for m, _ in plan],
        "consequences": [f"{{{{district.{d['id']}.name}}}}: районный индекс "
                         f"{{{{district.{d['id']}.score_before}}}} → {{{{district.{d['id']}.score_after}}}}."
                         for d in data["districts"]] + [
                         f"Наибольшее изменение индекса: {{{{district.{changed_district}.name}}}}, "
                         f"{{{{indicator.{changed_code}.name}}}}: "
                         f"{{{{district.{changed_district}.{changed_code}.raw_before}}}} → "
                         f"{{{{district.{changed_district}.{changed_code}.raw_after}}}}."],
        "main_tradeoff": "Слабейший район — {{weakest_district}}. Резерв {{remaining}} доступен для реакции "
                         "на отдельное событие. Средний стресс-балл {{stress_average}}, худший {{stress_worst}}. "
                         "Сопоставьте защиту слабого района с резервом на реагирование.",
    }
    if result["remaining"] == 0:
        payload["main_tradeoff"] += " Бюджет исчерпан: платные реакции на события недоступны."
    if "original_score" in facts:
        payload["summary"] += " Исходный план: {{original_score}}, выигрыш проверенной альтернативы {{improvement}}."

    return render_payload(payload, facts)


def explain(data: dict, plan: Plan, result: dict, *, context: dict | None = None,
            original_result: dict | None = None, original_plan: Plan | None = None,
            use_ai: bool = True) -> dict:
    events = stress_test(data, plan)
    facts = build_facts(data, plan, result, context=context, events=events, original_result=original_result)
    usage = metadata()
    usage["message"] = "Расчётный отчёт: API не использован."
    referenced_measures = {p[0] for p in plan + (original_plan or [])}
    cards = [m for m in data["measures"] if m["id"] in referenced_measures]
    for card in cards:
        facts[f"measure.{card['id']}.name"] = card["name"]
    messages = [{"role": "system", "content": EXPLAINER_PROMPT},
                {"role": "user", "content": json.dumps({"plan": plan, "facts": facts,
                 "measures": cards, "districts": data["districts"], "result": result,
                 "events": events, "original_result": original_result, "original_plan": original_plan},
                 ensure_ascii=False)}]
    if use_ai and available():
        for _ in range(2):
            try:
                message = chat(messages)
                add_usage(usage, message)
                content = message["content"].strip()
                if content.startswith("```"):
                    content = content.strip("`").removeprefix("json").strip()
                rendered = render_payload(json.loads(content), facts)
                usage.update(mode="live", message="Доклад подготовлен ИИ; числа взяты из расчёта.")
                return {**rendered, "ai": usage}
            except LLMError as error:
                add_usage(usage, {"_usage": error.usage})
                usage.update(error_code=error.code, message=str(error))
                break
            except (ValueError, KeyError, TypeError, RuntimeError, OSError, httpx.HTTPError):
                usage.update(error_code="invalid_output", message="Ответ ИИ не прошёл проверку. Показан расчётный отчёт.")
                messages.append({"role": "user", "content": "Invalid output. Return all JSON fields; use existing fact placeholders for every number."})
    return {**fallback(data, plan, result, facts), "ai": usage}
