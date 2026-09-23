from __future__ import annotations

import json

import pytest

from app.ai import advisor, explainer
from app.engine.dataset import load
from app.engine.simulator import simulate

EXAMPLE = [("M7", "nura"), ("M8", "nura"), ("M10", "nura"),
           ("M12", None), ("M5", "saryarka")]


def test_fact_rendering_rejects_unverified_numbers() -> None:
    assert explainer.render_text("Балл {{score}}", {"score": "56.54"}) == "Балл 56.54"
    with pytest.raises(ValueError):
        explainer.render_text("Балл 99", {"score": "56.54"})
    with pytest.raises(ValueError):
        explainer.render_text("{{missing}}", {"score": "56.54"})


def test_fallback_and_advisor_are_verified(monkeypatch) -> None:
    monkeypatch.setattr(explainer, "available", lambda: False)
    monkeypatch.setattr(advisor, "available", lambda: False)
    data = load()
    result = simulate(data, EXAMPLE)
    rendered = explainer.explain(data, EXAMPLE, result)
    assert rendered["verified"]
    assert "56.54" in rendered["summary"]
    advice = advisor.advise(data, EXAMPLE)
    assert advice["valid"]
    verified = simulate(data, [(item["measure"], item["district"]) for item in advice["best_plan"]])
    assert advice["best_score"] == verified["score"]


def test_mocked_llm_cannot_invent_numbers(monkeypatch) -> None:
    monkeypatch.setattr(explainer, "available", lambda: True)
    calls = []
    bad = {"summary": "Балл 999", "strengths": [], "risks": [],
           "consequences": [], "main_tradeoff": "Резерв 500"}

    def fake_chat(messages: list[dict]) -> dict:
        calls.append(messages)
        return {"content": json.dumps(bad)}

    monkeypatch.setattr(explainer, "chat", fake_chat)
    result = explainer.explain(load(), EXAMPLE, simulate(load(), EXAMPLE))
    assert len(calls) == 2
    assert result["verified"]
    assert "999" not in result["summary"]


def test_mocked_advisor_uses_engine_scores(monkeypatch) -> None:
    monkeypatch.setattr(advisor, "available", lambda: True)
    monkeypatch.setattr(explainer, "available", lambda: False)
    candidate = [{"measure": measure, "district": district} for measure, district in EXAMPLE]
    candidate[-1] = {"measure": "M3", "district": "nura"}
    responses = iter([
        {"tool_calls": [{"id": "call_1", "function": {"name": "simulate",
            "arguments": json.dumps({"plan": candidate})}}]},
        {"content": "done"},
    ])
    monkeypatch.setattr(advisor, "chat", lambda messages, tools=None: next(responses))
    result = advisor.advise(load(), EXAMPLE)
    assert result["valid"]
    assert len(result["trace"]) >= 2
    assert result["best_score"] == simulate(load(), [(p["measure"], p["district"]) for p in result["best_plan"]])["score"]
