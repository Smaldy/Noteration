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

const N = 36;

function linspace(a: number, b: number, n: number): number[] {
  if (n < 2) return [a];
  const step = (b - a) / (n - 1);
  return Array.from({ length: n }, (_, i) => a + i * step);
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

const BASE_LAYOUT = {
  autosize: true,
  height: 280,
  margin: { l: 30, r: 10, t: 10, b: 30 },
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
};
const CONFIG = { responsive: true, displayModeBar: false };

/**
 * 3D surfaces (`plotly_3d`: z = f(x, y)) and the complex plane (`plotly_complex`:
 * f sampled over the real domain, plotted Re vs Im on the Argand plane). A bad
 * expression throws and is caught by the VizRouter error boundary.
 */
export function PlotlyRenderer({ viz }: { viz: VizBlock }) {
  const data = useMemo<unknown[]>(() => {
    const [a, b] = viz.domain ?? [-5, 5];
    const node = compile(viz.expression ?? "x");

    if (viz.type === "plotly_complex") {
      const xs = linspace(a, b, N * 3);
      const re: number[] = [];
      const im: number[] = [];
      for (const x of xs) {
        const [r, i] = reim(node.evaluate({ x, z: x }));
        re.push(r);
        im.push(i);
      }
      return [
        {
          type: "scatter",
          mode: "lines+markers",
          x: re,
          y: im,
          marker: { size: 4 },
          line: { color: "#6366f1" },
        },
      ];
    }

    // plotly_3d surface: z = f(x, y) over the grid.
    const xs = linspace(a, b, N);
    const ys = linspace(a, b, N);
    const z = ys.map((y) =>
      xs.map((x) => {
        const out = node.evaluate({ x, y });
        return typeof out === "number" && Number.isFinite(out) ? out : 0;
      }),
    );
    return [{ type: "surface", x: xs, y: ys, z, colorscale: "Viridis" }];
  }, [viz]);

  const layout =
    viz.type === "plotly_3d"
      ? { ...BASE_LAYOUT, scene: { aspectmode: "cube" } }
      : { ...BASE_LAYOUT, xaxis: { title: "Re" }, yaxis: { title: "Im" } };

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <Suspense
        fallback={
          <div className="flex h-[280px] items-center justify-center text-sm text-muted-foreground">
            Loading plot…
          </div>
        }
      >
        <Plot
          data={data}
          layout={layout}
          config={CONFIG}
          useResizeHandler
          style={{ width: "100%", height: "280px" }}
        />
      </Suspense>
    </div>
  );
}
