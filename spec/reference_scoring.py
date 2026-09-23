"""Эталонный расчёт Astana Quality of Life Score по city_dataset.json.

Использование:
    python reference_scoring.py            # прогон тест-кейсов из test_cases.json
Как библиотека:
    from reference_scoring import load, validate, simulate, apply_event
    plan = [("M7", "nura"), ("M8", "nura"), ("M10", "nura"), ("M12", None), ("M5", "saryarka")]
"""
import json, os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))

def load(path=os.path.join(HERE, "city_dataset.json")):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def validate(data, plan):
    """Возвращает (код, текст) нарушения или None, если набор валиден."""
    R = data["rules"]; M = {m["id"]: m for m in data["measures"]}
    D = {d["id"] for d in data["districts"]}
    ids = [m for m, _ in plan]
    if len(plan) != R["decisions_exact"]:
        return "WRONG_COUNT", f"Нужно ровно {R['decisions_exact']} мер, выбрано {len(plan)}"
    for m in ids:
        if m not in M: return "UNKNOWN_MEASURE", f"Неизвестная мера {m}"
    dup = [m for m, c in Counter(ids).items() if c > 1]
    if dup: return "DUPLICATE", f"Мера {dup[0]} выбрана повторно"
    for m, d in plan:
        if M[m]["type"] == "district" and d is None:
            return "DISTRICT_REQUIRED", f"{m}: нужно указать район"
        if M[m]["type"] == "city" and d is not None:
            return "DISTRICT_NOT_ALLOWED", f"{m}: городская мера, район не указывается"
        if d is not None and d not in D:
            return "UNKNOWN_DISTRICT", f"{m}: неизвестный район {d}"
    cost = sum(M[m]["cost"] for m in ids)
    if cost > R["budget"]:
        return "OVER_BUDGET", f"Стоимость {cost} превышает бюджет {R['budget']}"
    per_dir = Counter(M[m]["direction"] for m in ids)
    for dr, c in per_dir.items():
        if c > R["max_per_direction"]:
            return "DIRECTION_LIMIT", f"Направление {dr}: {c} мер, максимум {R['max_per_direction']}"
    p = dict(plan)
    for inc in data["incompatibilities"]:
        a, b = inc["pair"]
        if a in p and b in p and (inc["scope"] == "any" or p[a] == p[b]):
            return "INCOMPATIBLE", f"{a} и {b} несовместимы: {inc['why']}"
    return None

def _targets(data, m, d):
    return [x["id"] for x in data["districts"]] if m["type"] == "city" else [d]

def simulate(data, plan, event_id=None, buy_response=False, check=True):
    """Считает Score. plan: список (measure_id, district_id|None).
    check=False позволяет посчитать базовый сценарий (пустой план)."""
    if check:
        err = validate(data, plan)
        if err: return {"valid": False, "error_code": err[0], "error": err[1]}
    M = {m["id"]: m for m in data["measures"]}
    K = [i["code"] for i in data["indicators"]]; W = {i["code"]: i["weight"] for i in data["indicators"]}
    H = data["rules"]["horizon_quarters"]
    val = {d["id"]: dict(d["indicators"]) for d in data["districts"]}
    contrib = []  # вклад каждой меры для объяснения AI
    for mid, d in plan:
        m = M[mid]; k_real = (H - m["lag"]) / H
        for t in _targets(data, m, d):
            for k, e in m["effects"].items():
                val[t][k] += e * k_real
                contrib.append({"source": mid, "district": t, "indicator": k, "delta": round(e * k_real, 4)})
    p = dict(plan)
    for s in data["synergies"]:
        a, b = s["pair"]
        if a in p and b in p:
            for t in _targets(data, M[a], p[a]):
                val[t][s["indicator"]] += s["bonus"]
                contrib.append({"source": f"{a}+{b}", "district": t, "indicator": s["indicator"], "delta": s["bonus"]})
    event_info = None
    if event_id:
        ev = next(e for e in data["events"]["catalog"] if e["id"] == event_id)
        cost = sum(M[m]["cost"] for m, _ in plan)
        reserve = data["rules"]["budget"] - cost
        resp = 0.0
        if buy_response:
            if ev["response"]["cost"] > reserve:
                return {"valid": False, "error_code": "RESPONSE_OVER_BUDGET",
                        "error": f"Реакция стоит {ev['response']['cost']}, резерв {reserve}"}
            resp = ev["response"]["reduction"]
        all_ids = [x["id"] for x in data["districts"]]
        for imp in ev["impacts"]:
            tgts = all_ids if imp["districts"] == "all" else imp["districts"]
            for t in tgts:
                for k, dmg in imp["effects"].items():
                    prot = 0.0
                    for mit in ev["mitigations"]:
                        mid = mit["measure"]
                        if mid not in p: continue
                        if M[mid]["type"] == "district" and p[mid] != t: continue
                        if "indicators" in mit and k not in mit["indicators"]: continue
                        prot = max(prot, mit["reduction"])
                    delta = dmg * (1 - prot) * (1 - resp)
                    val[t][k] += delta
                    contrib.append({"source": event_id, "district": t, "indicator": k, "delta": round(delta, 4)})
        event_info = {"id": event_id, "reserve": reserve, "response_bought": buy_response}
    for t in val:
        for k in K: val[t][k] = max(0.0, min(100.0, val[t][k]))
    Dd = {t: sum(W[k] * val[t][k] for k in K) for t in val}
    pop = {d["id"]: d["pop_share"] for d in data["districts"]}
    d_avg = sum(pop[t] * Dd[t] for t in Dd)
    crit = [(t, k) for t in val for k in K if val[t][k] < data["rules"]["critical_threshold"]]
    score = 0.7 * d_avg + 0.3 * min(Dd.values()) - data["rules"]["critical_penalty"] * len(crit)
    return {"valid": True, "score": score, "d_avg": d_avg, "district_scores": Dd,
            "weakest_district": min(Dd, key=Dd.get), "critical": crit, "indicators": val,
            "cost": sum(M[m]["cost"] for m, _ in plan), "contributions": contrib, "event": event_info}

def _plan(tc): return [(x["measure"], x.get("district")) for x in tc["plan"]]

if __name__ == "__main__":
    data = load()
    tcs = json.load(open(os.path.join(HERE, "test_cases.json"), encoding="utf-8"))
    ok = 0
    for tc in tcs:
        r = simulate(data, _plan(tc), tc.get("event"), tc.get("buy_response", False), check=tc.get("check", True))
        exp = tc["expected"]
        if exp["valid"]:
            good = r["valid"] and abs(round(r["score"], 2) - exp["score"]) < 1e-9
            got = round(r["score"], 2) if r["valid"] else r["error_code"]
        else:
            good = (not r["valid"]) and r["error_code"] == exp["error_code"]
            got = r.get("error_code", round(r.get("score", 0), 2))
        ok += good
        print(("PASS" if good else "FAIL"), tc["id"], tc["title"], "->", got)
    print(f"{ok}/{len(tcs)} passed")
