from fastapi.testclient import TestClient

from app.engine.dataset import load
from app.engine.score import clip, score_plan
from app.main import app

client = TestClient(app)

GOLDEN = [
    {"measure_id": "M7", "district": "nura"},
    {"measure_id": "M8", "district": "nura"},
    {"measure_id": "M10", "district": "nura"},
    {"measure_id": "M12", "district": None},
    {"measure_id": "M5", "district": "saryarka"},
]

BASE_D = {
    "yesil": 62.99,
    "almaty": 57.06,
    "saryarka": 54.65,
    "baikonur": 56.63,
    "nura": 49.18,
}


def test_clip_bounds():
    assert clip(-1) == 0
    assert clip(40) == 40
    assert clip(140) == 100


def test_dataset_closes():
    data = load()
    assert abs(sum(item["weight"] for item in data["indicators"]) - 1) < 1e-9
    assert abs(sum(item["pop"] for item in data["districts"]) - 1) < 1e-9
    assert [item["id"] for item in data["districts"]] == ["yesil", "almaty", "saryarka", "baikonur", "nura"]


def test_empty_plan_baseline():
    result = score_plan([])
    assert round(result["d_avg"], 2) == 56.86
    assert round(result["d_min"], 2) == 49.18
    assert result["n_crit"] == 2
    assert round(result["score"], 2) == 52.56
    assert result["weakest_district"] == "nura"
    assert {(item["district"], item["indicator"]) for item in result["crits"]} == {("nura", "S1"), ("nura", "S2")}
    for district_id, expected in BASE_D.items():
        assert round(result["districts"][district_id]["d_before"], 2) == expected
    assert result["score"] == result["d_avg"] * 0.7 + result["d_min"] * 0.3 - result["n_crit"]


def test_value_40_is_not_critical():
    result = score_plan([])
    crits = {(item["district"], item["indicator"]) for item in result["crits"]}
    assert ("almaty", "T1") not in crits
    assert ("nura", "T2") not in crits
    assert ("saryarka", "E2") not in crits


def test_golden_score():
    result = score_plan(GOLDEN)
    assert result["cost"] == 95
    assert abs(result["score"] - 56.5) < 0.05
    assert result["n_crit"] == 0
    assert result["weakest_district"] == "nura"
    assert result["synergies_applied"] == [
        {"measures": ["M10", "M12"], "indicator": "B1", "delta": 2.0, "district": "nura"}
    ]
    assert result["score"] == result["d_avg"] * 0.7 + result["d_min"] * 0.3 - result["n_crit"]
    reversed_plan = score_plan(list(reversed(GOLDEN)))
    assert reversed_plan["score"] == result["score"]
    assert reversed_plan["synergies_applied"] == result["synergies_applied"]


def test_synergy_is_fixed_and_lands_on_anchor_district():
    cameras = score_plan([{"measure_id": "M10", "district": "nura"}])
    both = score_plan([
        {"measure_id": "M10", "district": "nura"},
        {"measure_id": "M12", "district": None},
    ])
    before = cameras["districts"]["nura"]["indicators"]["B1"]["after"]
    after = both["districts"]["nura"]["indicators"]["B1"]["after"]
    assert before == 55 + 12 * 7 / 8
    assert after - before == 2
    pair = score_plan([
        {"measure_id": "M1", "district": "nura"},
        {"measure_id": "M2", "district": None},
    ])
    nura_t1 = pair["districts"]["nura"]["indicators"]["T1"]["after"]
    almaty_t1 = pair["districts"]["almaty"]["indicators"]["T1"]["after"]
    assert nura_t1 == 55 + 6 * 0.75 + 4 * 0.75 + 2
    assert almaty_t1 == 40 + 4 * 0.75


def test_city_measure_hits_every_district_and_negative_effect_can_open_a_crit():
    lights = score_plan([{"measure_id": "M2", "district": None}])
    for district_id in BASE_D:
        row = lights["districts"][district_id]["indicators"]["T1"]
        assert row["after"] - row["before"] == 4 * (8 - 2) / 8
    crossings = score_plan([{"measure_id": "M11", "district": "almaty"}])
    t1 = crossings["districts"]["almaty"]["indicators"]["T1"]["after"]
    assert t1 == 40 - 2 * 7 / 8
    assert ("almaty", "T1") in {(item["district"], item["indicator"]) for item in crossings["crits"]}


def test_api_golden_and_baseline():
    response = client.post("/simulate", json={"decisions": GOLDEN})
    body = response.json()
    assert body["valid"] is True
    assert body["cost"] == 95
    assert body["budget"] == 100
    assert body["baseline_score"] == 52.56
    assert abs(body["score"] - 56.5) < 0.05
    assert body["delta_vs_baseline"] == round(body["score"] - body["baseline_score"], 2)
    assert body["violations"] == []
    assert body["synergies_applied"][0]["district"] == "nura"
    assert body["synergies_applied"][0]["delta"] == 2
    assert body["n_crit"] == 0
    assert body["weakest_district"] == "nura"
    assert body["districts"]["nura"]["d_before"] == 49.18
