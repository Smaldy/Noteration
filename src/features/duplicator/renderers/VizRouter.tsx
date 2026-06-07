import { Component, type ReactNode, Suspense, lazy } from "react";

import type { VizBlock } from "@/types/duplicator";

// Each renderer is lazy so its heavy library only downloads for the viz type that
// actually appears: Plotly (every graph — 2D curves, the complex plane, and 3D
// surfaces) and matter-js (MatterRenderer) load on demand instead of all-at-once
// when the page first paints.
const ForceDiagramRenderer = lazy(() =>
  import("./ForceDiagramRenderer").then((m) => ({ default: m.ForceDiagramRenderer })),
);
const MatterRenderer = lazy(() =>
  import("./MatterRenderer").then((m) => ({ default: m.MatterRenderer })),
);
const PlotlyRenderer = lazy(() =>
  import("./PlotlyRenderer").then((m) => ({ default: m.PlotlyRenderer })),
);

/** Catches a renderer that throws (e.g. a malformed expression) → fallback. */
class VizErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="rounded-lg border border-dashed border-border px-3 py-2 text-xs text-muted-foreground">
          Visualization unavailable for this problem.
        </div>
      );
    }
    return this.props.children;
  }
}

function renderViz(viz: VizBlock, height?: number): ReactNode {
  switch (viz.type) {
    case "mafs_function":
    case "mafs_parametric":
    case "plotly_3d":
    case "plotly_complex":
      return <PlotlyRenderer viz={viz} height={height} />;
    case "matter_simulation":
      return <MatterRenderer viz={viz} />;
    case "force_diagram":
      return <ForceDiagramRenderer viz={viz} />;
    default:
      return null;
  }
}

/**
 * Reads `viz?.type` and renders the matching renderer (or nothing). `height` lets
 * the focus view request a taller graph than the compact grid card.
 */
export function VizRouter({
  viz,
  height,
}: {
  viz: VizBlock | null | undefined;
  height?: number;
}) {
  if (!viz || !viz.type) return null;
  const content = renderViz(viz, height);
  if (content === null) return null;
  return (
    <div className="mt-3">
      <VizErrorBoundary>
        <Suspense
          fallback={
            <div className="rounded-lg border border-dashed border-border px-3 py-2 text-xs text-muted-foreground">
              Loading visualization…
            </div>
          }
        >
          {content}
        </Suspense>
      </VizErrorBoundary>
    </div>
  );
}
