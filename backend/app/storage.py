"""SQLite leaderboard with one latest submission per team."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "leaderboard.sqlite3"


def db_path() -> Path:
    return Path(os.environ.get("LEADERBOARD_DB", DEFAULT_DB))


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE IF NOT EXISTS submissions (
        team_name TEXT PRIMARY KEY, plan TEXT NOT NULL, score REAL NOT NULL,
        percentile REAL NOT NULL, resilience_average REAL NOT NULL,
        strategy TEXT NOT NULL, submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    return connection


def save(team_name: str, plan: list[dict], score: float, percentile: float,
         resilience_average: float, strategy: str) -> None:
    with _connect() as connection:
        connection.execute("""INSERT INTO submissions
            (team_name, plan, score, percentile, resilience_average, strategy)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_name) DO UPDATE SET plan=excluded.plan, score=excluded.score,
            percentile=excluded.percentile, resilience_average=excluded.resilience_average,
            strategy=excluded.strategy, submitted_at=CURRENT_TIMESTAMP""",
            (team_name, json.dumps(plan, ensure_ascii=False), score, percentile,
             resilience_average, strategy))


def leaderboard(sort: str = "score") -> list[dict]:
    order = "resilience_average" if sort == "resilience" else "score"
    with _connect() as connection:
        rows = connection.execute(f"SELECT team_name, score, percentile, resilience_average, strategy, submitted_at "
                                  f"FROM submissions ORDER BY {order} DESC, submitted_at ASC").fetchall()
    return [dict(row) for row in rows]
