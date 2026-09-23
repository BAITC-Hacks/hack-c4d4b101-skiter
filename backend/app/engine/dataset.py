from __future__ import annotations

import json
from functools import cache
from pathlib import Path


@cache
def load() -> dict:
    path = Path(__file__).resolve().parents[1] / "data" / "dataset.json"
    return json.loads(path.read_text(encoding="utf-8"))
