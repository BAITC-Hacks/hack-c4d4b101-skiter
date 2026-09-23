from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

EXAMPLE = [{"measure": "M7", "district": "nura"},
           {"measure": "M8", "district": "nura"},
           {"measure": "M10", "district": "nura"},
           {"measure": "M12", "district": None},
           {"measure": "M5", "district": "saryarka"}]
OTHER = [{"measure": "M9", "district": "nura"},
         {"measure": "M11", "district": "nura"},
         {"measure": "M10", "district": "nura"},
         {"measure": "M12", "district": None},
         {"measure": "M4", "district": "nura"}]
OVER_BUDGET = [{"measure": "M3", "district": "nura"},
               {"measure": "M13", "district": "almaty"},
               {"measure": "M7", "district": "nura"},
               {"measure": "M8", "district": "saryarka"},
               {"measure": "M2", "district": None}]


def test_api_rules_determinism_and_submission(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LEADERBOARD_DB", str(tmp_path / "leaderboard.sqlite3"))
    monkeypatch.setenv("LLM_API_KEY", "")
    with TestClient(app) as client:
        state = client.get("/api/state").json()
        assert "best_score" not in state
        response = client.post("/api/simulate", json={"plan": OVER_BUDGET})
        assert response.status_code == 422
        assert response.json()["error_code"] == "OVER_BUDGET"
        assert client.post("/api/validate", json={"plan": OVER_BUDGET}).json()["error_code"] == "OVER_BUDGET"
        first = client.post("/api/simulate", json={"plan": EXAMPLE}).json()
        second = client.post("/api/simulate", json={"plan": EXAMPLE}).json()
        assert first["score"] == second["score"]
        submit_a = client.post("/api/submit", json={"team_name": "Команда А", "plan": EXAMPLE})
        submit_b = client.post("/api/submit", json={"team_name": "Команда Б", "plan": EXAMPLE})
        submit_c = client.post("/api/submit", json={"team_name": "Команда В", "plan": OTHER})
        assert submit_a.status_code == submit_b.status_code == submit_c.status_code == 200
        assert submit_a.json()["score"] == submit_b.json()["score"]
        assert submit_c.json()["score"] != submit_a.json()["score"]
        assert len(client.get("/api/leaderboard").json()["teams"]) == 3
        explanation = client.post("/api/explain", json={"plan": EXAMPLE}).json()
        assert explanation["verified"]
