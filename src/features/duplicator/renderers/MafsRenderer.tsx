import "mafs/core.css";

import { Coordinates, Mafs, Plot } from "mafs";
import { compile } from "mathjs";
import { useMemo } from "react";

import type { VizBlock } from "@/types/duplicator";

/** Compile an expression in one variable to a numeric function (NaN on failure). */
function compileFn(expr: string, variable: string): (v: number) => number {
  const node = compile(expr);
  return (v: number) => {
    try {
      const out = node.evaluate({ [variable]: v });
      return typeof out === "number" && Number.isFinite(out) ? out : NaN;
    } catch {
      return NaN;
    }
  };
}

/**
 * 2D graphs via Mafs:
 * - `mafs_function`  — y = f(x) from `viz.expression`.
 * - `mafs_parametric` — (x(t), y(t)) from `viz.params.x` / `viz.params.y` in t.
 *
 * `viz.domain` sets the x (or t) range; a thrown bad expression is caught by the
 * VizRouter error boundary, which shows a fallback instead of crashing the page.
 */
export function MafsRenderer({ viz }: { viz: VizBlock }) {
  const content = useMemo(() => {
    if (viz.type === "mafs_parametric") {
      const params = viz.params ?? {};
      const xExpr = typeof params.x === "string" ? params.x : "cos(t)";
      const yExpr = typeof params.y === "string" ? params.y : "sin(t)";
      const fx = compileFn(xExpr, "t");
      const fy = compileFn(yExpr, "t");
      const t: [number, number] = viz.domain ?? [0, 2 * Math.PI];
      return <Plot.Parametric xy={(tt) => [fx(tt), fy(tt)]} t={t} />;
    }
    const fn = compileFn(viz.expression ?? "x", "x");
    return <Plot.OfX y={fn} />;
  }, [viz]);

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <Mafs height={240} viewBox={{ x: [-6, 6], y: [-6, 6] }}>
        <Coordinates.Cartesian />
        {content}
      </Mafs>
    </div>
  );
}
