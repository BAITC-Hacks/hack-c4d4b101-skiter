"""Load the immutable city specification used by every calculation."""

from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "spec" / "city_dataset.json"


def dataset_path() -> Path:
    return Path(os.environ.get("CITY_DATASET_PATH", DEFAULT_PATH))


@lru_cache(maxsize=8)
def _read(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    required = {"rules", "indicators", "districts", "measures", "synergies", "incompatibilities", "events"}
    if not required.issubset(data):
        raise ValueError(f"Incomplete city dataset: {required - data.keys()}")
    if not data["districts"] or not data["indicators"]:
        raise ValueError("City dataset needs districts and indicators")
    return data


def load(path: str | Path | None = None) -> dict:
    return _read(str(Path(path) if path is not None else dataset_path()))


def dataset_hash(path: str | Path | None = None) -> str:
    return hashlib.sha256(Path(path or dataset_path()).read_bytes()).hexdigest()
