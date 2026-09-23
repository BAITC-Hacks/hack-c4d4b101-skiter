"""Build the dataset-hashed score cache used by submit and leaderboard context."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.engine.space import cache_path, load_scores  # noqa: E402


if __name__ == "__main__":
    scores = load_scores()
    print(f"{len(scores)} valid plans; range {scores[0]:.2f}–{scores[-1]:.2f}; {cache_path()}")
