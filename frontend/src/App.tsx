import { useEffect, useMemo, useRef, useState } from "react";
import { DistrictDetailsPanel } from "./components/DistrictDetailsPanel";
import { DistrictMap } from "./components/DistrictMap";
import { type DistrictId, toMapResult } from "./lib/districtMap";

import type { City, Slot, PlanItem, Validation, Simulation, Submission, Explanation, Advice, Stress, BoardRow } from "./types";
import { CityVisuals, RiskVisuals, StressVisuals, AiReport, AiNotice } from "./components/CityVisuals";

const pages = { home: "Обзор", city: "Город", plan: "Мой план", results: "Результат", risks: "Риски", stress: "Стресс-тест", advisor: "Советник", leaderboard: "Рейтинг" } as const;
type Page = keyof typeof pages;
function pageFromHash(): Page {
  const key = window.location.hash.slice(1);
  return Object.hasOwn(pages, key) ? key as Page : "home";
}

const emptySlots = (count: number): Slot[] => Array.from({ length: count }, () => ({ measureId: "", district: "" }));
const fmt = (value: number) => value.toFixed(2);

async function api<T>(path: string, payload?: object, signal?: AbortSignal): Promise<T> {
  const response = await fetch("/api" + path, {
    method: payload ? "POST" : "GET", headers: { "Content-Type": "application/json" },
    body: payload ? JSON.stringify(payload) : undefined, signal,
  }).catch(error => {
    if (signal?.aborted) throw error;
    throw new Error("Не удалось связаться с сервисом. Проверьте соединение и попробуйте ещё раз.");
  });
  const data = await response.json().catch(() => { throw new Error("Не удалось получить результат. Попробуйте ещё раз."); });
  if (!response.ok) throw new Error(data.error ?? data.detail?.error ?? "Сервис не ответил");
  return data as T;
}

export function App() {
  const [page, setPage] = useState<Page>(pageFromHash);
  const [planView, setPlanView] = useState<"builder" | "catalog">("builder");
  const [cityView, setCityView] = useState<"overview" | "indicators" | "profile" | "map">("overview");
  const pageHeading = useRef<HTMLHeadingElement>(null);
  function navigate(next: Page) {
    window.location.hash = next;
    setPage(next);
  }
  useEffect(() => {
    const changed = () => setPage(pageFromHash());
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {
    pageHeading.current?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }, [page]);
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
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const busy = pendingAction !== null;
  const [previewLoading, setPreviewLoading] = useState(false);
  const [boardError, setBoardError] = useState("");
  const generation = useRef(0);
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    api<City>("/state").then((data) => { setCity(data); setSlots(emptySlots(data.rules.decisions_exact)); })
      .catch((error: Error) => setLoadError(error.message));
  }, []);
  useEffect(() => {
    api<{ teams: BoardRow[] }>(`/leaderboard?sort=${sort}`).then((data) => { setBoard(data.teams); setBoardError(""); })
      .catch(() => setBoardError("Не удалось загрузить рейтинг. Попробуйте открыть его позже."));
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
  const indicatorName = (code: string) => city?.indicators.find(item => item.code === code)?.name ?? code;
  const planText = (items: PlanItem[]) => items.map((item) =>
    `${byId.get(item.measure)?.name ?? item.measure} — ${item.district ? districtName(item.district) : "город"}`).join(", ");

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
    generation.current += 1;
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
    setPreview(null); setPreviewLoading(true);
    api<Validation>("/validate", { plan }, controller.signal).then(async (check) => {
      if (controller.signal.aborted) return;
      setValidation(check);
      if (check.valid && ready) {
        const result = await api<Simulation>("/simulate", { plan }, controller.signal);
        if (!controller.signal.aborted) setPreview(result);
      }
    }).catch((error: Error) => { if (!controller.signal.aborted) setActionError(error.message); })
      .finally(() => { if (!controller.signal.aborted) setPreviewLoading(false); });
    return () => controller.abort();
  }, [city, signature, ready]);

  async function run<T>(path: string, payload: object, receive: (value: T) => void) {
    setPendingAction(path); setActionError("");
    const version = generation.current;
    try { const value = await api<T>(path, payload); if (generation.current === version) receive(value); }
    catch (error) { if (generation.current === version) setActionError(error instanceof Error ? error.message : "Сервис не ответил"); }
    finally { setPendingAction(null); }
  }
  const result = submission ?? preview;
  const mapResult = useMemo(() => toMapResult(result ?? city?.baseline ?? null), [result, city]);

  return <div className="page">
    <header className="top compact-top">
      <div><p className="eyebrow">Симулятор городского управления</p><div className="brand">Аким на 5 часов</div>
        {page === "home" && <p className="lede">{city?.rules.decisions_exact ?? 5} решений. Бюджет {budget}. Посмотрите, как ваш план изменит город.</p>}</div>
      <div className="budget"><span>Остаток бюджета</span><strong>{budget - spent}</strong>
        <div className="bar"><div style={{ width: `${Math.min(100, spent / budget * 100)}%` }} /></div>
        <small>занято {spent} из {budget}</small></div>
    </header>

    {loadError && <p className="error">{loadError}</p>}
    <nav className="page-nav" aria-label="Разделы симулятора">{(Object.entries(pages) as [Page, string][]).map(([key, label]) =>
      <a key={key} href={`#${key}`} aria-current={page === key ? "page" : undefined}>{label}</a>)}</nav>
    <main>
    <h1 className={page === "home" ? "sr-only" : "page-title"} ref={pageHeading} tabIndex={-1}>{pages[page]}</h1>
    {actionError && <p className="error" role="alert">{actionError}</p>}
    {(!city && !loadError || pendingAction) && <div className="loading-card" role="status" aria-live="polite">
      <span className="loading-spinner" aria-hidden="true" /><div><strong>{!city ? "Загружаем город…" : pendingAction === "/advise" ? "Советник изучает ваш план…" : pendingAction === "/explain" ? "Готовим доклад…" : pendingAction === "/stress-test" ? "Проверяем устойчивость…" : "Рассчитываем результат…"}</strong>
      <p>{pendingAction === "/advise" && <span className="loading-spinner" aria-hidden="true" />}{pendingAction === "/advise" ? "Сравниваем варианты и проверяем, какие решения улучшат результат." : pendingAction === "/explain" ? "Собираем выводы о районах, последствиях и рисках." : "Это может занять немного времени."}</p>
      {(pendingAction === "/advise" || pendingAction === "/explain") && <small>Можно перейти в другой раздел — ответ появится в «Советнике».</small>}</div>
    </div>}
    {page === "home" && <section className="slot welcome">
      <p className="eyebrow">Ваш город. Ваши решения.</p><h2>Начните с плана развития</h2>
      <p>Изучите районы, распределите бюджет и проверьте, как ваши решения изменят жизнь города.</p>
      <div className="journey-grid">
        <a href="#city"><span>01</span><strong>Изучите город</strong><small>Карта, показатели и особенности районов.</small></a>
        <a href="#plan"><span>02</span><strong>Составьте план</strong><small>{city?.rules.decisions_exact ?? 5} решений в пределах бюджета {budget}.</small></a>
        <a href="#results"><span>03</span><strong>Оцените последствия</strong><small>Результат, стресс-сценарии и советы ИИ.</small></a>
      </div>
      <button className="primary" onClick={() => navigate("plan")}>{plan.length ? "Продолжить мой план" : "Составить план"}</button>
    </section>}
    {page === "city" && city && <>
      <div className="view-switch" role="group" aria-label="Данные о городе">{([ ["overview", "Сравнение районов"], ["indicators", "Показатели"], ["profile", "Характеристики"], ["map", "Карта"] ] as const).map(([key, label]) =>
        <button key={key} aria-pressed={cityView === key} onClick={() => setCityView(key)}>{label}</button>)}</div>
      {cityView === "map" ? <section className="slot map-view"><DistrictMap simulationResult={mapResult} selectedDistrict={selectedDistrict} onDistrictSelect={setSelectedDistrict} />
        <DistrictDetailsPanel districtId={selectedDistrict} simulationResult={mapResult} /></section> :
        <CityVisuals city={city} result={result ?? city.baseline} planned={Boolean(result)} view={cityView} />}
    </>}
    {page === "plan" && <>
      <div className="view-switch" role="group" aria-label="Планирование"><button aria-pressed={planView === "builder"} onClick={() => setPlanView("builder")}>Пять решений</button>
        <button aria-pressed={planView === "catalog"} onClick={() => setPlanView("catalog")}>Каталог мер</button></div>
      {planView === "builder" && <section>
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
      </section>}
      {planView === "catalog" && <section>
        <h2>Каталог</h2><div className="catalog">{measures.map((measure) => {
          const selected = slots.some((slot) => slot.measureId === measure.id);
          const free = slots.findIndex((slot) => !slot.measureId);
          const reason = selected ? "Уже выбрано" : free < 0 ? "Все слоты заняты" : measureReason(free, measure.id);
          return <button type="button" key={measure.id} className={selected ? "card on" : "card"}
            disabled={Boolean(reason)} title={reason ?? "Добавить в первый свободный слот"}
            onClick={() => { if (free >= 0) { setMeasure(free, measure.id); setPlanView("builder"); } }}>
            <span className="tag" data-dir={measure.direction}>{city?.directions[measure.direction]}</span>
            <strong>{measure.id}. {measure.name}</strong>
            <small>{measure.cost} · лаг {measure.lag} · {measure.type === "city" ? "город" : "район"}
              <br />{Object.entries(measure.effects).map(([code, value]) => `${code} ${value > 0 ? "+" : ""}${value}`).join(", ")}</small>
          </button>;
        })}</div>

      </section>}
      <section className="slot plan-summary"><div className="row"><div><strong>Выбрано {plan.length} из {city?.rules.decisions_exact ?? 5} мер</strong>
        <p className="hint">Стоимость {spent} · резерв {budget - spent}{result ? ` · предварительный балл ${fmt(result.score)}` : ""}</p></div>
        <button className="ghost" disabled={!preview} onClick={() => navigate("results")}>Посмотреть результат</button></div>
        {previewLoading && ready && <p className="inline-loading" role="status"><span className="loading-spinner" aria-hidden="true" /> Рассчитываем предварительный результат…</p>}
        {validation?.error && <p className="hint">{validation.error}</p>}
        <button type="button" className="primary" disabled={!preview || !validation?.valid || !teamName.trim() || busy}
          onClick={() => run<Submission>("/submit", { team_name: teamName.trim(), plan }, value => { setSubmission(value); navigate("results"); })}>{pendingAction === "/submit" && <span className="loading-spinner" aria-hidden="true" />}{pendingAction === "/submit" ? "Отправляем…" : "Отправить сценарий"}</button>
        {!teamName.trim() && <p className="hint">Укажите название команды в разделе «Пять решений», чтобы отправить сценарий.</p>}
      </section>
    </>}
    {page === "results" && <section className="slot results-page">
        {!result && <div className="empty-state"><h2>План ещё не готов</h2><p>Выберите меры и районы — здесь появится результат.</p><button className="primary" onClick={() => navigate("plan")}>Перейти к плану</button></div>}
        {result && <>
          <div className="score">{fmt(result.score)}</div>
          <p className="delta">база {fmt(city?.base_score ?? 0)} · изменение {fmt(result.score - (city?.base_score ?? 0))}</p>
          <div className="stats"><div><span>Средний балл районов</span><strong>{fmt(result.d_avg)}</strong></div>
            <div><span>Слабейший район</span><strong>{fmt(Math.min(...Object.values(result.district_scores)))}</strong></div>
            <div><span>Критические показатели</span><strong>{result.critical.length}</strong></div></div>
          <p>Слабый район: <strong>{districtName(result.weakest_district)}</strong></p>
          <p className="hint">Стоимость {result.cost} из {budget}. Остаток на счёт не влияет.</p>
          <table><thead><tr><th>Район</th><th>До</th><th>После</th></tr></thead>
            <tbody>{city?.districts.map((district) => <tr key={district.id}
              className={district.id === result.weakest_district ? "weak" : ""}>
              <td>{district.name}</td>
              <td>{fmt(city.indicators.reduce((sum, item) => sum + item.weight * result.indicators_before[district.id][item.code], 0))}</td>
              <td>{fmt(result.district_scores[district.id])}</td></tr>)}</tbody></table>
          <h2>Показатели, требующие внимания</h2>
          {result.critical.length ? <ul className="crits">{result.critical.map(([district, code]) =>
            <li key={`${district}-${code}`}>{districtName(district)}, {indicatorName(code)}: {fmt(result.indicators_after[district][code])}</li>)}</ul>
            : <p className="hint">Нет показателей строго ниже {city?.rules.critical_threshold}.</p>}
          <h2>Совместный эффект мер</h2>
          {result.contributions.filter((item) => item.source.includes("+")).length ?
            <ul className="crits">{result.contributions.filter((item) => item.source.includes("+")).map((item, index) =>
              <li key={index}>{item.source.split("+").map(id => byId.get(id)?.name ?? id).join(" + ")}: {indicatorName(item.indicator)} +{fmt(item.delta)} в районе {districtName(item.district)}</li>)}</ul>
            : <p className="hint">Выбранные меры не дают дополнительного совместного эффекта.</p>}
          <details><summary>Изменения в натуральных единицах</summary>
            <table><thead><tr><th>Район</th><th>Показатель</th><th>До</th><th>После</th></tr></thead>
              <tbody>{Object.entries(result.natural_units).flatMap(([district, values]) => Object.entries(values)
                .filter(([code]) => result.indicators_before[district][code] !== result.indicators_after[district][code])
                .map(([code, value]) => <tr key={`${district}-${code}`}><td>{districtName(district)}</td>
                  <td>{value.name}</td><td>{fmt(value.before)} {value.unit}</td><td>{fmt(value.after)} {value.unit}</td></tr>))}</tbody></table>
          </details>
        </>}
        {result && !submission && <p className="hint">Это предварительный расчёт. Отправьте сценарий из раздела «Мой план», чтобы открыть рейтинг, стресс-тест и советника.</p>}
        {submission && <>
          <p className="delta">Лучше {fmt(submission.percentile)}% допустимых планов · место {submission.rank} из {submission.valid_plans}</p>
          <p>Отставание от лучшего плана: {fmt(submission.gap)}</p>
          <p className="hint">Лучшее одно изменение: {fmt(submission.best_single_swap.score)} ({fmt(submission.best_single_swap.improvement)}). {planText(submission.best_single_swap.plan)}</p>
          <div className="journey-grid result-links"><a href="#stress">Проверить устойчивость →</a><a href="#advisor">Открыть советника →</a><a href="#city">Сравнить районы →</a></div>
        </>}
        {result && <button className="ghost" onClick={() => navigate("plan")}>Вернуться к плану</button>}
    </section>}
    {page === "risks" && (city && plan.length ? <RiskVisuals city={city} plan={plan} remaining={budget - spent} /> :
      <section className="slot empty-state"><h2>Сначала выберите меры</h2><p>Здесь появятся бюджет, сроки реализации и риски выбранных решений.</p><button className="primary" onClick={() => navigate("plan")}>Составить план</button></section>)}
    {(page === "advisor" || page === "stress") && !submission && <section className="slot empty-state"><h2>Сначала отправьте сценарий</h2>
      <p>После отправки плана станут доступны стресс-сценарии и рекомендации советника.</p><button className="primary" onClick={() => navigate("plan")}>Перейти к плану</button></section>}
    {page === "advisor" && submission && <section className="slot" id="ai-report">
      <h2>Доклад и советник</h2><p className="hint">Доклад объясняет текущий результат. Советник ищет и проверяет улучшение плана.</p>
      <div className="advisor-actions"><button type="button" className="primary" disabled={busy} onClick={() => run<Explanation>("/explain", { plan }, setExplanation)}>{pendingAction === "/explain" && <span className="loading-spinner" aria-hidden="true" />}{pendingAction === "/explain" ? "Готовим доклад…" : "Доклад для руководства"}</button>
        <button type="button" className="primary" disabled={busy} onClick={() => run<Advice>("/advise", { plan }, setAdvice)}>{pendingAction === "/advise" && <span className="loading-spinner" aria-hidden="true" />}{pendingAction === "/advise" ? "Ищем улучшения…" : "Спросить советника"}</button></div>
      {explanation && <AiReport report={explanation} />}
      {advice && <><h2>Проверенная альтернатива</h2><AiNotice usage={advice.search_ai} advisor />
        <div className="metric-grid">{advice.comparison.map(item => <div className="metric" key={item.label}><span>{item.label}</span><strong>{fmt(item.before)} → {fmt(item.after)}</strong></div>)}</div>
        <p><strong>Убрать или перенести:</strong> {planText(advice.removed) || "Без изменений"}</p>
        <p><strong>Добавить:</strong> {planText(advice.added) || "Без изменений"}</p>
        <button className="primary" disabled={busy || advice.improvement <= 0} onClick={() => { changeSlots(advice.best_plan.map(item => ({ measureId: item.measure, district: item.district ?? "" }))); setPlanView("builder"); navigate("plan"); }}>Применить совет и пересчитать</button>
        <p className="hint">Показатели альтернативы пересчитаны. Это лучший найденный советником вариант; после применения отправьте новый сценарий.</p>
        <AiReport report={advice.explanation} />
        <details><summary>Рассмотренные варианты</summary><ol>{advice.trace.map((step, i) => <li key={i}>
          {({original: "Исходный план", verified_swap: "Ближайшая альтернатива", tool: "Предложение ИИ"})[step.source] ?? "Проверка"}: {step.score === undefined ? step.error ?? "Ограничения проверены" : fmt(step.score)}
        </li>)}</ol></details></>}
    </section>}
    {page === "stress" && submission && city && <section className="slot" id="stress-overview">
      <h2>Стресс-тест</h2><p className="hint">Независимые сценарии, а не последовательность событий. Основной балл не меняется. В каждом сценарии реакция оплачивается из резерва отдельно; среднее не является прогнозом вероятности.</p>
      {city.events.map((event) => <label key={event.id}><span>
        <input type="checkbox" checked={responses.includes(event.id)} disabled={busy || event.response.cost > submission.remaining}
          onChange={(e) => { setStress(null); setResponses(e.target.checked ? [...responses, event.id] : responses.filter((id) => id !== event.id)); }} />
        {event.name}: {event.response.name} · {event.response.cost}</span><small>{event.description}</small></label>)}
      <button type="button" className="primary" disabled={busy}
        onClick={() => run<Stress>("/stress-test", { plan, buy_responses: responses }, setStress)}>{pendingAction === "/stress-test" && <span className="loading-spinner" aria-hidden="true" />}{pendingAction === "/stress-test" ? "Проверяем…" : "Провести стресс-тест"}</button>
      <StressVisuals baseline={submission.stress_test} current={stress ?? submission.stress_test} official={submission.score} />
      {!stress && responses.length > 0 && <p className="hint">Пока показаны сценарии без реакций. Нажмите «Провести стресс-тест», чтобы рассчитать выбранную защиту.</p>}
    </section>}
    {page === "leaderboard" && <section className="slot"><div className="row"><h2>Рейтинг команд</h2>
      <select aria-label="Порядок рейтинга" value={sort} onChange={(event) => setSort(event.target.value as "score" | "resilience")}>
        <option value="score">По баллу</option><option value="resilience">По устойчивости</option></select></div>
      {boardError && <p className="error" role="alert">{boardError}</p>}
      {!boardError && !board.length && <p className="hint">Пока нет отправленных сценариев. Ваш план может стать первым.</p>}
      <table><thead><tr><th>Команда</th><th>Балл</th><th>Планов позади</th><th>Устойчивость</th></tr></thead>
        <tbody>{board.map((row, i) => <tr key={`${row.team_name}-${i}`}><td>{row.team_name}</td><td>{fmt(row.score)}</td>
          <td>{fmt(row.percentile)}%</td><td>{fmt(row.resilience_average)}</td></tr>)}</tbody></table>
    </section>}
    </main>
  </div>;
}
