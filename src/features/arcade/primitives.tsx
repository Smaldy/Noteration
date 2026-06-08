/**
 * Primitive shapes for the arcade cabinet blockout system.
 *
 * The cabinet is authored as a flat list of PARTS (see cabinetLayout.ts), each a
 * single primitive positioned by absolute coordinates inside a fixed design
 * stage. There are two render modes:
 *
 *   • BLOCKOUT — every part is a saturated-red shape with its label + live
 *     `w×h · x,y` readout, so you can nail proportions/coordinates by editing
 *     numbers in cabinetLayout.ts.
 *   • SKIN     — the same coordinates, now filled with the gradients / borders /
 *     shadows declared on each part.
 *
 * Shape vocabulary (the only four you need):
 *   rect   — plain rectangle (structure / panels)
 *   round  — rounded rectangle (`r` = corner radius)
 *   trap   — trapezoid for perspective. `taper` = units a pair of corners is
 *            pulled inward; bigger = stronger recede. SIGN picks which edge:
 *              taper > 0 → TOP narrower  (panel faces up / away)
 *              taper < 0 → BOTTOM narrower (panel faces down / toward you)
 *   oval   — ellipse / circle (buttons)
 */
import type { CSSProperties, ReactNode } from "react";

export type Shape = "rect" | "round" | "trap" | "oval";

export interface Part {
  /** kebab-case id; also the default blockout label and the functional-slot key. */
  id: string;
  shape: Shape;
  /** top-left corner + size, in stage design units. */
  x: number;
  y: number;
  w: number;
  h: number;
  /** round: corner radius (units). */
  r?: number;
  /** trap: units a corner-pair is pulled inward; >0 = top narrower, <0 = bottom narrower. */
  taper?: number;
  /** degrees, rotated about the part's own center. */
  rotate?: number;
  /** stacking order (higher = in front). Array order is the tiebreak. */
  z?: number;
  /** skin: background (solid or gradient). */
  fill?: string;
  /** skin: border shorthand. */
  border?: string;
  /** skin: box-shadow (or filter drop-shadow for trapezoids). */
  shadow?: string;
  /** blockout label override (defaults to id). */
  label?: string;
}

/** The clip / radius geometry for a part's shape, shared by both modes. */
function shapeGeometry(p: Part): CSSProperties {
  const s: CSSProperties = {};
  if (p.shape === "oval") s.borderRadius = "50%";
  else if (p.shape === "round") s.borderRadius = p.r ?? 10;
  else if (p.shape === "trap") {
    const t = p.taper ?? 24;
    const tp = (Math.abs(t) / p.w) * 100;
    s.clipPath =
      t >= 0
        ? `polygon(${tp}% 0, ${100 - tp}% 0, 100% 100%, 0 100%)` // top narrower
        : `polygon(0 0, 100% 0, ${100 - tp}% 100%, ${tp}% 100%)`; // bottom narrower
  }
  return s;
}

/** Absolute box for a part — used by both primitives and functional slots. */
export function partBox(p: Part): CSSProperties {
  return {
    position: "absolute",
    left: p.x,
    top: p.y,
    width: p.w,
    height: p.h,
    zIndex: p.z ?? 1,
    transform: p.rotate ? `rotate(${p.rotate}deg)` : undefined,
  };
}

export function Primitive({
  part,
  block,
  stageW,
  stageH,
  children,
}: {
  part: Part;
  block: boolean;
  /** stage width — enables the horizontal-centered (✓) check in blockout. */
  stageW?: number;
  /** stage height — enables the vertical-centered (✓) check in blockout. */
  stageH?: number;
  children?: ReactNode;
}) {
  const geom = shapeGeometry(part);

  if (block) {
    const cx = part.x + part.w / 2;
    const cy = part.y + part.h / 2;
    const hCentered = stageW != null && Math.round(cx) === Math.round(stageW / 2);
    const vCentered = stageH != null && Math.round(cy) === Math.round(stageH / 2);
    return (
      <div style={partBox(part)} className="prim-block">
        <div className="prim-block-fill" style={geom} />
        <span className="prim-label">{part.label ?? part.id}</span>
        <span className="prim-dim">
          {part.w}×{part.h} · {part.x},{part.y}
        </span>
        <span className="prim-center">
          c{cx},{cy}
          <b className={hCentered ? "ok" : "no"}>{hCentered ? " ↔✓" : ""}</b>
          <b className={vCentered ? "ok" : "no"}>{vCentered ? " ↕✓" : ""}</b>
        </span>
      </div>
    );
  }

  const skin: CSSProperties = { position: "absolute", inset: 0, ...geom };
  if (part.shape === "trap") {
    // box-shadow is clipped by clip-path; use a drop-shadow filter instead.
    skin.background = part.fill;
    if (part.shadow) skin.filter = `drop-shadow(${part.shadow})`;
  } else {
    skin.background = part.fill;
    skin.border = part.border;
    skin.boxShadow = part.shadow;
  }

  return (
    <div style={partBox(part)}>
      <div className="prim-skin" style={skin}>
        {children}
      </div>
    </div>
  );
}
