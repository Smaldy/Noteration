/**
 * NOTINVASION — the live game. React owns only the canvas element, the rAF loop,
 * and input; all rules live in `game/world.ts` and drawing in `game/render.ts`.
 *
 * The player IS the cursor (a reticle). Click to zap (and, with the Sidearm, fire
 * a radiating bullet burst) the enemy under it; dodge the clocks' spikes. The
 * game plays over the live app across sectors — switching (nav bar / keys 1-5)
 * drives the real router, so the actual page changes behind the transparent game.
 * Bombs planted in other sectors glow their nav button; go there and *hold* on the
 * bomb to defuse it before the fuse blows. Owned upgrades shape the loadout (max
 * health, Sidearm, bullets-per-click, Overclock slow-mo dodge, score multiplier).
 * Death or BANK & EXIT ends the run through the store, which banks the score and
 * restores the page the player came from.
 */
import {
  Bookmark,
  Calendar,
  Heart,
  Library,
  ListChecks,
  type LucideIcon,
  Settings,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useArcadeStore } from "@/stores/arcade";

import { ARCADE_PIXEL } from "./crtStyles";
import { render } from "./game/render";
import { ARENAS, type ArenaId, type FrameInput, type World } from "./game/types";
import { loadoutFrom } from "./game/types";
import { bulletsPerClick, createWorld, step, switchArena } from "./game/world";

const ARENA_ICON: Record<ArenaId, LucideIcon> = {
  calendar: Calendar,
  queue: ListChecks,
  library: Library,
  bookmarks: Bookmark,
  settings: Settings,
};

/** Lightweight HUD mirror so React re-renders only when these change. */
interface Hud {
  health: number;
  maxHealth: number;
  score: number;
  wave: number;
  arena: ArenaId;
  bombArenas: ArenaId[]; // sectors with a live bomb (drive the nav flash)
  slowReady: boolean;
  hasSlow: boolean;
}

export function GameCanvas() {
  const state = useArcadeStore((s) => s.state);
  const run = useArcadeStore((s) => s.run);
  const endRun = useArcadeStore((s) => s.endRun);
  const navigate = useNavigate();
  const location = useLocation();

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const worldRef = useRef<World | null>(null);
  const inputRef = useRef<FrameInput>({
    pointer: { x: 0, y: 0 },
    clicked: false,
    held: false,
    dodge: false,
  });
  const endedRef = useRef(false);
  // The real route the player was on when the run began — restored on exit.
  const homeRef = useRef(location.pathname);

  const [hud, setHud] = useState<Hud>({
    health: 0,
    maxHealth: 0,
    score: run?.start_score ?? 0,
    wave: run?.start_wave ?? 1,
    arena: "calendar",
    bombArenas: [],
    slowReady: false,
    hasSlow: false,
  });

  // End the run exactly once, banking whatever the world reached. The "wave
  // reached" reported is the best sector progress, since each sector advances
  // independently.
  const finish = useCallback(
    (died: boolean) => {
      if (endedRef.current) return;
      endedRef.current = true;
      const w = worldRef.current;
      const wave = w
        ? Math.max(...ARENAS.map((a) => w.arenas[a.id].wave))
        : (run?.start_wave ?? 1);
      void endRun(wave, w?.score ?? 0, died);
    },
    [endRun, run],
  );

  // Switch sector AND drive the real router so the live page changes behind the
  // (transparent) game. Kept in a ref so the keydown handler can call the latest.
  const go = useCallback(
    (id: ArenaId) => {
      if (!worldRef.current) return;
      switchArena(worldRef.current, id);
      const def = ARENAS.find((a) => a.id === id);
      if (def) navigate(def.route);
    },
    [navigate],
  );
  const goRef = useRef(go);
  goRef.current = go;

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
      if (e.button === 0) {
        inputRef.current.clicked = true;
        inputRef.current.held = true; // held drives hold-to-defuse
      } else if (e.button === 2) {
        inputRef.current.dodge = true; // right-click dodges
      }
    };
    const onUp = (e: MouseEvent) => {
      if (e.button === 0) inputRef.current.held = false;
    };
    const releaseHold = () => {
      inputRef.current.held = false;
    };
    const onContext = (e: MouseEvent) => e.preventDefault();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === " ") {
        e.preventDefault();
        inputRef.current.dodge = true;
      } else if (e.key === "Escape") {
        finish(false);
      } else if (e.key >= "1" && e.key <= "5") {
        const def = ARENAS[Number(e.key) - 1];
        if (def) goRef.current(def.id);
      }
    };
    canvas.addEventListener("mousemove", onMove);
    canvas.addEventListener("mousedown", onDown);
    window.addEventListener("mouseup", onUp);
    canvas.addEventListener("mouseleave", releaseHold);
    window.addEventListener("blur", releaseHold);
    canvas.addEventListener("contextmenu", onContext);
    window.addEventListener("keydown", onKey);
    window.addEventListener("resize", resize);

    // Drive the real router to the starting sector so the live page matches.
    goRef.current(world.arena);

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
        const bombArenas = [...new Set(world.bombs.map((b) => b.arena))];
        setHud({
          health: world.player.health,
          maxHealth: world.player.maxHealth,
          score: world.score,
          wave: world.arenas[world.arena].wave,
          arena: world.arena,
          bombArenas,
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
      window.removeEventListener("mouseup", onUp);
      canvas.removeEventListener("mouseleave", releaseHold);
      window.removeEventListener("blur", releaseHold);
      canvas.removeEventListener("contextmenu", onContext);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", resize);
      navigate(homeRef.current); // put the app back where the player was
    };
    // Run once per mount: a run is a fresh world; loadout is fixed at start.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = loadoutFrom(state);
  const activeDef = ARENAS.find((a) => a.id === hud.arena);

  return (
    <div className="absolute inset-0 select-none bg-black/35">
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
          <p className="mt-1 text-[9px]" style={{ color: activeDef?.color }}>
            {activeDef?.label} · W{hud.wave}
          </p>
        </div>
      </div>

      {/* Sector nav — switching drives the real router (the live page changes
          behind the game). A button glows/shines when a bomb is live in that
          non-active sector; go there and hold to defuse it. */}
      <div className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2">
        <div className="pointer-events-auto flex gap-1.5 rounded-xl border border-white/10 bg-black/55 p-1.5 backdrop-blur">
          {ARENAS.map((a, i) => {
            const Icon = ARENA_ICON[a.id];
            const active = a.id === hud.arena;
            const alert = !active && hud.bombArenas.includes(a.id);
            return (
              <button
                key={a.id}
                type="button"
                onClick={() => go(a.id)}
                title={`${a.label} (${i + 1})`}
                className={`relative grid size-11 place-items-center rounded-lg border transition ${
                  alert ? "arcade-bomb-alert" : "border-white/10 hover:bg-white/10"
                }`}
                style={
                  active
                    ? {
                        color: a.color,
                        borderColor: a.color,
                        background: "rgba(255,255,255,0.08)",
                        boxShadow: `0 0 12px ${a.color}66`,
                      }
                    : alert
                      ? { color: "#ffd0e8" }
                      : { color: "rgba(255,255,255,0.5)" }
                }
              >
                <Icon className="size-5" />
                {alert && (
                  <span className="absolute -right-1 -top-1 size-2.5 rounded-full bg-rose-500 shadow" />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Controls hint + dodge state */}
      <div className={`pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between p-4 ${ARCADE_PIXEL}`}>
        <p className="arcade-dim text-[7px] leading-relaxed">
          {load.canShoot ? `CLICK — ZAP + ${bulletsPerClick(load)} SHOTS` : "CLICK TO ZAP"}
          <br />
          HOLD ON A BOMB TO DEFUSE
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
