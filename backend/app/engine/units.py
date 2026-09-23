"""Convert score-point changes into the synthetic real-world units."""

from __future__ import annotations


def natural_values(data: dict, before: dict, after: dict) -> dict:
    indicators = {item["code"]: item for item in data["indicators"]}
    districts = {item["id"]: item for item in data["districts"]}
    result = {}
    for district_id, values in after.items():
        result[district_id] = {}
        for code, score_after in values.items():
            indicator = indicators[code]
            raw_before = districts[district_id]["raw_indicators"][code]
            raw_after = raw_before + (score_after - before[district_id][code]) * indicator["raw"]["raw_per_score_point"]
            result[district_id][code] = {
                "before": raw_before,
                "after": raw_after,
                "unit": indicator["raw"]["unit"],
                "name": indicator["raw"]["name"],
            }
    return result
