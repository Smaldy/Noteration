/**
 * Minimal ambient declarations for the Plotly packages, which ship without
 * (compatible) TypeScript types. We only use `plotly.js-dist-min` through
 * `react-plotly.js/factory`, so a permissive surface keeps `tsc` clean without
 * pulling in the heavy `@types/plotly.js`.
 */

declare module "plotly.js-dist-min" {
  const Plotly: unknown;
  export default Plotly;
}

declare module "react-plotly.js/factory" {
  import type { ComponentType } from "react";

  interface PlotParams {
    data: unknown[];
    layout?: Record<string, unknown>;
    config?: Record<string, unknown>;
    style?: Record<string, unknown>;
    useResizeHandler?: boolean;
    className?: string;
  }
  export default function createPlotlyComponent(
    plotly: unknown,
  ): ComponentType<PlotParams>;
}
