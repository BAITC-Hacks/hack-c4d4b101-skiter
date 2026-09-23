import { useState } from "react";
import {
  type DistrictId,
  type SimulationResult,
  districtLabels,
  getDistrictFinalScore,
  scoreToColor,
} from "../lib/districtMap";
import { DistrictTooltip } from "./DistrictTooltip";
import districtsSvg from "../assets/astana-districts.svg?raw";

type DistrictMapProps = {
  simulationResult: SimulationResult | null;
  selectedDistrict: DistrictId | null;
  onDistrictSelect: (district: DistrictId) => void;
};

const viewBox = districtsSvg.match(/viewBox="([^"]+)"/)?.[1] ?? "0 0 1080 1487.35";
const [, , viewWidth, viewHeight] = viewBox.split(/\s+/).map(Number);

const polygons: { id: DistrictId; d: string }[] = (["yesil", "almaty", "saryarka", "baikonur", "nura"] as const).map((id) => {
  const tag = districtsSvg.match(new RegExp(`<path\\b(?=[^>]*\\bid="${id}")[^>]*\\/>`))?.[0];
  const d = tag?.match(/\bd="([^"]*)"/)?.[1];
  if (!d) throw new Error(`Missing district path: ${id}`);
  return { id, d };
});

const legend = [
  ["#EF4444", "Красный — требует внимания"],
  ["#F97316", "Оранжевый — ниже среднего"],
  ["#FACC15", "Жёлтый — средний уровень"],
  ["#84CC16", "Светло-зелёный — хороший уровень"],
  ["#22C55E", "Зелёный — высокий уровень"],
] as const;

function anchor(path: SVGPathElement): { x: number; y: number } {
  const box = path.getBBox();
  return {
    x: ((box.x + box.width / 2) / viewWidth) * 100,
    y: ((box.y + box.height / 2) / viewHeight) * 100,
  };
}

export function DistrictMap({ simulationResult, selectedDistrict, onDistrictSelect }: DistrictMapProps) {
  const [hovered, setHovered] = useState<DistrictId | null>(null);
  const [tip, setTip] = useState<{ x: number; y: number } | null>(null);
  const active = polygons.find((item) => item.id === hovered);

  return (
    <div className="district-map-block">
      <div className="district-map">
        <svg viewBox={viewBox} className="district-map__overlay" role="img" aria-label="Карта районов Астаны">
          {polygons.map((district) => {
            const selected = district.id === selectedDistrict;
            return (
              <path
                key={district.id}
                id={district.id}
                className={selected ? "district-polygon district-polygon--selected" : "district-polygon"}
                d={district.d}
                data-district={district.id}
                role="button"
                tabIndex={0}
                aria-label={`Район ${districtLabels[district.id]}. Нажмите, чтобы открыть подробности.`}
                fill={scoreToColor(getDistrictFinalScore(simulationResult, district.id))}
                onClick={() => onDistrictSelect(district.id)}
                onKeyDown={(event) => {
                  if (event.key !== "Enter" && event.key !== " ") return;
                  event.preventDefault();
                  onDistrictSelect(district.id);
                }}
                onMouseEnter={(event) => {
                  setHovered(district.id);
                  setTip(anchor(event.currentTarget));
                }}
                onMouseLeave={() => {
                  setHovered((current) => (current === district.id ? null : current));
                  setTip(null);
                }}
                onFocus={(event) => {
                  setHovered(district.id);
                  setTip(anchor(event.currentTarget));
                }}
                onBlur={() => {
                  setHovered((current) => (current === district.id ? null : current));
                  setTip(null);
                }}
              />
            );
          })}
        </svg>
        {active && tip && (
          <DistrictTooltip
            districtId={active.id}
            simulationResult={simulationResult}
            x={tip.x}
            y={tip.y}
          />
        )}
      </div>
      <div className="map-legend">
        <p>Оценка района:</p>
        <ul>
          {legend.map(([color, label]) => (
            <li key={color}>
              <span style={{ background: color }} />
              {label}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
