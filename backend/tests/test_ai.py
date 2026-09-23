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


def test_invalid_key_is_visible_and_not_retried(monkeypatch) -> None:
    from app.ai.llm import LLMError
    monkeypatch.setattr(explainer, "available", lambda: True)
    calls = []
    def rejected(messages):
        calls.append(messages)
        raise LLMError("invalid_key", "Ключ отклонён")
    monkeypatch.setattr(explainer, "chat", rejected)
    result = explainer.explain(load(), EXAMPLE, simulate(load(), EXAMPLE))
    assert len(calls) == 1
    assert result["ai"]["mode"] == "fallback"
    assert result["ai"]["error_code"] == "invalid_key"
    assert result["verified"]


def test_responses_tool_continuation_and_usage(monkeypatch) -> None:
    from app.ai import llm
    monkeypatch.setattr(llm, "llm_settings", lambda: ("https://api.openai.com/v1", "test-secret", "gpt-6-sol"))
    requests = []
    def post(path, body):
        requests.append((path, body))
        return {"id": "resp_test", "output": [{"type": "function_call", "name": "simulate", "call_id": "call_test", "arguments": "{}"}],
                "usage": {"input_tokens": 100, "output_tokens": 50, "output_tokens_details": {"reasoning_tokens": 20}}}
    monkeypatch.setattr(llm, "_post", post)
    messages = [{"role": "system", "content": "rules"}, {"role": "user", "content": "plan"}]
    first = llm.chat(messages, tools=advisor.TOOLS)
    assert first["role"] == "assistant"
    assert first["_usage"]["total_tokens"] == 150
    assert first["_usage"]["reasoning_tokens"] == 20
    llm.chat(messages + [first, {"role": "tool", "tool_call_id": "call_test", "content": "verified"}], tools=advisor.TOOLS)
    body = requests[1][1]
    assert body["previous_response_id"] == "resp_test"
    assert body["instructions"] == "rules"
    assert body["input"] == [{"type": "function_call_output", "call_id": "call_test", "output": "verified"}]


def test_advisor_context_and_comparison(monkeypatch) -> None:
    monkeypatch.setattr(advisor, "available", lambda: True)
    monkeypatch.setattr(explainer, "available", lambda: False)
    def response(messages, tools=None):
        payload = json.loads(messages[1]["content"])
        assert len(payload["measures"]) == len(load()["measures"])
        assert payload["rules"] == load()["rules"]
        assert payload["synergies"] and payload["events"]
        return {"role": "assistant", "content": "", "_usage": {"total_tokens": 120}}
    monkeypatch.setattr(advisor, "chat", response)
    result = advisor.advise(load(), EXAMPLE)
    assert result["search_ai"]["total_tokens"] == 120
    assert result["comparison"][0]["after"] == result["best_score"]
    assert result["best_score"] >= result["comparison"][0]["before"]


def test_safe_provider_error_does_not_leak_key(monkeypatch) -> None:
    import httpx
    from app.ai import llm
    monkeypatch.setattr(llm, "llm_settings", lambda: ("https://api.openai.com/v1", "test-secret", "gpt-6-sol"))
    monkeypatch.setattr(llm.httpx, "post", lambda *args, **kwargs: httpx.Response(401,
        json={"error": {"code": "token_invalidated", "message": "key test-secret invalid"}}))
    with pytest.raises(llm.LLMError) as caught:
        llm.chat([{"role": "user", "content": "test"}])
    assert caught.value.code == "invalid_key"
    assert "test-secret" not in str(caught.value)
    assert llm.status()["mode"] == "fallback"
