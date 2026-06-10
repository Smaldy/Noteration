/**
 * NOTINVASION — the live game. React owns only the canvas element, the rAF loop,
 * and input; all rules live in `game/world.ts` and drawing in `game/render.ts`.
 *
 * The player IS the cursor (a reticle). Click to zap the enemy under it; dodge
 * the clocks' radiating spikes. Owned upgrades shape the loadout (max health,
 * Sidearm auto-fire, fire rate, Overclock slow-mo dodge, score multiplier).
 * Death or BANK & EXIT ends the run through the store, which banks the score.
 */
import { Heart, Zap } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { useArcadeStore } from "@/stores/arcade";

import { ARCADE_PIXEL } from "./crtStyles";
import { render } from "./game/render";
import type { FrameInput, World } from "./game/types";
import { loadoutFrom } from "./game/types";
import { createWorld, step } from "./game/world";

/** Lightweight HUD mirror so React re-renders only when these change. */
interface Hud {
  health: number;
  maxHealth: number;
  score: number;
  wave: number;
  slowReady: boolean;
  hasSlow: boolean;
}

export function GameCanvas() {
  const state = useArcadeStore((s) => s.state);
  const run = useArcadeStore((s) => s.run);
  const endRun = useArcadeStore((s) => s.endRun);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const worldRef = useRef<World | null>(null);
  const inputRef = useRef<FrameInput>({ pointer: { x: 0, y: 0 }, clicked: false, dodge: false });
  const endedRef = useRef(false);

  const [hud, setHud] = useState<Hud>({
    health: 0,
    maxHealth: 0,
    score: run?.start_score ?? 0,
    wave: run?.start_wave ?? 1,
    slowReady: false,
    hasSlow: false,
  });

  // End the run exactly once, banking whatever the world reached.
  const finish = useCallback(
    (died: boolean) => {
      if (endedRef.current) return;
      endedRef.current = true;
      const w = worldRef.current;
      void endRun(w?.wave ?? run?.start_wave ?? 1, w?.score ?? 0, died);
    },
    [endRun, run],
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = window.innerWidth;
      const h = window.innerHeight;
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      const world = worldRef.current;
      if (world) {
        world.w = w;
        world.h = h;
      }
    };
    resize();

    const load = loadoutFrom(state);
    const world = createWorld(
      window.innerWidth,
      window.innerHeight,
      load,
      run?.start_wave ?? 1,
      run?.start_score ?? 0,
    );
    world.player.pos = { x: world.w / 2, y: world.h / 2 };
    inputRef.current.pointer = { ...world.player.pos };
    worldRef.current = world;

    // ── Input ────────────────────────────────────────────────────────────────
    const rect = () => canvas.getBoundingClientRect();
    const onMove = (e: MouseEvent) => {
      const r = rect();
      inputRef.current.pointer = { x: e.clientX - r.left, y: e.clientY - r.top };
    };
    const onDown = (e: MouseEvent) => {
      if (e.button === 0) inputRef.current.clicked = true;
      else if (e.button === 2) inputRef.current.dodge = true; // right-click dodges
    };
    const onContext = (e: MouseEvent) => e.preventDefault();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === " ") {
        e.preventDefault();
        inputRef.current.dodge = true;
      } else if (e.key === "Escape") {
        finish(false);
      }
    };
    canvas.addEventListener("mousemove", onMove);
    canvas.addEventListener("mousedown", onDown);
    canvas.addEventListener("contextmenu", onContext);
    window.addEventListener("keydown", onKey);
    window.addEventListener("resize", resize);

    // ── Loop ─────────────────────────────────────────────────────────────────
    let raf = 0;
    let last = performance.now();
    let hudAccum = 0;
    const frame = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;

      step(world, dt, inputRef.current);
      // Consume one-shot inputs after the step reads them.
      inputRef.current.clicked = false;
      inputRef.current.dodge = false;

      ctx.save();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      render(ctx, world);
      ctx.restore();

      hudAccum += dt;
      if (hudAccum >= 0.1) {
        hudAccum = 0;
        setHud({
          health: world.player.health,
          maxHealth: world.player.maxHealth,
          score: world.score,
          wave: world.wave,
          slowReady: world.slowmo.cooldown <= 0,
          hasSlow: world.load.slowMoLevel > 0,
        });
      }

      if (world.status === "over") {
        finish(true);
        return; // stop the loop; the store flips to the GAME OVER screen
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      canvas.removeEventListener("mousemove", onMove);
      canvas.removeEventListener("mousedown", onDown);
      canvas.removeEventListener("contextmenu", onContext);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", resize);
    };
    // Run once per mount: a run is a fresh world; loadout is fixed at start.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="absolute inset-0 select-none bg-[#0a0617]">
      <canvas ref={canvasRef} className="block h-full w-full cursor-none" />

      {/* HUD */}
      <div className={`pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between p-4 ${ARCADE_PIXEL}`}>
        <div className="flex items-center gap-1.5">
          {Array.from({ length: hud.maxHealth }, (_, i) => (
            <Heart
              key={i}
              className={`size-5 ${i < hud.health ? "fill-rose-500 text-rose-400" : "text-white/20"}`}
            />
          ))}
        </div>
        <div className="text-right">
          <p className="arcade-neon-yellow text-base tabular-nums">{hud.score}</p>
          <p className="arcade-neon-cyan mt-1 text-[9px]">WAVE {hud.wave}</p>
        </div>
      </div>

      {/* Controls hint + dodge state */}
      <div className={`pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between p-4 ${ARCADE_PIXEL}`}>
        <p className="arcade-dim text-[7px] leading-relaxed">
          CLICK TO ZAP
          {hud.hasSlow && (
            <>
              <br />
              <span className={hud.slowReady ? "arcade-neon-green" : "arcade-dim"}>
                <Zap className="mb-0.5 inline size-2.5" /> SPACE / RMB — OVERCLOCK
                {hud.slowReady ? " READY" : " ..."}
              </span>
            </>
          )}
        </p>
        <button
          type="button"
          onClick={() => finish(false)}
          className="pointer-events-auto rounded border border-white/30 px-3 py-1.5 text-[8px] arcade-dim transition hover:scale-105 hover:text-white"
        >
          BANK &amp; EXIT
        </button>
      </div>
    </div>
  );
}
