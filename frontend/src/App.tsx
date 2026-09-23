import { useEffect, useMemo, useState } from "react";
import { DistrictDetailsPanel } from "./components/DistrictDetailsPanel";
import { DistrictMap } from "./components/DistrictMap";
import { type DistrictId } from "./lib/districtMap";

type Measure = {
  id: string;
  name: string;
  direction: string;
  direction_name: string;
  type: "district" | "city";
  cost: number;
  lag: number;
  effects: Record<string, number>;
};

type Catalog = {
  budget: number;
  horizon: number;
  max_decisions: number;
  max_per_direction: number;
  districts: { id: string; name: string; pop: number }[];
  measures: Measure[];
  incompatibilities: { measures: string[]; scope: "any" | "same_district" }[];
};

type Slot = { measureId: string; district: string };

type Crit = {
  district_name: string;
  indicator: string;
  indicator_name: string;
  value: number;
};

type DistrictRow = {
  name: string;
  d_before: number;
  d_after: number;
  indicators?: Record<string, { name?: string; before?: number; after?: number }>;
};

type SimulateResponse = {
  valid: boolean;
  cost: number | null;
  budget: number;
  score: number | null;
  baseline_score: number | null;
  delta_vs_baseline: number | null;
  d_avg: number | null;
  d_min: number | null;
  n_crit: number | null;
  weakest_district: string | null;
  weakest_district_name: string | null;
  districts: Record<string, DistrictRow> | null;
  measure_contributions?: {
    measure_id?: string;
    name?: string;
    district?: string | null;
    effects?: { district?: string; indicator?: string; delta?: number }[];
  }[] | null;
  synergies_applied: { measures: string[]; indicator: string; delta: number; district: string }[] | null;
  crits: (Crit & { district?: string })[] | null;
  violations: { code: string; message: string }[];
};

const emptySlots = (): Slot[] => Array.from({ length: 5 }, () => ({ measureId: "", district: "" }));

function effectsText(effects: Record<string, number>): string {
  return Object.entries(effects)
    .map(([key, value]) => `${key} ${value > 0 ? "+" : ""}${value}`)
    .join(", ");
}

function detailOf(data: { detail?: unknown }): string {
  return typeof data.detail === "string" ? data.detail : "Сервис не ответил";
}

function formatInline(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => (
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={index}>{part.slice(2, -2)}</strong>
      : part
  ));
}

function Explanation({ text }: { text: string }) {
  const blocks: JSX.Element[] = [];
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  let index = 0;
  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ""));
        index += 1;
      }
      blocks.push(<ul key={blocks.length}>{items.map((item, itemIndex) => <li key={itemIndex}>{formatInline(item)}</li>)}</ul>);
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^\d+\.\s+/, ""));
        index += 1;
      }
      blocks.push(<ol key={blocks.length}>{items.map((item, itemIndex) => <li key={itemIndex}>{formatInline(item)}</li>)}</ol>);
      continue;
    }
    if (/^\*\*[^*]+\*\*:?$/.test(line)) {
      blocks.push(<h3 key={blocks.length}>{line.replace(/\*\*/g, "").replace(/:$/, "")}</h3>);
      index += 1;
      continue;
    }
    const paragraph = [line];
    index += 1;
    while (
      index < lines.length
      && lines[index].trim()
      && !/^[-*]\s+/.test(lines[index].trim())
      && !/^\d+\.\s+/.test(lines[index].trim())
      && !/^\*\*[^*]+\*\*:?$/.test(lines[index].trim())
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(<p key={blocks.length}>{formatInline(paragraph.join(" "))}</p>);
  }
  return <div className="explain">{blocks}</div>;
}

export function App() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [loadError, setLoadError] = useState("");
  const [slots, setSlots] = useState<Slot[]>(emptySlots);
  const [result, setResult] = useState<SimulateResponse | null>(null);
  const [simError, setSimError] = useState("");
  const [loading, setLoading] = useState(false);
  const [explanation, setExplanation] = useState("");
  const [explaining, setExplaining] = useState(false);
  const [mapResult, setMapResult] = useState<SimulateResponse | null>(null);
  const [selectedDistrict, setSelectedDistrict] = useState<DistrictId | null>(null);

  useEffect(() => {
    fetch("/api/catalog")
      .then(async (response) => {
        if (!response.ok) throw new Error("Каталог недоступен. Запустите backend на порту 8000.");
        return response.json() as Promise<Catalog>;
      })
      .then(setCatalog)
      .catch((error: unknown) => setLoadError(error instanceof Error ? error.message : "Каталог недоступен"));
  }, []);

  const measures = catalog?.measures ?? [];
  const byId = useMemo(() => new Map(measures.map((measure) => [measure.id, measure])), [measures]);
  const budget = catalog?.budget ?? 100;
  const spent = slots.reduce((sum, slot) => sum + (byId.get(slot.measureId)?.cost ?? 0), 0);

  function blockedMeasure(slotIndex: number, measureId: string): boolean {
    if (!catalog) return true;
    if (measureId === slots[slotIndex].measureId) return false;
    if (slots.some((slot, index) => index !== slotIndex && slot.measureId === measureId)) return true;
    const measure = byId.get(measureId);
    if (!measure) return true;
    const currentCost = byId.get(slots[slotIndex].measureId)?.cost ?? 0;
    if (spent - currentCost + measure.cost > budget) return true;
    const sameDirection = slots.filter((slot, index) => {
      return index !== slotIndex && byId.get(slot.measureId)?.direction === measure.direction;
    }).length;
    if (sameDirection >= catalog.max_per_direction) return true;
    return catalog.incompatibilities.some((rule) => {
      if (rule.scope !== "any") return false;
      const [left, right] = rule.measures;
      const other = measureId === left ? right : measureId === right ? left : null;
      return Boolean(other && slots.some((slot, index) => index !== slotIndex && slot.measureId === other));
    });
  }

  function districtBlocked(slotIndex: number, districtId: string): boolean {
    if (!catalog || slots[slotIndex].district === districtId) return false;
    const measureId = slots[slotIndex].measureId;
    return catalog.incompatibilities.some((rule) => {
      if (rule.scope !== "same_district") return false;
      const [left, right] = rule.measures;
      const other = measureId === left ? right : measureId === right ? left : null;
      return Boolean(other && slots.some((slot, index) => index !== slotIndex && slot.measureId === other && slot.district === districtId));
    });
  }

  function cardReason(measure: Measure): string | null {
    if (slots.some((slot) => slot.measureId === measure.id)) return "уже выбрано";
    const index = slots.findIndex((slot) => !slot.measureId);
    if (index < 0) return "все 5 слотов заняты";
    if (!blockedMeasure(index, measure.id)) return null;
    const currentCost = byId.get(slots[index].measureId)?.cost ?? 0;
    if (spent - currentCost + measure.cost > budget) return "не хватает бюджета";
    return "нельзя добавить: направление или несовместимость";
  }

  function setMeasure(index: number, measureId: string) {
    setSlots((prev) => prev.map((slot, slotIndex) => {
      if (slotIndex !== index) return slot;
      const measure = byId.get(measureId);
      return { measureId, district: measure?.type === "district" ? slot.district : "" };
    }));
  }

  const signature = JSON.stringify(slots);

  useEffect(() => {
    if (!catalog) return;
    setExplanation("");
    const ready = slots.every((slot) => {
      const measure = byId.get(slot.measureId);
      if (!measure) return false;
      return measure.type === "city" || Boolean(slot.district);
    });
    if (!ready) {
      setResult(null);
      setSimError("");
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    const decisions = slots.map((slot) => {
      const measure = byId.get(slot.measureId)!;
      return { measure_id: slot.measureId, district: measure.type === "district" ? slot.district : null };
    });
    fetch("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decisions }),
      signal: controller.signal,
    })
      .then(async (response) => {
        const data = await response.json() as SimulateResponse & { detail?: unknown };
        if (!response.ok) throw new Error(detailOf(data));
        setResult(data);
        if (data.valid) setMapResult(data);
        setSimError("");
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setResult(null);
        setSimError(error instanceof Error ? error.message : "Ошибка расчёта");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [signature, catalog, byId, slots]);

  async function explain() {
    if (!result?.valid) return;
    setExplaining(true);
    setExplanation("");
    try {
      const response = await fetch("/api/explain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(result),
      });
      const data = await response.json() as { explanation?: string; detail?: unknown };
      setExplanation(response.ok ? data.explanation ?? "" : detailOf(data));
    } catch {
      setExplanation("Не удалось получить объяснение");
    } finally {
      setExplaining(false);
    }
  }

  const districtName = (id: string) => catalog?.districts.find((district) => district.id === id)?.name ?? id;

  return (
    <div className="page">
      <header className="top">
        <div>
          <p className="eyebrow">Симулятор городского управления</p>
          <h1>Аким на 5 часов</h1>
          <p className="lede">
            Ровно 5 мер и бюджет 100. Остаток не даёт бонуса. Не больше двух мер одного направления.
            Счёт считает движок, кнопка «Объяснить» только комментирует эти числа.
          </p>
        </div>
        <div className="budget">
          <span>Остаток бюджета</span>
          <strong>{budget - spent}</strong>
          <div className="bar"><div style={{ width: `${Math.min(100, spent)}%` }} /></div>
          <small>занято {spent} из {budget}</small>
        </div>
      </header>

      {loadError && <p className="error">{loadError}</p>}

      <div className="layout">
        <section>
          <div className="row">
            <h2>Пять решений</h2>
            <button type="button" className="ghost" onClick={() => { setSlots(emptySlots()); setMapResult(null); setSelectedDistrict(null); }}>Сбросить</button>
          </div>
          <ol className="slots">
            {slots.map((slot, index) => {
              const measure = byId.get(slot.measureId);
              return (
                <li className="slot" key={index}>
                  <div className="slot-head">
                    <span>Решение {index + 1}</span>
                    {slot.measureId && (
                      <button type="button" className="ghost" onClick={() => setMeasure(index, "")}>Убрать</button>
                    )}
                  </div>
                  <div className="fields">
                    <label>
                      Мера
                      <select value={slot.measureId} onChange={(event) => setMeasure(index, event.target.value)}>
                        <option value="">Выберите меру</option>
                        {measures.map((item) => (
                          <option key={item.id} value={item.id} disabled={blockedMeasure(index, item.id)}>
                            {item.id} · {item.name} · {item.cost}
                          </option>
                        ))}
                      </select>
                    </label>
                    {measure?.type === "district" ? (
                      <label>
                        Район
                        <select
                          value={slot.district}
                          onChange={(event) => setSlots((prev) => prev.map((item, slotIndex) => (
                            slotIndex === index ? { ...item, district: event.target.value } : item
                          )))}
                        >
                          <option value="">Район</option>
                          {catalog?.districts.map((district) => (
                            <option key={district.id} value={district.id} disabled={districtBlocked(index, district.id)}>
                              {district.name}
                            </option>
                          ))}
                        </select>
                      </label>
                    ) : (
                      <p className="city-note">{measure ? "Весь город" : "Сначала выберите меру"}</p>
                    )}
                  </div>
                  {measure && (
                    <p className="hint">
                      {measure.direction_name} · {measure.type === "city" ? "город" : "район"} · лаг {measure.lag} кв. · {effectsText(measure.effects)}
                    </p>
                  )}
                </li>
              );
            })}
          </ol>

          <h2>Каталог</h2>
          <div className="catalog">
            {measures.map((measure) => {
              const reason = cardReason(measure);
              const selected = slots.some((slot) => slot.measureId === measure.id);
              return (
                <button
                  type="button"
                  key={measure.id}
                  className={selected ? "card on" : "card"}
                  disabled={reason !== null}
                  title={reason ?? "Добавить в первый свободный слот"}
                  onClick={() => {
                    const index = slots.findIndex((slot) => !slot.measureId);
                    if (index >= 0) setMeasure(index, measure.id);
                  }}
                >
                  <span className="tag" data-dir={measure.direction}>{measure.direction_name}</span>
                  <strong>{measure.id}. {measure.name}</strong>
                  <small>
                    {measure.cost} · лаг {measure.lag} · {measure.type === "city" ? "город" : "район"}
                    <br />
                    {effectsText(measure.effects)}
                  </small>
                </button>
              );
            })}
          </div>
        </section>

        <aside className="panel">
          <h2>Результат</h2>
          {loading && <p>Считаем…</p>}
          {!loading && !result && !simError && <p className="hint">Заполните 5 слотов — Score появится здесь.</p>}
          {simError && <p className="error">{simError}</p>}
          {result && !result.valid && (
            <ul className="crits">
              {result.violations.map((item) => <li key={item.code} className="error">{item.message}</li>)}
            </ul>
          )}
          {result?.valid && result.score !== null && (
            <>
              <div className="score">{result.score.toFixed(2)}</div>
              <p className="delta">
                база {result.baseline_score?.toFixed(2)} · дельта {result.delta_vs_baseline !== null && result.delta_vs_baseline > 0 ? "+" : ""}{result.delta_vs_baseline?.toFixed(2)}
              </p>
              <div className="stats">
                <div><span>D средн.</span><strong>{result.d_avg?.toFixed(2)}</strong></div>
                <div><span>D мин.</span><strong>{result.d_min?.toFixed(2)}</strong></div>
                <div><span>N крит.</span><strong>{result.n_crit}</strong></div>
              </div>
              <p>Слабый район: <strong>{result.weakest_district_name}</strong></p>
              <p className="hint">Стоимость {result.cost} из {result.budget}. Остаток на счёт не влияет.</p>
            </>
          )}
          <DistrictMap
            simulationResult={mapResult}
            selectedDistrict={selectedDistrict}
            onDistrictSelect={setSelectedDistrict}
          />
          <DistrictDetailsPanel districtId={selectedDistrict} simulationResult={mapResult} />
          {result?.valid && result.score !== null && (
            <>
              <table>
                <thead>
                  <tr><th>Район</th><th>D до</th><th>D после</th></tr>
                </thead>
                <tbody>
                  {result.districts && Object.entries(result.districts).map(([id, district]) => (
                    <tr key={id} className={id === result.weakest_district ? "weak" : undefined}>
                      <td>{district.name}</td>
                      <td>{district.d_before.toFixed(2)}</td>
                      <td>{district.d_after.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <h2>Критические ячейки</h2>
              {result.crits && result.crits.length > 0 ? (
                <ul className="crits">
                  {result.crits.map((crit) => (
                    <li key={`${crit.district_name}-${crit.indicator}`}>
                      {crit.district_name}, {crit.indicator} {crit.indicator_name}: {crit.value.toFixed(2)}
                    </li>
                  ))}
                </ul>
              ) : <p className="hint">Нет показателей строго ниже 40.</p>}
              <h2>Синергии</h2>
              {result.synergies_applied && result.synergies_applied.length > 0 ? (
                <ul className="crits">
                  {result.synergies_applied.map((item) => (
                    <li key={item.measures.join("+")}>
                      {item.measures.join(" + ")}: {item.indicator} +{item.delta} в районе {districtName(item.district)}
                    </li>
                  ))}
                </ul>
              ) : <p className="hint">Синергия не сработала.</p>}
              <button type="button" className="primary" onClick={explain} disabled={explaining}>
                {explaining ? "Объясняем…" : "Объяснить"}
              </button>
              {explanation && <Explanation text={explanation} />}
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
