import { compile } from "mathjs";
import { type ComponentType, Suspense, lazy, useMemo } from "react";

import type { VizBlock } from "@/types/duplicator";

interface PlotProps {
  data: unknown[];
  layout?: Record<string, unknown>;
  config?: Record<string, unknown>;
  style?: Record<string, unknown>;
  useResizeHandler?: boolean;
}

// Lazy-load Plotly (it's heavy) and build a React component from the dist-min
// bundle via react-plotly.js's factory.
const Plot = lazy(async () => {
  const [{ default: createPlotlyComponent }, plotly] = await Promise.all([
    import("react-plotly.js/factory"),
    import("plotly.js-dist-min"),
  ]);
  return {
    default: createPlotlyComponent(plotly) as ComponentType<PlotProps>,
  };
});

const ACCENT = "#6366f1";
const SURFACE_N = 40; // grid resolution for 3D surfaces
const LINE_N = 480; // sample count for 2D curves (smooth without being heavy)
const CONFIG = { responsive: true, displayModeBar: false };

function linspace(a: number, b: number, n: number): number[] {
  if (n < 2) return [a];
  const step = (b - a) / (n - 1);
  return Array.from({ length: n }, (_, i) => a + i * step);
}

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

/** Pull (re, im) out of a mathjs evaluation result. */
function reim(value: unknown): [number, number] {
  if (typeof value === "number") return [value, 0];
  if (value && typeof value === "object" && "re" in value && "im" in value) {
    const v = value as { re: number; im: number };
    return [v.re, v.im];
  }
  return [NaN, NaN];
}

function percentile(sorted: number[], p: number): number {
  const idx = (sorted.length - 1) * p;
  const lo = Math.floor(idx);
  const hi = Math.ceil(idx);
  return lo === hi ? sorted[lo] : sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
}

/**
 * Frame an axis to the 5th–95th percentile of the data (padded), so a curve with
 * a pole (tan, 1/x, log x / x²) shows its interesting band instead of collapsing
 * against an infinite spike.
 */
function fitRange(samples: number[], fallback: [number, number]): [number, number] {
  const finite = samples.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (finite.length < 2) return fallback;
  let lo = percentile(finite, 0.05);
  let hi = percentile(finite, 0.95);
  if (!(hi > lo)) {
    const c = finite[Math.floor(finite.length / 2)];
    lo = c - 4;
    hi = c + 4;
  }
  const pad = (hi - lo) * 0.15;
  return [lo - pad, hi + pad];
}

/**
 * Replace a value with `null` when it's non-finite or shoots far outside the
 * framed window. `null` makes Plotly *break* the line (with `connectgaps:false`)
 * rather than drawing a tall vertical streak through an asymptote.
 */
function clampNull(v: number, [lo, hi]: [number, number]): number | null {
  if (!Number.isFinite(v)) return null;
  const mid = (lo + hi) / 2;
  return Math.abs(v - mid) > (hi - lo) * 3 ? null : v;
}

/** Theme-aware plot colors (Plotly layout is static, so we read the mode once). */
function themeColors() {
  const dark =
    typeof document !== "undefined" &&
    document.documentElement.classList.contains("dark");
  return {
    grid: dark ? "rgba(148,163,184,0.16)" : "rgba(100,116,139,0.16)",
    zero: dark ? "rgba(148,163,184,0.45)" : "rgba(100,116,139,0.4)",
    font: dark ? "#cbd5e1" : "#475569",
  };
}

/**
 * All Exercise-Duplicator graphs render through Plotly — one clean, themed,
 * battle-tested engine instead of two:
 * - `mafs_function`   — y = f(x) line.
 * - `mafs_parametric` — (x(t), y(t)) curve.
 * - `plotly_complex`  — f sampled over the reals, plotted on the Argand plane.
 * - `plotly_3d`       — z = f(x, y) surface.
 *
 * 2D curves auto-frame to the data (percentile range) and break the line at poles
 * so asymptotes look clean, not like a black wall. A bad expression throws and is
 * caught by the VizRouter error boundary.
 */
export function PlotlyRenderer({
  viz,
  height = 280,
}: {
  viz: VizBlock;
  height?: number;
}) {
  const { data, layout } = useMemo<{
    data: unknown[];
    layout: Record<string, unknown>;
  }>(() => {
    const c = themeColors();
    const axis2d = (title?: string) => ({
      gridcolor: c.grid,
      zerolinecolor: c.zero,
      linecolor: c.grid,
      tickfont: { color: c.font, size: 11 },
      ...(title ? { title: { text: title, font: { color: c.font, size: 12 } } } : {}),
    });
    const base = {
      autosize: true,
      height,
      margin: { l: 44, r: 16, t: 10, b: 36 },
      paper_bgcolor: "transparent",
      plot_bgcolor: "transparent",
      showlegend: false,
      font: { color: c.font },
      hovermode: "closest" as const,
    };
    const lineTrace = (x: (number | null)[], y: (number | null)[]) => ({
      type: "scatter",
      mode: "lines",
      x,
      y,
      line: { color: ACCENT, width: 2.5, shape: "spline" as const },
      connectgaps: false,
    });

    if (viz.type === "plotly_3d") {
      const [a, b] = viz.domain ?? [-5, 5];
      const node = compile(viz.expression ?? "x");
      const xs = linspace(a, b, SURFACE_N);
      const ys = linspace(a, b, SURFACE_N);
      const z = ys.map((y) =>
        xs.map((x) => {
          const out = node.evaluate({ x, y });
          return typeof out === "number" && Number.isFinite(out) ? out : 0;
        }),
      );
      return {
        data: [{ type: "surface", x: xs, y: ys, z, colorscale: "Viridis", showscale: false }],
        layout: { ...base, scene: { aspectmode: "cube" } },
      };
    }

    if (viz.type === "plotly_complex") {
      const [a, b] = viz.domain ?? [-5, 5];
      const node = compile(viz.expression ?? "x");
      const xs = linspace(a, b, LINE_N);
      const re: number[] = [];
      const im: number[] = [];
      for (const x of xs) {
        const [r, i] = reim(node.evaluate({ x, z: x }));
        re.push(r);
        im.push(i);
      }
      const xr = fitRange(re, [-5, 5]);
      const yr = fitRange(im, [-5, 5]);
      return {
        data: [lineTrace(re.map((v) => clampNull(v, xr)), im.map((v) => clampNull(v, yr)))],
        layout: { ...base, xaxis: { ...axis2d("Re"), range: xr }, yaxis: { ...axis2d("Im"), range: yr } },
      };
    }

    if (viz.type === "mafs_parametric") {
      const params = viz.params ?? {};
      const fx = compileFn(typeof params.x === "string" ? params.x : "cos(t)", "t");
      const fy = compileFn(typeof params.y === "string" ? params.y : "sin(t)", "t");
      const [t0, t1] = viz.domain ?? [0, 2 * Math.PI];
      const ts = linspace(t0, t1, LINE_N);
      const xsRaw = ts.map(fx);
      const ysRaw = ts.map(fy);
      const xr = fitRange(xsRaw, [-6, 6]);
      const yr = fitRange(ysRaw, [-6, 6]);
      return {
        data: [lineTrace(xsRaw.map((v) => clampNull(v, xr)), ysRaw.map((v) => clampNull(v, yr)))],
        layout: { ...base, xaxis: { ...axis2d(), range: xr }, yaxis: { ...axis2d(), range: yr } },
      };
    }

    // mafs_function: y = f(x)
    const f = compileFn(viz.expression ?? "x", "x");
    const [x0, x1] = viz.domain ?? [-6, 6];
    const xs = linspace(x0, x1, LINE_N);
    const ysRaw = xs.map(f);
    const yr = fitRange(ysRaw, [-6, 6]);
    return {
      data: [lineTrace(xs, ysRaw.map((v) => clampNull(v, yr)))],
      layout: { ...base, xaxis: { ...axis2d(), range: [x0, x1] }, yaxis: { ...axis2d(), range: yr } },
    };
  }, [viz, height]);

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <Suspense
        fallback={
          <div
            className="flex items-center justify-center text-sm text-muted-foreground"
            style={{ height }}
          >
            Loading plot…
          </div>
        }
      >
        <Plot
          data={data}
          layout={layout}
          config={CONFIG}
          useResizeHandler
          style={{ width: "100%", height: `${height}px` }}
        />
      </Suspense>
    </div>
  );
}
