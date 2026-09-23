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
    if model.startswith("gpt-6-"):
        previous = next((item for item in reversed(messages) if item.get("_response_id")), None)
        recent = messages[messages.index(previous) + 1:] if previous else messages
        inputs = [{"type": "function_call_output", "call_id": item["tool_call_id"],
                   "output": item["content"]} if item["role"] == "tool" else
                  {"role": item["role"], "content": item["content"]}
                  for item in recent if item["role"] != "system"]
        body = {"model": model, "instructions": "\n".join(
            item["content"] for item in messages if item["role"] == "system"),
                "input": inputs, "reasoning": {"effort": "medium"}}
        if previous:
            body["previous_response_id"] = previous["_response_id"]
        if tools:
            body["tools"] = [{"type": "function", **tool["function"]} for tool in tools]
        response = httpx.post(f"{base_url}/responses",
                              headers={"Authorization": f"Bearer {key}"}, json=body, timeout=120)
        response.raise_for_status()
        data = response.json()
        output = data["output"]
        return {"content": "".join(part["text"] for item in output if item["type"] == "message"
                                   for part in item.get("content", []) if part["type"] == "output_text"),
                "tool_calls": [{"id": item["call_id"], "function": {"name": item["name"],
                                "arguments": item["arguments"]}} for item in output
                               if item["type"] == "function_call"],
                "_response_id": data["id"]}
    body = {"model": model, "messages": messages}
    if tools:
        body["tools"] = tools
    response = httpx.post(f"{base_url}/chat/completions",
                          headers={"Authorization": f"Bearer {key}"}, json=body, timeout=60)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]
