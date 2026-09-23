from __future__ import annotations

from collections import Counter

from app.engine.dataset import load


def normalize(decisions: list) -> list[dict]:
    out = []
    for item in decisions:
        if isinstance(item, dict):
            raw_id = item.get("measure_id")
            raw_district = item.get("district")
        else:
            raw_id = getattr(item, "measure_id", None)
            raw_district = getattr(item, "district", None)
        measure_id = str(raw_id).strip().upper() if raw_id is not None else ""
        if isinstance(raw_district, str):
            district = raw_district.strip().lower() or None
        else:
            district = None
        out.append({"measure_id": measure_id, "district": district})
    return out


def total_cost(decisions: list) -> int:
    data = load()
    measures = {m["id"]: m for m in data["measures"]}
    return sum(measures[d["measure_id"]]["cost"] for d in normalize(decisions) if d["measure_id"] in measures)


def validate(decisions: list) -> list[dict]:
    data = load()
    decs = normalize(decisions)
    measures = {m["id"]: m for m in data["measures"]}
    districts = {d["id"] for d in data["districts"]}
    directions = {d["id"]: d["name"] for d in data["directions"]}
    violations: list[dict] = []

    if len(decs) != data["max_decisions"]:
        violations.append({
            "code": "WRONG_COUNT",
            "message": f"Нужно ровно {data['max_decisions']} решений, получено {len(decs)}",
        })

    counts = Counter(d["measure_id"] for d in decs)
    for measure_id, count in counts.items():
        if measure_id in measures and count > 1:
            violations.append({
                "code": "DUPLICATE_MEASURE",
                "message": f"Мера {measure_id} выбрана более одного раза",
            })

    seen_unknown: set[str] = set()
    for dec in decs:
        measure = measures.get(dec["measure_id"])
        if measure is None:
            if dec["measure_id"] not in seen_unknown:
                seen_unknown.add(dec["measure_id"])
                violations.append({
                    "code": "UNKNOWN_MEASURE",
                    "message": f"Неизвестная мера {dec['measure_id'] or '—'}",
                })
            continue
        if measure["type"] == "district":
            if not dec["district"]:
                violations.append({
                    "code": "DISTRICT_REQUIRED",
                    "message": f"Для меры {measure['id']} нужно указать район",
                })
            elif dec["district"] not in districts:
                violations.append({
                    "code": "UNKNOWN_DISTRICT",
                    "message": f"Неизвестный район «{dec['district']}» у меры {measure['id']}",
                })
        elif dec["district"]:
            violations.append({
                "code": "DISTRICT_FORBIDDEN",
                "message": f"Для городской меры {measure['id']} район указывать нельзя",
            })

    cost = total_cost(decs)
    if cost > data["budget"]:
        violations.append({
            "code": "OVER_BUDGET",
            "message": f"Стоимость {cost} больше бюджета {data['budget']}",
        })

    direction_counts: Counter[str] = Counter()
    for dec in decs:
        measure = measures.get(dec["measure_id"])
        if measure:
            direction_counts[measure["direction"]] += 1
    for direction, count in direction_counts.items():
        if count > data["max_per_direction"]:
            violations.append({
                "code": "DIRECTION_LIMIT",
                "message": (
                    f"Направление «{directions[direction]}»: {count} меры, "
                    f"максимум {data['max_per_direction']}"
                ),
            })

    chosen = {dec["measure_id"]: dec for dec in decs}
    for rule in data["incompatibilities"]:
        left, right = rule["measures"]
        if left not in chosen or right not in chosen:
            continue
        if rule["scope"] == "any":
            violations.append({"code": rule["code"], "message": rule["message"]})
            continue
        left_district = chosen[left]["district"]
        right_district = chosen[right]["district"]
        if left_district and left_district == right_district:
            violations.append({"code": rule["code"], "message": rule["message"]})

    return violations
