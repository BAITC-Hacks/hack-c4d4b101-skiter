from __future__ import annotations

import os
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.engine.dataset import load
from app.engine.score import score_plan
from app.engine.validate import total_cost, validate
from app.schemas import (
    CritCell,
    Decision,
    DistrictResult,
    EffectLine,
    IndicatorValue,
    MeasureContribution,
    SimulateRequest,
    SimulateResponse,
    SynergyApplied,
    Violation,
)

SYSTEM_PROMPT = """Ты — аппарат акима. Готовишь служебный доклад вышестоящему руководству по итогам симуляции. Не чат-бот.

Источник истины — только JSON симулятора и каталог мер ниже. Не считай заново и не добавляй эффектов, которых нет во входе.

Тон: официальный устный доклад на совещании. Спокойно, ясно, по делу. Без маркетинга, без обращения к пользователю, без метакомментариев о модели, промпте, JSON, API и симуляторе.

Жёсткий запрет на формулировки вида:
«проверить симулятором», «итог не утверждаю», «направить на повторный расчёт», «движок посчитает», «каталог не передан», «по имеющимся данным нельзя подтвердить». Таких фраз в докладе быть не должно — ни в конце, ни внутри.

Меры — полным названием из каталога, районы — по имени. Коды мер и кодов показателей в тексте не используй.

Опора доклада — эффекты пакета на город. Из JSON извлеки:
- допустим ли набор; если нет — только суть нарушения и стоп;
- что изменилось в затронутых районах (дороги, транспорт, зелень, воздух, школы, поликлиники, безопасность улиц и дорог, ЖКХ, обращения);
- вклад выбранных мер, в том числе если мера ещё не раскрылась полностью — скажи это обычными словами;
- сработали ли связки мер и где это видно;
- слабейший район, остались ли критические провалы;
- какие болевые точки пакет не тронул.

Цифры только из JSON, только рядом с выводом. Чужие не выдумывай.

Структура с этими заголовками:

Исход и решение
Допустим ли пакет. Чем закончилась попытка для города в целом. Закрыты ли критические провалы. Стоимость относительно бюджета — одной фразой.

Влияние на город
Сначала город, затем районы, которых коснулись меры. По каждому: что улучшилось или ухудшилось и за счёт каких мер. Общегородские меры — отдельно, как они разошлись по районам. Отрицательный эффект называй прямо.

Что дало результат и что нет
Свяжи меры с эффектами: что закрыло провал, что сработало в связке, что слабо раскрылось из-за срока. Не пересказывай весь каталог.

Риски для руководства
Слабейший район как ограничение города. Какие темы там по-прежнему тянут вниз.

Объём — примерно одна страница устной речи. Не извиняйся. Не пиши, что ты модель.

Каталог мер: {MEASURES_JSON}
Результат симулятора: {SIMULATE_JSON}"""

app = FastAPI(title="Аким на 5 часов")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_env_loaded = False


def _load_env() -> None:
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    root = Path(__file__).resolve().parents[2]
    backend = Path(__file__).resolve().parents[1]
    for path in (root / ".env", backend / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _r2(value: float) -> float:
    return round(value, 2)


def _r4(value: float) -> float:
    return round(value, 4)


def _public(current: dict, baseline: dict) -> SimulateResponse:
    score = _r2(current["score"])
    baseline_score = _r2(baseline["score"])
    districts = {
        district_id: DistrictResult(
            name=district["name"],
            pop=district["pop"],
            d_before=_r2(district["d_before"]),
            d_after=_r2(district["d_after"]),
            indicators={
                key: IndicatorValue(name=item["name"], before=_r2(item["before"]), after=_r4(item["after"]))
                for key, item in district["indicators"].items()
            },
        )
        for district_id, district in current["districts"].items()
    }
    return SimulateResponse(
        valid=True,
        cost=current["cost"],
        budget=load()["budget"],
        score=score,
        baseline_score=baseline_score,
        delta_vs_baseline=round(score - baseline_score, 2),
        d_avg=_r2(current["d_avg"]),
        d_min=_r2(current["d_min"]),
        n_crit=current["n_crit"],
        weakest_district=current["weakest_district"],
        weakest_district_name=current["weakest_district_name"],
        districts=districts,
        measure_contributions=[
            MeasureContribution(
                measure_id=item["measure_id"],
                name=item["name"],
                district=item["district"],
                cost=item["cost"],
                lag=item["lag"],
                realized_fraction=_r4(item["realized_fraction"]),
                effects=[
                    EffectLine(
                        district=effect["district"],
                        indicator=effect["indicator"],
                        delta=_r4(effect["delta"]),
                    )
                    for effect in item["effects"]
                ],
            )
            for item in current["measure_contributions"]
        ],
        synergies_applied=[
            SynergyApplied(
                measures=item["measures"],
                indicator=item["indicator"],
                delta=item["delta"],
                district=item["district"],
            )
            for item in current["synergies_applied"]
        ],
        crits=[CritCell(**{**cell, "value": _r4(cell["value"])}) for cell in current["crits"]],
        violations=[],
    )


def _invalid(decisions: list[Decision], violations: list[dict]) -> SimulateResponse:
    return SimulateResponse(
        valid=False,
        cost=total_cost([item.model_dump() for item in decisions]),
        budget=load()["budget"],
        violations=[Violation(**item) for item in violations],
    )


@app.get("/catalog")
def catalog() -> dict:
    data = load()
    direction_names = {item["id"]: item["name"] for item in data["directions"]}
    return {
        "budget": data["budget"],
        "horizon": data["horizon"],
        "max_decisions": data["max_decisions"],
        "max_per_direction": data["max_per_direction"],
        "indicators": [{"id": item["id"], "name": item["name"]} for item in data["indicators"]],
        "districts": [{"id": item["id"], "name": item["name"], "pop": item["pop"]} for item in data["districts"]],
        "measures": [
            {
                "id": item["id"],
                "name": item["name"],
                "direction": item["direction"],
                "direction_name": direction_names[item["direction"]],
                "type": item["type"],
                "cost": item["cost"],
                "lag": item["lag"],
                "effects": item["effects"],
            }
            for item in data["measures"]
        ],
        "incompatibilities": data["incompatibilities"],
    }


@app.post("/simulate", response_model=SimulateResponse)
def simulate(body: SimulateRequest) -> SimulateResponse:
    violations = validate(body.decisions)
    if violations:
        return _invalid(body.decisions, violations)
    return _public(score_plan(body.decisions), score_plan([]))


@app.post("/explain")
def explain(payload: SimulateResponse) -> dict:
    if not payload.valid or payload.score is None:
        raise HTTPException(status_code=400, detail="Нужен валидный ответ /simulate")
    _load_env()
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="Не задан OPENAI_API_KEY")
    model = os.environ.get("OPENAI_MODEL", "").strip() or "gpt-4o-mini"
    base = (os.environ.get("OPENAI_BASE_URL", "").strip() or "https://api.openai.com/v1").rstrip("/")
    try:
        response = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": payload.model_dump_json()},
                ],
            },
            timeout=90,
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="LLM не ответил")
    if response.status_code >= 400:
        detail = "LLM не ответил"
        try:
            detail = response.json()["error"]["message"]
        except (ValueError, KeyError, TypeError):
            pass
        raise HTTPException(status_code=502, detail=detail)
    try:
        text = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError, TypeError):
        raise HTTPException(status_code=502, detail="LLM не ответил")
    if not text:
        raise HTTPException(status_code=502, detail="LLM не ответил")
    return {"explanation": text}
