"""One replaceable OpenAI-compatible chat client."""

from __future__ import annotations

import httpx

from app.config import llm_settings


def available() -> bool:
    return bool(llm_settings()[1])


def chat(messages: list[dict], *, tools: list[dict] | None = None) -> dict:
    base_url, key, model = llm_settings()
    if not key:
        raise RuntimeError("LLM key is not configured")
    body = {"model": model, "messages": messages}
    if tools:
        body["tools"] = tools
    response = httpx.post(f"{base_url}/chat/completions",
                          headers={"Authorization": f"Bearer {key}"}, json=body, timeout=60)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]
