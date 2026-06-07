import { ZoomIn, ZoomOut, RotateCcw } from "lucide-react";
import { compile } from "mathjs";
import {
  type ComponentType,
  type ReactNode,
  Suspense,
  lazy,
  useEffect,
  useMemo,
  useState,
} from "react";

import type { VizBlock, VizPiece } from "@/types/duplicator";

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
// Distinct hues for a *system* of functions plotted together.
const PALETTE = ["#6366f1", "#10b981", "#f59e0b", "#ec4899", "#06b6d4", "#a855f7"];
const SURFACE_N = 40; // grid resolution for 3D surfaces
const LINE_N = 480; // sample count for 2D curves (smooth without being heavy)
const CONFIG = { responsive: true, displayModeBar: false };

type Range = [number, number];
type Num = number | null;

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
function fitRange(samples: number[], fallback: Range): Range {
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
function clampNull(v: number, [lo, hi]: Range): Num {
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

/** Read piecewise branches from `viz.pieces` (or `viz.params.pieces`). */
function readPieces(viz: VizBlock): VizPiece[] {
  const raw = (viz.pieces ?? (viz.params?.pieces as unknown)) as unknown;
  if (!Array.isArray(raw)) return [];
  const out: VizPiece[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const o = item as Record<string, unknown>;
    const expr =
      typeof o.expression === "string"
        ? o.expression
        : typeof o.expr === "string"
          ? o.expr
          : null;
    if (!expr) continue;
    const dom =
      Array.isArray(o.domain) &&
      o.domain.length === 2 &&
      o.domain.every((n) => typeof n === "number")
        ? ([o.domain[0], o.domain[1]] as Range)
        : viz.domain;
    out.push({ expression: expr, domain: dom });
  }
  return out;
}

/** Read a system of full-domain expressions from `viz.expressions`. */
function readExpressions(viz: VizBlock): string[] {
  const raw = (viz.expressions ?? (viz.params?.expressions as unknown)) as unknown;
  if (!Array.isArray(raw)) return [];
  return raw.filter((e): e is string => typeof e === "string" && e.trim().length > 0);
}

/** Scale a range about its center; zoom > 1 narrows the window (zooms in). */
function scaleRange([lo, hi]: Range, zoom: number): Range {
  const mid = (lo + hi) / 2;
  const half = (hi - lo) / 2 / zoom;
  return [mid - half, mid + half];
}

/**
 * All Exercise-Duplicator graphs render through Plotly — one clean, themed engine:
 * - `mafs_function`   — y = f(x); supports `pieces` (piecewise / system by cases)
 *                       and `expressions` (several curves plotted together).
 * - `mafs_parametric` — (x(t), y(t)) curve.
 * - `plotly_complex`  — f sampled over the reals, on the Argand plane.
 * - `plotly_3d`       — z = f(x, y) surface.
 *
 * 2D graphs auto-frame to the data and break the line at poles so asymptotes look
 * clean. 2D graphs also get in-box zoom controls. A bad expression throws and is
 * caught by the VizRouter error boundary.
 */
export function PlotlyRenderer({
  viz,
  height = 280,
}: {
  viz: VizBlock;
  height?: number;
}) {
  const [zoom, setZoom] = useState(1);
  // A fresh graph resets the zoom level.
  useEffect(() => setZoom(1), [viz]);

  const { data, layoutBase, ranges } = useMemo<{
    data: unknown[];
    layoutBase: Record<string, unknown>;
    ranges: { x: Range; y: Range } | null;
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
    const lineTrace = (
      x: Num[],
      y: Num[],
      color = ACCENT,
      name?: string,
    ) => ({
      type: "scatter",
      mode: "lines",
      x,
      y,
      line: { color, width: 2.5, shape: "spline" as const },
      connectgaps: false,
      ...(name ? { name } : {}),
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
        layoutBase: { ...base, scene: { aspectmode: "cube" } },
        ranges: null,
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
        layoutBase: { ...base, xaxis: { ...axis2d("Re"), range: xr }, yaxis: { ...axis2d("Im"), range: yr } },
        ranges: { x: xr, y: yr },
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
        layoutBase: { ...base, xaxis: { ...axis2d(), range: xr }, yaxis: { ...axis2d(), range: yr } },
        ranges: { x: xr, y: yr },
      };
    }

    // mafs_function — piecewise, system, or single curve.
    const pieces = readPieces(viz);
    const expressions = readExpressions(viz);
    const fullDomain: Range = viz.domain ?? [-6, 6];

    if (pieces.length > 0) {
      // One trace per branch over its own sub-domain → clean breaks between cases.
      const allY: number[] = [];
      const perPiece = pieces.map((p) => {
        const dom = p.domain ?? fullDomain;
        const f = compileFn(p.expression, "x");
        const n = Math.max(60, Math.round(LINE_N / pieces.length));
        const xs = linspace(dom[0], dom[1], n);
        const ys = xs.map(f);
        allY.push(...ys);
        return { xs, ys };
      });
      const xr: Range = viz.domain ?? [
        Math.min(...pieces.map((p) => (p.domain ?? fullDomain)[0])),
        Math.max(...pieces.map((p) => (p.domain ?? fullDomain)[1])),
      ];
      const yr = fitRange(allY, [-6, 6]);
      return {
        data: perPiece.map((t) => lineTrace(t.xs, t.ys.map((v) => clampNull(v, yr)))),
        layoutBase: { ...base, xaxis: { ...axis2d(), range: xr }, yaxis: { ...axis2d(), range: yr } },
        ranges: { x: xr, y: yr },
      };
    }

    const exprList =
      expressions.length > 0 ? expressions : [viz.expression ?? "x"];
    const xs = linspace(fullDomain[0], fullDomain[1], LINE_N);
    const allY: number[] = [];
    const series = exprList.map((expr) => {
      const ys = xs.map(compileFn(expr, "x"));
      allY.push(...ys);
      return { expr, ys };
    });
    const yr = fitRange(allY, [-6, 6]);
    const multi = series.length > 1;
    return {
      data: series.map((s, i) =>
        lineTrace(
          xs,
          s.ys.map((v) => clampNull(v, yr)),
          PALETTE[i % PALETTE.length],
          multi ? s.expr : undefined,
        ),
      ),
      layoutBase: {
        ...base,
        showlegend: multi,
        legend: multi
          ? { font: { color: themeColors().font, size: 11 }, orientation: "h", y: 1.08 }
          : undefined,
        xaxis: { ...axis2d(), range: fullDomain },
        yaxis: { ...axis2d(), range: yr },
      },
      ranges: { x: fullDomain, y: yr },
    };
  }, [viz, height]);

  // Apply the zoom level to 2D axis ranges (3D uses Plotly's own camera).
  const layout = useMemo(() => {
    if (!ranges) return layoutBase;
    return {
      ...layoutBase,
      xaxis: { ...(layoutBase.xaxis as object), range: scaleRange(ranges.x, zoom) },
      yaxis: { ...(layoutBase.yaxis as object), range: scaleRange(ranges.y, zoom) },
    };
  }, [layoutBase, ranges, zoom]);

  return (
    <div className="relative overflow-hidden rounded-lg border border-border bg-card">
      {ranges && (
        <div className="absolute right-2 top-2 z-10 flex flex-col overflow-hidden rounded-lg border border-border bg-background/80 shadow-sm backdrop-blur">
          <ZoomButton label="Zoom in" onClick={() => setZoom((z) => Math.min(z * 1.4, 25))}>
            <ZoomIn className="h-4 w-4" />
          </ZoomButton>
          <ZoomButton label="Zoom out" onClick={() => setZoom((z) => Math.max(z / 1.4, 0.05))}>
            <ZoomOut className="h-4 w-4" />
          </ZoomButton>
          <ZoomButton label="Reset zoom" onClick={() => setZoom(1)} disabled={zoom === 1}>
            <RotateCcw className="h-3.5 w-3.5" />
          </ZoomButton>
        </div>
      )}
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

function ZoomButton({
  label,
  onClick,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className="grid h-7 w-7 place-items-center border-b border-border/60 text-muted-foreground transition-colors last:border-b-0 hover:bg-accent hover:text-accent-foreground disabled:opacity-40 disabled:hover:bg-transparent"
    >
      {children}
    </button>
  );
}
