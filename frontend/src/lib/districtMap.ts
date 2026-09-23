export type DistrictId = "yesil" | "almaty" | "saryarka" | "baikonur" | "nura";

export const districtLabels: Record<DistrictId, string> = {
  yesil: "Есиль",
  almaty: "Алматы",
  saryarka: "Сарыарка",
  baikonur: "Байконур",
  nura: "Нура",
};

export const districtIds: DistrictId[] = ["yesil", "almaty", "saryarka", "baikonur", "nura"];

export const indicatorLabels: Record<string, string> = {
  T1: "Разгрузка дорог",
  T2: "Доступность общественного транспорта",
  E1: "Озеленение",
  E2: "Качество воздуха",
  S1: "Школы и детсады",
  S2: "Поликлиники и первичная медпомощь",
  B1: "Безопасность улиц",
  B2: "Безопасность дорожного движения",
  C1: "Надёжность ЖКХ",
  C2: "Скорость решения обращений",
};

export const indicatorGroups: { title: string; codes: string[] }[] = [
  { title: "Транспорт", codes: ["T1", "T2"] },
  { title: "Экология", codes: ["E1", "E2"] },
  { title: "Социальная сфера", codes: ["S1", "S2"] },
  { title: "Безопасность", codes: ["B1", "B2"] },
  { title: "Городские сервисы", codes: ["C1", "C2"] },
];

type IndicatorPoint = {
  name?: string;
  before?: number;
  after?: number;
};

type DistrictSnapshot = {
  name?: string;
  d_before?: number;
  d_after?: number;
  score_after?: number;
  district_score?: number;
  D_d?: number;
  score?: number;
  indicators?: Record<string, IndicatorPoint>;
};

export type MeasureEffect = {
  district?: string;
  indicator?: string;
  delta?: number;
};

export type MeasureContribution = {
  measure_id?: string;
  name?: string;
  district?: string | null;
  effects?: MeasureEffect[];
};

export type AppliedSynergy = {
  measures?: string[];
  indicator?: string;
  delta?: number;
  district?: string;
};

export type CritCell = {
  district?: string;
  district_name?: string;
  indicator?: string;
  indicator_name?: string;
  value?: number;
};

export type SimulationResult = {
  valid?: boolean;
  districts?: Record<string, DistrictSnapshot> | null;
  measure_contributions?: MeasureContribution[] | null;
  synergies_applied?: AppliedSynergy[] | null;
  crits?: CritCell[] | null;
};

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function districtOf(result: SimulationResult | null, districtId: DistrictId): DistrictSnapshot | null {
  if (!result || result.valid === false) return null;
  return result.districts?.[districtId] ?? null;
}

export function scoreToColor(score: number | null): string {
  if (score === null) return "#E5E7EB";
  if (score < 50) return "#EF4444";
  if (score < 55) return "#F97316";
  if (score < 60) return "#FACC15";
  if (score < 65) return "#84CC16";
  return "#22C55E";
}

export function getDistrictFinalScore(simulationResult: SimulationResult | null, districtId: DistrictId): number | null {
  const district = districtOf(simulationResult, districtId);
  if (!district) return null;
  return asNumber(district.d_after)
    ?? asNumber(district.score_after)
    ?? asNumber(district.district_score)
    ?? asNumber(district.D_d)
    ?? asNumber(district.score);
}

export function getDistrictScoreBefore(simulationResult: SimulationResult | null, districtId: DistrictId): number | null {
  return asNumber(districtOf(simulationResult, districtId)?.d_before);
}

export function getDistrictScoreChange(simulationResult: SimulationResult | null, districtId: DistrictId): number | null {
  const after = getDistrictFinalScore(simulationResult, districtId);
  const before = getDistrictScoreBefore(simulationResult, districtId);
  if (after === null || before === null) return null;
  return after - before;
}

export function formatScore(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}

export function formatDelta(value: number | null): string | null {
  if (value === null) return null;
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}

export function indicatorLabel(code: string, fallback?: string): string {
  return indicatorLabels[code] ?? fallback ?? code;
}

export function lowestIndicators(simulationResult: SimulationResult | null, districtId: DistrictId, count = 2) {
  const indicators = districtOf(simulationResult, districtId)?.indicators;
  if (!indicators) return [];
  return Object.entries(indicators)
    .flatMap(([code, point]) => {
      const value = asNumber(point?.after);
      return value === null ? [] : [{ code, label: indicatorLabel(code, point?.name), value }];
    })
    .sort((left, right) => left.value - right.value)
    .slice(0, count);
}

export function indicatorValue(simulationResult: SimulationResult | null, districtId: DistrictId, code: string) {
  const point = districtOf(simulationResult, districtId)?.indicators?.[code];
  if (!point) return null;
  const before = asNumber(point.before);
  const after = asNumber(point.after);
  if (before === null && after === null) return null;
  return { before, after, name: point.name };
}

export function measuresForDistrict(simulationResult: SimulationResult | null, districtId: DistrictId) {
  return (simulationResult?.valid === false ? [] : simulationResult?.measure_contributions ?? []).filter((item) =>
    item.district === districtId || item.effects?.some((effect) => effect.district === districtId)
  );
}

export function synergiesForDistrict(simulationResult: SimulationResult | null, districtId: DistrictId) {
  if (simulationResult?.valid === false) return [];
  return (simulationResult?.synergies_applied ?? []).filter((item) => item.district === districtId);
}

export function critsForDistrict(simulationResult: SimulationResult | null, districtId: DistrictId) {
  if (simulationResult?.valid === false) return [];
  return (simulationResult?.crits ?? []).filter((item) => item.district === districtId);
}

const mapId: Record<string, DistrictId> = {
  esil: "yesil",
  yesil: "yesil",
  almaty: "almaty",
  saryarka: "saryarka",
  baikonur: "baikonur",
  nura: "nura",
};

type EngineSimulation = {
  valid?: boolean;
  district_scores?: Record<string, number>;
  indicators_before?: Record<string, Record<string, number>>;
  indicators_after?: Record<string, Record<string, number>>;
  contributions?: { source: string; district: string; indicator: string; delta: number }[];
  critical?: [string, string][];
};

export function toMapResult(simulation: EngineSimulation | null): SimulationResult | null {
  if (!simulation || simulation.valid === false || !simulation.district_scores) return null;
  const districts: Record<string, DistrictSnapshot> = {};
  for (const [rawId, score] of Object.entries(simulation.district_scores)) {
    const id = mapId[rawId];
    if (!id) continue;
    const before = simulation.indicators_before?.[rawId] ?? {};
    const after = simulation.indicators_after?.[rawId] ?? {};
    const indicators: Record<string, IndicatorPoint> = {};
    for (const code of new Set([...Object.keys(before), ...Object.keys(after)])) {
      indicators[code] = { before: before[code], after: after[code] };
    }
    districts[id] = { d_after: score, indicators };
  }
  const grouped = new Map<string, MeasureContribution>();
  const synergies: AppliedSynergy[] = [];
  for (const item of simulation.contributions ?? []) {
    const district = mapId[item.district];
    if (!district) continue;
    if (item.source.includes("+")) {
      synergies.push({ measures: item.source.split("+"), indicator: item.indicator, delta: item.delta, district });
      continue;
    }
    const row = grouped.get(item.source) ?? { measure_id: item.source, effects: [] };
    row.effects = [...(row.effects ?? []), { district, indicator: item.indicator, delta: item.delta }];
    grouped.set(item.source, row);
  }
  return {
    valid: true,
    districts,
    measure_contributions: [...grouped.values()],
    synergies_applied: synergies,
    crits: (simulation.critical ?? []).flatMap(([rawId, indicator]) => {
      const district = mapId[rawId];
      return district ? [{ district, indicator, value: simulation.indicators_after?.[rawId]?.[indicator] }] : [];
    }),
  };
}
