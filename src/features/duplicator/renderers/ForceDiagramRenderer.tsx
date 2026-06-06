import type { VizBlock } from "@/types/duplicator";

const SIZE = 240;
const CENTER = SIZE / 2;
const MAX_LEN = 80;

interface Force {
  label: string;
  angle_deg: number;
  magnitude: number;
  color: string;
}

function parseForces(raw: unknown): Force[] {
  if (!Array.isArray(raw)) return [];
  const forces: Force[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const f = item as Record<string, unknown>;
    const magnitude = typeof f.magnitude === "number" ? f.magnitude : 1;
    const angle_deg = typeof f.angle_deg === "number" ? f.angle_deg : 0;
    forces.push({
      label: typeof f.label === "string" ? f.label : "",
      angle_deg,
      magnitude,
      color: typeof f.color === "string" ? f.color : "#6366f1",
    });
  }
  return forces;
}

/**
 * Static force/torque diagrams in pure SVG (no library). Reads
 * `viz.params.forces` (label / angle_deg / magnitude / color), draws each as an
 * arrow whose length is proportional to its magnitude (capped at 80px) from a
 * central object.
 */
export function ForceDiagramRenderer({ viz }: { viz: VizBlock }) {
  const forces = parseForces((viz.params ?? {}).forces);
  const maxMag = Math.max(1, ...forces.map((f) => Math.abs(f.magnitude)));

  return (
    <div className="flex justify-center overflow-hidden rounded-lg border border-border bg-card">
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}>
        {forces.map((f, i) => {
          const len = (Math.abs(f.magnitude) / maxMag) * MAX_LEN;
          const rad = (f.angle_deg * Math.PI) / 180;
          const ex = CENTER + Math.cos(rad) * len;
          const ey = CENTER - Math.sin(rad) * len; // SVG y points down
          // Arrowhead: a small triangle at the tip, aligned with the arrow.
          const head = 8;
          const left = {
            x: ex - head * Math.cos(rad - Math.PI / 6),
            y: ey + head * Math.sin(rad - Math.PI / 6),
          };
          const right = {
            x: ex - head * Math.cos(rad + Math.PI / 6),
            y: ey + head * Math.sin(rad + Math.PI / 6),
          };
          return (
            <g key={i}>
              <line
                x1={CENTER}
                y1={CENTER}
                x2={ex}
                y2={ey}
                stroke={f.color}
                strokeWidth={2.5}
              />
              <polygon
                points={`${ex},${ey} ${left.x},${left.y} ${right.x},${right.y}`}
                fill={f.color}
              />
              {f.label && (
                <text
                  x={ex + Math.cos(rad) * 12}
                  y={ey - Math.sin(rad) * 12}
                  fontSize={12}
                  fill="currentColor"
                  textAnchor="middle"
                  dominantBaseline="middle"
                >
                  {f.label}
                </text>
              )}
            </g>
          );
        })}
        {/* The object the forces act on. */}
        <rect
          x={CENTER - 12}
          y={CENTER - 12}
          width={24}
          height={24}
          rx={4}
          fill="#475569"
        />
      </svg>
    </div>
  );
}
