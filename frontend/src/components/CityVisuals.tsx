import { useState } from "react";
import type { City, Simulation, PlanItem, Stress, Explanation, AiUsage } from "../types";

const fmt = (n: number) => n.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
const labels: Record<string, [string, string]> = {
  population: ["Население", "чел."], area_km2: ["Площадь", "км²"], density_per_km2: ["Плотность", "чел./км²"],
  children_share: ["Доля детей", "%"], private_housing_share: ["Частное жильё", "%"], housing_age_years: ["Возраст жилья", "лет"],
  cars_per_1000: ["Автомобили", "на 1 000 жителей"], pop_growth_pct_per_year: ["Рост населения", "% в год"],
  second_shift_pct: ["Ученики второй смены", "%"], residents_per_gp: ["Жители на врача", "чел."],
  street_offences_per_10k: ["Уличные правонарушения", "на 10 000 жителей"], network_wear_pct: ["Износ сетей", "%"],
  avg_request_days: ["Обработка обращений", "дней"], peak_trip_to_center_min: ["Поездка в центр в час пик", "мин."],
};
function ScoreBar({ before, after, label }: { before: number; after: number; label: string }) {
  return <div className="comparison-bar" aria-label={`${label}: до ${fmt(before)}, после ${fmt(after)} из 100`}>
    <span className="bar-before" style={{ width: `${before}%` }} /><span className="bar-after" style={{ width: `${after}%` }} />
  </div>;
}
export function CityVisuals({ city, result, planned, view = "overview" }: { city: City; result: Simulation; planned: boolean; view?: "overview" | "indicators" | "profile" }) {
  const [selected, setSelected] = useState(city.districts[0].id);
  const district = city.districts.find(d => d.id === selected) ?? city.districts[0];
  return <section className="slot visual-section" id="city-overview">
    <div className="row"><div><p className="eyebrow">Город в цифрах</p><h2>{planned ? "Что изменит ваш план" : "Исходное состояние города"}</h2></div>
      <span className="status-chip">{planned ? "Предварительный расчёт" : "Базовые показатели"}</span></div>
    {view === "overview" && <><div className="metric-grid"><div className="metric"><span>Балл города</span><strong>{fmt(result.score)}</strong><small>База {fmt(city.base_score)}</small></div>
      <div className="metric"><span>Критические показатели</span><strong>{result.critical.length}</strong><small>Строго ниже {city.rules.critical_threshold} баллов</small></div>
      <div className="metric"><span>Слабейший район</span><strong>{city.districts.find(d => d.id === result.weakest_district)?.name}</strong><small>Индекс {fmt(result.district_scores[result.weakest_district])}</small></div></div>
    <h3>Индексы районов</h3><p className="hint"><span className="legend-before">━ До</span> · <span className="legend-after">━ После</span> · единая шкала от 0 до 100</p>
    <div className="district-bars">{city.districts.map(d => <div key={d.id} className="district-bar-row"><strong>{d.name}</strong>
      <ScoreBar before={city.baseline.district_scores[d.id]} after={result.district_scores[d.id]} label={d.name} />
      <span>{fmt(city.baseline.district_scores[d.id])} → <b>{fmt(result.district_scores[d.id])}</b></span></div>)}</div>
    </>}
    {view === "indicators" && <><h3>Карта показателей</h3><p className="hint">Красный — ниже {city.rules.critical_threshold}; песочный — ниже 60; зелёный — от 60 баллов. Больше баллов — лучше. Натуральные значения доступны при выборе ячейки.</p>
    <div className="table-scroll"><table className="heatmap"><thead><tr><th>Показатель</th>{city.districts.map(d => <th key={d.id}>{d.name}</th>)}</tr></thead>
      <tbody>{city.indicators.map(ind => <tr key={ind.code}><th>{ind.name}</th>{city.districts.map(d => {
        const value = result.indicators_after[d.id][ind.code]; const raw = result.natural_units[d.id][ind.code];
        return <td key={d.id} className={value < city.rules.critical_threshold ? "heat-critical" : value < 60 ? "heat-watch" : "heat-good"}>
          <details><summary aria-label={`${d.name}, ${ind.name}: ${fmt(value)} баллов`}>{fmt(value)}<small>{planned ? `${fmt(value - result.indicators_before[d.id][ind.code])} Δ` : "баллов"}</small></summary>
            <span>{fmt(raw.before)} → {fmt(raw.after)} {raw.unit}</span></details></td>;
      })}</tr>)}</tbody></table></div>
    </>}
    {view === "profile" && <><div className="row"><h3>Характеристики района</h3><select aria-label="Район для сравнения характеристик" value={district.id} onChange={e => setSelected(e.target.value)}>{city.districts.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></div>
    <p>{district.profile}</p><p className="hint">{district.key_issues.join(" · ")}</p>
    <div className="metric-grid profile-grid">{Object.entries({ ...district.passport, ...district.context_indicators }).map(([key, value]) => {
      const [name, unit] = labels[key] ?? [key, ""]; const shown = key.endsWith("_share") && value <= 1 ? value * 100 : value;
      return <div className="metric" key={key}><span>{name}</span><strong>{fmt(shown)} <small>{unit}</small></strong></div>;
    })}</div><p className="hint">Паспорт и условия района — контекст для решений. Эти величины напрямую не входят в формулу балла.</p></>}
  </section>;
}
export function RiskVisuals({ city, plan, remaining }: { city: City; plan: PlanItem[]; remaining: number }) {
  const selected = city.measures.filter(m => plan.some(p => p.measure === m.id));
  if (!selected.length) return null;
  return <section className="slot visual-section" id="risk-overview"><p className="eyebrow">Ресурсы и исполнение</p><h2>Бюджет и риски плана</h2>
    <div className="budget-stack" aria-label={`Резерв ${remaining} из ${city.rules.budget}`}>{selected.map((m, i) => <span key={m.id} style={{ flexBasis: `${m.cost / city.rules.budget * 100}%`, background: ["#0c6b52", "#43806c", "#777b4f", "#a68a55", "#d0ac73"][i] }} title={`${m.name}: ${m.cost}`}>{m.cost}</span>)}<span className="budget-reserve" style={{ flexBasis: `${remaining / city.rules.budget * 100}%` }}>{remaining > 0 ? remaining : ""}</span></div>
    <p className="hint">{selected.map(m => `${m.name}: ${m.cost}`).join(" · ")} · Резерв: {remaining}</p>
    <div className="risk-grid">{selected.map(m => <article className="risk-card" key={m.id}><span className="tag">{city.directions[m.direction]}</span><h3>{m.name}</h3>
      <p>{m.risks}</p><div className="realization"><span style={{ width: `${m.realized_share * 100}%` }} /></div><small>Реализация эффекта {fmt(m.realized_share * 100)}% · лаг {m.lag} кв.</small></article>)}</div>
    <p className="hint">Риски взяты из карточек мер; вероятности не заданы. Полоса показывает долю реализуемого эффекта, а не вероятность успеха.</p>
  </section>;
}
export function StressVisuals({ baseline, current, official }: { baseline: Stress; current: Stress; official: number }) {
  return <div className="visual-section"><div className="metric-grid"><div className="metric"><span>Официальный балл</span><strong>{fmt(official)}</strong></div><div className="metric"><span>Среднее по сценариям</span><strong>{fmt(current.average)}</strong></div><div className="metric"><span>Худший сценарий</span><strong>{fmt(current.worst)}</strong></div></div>
    <p className="hint"><span className="legend-before">━ Без реакции</span> · <span className="legend-after">━ Текущая защита</span> · вертикальная черта — официальный балл · шкала 0–100</p>
    {current.events.map(event => <div className="stress-row" key={event.id}><div className="row"><strong>{event.name}</strong><span>{fmt(event.score)} <b className={event.delta < 0 ? "negative" : "positive"}>({event.delta >= 0 ? "+" : ""}{fmt(event.delta)})</b></span></div>
      <div className="stress-track"><ScoreBar label={event.name} before={baseline.events.find(e => e.id === event.id)?.score ?? event.score} after={event.score} /><i style={{ left: `${official}%` }} /></div>
      <small>Критических показателей: {event.n_critical} · без реакции {fmt(baseline.events.find(e => e.id === event.id)?.score ?? event.score)}</small></div>)}
  </div>;
}
export function AiNotice({ usage, advisor = false }: { usage: AiUsage; advisor?: boolean }) {
  if (usage.mode === "live") return null;
  return <p className="hint fallback-notice">{advisor
    ? "Советник временно недоступен. Показываем альтернативу, рассчитанную по правилам симуляции."
    : "Сейчас доступен расчётный доклад. Развёрнутый комментарий ИИ можно запросить позже."}</p>;
}
export function AiReport({ report }: { report: Explanation }) {
  return <article className="briefing"><AiNotice usage={report.ai} /><p className="hint">✓ Показатели проверены расчётом</p><h3>Исход и решение</h3><p>{report.summary}</p>
    {([ ["consequences", "Влияние на город"], ["strengths", "Что дало результат и что нет"], ["risks", "Риски для руководства"] ] as const).map(([key, title]) => <section key={key}><h3>{title}</h3>{report[key].map((line, i) => <p key={i}>{line}</p>)}</section>)}
    <h3>Управленческий выбор</h3><p>{report.main_tradeoff}</p></article>;
}
