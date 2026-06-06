import { Component, type ReactNode } from "react";

import type { VizBlock } from "@/types/duplicator";

import { ForceDiagramRenderer } from "./ForceDiagramRenderer";
import { MafsRenderer } from "./MafsRenderer";
import { MatterRenderer } from "./MatterRenderer";
import { PlotlyRenderer } from "./PlotlyRenderer";

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

function renderViz(viz: VizBlock): ReactNode {
  switch (viz.type) {
    case "mafs_function":
    case "mafs_parametric":
      return <MafsRenderer viz={viz} />;
    case "plotly_3d":
    case "plotly_complex":
      return <PlotlyRenderer viz={viz} />;
    case "matter_simulation":
      return <MatterRenderer viz={viz} />;
    case "force_diagram":
      return <ForceDiagramRenderer viz={viz} />;
    default:
      return null;
  }
}

/** Reads `viz?.type` and renders the matching renderer (or nothing). */
export function VizRouter({ viz }: { viz: VizBlock | null | undefined }) {
  if (!viz || !viz.type) return null;
  const content = renderViz(viz);
  if (content === null) return null;
  return (
    <div className="mt-3">
      <VizErrorBoundary>{content}</VizErrorBoundary>
    </div>
  );
}
