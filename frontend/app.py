"""Russian Streamlit interface for the deterministic city simulator."""

from __future__ import annotations

import os

import httpx
import pandas as pd
import streamlit as st

API = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def request(method: str, path: str, payload: dict | None = None) -> dict:
    try:
        response = httpx.request(method, f"{API}{path}", json=payload, timeout=120)
        body = response.json()
        if response.status_code >= 400:
            detail = body.get("detail", body)
            raise ValueError(detail.get("error", str(detail)) if isinstance(detail, dict) else str(detail))
        return body
    except (httpx.HTTPError, ValueError) as error:
        raise RuntimeError(str(error)) from error


@st.cache_data(ttl=60)
def state() -> dict:
    return request("GET", "/api/state")


st.set_page_config(page_title="Аким на 5 часов", page_icon="🏙️", layout="wide")
st.title("Аким на 5 часов")
st.caption("Пять решений, один бюджет и проверяемый расчёт качества жизни Астаны")

try:
    city = state()
except RuntimeError as error:
    st.error(f"Сервер недоступен: {error}")
    st.stop()

rules = city["rules"]
districts = city["districts"]
measures = city["measures"]
directions = city["directions"]
measure_by_id = {item["id"]: item for item in measures}
district_by_id = {item["id"]: item for item in districts}
events = city["events"]
passport_labels = {
    "population": "Население", "area_km2": "Площадь, км²",
    "density_per_km2": "Плотность, чел./км²", "children_share": "Доля детей",
    "private_housing_share": "Доля частного сектора", "housing_age_years": "Возраст жилья, лет",
    "cars_per_1000": "Автомобилей на тысячу жителей",
    "pop_growth_pct_per_year": "Рост населения в год, %",
}
context_labels = {
    "second_shift_pct": "Ученики во вторую смену, %",
    "residents_per_gp": "Жителей на одного врача ПМСП",
    "street_offences_per_10k": "Уличных правонарушений на десять тысяч жителей",
    "network_wear_pct": "Износ сетей, %",
    "avg_request_days": "Средний срок обращения, дни",
    "peak_trip_to_center_min": "Поездка до центра в час пик, мин",
}

start_tab, city_tab, plan_tab, result_tab, stress_tab, board_tab = st.tabs(
    ["Старт", "Город", "План", "Результат", "Стресс-тест", "Рейтинг"])

with start_tab:
    st.subheader("Команда")
    st.text_input("Название команды", key="team_name", placeholder="Например, Команда А")
    st.write("Все команды получают одинаковый бюджет и исходные данные. Выберите ровно пять мер из каталога.")
    st.metric("Базовый балл города", f"{city['base_score']:.2f}")
    st.info("Числа рассчитывает симулятор. ИИ объясняет результат и предлагает проверенные варианты.")

with city_tab:
    st.subheader("Районы")
    for district in districts:
        with st.expander(f"{district['name']} · {district['pop_share']:.0%} населения"):
            st.write(district["profile"])
            st.write("**Главные проблемы:** " + "; ".join(district["key_issues"]))
            st.dataframe([{"Показатель": passport_labels.get(key, key), "Значение": value}
                          for key, value in district["passport"].items()], hide_index=True)
            st.dataframe([{"Показатель": context_labels.get(key, key), "Значение": value}
                          for key, value in district["context_indicators"].items()], hide_index=True)
    st.subheader("Показатели по районам")
    codes = [item["code"] for item in city["indicators"]]
    heatmap = pd.DataFrame({d["name"]: [d["indicators"][code] for code in codes] for d in districts}, index=codes).T
    st.dataframe(heatmap.style.map(lambda value: f"background-color: hsl({value * 1.2:.0f}, 45%, 30%); color: white"),
                 width="stretch")
    with st.expander("Значения в натуральных единицах"):
        raw_rows = []
        for district in districts:
            for indicator in city["indicators"]:
                code = indicator["code"]
                raw_rows.append({"Район": district["name"], "Показатель": indicator["name"],
                                 "Значение": district["raw_indicators"][code],
                                 "Единица": indicator["raw"]["unit"]})
        st.dataframe(raw_rows, width="stretch", hide_index=True)

with plan_tab:
    st.subheader("Выберите пять мер")
    options = [""] + [m["id"] for m in measures]
    plan = []
    for index in range(rules["decisions_exact"]):
        left, right = st.columns([2, 1])
        measure_id = left.selectbox(f"Решение {index + 1}", options,
            format_func=lambda value: "Выберите меру" if not value else
            f"{directions[measure_by_id[value]['direction']]} · {value} · {measure_by_id[value]['name']} · {measure_by_id[value]['cost']}",
            key=f"measure_{index}")
        if not measure_id:
            continue
        measure = measure_by_id[measure_id]
        district_id = None
        if measure["type"] == "district":
            district_id = right.selectbox("Район", [None] + [d["id"] for d in districts],
                format_func=lambda value: "Выберите район" if value is None else district_by_id[value]["name"],
                key=f"district_{index}")
        else:
            right.write("Мера для всего города")
        plan.append({"measure": measure_id, "district": district_id})
        with st.expander(f"{measure_id}: описание и риски"):
            st.write(measure["description"])
            st.write(f"**Риски:** {measure['risks']}")
            st.caption(f"Лаг: {measure['lag']} кв. · Реализуется {measure['realized_share']:.0%} эффекта")
    st.session_state["current_plan"] = plan
    validation = request("POST", "/api/validate", {"plan": plan})
    spent = validation["cost"]
    st.progress(min(spent / rules["budget"], 1.0), text=f"Потрачено {spent} из {rules['budget']} · остаток {validation['remaining']}")
    if not validation["valid"]:
        st.warning(validation["error"])
    team_name = st.session_state.get("team_name", "").strip()
    if st.button("Отправить сценарий", type="primary", disabled=not validation["valid"] or not team_name):
        try:
            st.session_state["submission"] = request("POST", "/api/submit",
                {"team_name": team_name, "plan": plan})
            st.session_state["submitted_plan"] = [dict(item) for item in plan]
            st.session_state.pop("explanation", None)
            st.session_state.pop("advice", None)
            st.session_state.pop("stress", None)
            st.success("Сценарий сохранён. Откройте вкладку «Результат».")
        except RuntimeError as error:
            st.error(str(error))

submission = st.session_state.get("submission")
with result_tab:
    if not submission:
        st.info("Сначала отправьте допустимый сценарий на вкладке «План».")
    else:
        st.subheader(f"Результат команды {submission['team_name']}")
        a, b, c, d = st.columns(4)
        a.metric("Баллы", f"{submission['score']:.2f}",
                 f"{submission['score'] - city['base_score']:+.2f} к базе")
        b.metric("Перцентиль", f"{submission['percentile']:.2f}%")
        c.metric("Место", f"{submission['rank']} из {submission['valid_plans']}")
        d.metric("До лучшего", f"{submission['gap']:.2f}")
        score_rows = [{"Район": district_by_id[key]["name"],
                       "До": sum(item["weight"] * submission["indicators_before"][key][item["code"]]
                                 for item in city["indicators"]),
                       "После": value}
                      for key, value in submission["district_scores"].items()]
        st.subheader("Баллы районов")
        st.bar_chart(pd.DataFrame(score_rows).set_index("Район")[["До", "После"]])
        with st.expander("Изменения показателей в натуральных единицах"):
            changed = []
            for district_id, values in submission["natural_units"].items():
                for code, item in values.items():
                    if submission["indicators_before"][district_id][code] == submission["indicators_after"][district_id][code]:
                        continue
                    changed.append({"Район": district_by_id[district_id]["name"],
                                    "Показатель": item["name"], "До": round(item["before"], 2),
                                    "После": round(item["after"], 2), "Единица": item["unit"]})
            st.dataframe(changed, hide_index=True, width="stretch")
        if submission["critical"]:
            st.warning("Критические значения: " + ", ".join(
                f"{district_by_id[d]['name']} {code}" for d, code in submission["critical"]))
        else:
            st.success("Критических значений нет")
        swap = submission["best_single_swap"]
        st.write(f"**Лучшее одно изменение:** {swap['score']:.2f} ({swap['improvement']:+.2f})")
        st.caption(", ".join(f"{item['measure']} {district_by_id[item['district']]['name'] if item['district'] else 'город'}"
                             for item in swap["plan"]))
        if st.button("Объяснить результат"):
            try:
                st.session_state["explanation"] = request("POST", "/api/explain",
                    {"plan": st.session_state["submitted_plan"]})
            except RuntimeError as error:
                st.error(str(error))
        explanation = st.session_state.get("explanation")
        if explanation:
            st.success("✓ проверено симулятором")
            st.write(explanation["summary"])
            for title, key in [("Сильные стороны", "strengths"), ("Риски", "risks"),
                               ("Последствия", "consequences")]:
                st.write(f"**{title}**")
                for line in explanation[key]:
                    st.write("• " + line)
            st.write("**Главный компромисс:** " + explanation["main_tradeoff"])
        if st.button("Спросить советника"):
            try:
                st.session_state["advice"] = request("POST", "/api/advise",
                    {"plan": st.session_state["submitted_plan"]})
            except RuntimeError as error:
                st.error(str(error))
        advice = st.session_state.get("advice")
        if advice:
            st.write(f"**Проверенный вариант:** {advice['best_score']:.2f} ({advice['improvement']:+.2f})")
            st.caption(", ".join(f"{item['measure']} {district_by_id[item['district']]['name'] if item['district'] else 'город'}"
                                 for item in advice["best_plan"]))
            with st.expander("Ход проверки советника"):
                for step in advice["trace"]:
                    st.write(f"{step['source']}: {step.get('score', step.get('error'))}")

with stress_tab:
    if not submission:
        st.info("Сначала отправьте сценарий.")
    else:
        st.subheader("Семь городских событий")
        st.caption("Это отдельная оценка устойчивости. Основной балл не меняется.")
        reserve = submission["remaining"]
        buy = set()
        for event in events:
            cost = event["response"]["cost"]
            st.write(f"**{event['name']}** · {event['description']}")
            if st.checkbox(f"Купить реакцию: {event['response']['name']} · {cost}",
                           key=f"buy_{event['id']}", disabled=cost > reserve):
                buy.add(event["id"])
        if st.button("Провести стресс-тест"):
            try:
                st.session_state["stress"] = request("POST", "/api/stress-test",
                    {"plan": st.session_state["submitted_plan"], "buy_responses": sorted(buy)})
            except RuntimeError as error:
                st.error(str(error))
        stress = st.session_state.get("stress")
        if stress:
            a, b = st.columns(2)
            a.metric("Средний балл при событиях", f"{stress['average']:.2f}")
            b.metric("Худший случай", f"{stress['worst']:.2f}")
            st.dataframe([{"Событие": item["name"], "Балл": round(item["score"], 2),
                           "Изменение": round(item["delta"], 2), "Критических": item["n_critical"],
                           "Реакция куплена": "Да" if item["response_bought"] else "Нет"}
                          for item in stress["events"]], hide_index=True, width="stretch")

with board_tab:
    st.subheader("Рейтинг команд")
    sort = st.radio("Сортировка", ["score", "resilience"],
                    format_func=lambda value: "По баллу" if value == "score" else "По устойчивости",
                    horizontal=True)
    try:
        board = request("GET", f"/api/leaderboard?sort={sort}")["teams"]
        st.dataframe([{"Команда": row["team_name"], "Балл": round(row["score"], 2),
                       "Перцентиль": round(row["percentile"], 2),
                       "Устойчивость": round(row["resilience_average"], 2),
                       "Стратегия": row["strategy"]} for row in board],
                     hide_index=True, width="stretch")
    except RuntimeError as error:
        st.error(str(error))
