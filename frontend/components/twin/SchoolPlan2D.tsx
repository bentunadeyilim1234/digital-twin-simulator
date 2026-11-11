"use client";

// 2D schematic fallback (no WebGL needed). Same zones, same engine-derived tints.
import { ZONES, type FloorId, type ZoneId } from "@/lib/zones";

const SCALE = 26;
const OX = 9 * SCALE;
const OZ = 5 * SCALE;

export function SchoolPlan2D({ tints, selected, onSelect, floor, labels }: {
  tints: Record<ZoneId, string>; selected: ZoneId | null; onSelect: (z: ZoneId | null) => void; floor: FloorId | "all"; labels: Record<ZoneId, string>;
}) {
  const shownFloor = floor === "all" ? 0 : floor;
  return (
    <svg viewBox={`0 0 ${22 * SCALE} ${13.5 * SCALE}`} className="h-full w-full" role="img" aria-label="2D school schematic" data-testid="twin-2d">
      <rect x={0} y={0} width={22 * SCALE} height={13.5 * SCALE} fill="#0e1217" />
      {ZONES.map((z) => z.blocks.filter((b) => b.floor === shownFloor || b.floor === "outdoor" || (floor === "all" && b.floor === 0)).map((b, i) => {
        const x = OX + (b.pos[0] - b.size[0] / 2) * SCALE;
        const y = OZ + (b.pos[2] - b.size[2] / 2) * SCALE;
        const isSel = selected === z.id;
        return (
          <g key={`${z.id}-${i}`} onClick={() => onSelect(z.id)} className="cursor-pointer">
            <rect x={x} y={y} width={b.size[0] * SCALE} height={b.size[2] * SCALE} rx={3} fill={tints[z.id]}
              opacity={b.floor === "outdoor" ? 0.65 : 0.95} stroke={isSel ? "#f0c070" : "#0b0e12"} strokeWidth={isSel ? 3 : 1.5} />
            {i === 0 && b.size[0] * SCALE > 60 && (
              <text x={x + (b.size[0] * SCALE) / 2} y={y + (b.size[2] * SCALE) / 2 + 4} textAnchor="middle" fontSize="11" fill="#e8ebef" style={{ pointerEvents: "none" }}>
                {labels[z.id]}
              </text>
            )}
          </g>
        );
      }))}
    </svg>
  );
}
