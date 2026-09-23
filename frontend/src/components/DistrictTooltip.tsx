import {
  type DistrictId,
  type SimulationResult,
  districtLabels,
  formatDelta,
  formatScore,
  getDistrictFinalScore,
  getDistrictScoreChange,
  lowestIndicators,
} from "../lib/districtMap";

type DistrictTooltipProps = {
  districtId: DistrictId;
  simulationResult: SimulationResult | null;
  x: number;
  y: number;
};

export function DistrictTooltip({ districtId, simulationResult, x, y }: DistrictTooltipProps) {
  const score = getDistrictFinalScore(simulationResult, districtId);
  const change = getDistrictScoreChange(simulationResult, districtId);
  const risks = lowestIndicators(simulationResult, districtId);
  const delta = formatDelta(change);

  return (
    <div className="district-tooltip" style={{ left: `${x}%`, top: `${y}%` }} role="tooltip">
      <strong>{districtLabels[districtId]}</strong>
      {score === null ? (
        <p>Выберите меры для расчёта</p>
      ) : (
        <>
          <p>Оценка района: {formatScore(score)}</p>
          {delta !== null && <p>Изменение к базе: {delta}</p>}
        </>
      )}
      {risks.length > 0 && (
        <p>
          Ниже остальных: {risks.map((item) => `${item.label} (${formatScore(item.value)})`).join(", ")}
        </p>
      )}
    </div>
  );
}
