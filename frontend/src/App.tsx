import { useEffect, useMemo, useState } from "react";
import { DistrictDetailsPanel } from "./components/DistrictDetailsPanel";
import { DistrictMap } from "./components/DistrictMap";
import { type DistrictId, toMapResult } from "./lib/districtMap";

type Measure = { id: string; name: string; direction: string; type: "city" | "district"; cost: number; lag: number; realized_share: number; effects: Record<string, number>; description: string; risks: string };
type District = { id: string; name: string; pop_share: number; profile: string; key_issues: string[]; indicators: Record<string, number>; raw_indicators: Record<string, number>; passport: Record<string, number>; context_indicators: Record<string, number> };
type PlanItem = { measure: string; district: string | null };
type Slot = { measureId: string; district: string };
type City = {
  rules: { budget: number; decisions_exact: number; max_per_direction: number; critical_threshold: number };
  directions: Record<string, string>; measures: Measure[]; districts: District[];
  indicators: { code: string; name: string; weight: number; raw: { unit: string } }[];
  incompatibilities: { pair: [string, string]; scope: "any" | "same_district"; why: string }[];
  events: { id: string; name: string; description: string; response: { name: string; cost: number } }[];
  base_score: number;
};
type Validation = { valid: boolean; error: string | null; cost: number; remaining: number };
type Simulation = {
  score: number; d_avg: number; district_scores: Record<string, number>; weakest_district: string;
  critical: [string, string][]; indicators_before: Record<string, Record<string, number>>;
  indicators_after: Record<string, Record<string, number>>;
  natural_units: Record<string, Record<string, { name: string; before: number; after: number; unit: string }>>;
  cost: number; remaining: number; contributions: { source: string; district: string; indicator: string; delta: number }[];
};
type Submission = Simulation & { team_name: string; percentile: number; rank: number; valid_plans: number; gap: number; best_single_swap: { plan: PlanItem[]; score: number; improvement: number } };
type Explanation = { summary: string; strengths: string[]; risks: string[]; consequences: string[]; main_tradeoff: string; verified: boolean };
type Advice = { best_plan: PlanItem[]; best_score: number; improvement: number; trace: { source: string; score?: number; error?: string }[]; explanation: Explanation };
type Stress = { average: number; worst: number; events: { id: string; name: string; score: number; delta: number; n_critical: number }[] };
type BoardRow = { team_name: string; score: number; percentile: number; resilience_average: number };

const emptySlots = (count: number): Slot[] => Array.from({ length: count }, () => ({ measureId: "", district: "" }));
const fmt = (value: number) => value.toFixed(2);

async function api<T>(path: string, payload?: object, signal?: AbortSignal): Promise<T> {
  const response = await fetch("/api" + path, {
    method: payload ? "POST" : "GET", headers: { "Content-Type": "application/json" },
    body: payload ? JSON.stringify(payload) : undefined, signal,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error ?? data.detail?.error ?? "Сервис не ответил");
  return data as T;
}

export function App() {
  const [city, setCity] = useState<City | null>(null);
  const [loadError, setLoadError] = useState("");
  const [slots, setSlots] = useState<Slot[]>(emptySlots(5));
  const [teamName, setTeamName] = useState("");
  const [validation, setValidation] = useState<Validation | null>(null);
  const [preview, setPreview] = useState<Simulation | null>(null);
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [advice, setAdvice] = useState<Advice | null>(null);
  const [stress, setStress] = useState<Stress | null>(null);
  const [responses, setResponses] = useState<string[]>([]);
  const [board, setBoard] = useState<BoardRow[]>([]);
  const [selectedDistrict, setSelectedDistrict] = useState<DistrictId | null>(null);
  const [sort, setSort] = useState<"score" | "resilience">("score");
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    api<City>("/state").then((data) => { setCity(data); setSlots(emptySlots(data.rules.decisions_exact)); })
      .catch((error: Error) => setLoadError(error.message));
  }, []);
  useEffect(() => {
    api<{ teams: BoardRow[] }>(`/leaderboard?sort=${sort}`).then((data) => setBoard(data.teams))
      .catch(() => setBoard([]));
  }, [sort, submission]);

  const measures = city?.measures ?? [];
  const byId = useMemo(() => new Map(measures.map((measure) => [measure.id, measure])), [measures]);
  const budget = city?.rules.budget ?? 100;
  const spent = slots.reduce((sum, slot) => sum + (byId.get(slot.measureId)?.cost ?? 0), 0);
  const ready = Boolean(city && slots.every((slot) => {
    const measure = byId.get(slot.measureId);
    return measure && (measure.type === "city" || slot.district);
  }));
  const plan: PlanItem[] = slots.filter((slot) => slot.measureId).map((slot) => ({
    measure: slot.measureId, district: byId.get(slot.measureId)?.type === "district" ? slot.district || null : null,
  }));
  const signature = JSON.stringify(plan);
  const districtName = (id: string) => city?.districts.find((district) => district.id === id)?.name ?? id;
  const planText = (items: PlanItem[]) => items.map((item) =>
    `${item.measure} ${item.district ? districtName(item.district) : "город"}`).join(", ");

  function measureReason(index: number, measureId: string): string | null {
    if (!city || !measureId || slots[index].measureId === measureId) return null;
    const measure = byId.get(measureId);
    if (!measure) return "Неизвестная мера";
    const others = slots.filter((_, i) => i !== index);
    if (others.some((slot) => slot.measureId === measureId)) return "Уже выбрано";
    if (others.reduce((sum, slot) => sum + (byId.get(slot.measureId)?.cost ?? 0), 0) + measure.cost > budget)
      return "Не хватает бюджета";
    if (others.filter((slot) => byId.get(slot.measureId)?.direction === measure.direction).length >= city.rules.max_per_direction)
      return "Лимит направления";
    if (city.incompatibilities.some((rule) => rule.scope === "any" && rule.pair.includes(measureId) &&
      others.some((slot) => rule.pair.includes(slot.measureId)))) return "Несовместимо с выбранной мерой";
    return null;
  }
  function districtReason(index: number, districtId: string): string | null {
    if (!city || !districtId) return null;
    const measureId = slots[index].measureId;
    const conflict = city.incompatibilities.find((rule) => rule.scope === "same_district" &&
      rule.pair.includes(measureId) && slots.some((slot, i) => i !== index &&
        rule.pair.includes(slot.measureId) && slot.district === districtId));
    return conflict ? `Несовместимо: ${conflict.pair.join(" и ")}` : null;
  }
  function changeSlots(next: Slot[]) {
    setSlots(next); setValidation(null); setPreview(null); setSubmission(null);
    setExplanation(null); setAdvice(null); setStress(null); setResponses([]);
    setActionError("");
  }
  function setMeasure(index: number, measureId: string) {
    if (measureReason(index, measureId)) return;
    changeSlots(slots.map((slot, i) => i === index ? { measureId, district: "" } : slot));
  }
  function setDistrict(index: number, district: string) {
    if (districtReason(index, district)) return;
    changeSlots(slots.map((slot, i) => i === index ? { ...slot, district } : slot));
  }

  useEffect(() => {
    if (!city) return;
    const controller = new AbortController();
    setPreview(null);
    api<Validation>("/validate", { plan }, controller.signal).then(async (check) => {
      if (controller.signal.aborted) return;
      setValidation(check);
      if (check.valid && ready) {
        const result = await api<Simulation>("/simulate", { plan }, controller.signal);
        if (!controller.signal.aborted) setPreview(result);
      }
    }).catch((error: Error) => { if (!controller.signal.aborted) setActionError(error.message); });
    return () => controller.abort();
  }, [city, signature, ready]);

  async function run<T>(path: string, payload: object, receive: (value: T) => void) {
    setBusy(true); setActionError("");
    try { receive(await api<T>(path, payload)); }
    catch (error) { setActionError(error instanceof Error ? error.message : "Сервис не ответил"); }
    finally { setBusy(false); }
  }
  const result = submission ?? preview;
  const mapResult = useMemo(() => toMapResult(result), [result]);

  return <div className="page">
    <header className="top">
      <div><p className="eyebrow">Симулятор городского управления</p><h1>Аким на 5 часов</h1>
        <p className="lede">Ровно {city?.rules.decisions_exact ?? 5} мер и бюджет {budget}. Остаток не даёт бонуса. Не больше двух мер одного направления. Счёт считает движок, ИИ объясняет и советует.</p></div>
      <div className="budget"><span>Остаток бюджета</span><strong>{budget - spent}</strong>
        <div className="bar"><div style={{ width: `${Math.min(100, spent / budget * 100)}%` }} /></div>
        <small>занято {spent} из {budget}</small></div>
    </header>
    {loadError && <p className="error">{loadError}</p>}
    <div className="layout">
      <section>
        <div className="row"><h2>Пять решений</h2>
          <button type="button" className="ghost" onClick={() => changeSlots(emptySlots(city?.rules.decisions_exact ?? 5))}>Сбросить</button></div>
        <label>Название команды<input value={teamName} onChange={(event) => setTeamName(event.target.value)}
          placeholder="Например, Команда А" maxLength={80} /></label>
        <ol className="slots">{slots.map((slot, index) => {
          const measure = byId.get(slot.measureId);
          return <li className="slot" key={index}>
            <div className="slot-head"><span>Решение {index + 1}</span>
              {slot.measureId && <button type="button" className="ghost" onClick={() => setMeasure(index, "")}>Убрать</button>}</div>
            <div className="fields">
              <label>Мера<select value={slot.measureId} onChange={(event) => setMeasure(index, event.target.value)}>
                <option value="">Выберите меру</option>
                {measures.map((item) => {
                  const reason = measureReason(index, item.id);
                  return <option key={item.id} value={item.id} disabled={Boolean(reason)}>
                    {city?.directions[item.direction]} · {item.id} · {item.name} · {item.cost}{reason ? ` — ${reason}` : ""}
                  </option>;
                })}</select></label>
              {measure?.type === "district" ? <label>Район
                <select value={slot.district} onChange={(event) => setDistrict(index, event.target.value)}>
                  <option value="">Выберите район</option>
                  {city?.districts.map((district) => {
                    const reason = districtReason(index, district.id);
                    return <option key={district.id} value={district.id} disabled={Boolean(reason)}>
                      {district.name}{reason ? ` — ${reason}` : ""}</option>;
                  })}</select></label> :
                <p className="city-note">{measure ? "Весь город" : "Сначала выберите меру"}</p>}
            </div>
            {measure && <p className="hint">{city?.directions[measure.direction]} · лаг {measure.lag} кв. ·
              {Object.entries(measure.effects).map(([code, value]) => ` ${code} ${value > 0 ? "+" : ""}${value}`).join(",")}</p>}
            {measure && <details><summary>Описание и риски</summary><p>{measure.description}</p>
              <p className="hint">Риски: {measure.risks} · реализуется {(measure.realized_share * 100).toFixed(0)}% эффекта</p></details>}
          </li>;
        })}</ol>
        <h2>Каталог</h2><div className="catalog">{measures.map((measure) => {
          const selected = slots.some((slot) => slot.measureId === measure.id);
          const free = slots.findIndex((slot) => !slot.measureId);
          const reason = selected ? "Уже выбрано" : free < 0 ? "Все слоты заняты" : measureReason(free, measure.id);
          return <button type="button" key={measure.id} className={selected ? "card on" : "card"}
            disabled={Boolean(reason)} title={reason ?? "Добавить в первый свободный слот"}
            onClick={() => free >= 0 && setMeasure(free, measure.id)}>
            <span className="tag" data-dir={measure.direction}>{city?.directions[measure.direction]}</span>
            <strong>{measure.id}. {measure.name}</strong>
            <small>{measure.cost} · лаг {measure.lag} · {measure.type === "city" ? "город" : "район"}
              <br />{Object.entries(measure.effects).map(([code, value]) => `${code} ${value > 0 ? "+" : ""}${value}`).join(", ")}</small>
          </button>;
        })}</div>
        <details className="slot"><summary>Районы и исходные показатели · база {city ? fmt(city.base_score) : "…"}</summary>
          {city?.districts.map((district) => <details key={district.id}>
            <summary>{district.name} · {(district.pop_share * 100).toFixed(0)}% населения</summary>
            <p>{district.profile}</p><p className="hint">{district.key_issues.join("; ")}</p>
            <details><summary>Паспорт района</summary><table><tbody>{Object.entries(district.passport).map(([key, value]) =>
              <tr key={key}><td>{key}</td><td>{value}</td></tr>)}</tbody></table></details>
            <details><summary>Дополнительные условия</summary><table><tbody>{Object.entries(district.context_indicators).map(([key, value]) =>
              <tr key={key}><td>{key}</td><td>{value}</td></tr>)}</tbody></table></details>
            <table><thead><tr><th>Показатель</th><th>Баллы</th><th>Натуральное значение</th></tr></thead>
              <tbody>{city.indicators.map((indicator) => <tr key={indicator.code}>
                <td>{indicator.code} · {indicator.name}</td><td>{fmt(district.indicators[indicator.code])}</td>
                <td>{district.raw_indicators[indicator.code]} {indicator.raw.unit}</td></tr>)}</tbody></table>
          </details>)}</details>
      </section>
      <aside className="panel">
        <h2>Результат</h2>
        {!result && <p className="hint">Заполните {city?.rules.decisions_exact ?? 5} слотов — Score появится здесь.</p>}
        {validation?.error && ready && <p className="error">{validation.error}</p>}
        {actionError && <p className="error">{actionError}</p>}
        <DistrictMap simulationResult={mapResult} selectedDistrict={selectedDistrict} onDistrictSelect={setSelectedDistrict} />
        <DistrictDetailsPanel districtId={selectedDistrict} simulationResult={mapResult} />
        {result && <>
          <div className="score">{fmt(result.score)}</div>
          <p className="delta">база {fmt(city?.base_score ?? 0)} · дельта {fmt(result.score - (city?.base_score ?? 0))}</p>
          <div className="stats"><div><span>D средн.</span><strong>{fmt(result.d_avg)}</strong></div>
            <div><span>D мин.</span><strong>{fmt(Math.min(...Object.values(result.district_scores)))}</strong></div>
            <div><span>N крит.</span><strong>{result.critical.length}</strong></div></div>
          <p>Слабый район: <strong>{districtName(result.weakest_district)}</strong></p>
          <p className="hint">Стоимость {result.cost} из {budget}. Остаток на счёт не влияет.</p>
          <table><thead><tr><th>Район</th><th>D до</th><th>D после</th></tr></thead>
            <tbody>{city?.districts.map((district) => <tr key={district.id}
              className={district.id === result.weakest_district ? "weak" : ""}>
              <td>{district.name}</td>
              <td>{fmt(city.indicators.reduce((sum, item) => sum + item.weight * result.indicators_before[district.id][item.code], 0))}</td>
              <td>{fmt(result.district_scores[district.id])}</td></tr>)}</tbody></table>
          <h2>Критические ячейки</h2>
          {result.critical.length ? <ul className="crits">{result.critical.map(([district, code]) =>
            <li key={`${district}-${code}`}>{districtName(district)}, {code}: {fmt(result.indicators_after[district][code])}</li>)}</ul>
            : <p className="hint">Нет показателей строго ниже {city?.rules.critical_threshold}.</p>}
          <h2>Синергии</h2>
          {result.contributions.filter((item) => item.source.includes("+")).length ?
            <ul className="crits">{result.contributions.filter((item) => item.source.includes("+")).map((item, index) =>
              <li key={index}>{item.source}: {item.indicator} +{item.delta} в районе {districtName(item.district)}</li>)}</ul>
            : <p className="hint">Синергия не сработала.</p>}
          <details><summary>Изменения в натуральных единицах</summary>
            <table><thead><tr><th>Район</th><th>Показатель</th><th>До</th><th>После</th></tr></thead>
              <tbody>{Object.entries(result.natural_units).flatMap(([district, values]) => Object.entries(values)
                .filter(([code]) => result.indicators_before[district][code] !== result.indicators_after[district][code])
                .map(([code, value]) => <tr key={`${district}-${code}`}><td>{districtName(district)}</td>
                  <td>{value.name}</td><td>{fmt(value.before)} {value.unit}</td><td>{fmt(value.after)} {value.unit}</td></tr>))}</tbody></table>
          </details>
        </>}
        <button type="button" className="primary" disabled={!preview || !validation?.valid || !teamName.trim() || busy}
          onClick={() => run<Submission>("/submit", { team_name: teamName.trim(), plan }, setSubmission)}>Отправить сценарий</button>
        {submission && <>
          <p className="delta">Перцентиль {fmt(submission.percentile)}% · место {submission.rank} из {submission.valid_plans}</p>
          <p>До лучшего: {fmt(submission.gap)}</p>
          <p className="hint">Лучшее одно изменение: {fmt(submission.best_single_swap.score)} ({fmt(submission.best_single_swap.improvement)}). {planText(submission.best_single_swap.plan)}</p>
          <button type="button" className="primary" disabled={busy} onClick={() => run<Explanation>("/explain", { plan }, setExplanation)}>Объяснить</button>
          <button type="button" className="primary" disabled={busy} onClick={() => run<Advice>("/advise", { plan }, setAdvice)}>Спросить советника</button>
        </>}
        {explanation && <div className="explain"><strong>✓ проверено симулятором</strong><p>{explanation.summary}</p>
          {(["strengths", "risks", "consequences"] as const).map((key) =>
            <section key={key}><strong>{({ strengths: "Сильные стороны", risks: "Риски", consequences: "Последствия" })[key]}</strong>
              <ul>{explanation[key].map((line, i) => <li key={i}>{line}</li>)}</ul></section>)}
          <p>{explanation.main_tradeoff}</p></div>}
        {advice && <div className="explain"><strong>Проверенный совет: {fmt(advice.best_score)} ({fmt(advice.improvement)})</strong>
          <p>{planText(advice.best_plan)}</p><p>{advice.explanation.summary}</p>
          <details><summary>Ход проверки</summary><ul>{advice.trace.map((step, i) =>
            <li key={i}>{step.source}: {step.score === undefined ? step.error : fmt(step.score)}</li>)}</ul></details></div>}
      </aside>
    </div>
    {submission && city && <section className="slot">
      <h2>Стресс-тест</h2><p className="hint">Семь событий. Основной балл не меняется; реакции оплачиваются из резерва.</p>
      {city.events.map((event) => <label key={event.id}><span>
        <input type="checkbox" checked={responses.includes(event.id)} disabled={event.response.cost > submission.remaining}
          onChange={(e) => setResponses(e.target.checked ? [...responses, event.id] : responses.filter((id) => id !== event.id))} />
        {event.name}: {event.response.name} · {event.response.cost}</span><small>{event.description}</small></label>)}
      <button type="button" className="primary" disabled={busy}
        onClick={() => run<Stress>("/stress-test", { plan, buy_responses: responses }, setStress)}>Провести стресс-тест</button>
      {stress && <><p>Средний балл {fmt(stress.average)} · худший случай {fmt(stress.worst)}</p>
        <table><thead><tr><th>Событие</th><th>Балл</th><th>Изменение</th><th>Критических</th></tr></thead>
          <tbody>{stress.events.map((event) => <tr key={event.id}><td>{event.name}</td><td>{fmt(event.score)}</td>
            <td>{fmt(event.delta)}</td><td>{event.n_critical}</td></tr>)}</tbody></table></>}
    </section>}
    <section className="slot"><div className="row"><h2>Рейтинг команд</h2>
      <select value={sort} onChange={(event) => setSort(event.target.value as "score" | "resilience")}>
        <option value="score">По баллу</option><option value="resilience">По устойчивости</option></select></div>
      <table><thead><tr><th>Команда</th><th>Балл</th><th>Перцентиль</th><th>Устойчивость</th></tr></thead>
        <tbody>{board.map((row, i) => <tr key={`${row.team_name}-${i}`}><td>{row.team_name}</td><td>{fmt(row.score)}</td>
          <td>{fmt(row.percentile)}%</td><td>{fmt(row.resilience_average)}</td></tr>)}</tbody></table>
    </section>
  </div>;
}
