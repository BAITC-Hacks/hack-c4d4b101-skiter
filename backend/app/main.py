"""HTTP API for the city simulator."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.ai.advisor import advise
from app.ai.explainer import explain
from app.ai.llm import available
from app.engine.dataset import dataset_hash, load
from app.engine.events import stress_test
from app.engine.simulator import simulate
from app.engine.space import best_single_swap, context, load_scores
from app.engine.validator import normalize, validation_result
from app.storage import leaderboard, save


class Decision(BaseModel):
    measure: str
    district: str | None = None


class PlanRequest(BaseModel):
    plan: list[Decision]


class SubmitRequest(PlanRequest):
    team_name: str = Field(min_length=1, max_length=80)


class StressRequest(PlanRequest):
    buy_responses: set[str] = Field(default_factory=set)


def checked_plan(body: PlanRequest) -> tuple[dict, list[tuple[str, str | None]]]:
    data = load()
    plan = normalize(body.plan)
    validation = validation_result(data, plan)
    if not validation["valid"]:
        raise HTTPException(status_code=422, detail={"error_code": validation["error_code"],
                                                      "error": validation["error"]})
    return data, plan


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.scores = load_scores()
    yield


app = FastAPI(title="Аким на 5 часов", lifespan=lifespan)


@app.exception_handler(HTTPException)
async def api_error(_request: Request, error: HTTPException) -> JSONResponse:
    content = error.detail if isinstance(error.detail, dict) else {"error": str(error.detail)}
    return JSONResponse(status_code=error.status_code, content=content)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "llm_mode": "live" if available() else "fallback",
            "dataset_hash": dataset_hash()}


@app.get("/api/state")
def state() -> dict:
    data = load()
    return {"rules": data["rules"], "directions": data["directions"],
            "indicators": data["indicators"], "districts": data["districts"],
            "measures": data["measures"], "events": data["events"]["catalog"],
            "base_score": simulate(data, [], check=False)["score"]}


@app.post("/api/validate")
def validate_plan(body: PlanRequest) -> dict:
    return validation_result(load(), normalize(body.plan))


@app.post("/api/simulate")
def simulate_plan(body: PlanRequest) -> dict:
    data, plan = checked_plan(body)
    return simulate(data, plan)


@app.post("/api/submit")
def submit(body: SubmitRequest) -> dict:
    data, plan = checked_plan(body)
    result = simulate(data, plan)
    scores = getattr(app.state, "scores", None)
    ranked = context(result["score"], scores if scores is not None else load_scores(data))
    swap = best_single_swap(data, plan)
    resilience = stress_test(data, plan)
    team_name = body.team_name.strip()
    if not team_name:
        raise HTTPException(status_code=422, detail={"error_code": "TEAM_REQUIRED", "error": "Укажите команду"})
    measure_names = {m["id"]: m["name"] for m in data["measures"]}
    strategy = ", ".join(measure_names[measure] for measure, _ in plan)
    save(team_name, [item.model_dump() for item in body.plan], result["score"],
         ranked["percentile"], resilience["average"], strategy)
    return {**result, **ranked, "best_single_swap": swap,
            "resilience_average": resilience["average"], "team_name": team_name}


@app.post("/api/explain")
def explain_plan(body: PlanRequest) -> dict:
    data, plan = checked_plan(body)
    result = simulate(data, plan)
    return explain(data, plan, result)


@app.post("/api/advise")
def advise_plan(body: PlanRequest) -> dict:
    data, plan = checked_plan(body)
    return advise(data, plan)


@app.post("/api/stress-test")
def stress_plan(body: StressRequest) -> dict:
    data, plan = checked_plan(body)
    result = stress_test(data, plan, body.buy_responses)
    if not result["valid"]:
        raise HTTPException(status_code=422, detail={"error_code": result["error_code"],
                                                      "error": result["error"]})
    return result


@app.get("/api/leaderboard")
def list_leaderboard(sort: str = "score") -> dict:
    if sort not in ("score", "resilience"):
        raise HTTPException(status_code=422, detail={"error_code": "INVALID_SORT", "error": "Неизвестная сортировка"})
    return {"teams": leaderboard(sort)}
