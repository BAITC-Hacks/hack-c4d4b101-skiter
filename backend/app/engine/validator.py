"""Dataset-driven plan validation in the reference implementation's order."""

from __future__ import annotations

from collections import Counter
from typing import Any

Plan = list[tuple[str, str | None]]


def normalize(plan: list[Any]) -> Plan:
    result = []
    for item in plan:
        if isinstance(item, (tuple, list)):
            measure, district = item
        elif isinstance(item, dict):
            measure, district = item.get("measure", item.get("measure_id")), item.get("district")
        else:
            measure, district = getattr(item, "measure", None), getattr(item, "district", None)
        result.append((measure, district))
    return result


def cost(data: dict, plan: Plan) -> int:
    measures = {m["id"]: m for m in data["measures"]}
    return sum(measures[m]["cost"] for m, _ in plan if m in measures)


def validate(data: dict, plan: Plan) -> tuple[str, str] | None:
    rules = data["rules"]
    measures = {m["id"]: m for m in data["measures"]}
    districts = {d["id"] for d in data["districts"]}
    ids = [m for m, _ in plan]
    if len(plan) != rules["decisions_exact"]:
        return "WRONG_COUNT", f"Нужно ровно {rules['decisions_exact']} мер, выбрано {len(plan)}"
    for measure in ids:
        if measure not in measures:
            return "UNKNOWN_MEASURE", f"Неизвестная мера {measure}"
    duplicate = [m for m, count in Counter(ids).items() if count > 1]
    if duplicate:
        return "DUPLICATE", f"Мера {duplicate[0]} выбрана повторно"
    for measure, district in plan:
        if measures[measure]["type"] == "district" and district is None:
            return "DISTRICT_REQUIRED", f"{measure}: нужно указать район"
        if measures[measure]["type"] == "city" and district is not None:
            return "DISTRICT_NOT_ALLOWED", f"{measure}: городская мера, район не указывается"
        if district is not None and district not in districts:
            return "UNKNOWN_DISTRICT", f"{measure}: неизвестный район {district}"
    total = cost(data, plan)
    if total > rules["budget"]:
        return "OVER_BUDGET", f"Стоимость {total} превышает бюджет {rules['budget']}"
    for direction, count in Counter(measures[m]["direction"] for m in ids).items():
        if count > rules["max_per_direction"]:
            return "DIRECTION_LIMIT", f"Направление {direction}: {count} мер, максимум {rules['max_per_direction']}"
    chosen = dict(plan)
    for incompatibility in data["incompatibilities"]:
        left, right = incompatibility["pair"]
        if left in chosen and right in chosen and (
            incompatibility["scope"] == "any" or chosen[left] == chosen[right]
        ):
            return "INCOMPATIBLE", f"{left} и {right} несовместимы: {incompatibility['why']}"
    return None


def validation_result(data: dict, plan: Plan) -> dict:
    error = validate(data, plan)
    total = cost(data, plan)
    return {
        "valid": error is None,
        "error_code": error[0] if error else None,
        "error": error[1] if error else None,
        "cost": total,
        "remaining": data["rules"]["budget"] - total,
    }
