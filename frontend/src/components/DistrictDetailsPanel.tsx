import {
  type DistrictId,
  type SimulationResult,
  critsForDistrict,
  districtLabels,
  formatDelta,
  formatScore,
  getDistrictFinalScore,
  getDistrictScoreChange,
  indicatorGroups,
  indicatorLabel,
  indicatorValue,
  measuresForDistrict,
  synergiesForDistrict,
} from "../lib/districtMap";

type DistrictDetailsPanelProps = {
  districtId: DistrictId | null;
  simulationResult: SimulationResult | null;
};

export function DistrictDetailsPanel({ districtId, simulationResult }: DistrictDetailsPanelProps) {
  if (!districtId) {
    return <section className="district-details"><p className="hint">Нажмите район на карте, чтобы открыть подробности.</p></section>;
  }

  const score = getDistrictFinalScore(simulationResult, districtId);
  const delta = formatDelta(getDistrictScoreChange(simulationResult, districtId));
  const measures = measuresForDistrict(simulationResult, districtId);
  const synergies = synergiesForDistrict(simulationResult, districtId);
  const crits = critsForDistrict(simulationResult, districtId);

  return (
    <section className="district-details">
      <h3>{districtLabels[districtId]}</h3>
      {score === null ? (
        <p>Выберите меры для расчёта</p>
      ) : (
        <p>
          Оценка района: <strong>{formatScore(score)}</strong>
          {delta !== null && <> · изменение к базе: <strong>{delta}</strong></>}
        </p>
      )}

      {score !== null && indicatorGroups.map((group) => {
        const rows = group.codes.flatMap((code) => {
          const point = indicatorValue(simulationResult, districtId, code);
          return point ? [{ code, ...point }] : [];
        });
        if (rows.length === 0) return null;
        return (
          <div key={group.title}>
            <h4>{group.title}</h4>
            <ul>
              {rows.map((row) => (
                <li key={row.code}>
                  {indicatorLabel(row.code, row.name)}: {formatScore(row.before)} → {formatScore(row.after)}
                </li>
              ))}
            </ul>
          </div>
        );
      })}

      <h4>Меры, которые затрагивают район</h4>
      {measures.length === 0 ? <p className="hint">Нет данных о мерах для этого района.</p> : (
        <ul>
          {measures.map((item) => {
            const effects = (item.effects ?? []).filter((effect) => effect.district === districtId && effect.indicator);
            return (
              <li key={item.measure_id}>
                {item.measure_id} {item.name}
                {effects.length > 0 && ` — ${effects.map((effect) => `${effect.indicator} ${formatDelta(effect.delta ?? null) ?? ""}`).join(", ")}`}
              </li>
            );
          })}
        </ul>
      )}

      <h4>Синергии</h4>
      {synergies.length === 0 ? <p className="hint">Для этого района синергия не вернулась.</p> : (
        <ul>
          {synergies.map((item) => (
            <li key={(item.measures ?? []).join("+")}>
              {(item.measures ?? []).join(" + ")}: {item.indicator} {formatDelta(item.delta ?? null)}
            </li>
          ))}
        </ul>
      )}

      <h4>Критические показатели</h4>
      {crits.length === 0 ? <p className="hint">Сервер не вернул критических показателей для этого района.</p> : (
        <ul>
          {crits.map((item) => (
            <li key={item.indicator}>
              {item.indicator} {item.indicator_name ?? indicatorLabel(item.indicator ?? "")}: {formatScore(item.value ?? null)}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
