from fastapi.testclient import TestClient

from app.engine.validate import total_cost, validate
from app.main import app

client = TestClient(app)

GOLDEN = [
    {"measure_id": "M7", "district": "nura"},
    {"measure_id": "M8", "district": "nura"},
    {"measure_id": "M10", "district": "nura"},
    {"measure_id": "M12", "district": None},
    {"measure_id": "M5", "district": "saryarka"},
]


def codes(decisions):
    return {item["code"] for item in validate(decisions)}


def test_golden_set_is_valid():
    assert validate(GOLDEN) == []
    assert total_cost(GOLDEN) == 95


def test_exactly_five_decisions():
    four = GOLDEN[:4]
    assert codes(four) == {"WRONG_COUNT"}
    six = GOLDEN + [{"measure_id": "M4", "district": "yesil"}]
    assert "WRONG_COUNT" in codes(six)


def test_duplicate_measure_ids():
    decisions = [
        {"measure_id": "M9", "district": "nura"},
        {"measure_id": "m9", "district": "yesil"},
        {"measure_id": "M11", "district": "almaty"},
        {"measure_id": "M12", "district": None},
        {"measure_id": "M4", "district": "saryarka"},
    ]
    assert codes(decisions) == {"DUPLICATE_MEASURE"}


def test_unknown_measure():
    decisions = [
        {"measure_id": "M99", "district": "nura"},
        {"measure_id": "M8", "district": "nura"},
        {"measure_id": "M10", "district": "almaty"},
        {"measure_id": "M12", "district": None},
        {"measure_id": "M4", "district": "saryarka"},
    ]
    assert "UNKNOWN_MEASURE" in codes(decisions)


def test_district_required_for_district_measures():
    decisions = [
        {"measure_id": "M4", "district": None},
        {"measure_id": "M8", "district": "nura"},
        {"measure_id": "M10", "district": "almaty"},
        {"measure_id": "M12", "district": None},
        {"measure_id": "M9", "district": "saryarka"},
    ]
    assert codes(decisions) == {"DISTRICT_REQUIRED"}


def test_district_forbidden_for_city_measures():
    decisions = [
        {"measure_id": "M2", "district": "nura"},
        {"measure_id": "M4", "district": "almaty"},
        {"measure_id": "M8", "district": "saryarka"},
        {"measure_id": "M10", "district": "baikonur"},
        {"measure_id": "M9", "district": "yesil"},
    ]
    assert codes(decisions) == {"DISTRICT_FORBIDDEN"}


def test_unknown_district():
    decisions = [
        {"measure_id": "M4", "district": "astana"},
        {"measure_id": "M8", "district": "nura"},
        {"measure_id": "M10", "district": "almaty"},
        {"measure_id": "M12", "district": None},
        {"measure_id": "M9", "district": "saryarka"},
    ]
    assert codes(decisions) == {"UNKNOWN_DISTRICT"}


def test_district_name_case_is_normalized():
    decisions = [
        {"measure_id": "M7", "district": "Nura"},
        {"measure_id": "M8", "district": "NURA"},
        {"measure_id": "M10", "district": "nura"},
        {"measure_id": "M12", "district": None},
        {"measure_id": "M5", "district": "Saryarka"},
    ]
    assert validate(decisions) == []


def test_budget_allows_100_and_rejects_above():
    exact = [
        {"measure_id": "M1", "district": "yesil"},
        {"measure_id": "M6", "district": None},
        {"measure_id": "M7", "district": "nura"},
        {"measure_id": "M9", "district": "almaty"},
        {"measure_id": "M13", "district": "saryarka"},
    ]
    assert total_cost(exact) == 100
    assert validate(exact) == []

    over = [
        {"measure_id": "M3", "district": "nura"},
        {"measure_id": "M5", "district": "almaty"},
        {"measure_id": "M13", "district": "saryarka"},
        {"measure_id": "M7", "district": "baikonur"},
        {"measure_id": "M2", "district": None},
    ]
    assert total_cost(over) == 129
    assert codes(over) == {"OVER_BUDGET"}


def test_max_two_measures_per_direction():
    decisions = [
        {"measure_id": "M4", "district": "nura"},
        {"measure_id": "M5", "district": "almaty"},
        {"measure_id": "M6", "district": None},
        {"measure_id": "M9", "district": "saryarka"},
        {"measure_id": "M10", "district": "baikonur"},
    ]
    assert codes(decisions) == {"DIRECTION_LIMIT"}


def test_m1_and_m3_conflict_in_any_districts():
    decisions = [
        {"measure_id": "M1", "district": "nura"},
        {"measure_id": "M3", "district": "almaty"},
        {"measure_id": "M4", "district": "saryarka"},
        {"measure_id": "M8", "district": "baikonur"},
        {"measure_id": "M12", "district": None},
    ]
    assert codes(decisions) == {"INCOMPATIBLE_M1_M3"}


def test_m4_and_m7_conflict_only_in_the_same_district():
    same = [
        {"measure_id": "M4", "district": "nura"},
        {"measure_id": "M7", "district": "nura"},
        {"measure_id": "M8", "district": "almaty"},
        {"measure_id": "M10", "district": "saryarka"},
        {"measure_id": "M12", "district": None},
    ]
    assert codes(same) == {"INCOMPATIBLE_M4_M7"}
    split = [
        {"measure_id": "M4", "district": "nura"},
        {"measure_id": "M7", "district": "almaty"},
        {"measure_id": "M8", "district": "saryarka"},
        {"measure_id": "M10", "district": "baikonur"},
        {"measure_id": "M12", "district": None},
    ]
    assert validate(split) == []


def test_m5_and_m13_conflict_only_in_the_same_district():
    same = [
        {"measure_id": "M5", "district": "saryarka"},
        {"measure_id": "M13", "district": "saryarka"},
        {"measure_id": "M8", "district": "nura"},
        {"measure_id": "M10", "district": "almaty"},
        {"measure_id": "M12", "district": None},
    ]
    assert codes(same) == {"INCOMPATIBLE_M5_M13"}
    split = [
        {"measure_id": "M5", "district": "saryarka"},
        {"measure_id": "M13", "district": "nura"},
        {"measure_id": "M8", "district": "almaty"},
        {"measure_id": "M10", "district": "baikonur"},
        {"measure_id": "M9", "district": "yesil"},
    ]
    assert validate(split) == []


def test_invalid_plan_does_not_return_score():
    response = client.post("/simulate", json={"decisions": GOLDEN[:4]})
    body = response.json()
    assert response.status_code == 200
    assert body["valid"] is False
    assert body["score"] is None
    assert body["violations"][0]["code"] == "WRONG_COUNT"


def test_catalog_has_five_districts_and_fourteen_measures():
    body = client.get("/catalog").json()
    assert [item["id"] for item in body["districts"]] == ["yesil", "almaty", "saryarka", "baikonur", "nura"]
    assert len(body["measures"]) == 14
    assert body["budget"] == 100


def test_explain_rejects_invalid_plan():
    response = client.post("/explain", json={"valid": False, "budget": 100, "violations": []})
    assert response.status_code == 400


def test_explain_requires_api_key(monkeypatch):
    monkeypatch.setattr("app.main._load_env", lambda: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post("/explain", json={"valid": True, "budget": 100, "score": 52.56, "violations": []})
    assert response.status_code == 503
