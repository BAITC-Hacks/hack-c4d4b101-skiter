"""Small environment loader for local and container runs."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    for path in (ROOT / ".env", ROOT / "backend" / ".env"):
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def llm_settings() -> tuple[str, str, str]:
    load_env()
    return (os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            os.getenv("LLM_API_KEY", "").strip(), os.getenv("LLM_MODEL", "gpt-4o-mini"))
