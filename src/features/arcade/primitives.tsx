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
 *   trap   — trapezoid for perspective (`taper` = units each TOP corner is
 *            pulled inward; bigger taper = stronger recede)
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
  /** trap: units each TOP corner is pulled inward (perspective). */
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
    const tp = ((p.taper ?? 24) / p.w) * 100;
    s.clipPath = `polygon(${tp}% 0, ${100 - tp}% 0, 100% 100%, 0 100%)`;
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
  children,
}: {
  part: Part;
  block: boolean;
  children?: ReactNode;
}) {
  const geom = shapeGeometry(part);

  if (block) {
    return (
      <div style={partBox(part)} className="prim-block">
        <div className="prim-block-fill" style={geom} />
        <span className="prim-label">{part.label ?? part.id}</span>
        <span className="prim-dim">
          {part.w}×{part.h} · {part.x},{part.y}
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
