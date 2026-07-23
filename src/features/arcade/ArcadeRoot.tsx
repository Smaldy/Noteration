import { useEffect } from "react";

import { onStudyEvent } from "@/lib/arcadeEvents";
import { useArcadeStore } from "@/stores/arcade";

import { ArcadeOverlay } from "./ArcadeOverlay";
import { GameLayer } from "./GameLayer";

/**
 * Single mount point for the additive arcade feature. Mounted once at the app
 * shell level alongside the other always-on overlays. It owns nothing in the
 * real app — it only listens for study actions (to award coins) and renders the
 * arcade-cabinet hub and the game layer.
 */
export function ArcadeRoot() {
  const fetchState = useArcadeStore((s) => s.fetchState);
  const earn = useArcadeStore((s) => s.earn);

  useEffect(() => {
    void fetchState();
  }, [fetchState]);

  // Study → coins. The only coupling to the real app: a fire-and-forget event.
  useEffect(() => onStudyEvent((kind) => void earn(kind)), [earn]);

  return (
    <>
      {/* The joystick entry point lives in the sidebar footer (AppSidebar), so
          it no longer collides with the Settings button in the same corner. */}
      <ArcadeOverlay />
      <GameLayer />
    </>
  );
}
