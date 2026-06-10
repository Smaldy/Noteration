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
  CalendarDays,
  GraduationCap,
  Heart,
  ListChecks,
  type LucideIcon,
  Settings,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useArcadeStore } from "@/stores/arcade";

import { ARCADE_PIXEL } from "./crtStyles";
import { render } from "./game/render";
import { ARENAS, type ArenaId, type FrameInput, type World } from "./game/types";
import { loadoutFrom } from "./game/types";
import { bulletsPerClick, createWorld, step, switchArena } from "./game/world";

// Same icons the real Library header uses for each section button.
const ARENA_ICON: Record<ArenaId, LucideIcon> = {
  exam: GraduationCap,
  bookmarks: Bookmark,
  calendar: CalendarDays,
  queue: ListChecks,
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
  const { t } = useTranslation();

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

  // End the run exactly once, banking the global wave + score the world reached.
  const finish = useCallback(
    (died: boolean) => {
      if (endedRef.current) return;
      endedRef.current = true;
      const w = worldRef.current;
      void endRun(w?.wave ?? run?.start_wave ?? 1, w?.score ?? 0, died);
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
          wave: world.wave,
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
    <div className="absolute inset-0 select-none">
      <canvas ref={canvasRef} className="block h-full w-full cursor-none" />

      {/* Sector nav — a replica of the real Library-header button row, in the
          same top-right space and using the same Button component / icons /
          labels, so it reads as the app's own nav. Switching drives the real
          router; a sector with a live bomb glows (go there and hold to defuse). */}
      <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-end px-6 py-6">
        <div className="pointer-events-auto flex items-center gap-2">
          {ARENAS.map((a, i) => {
            const Icon = ARENA_ICON[a.id];
            const active = a.id === hud.arena;
            const alert = !active && hud.bombArenas.includes(a.id);
            return (
              <Button
                key={a.id}
                variant="outline"
                size={a.iconOnly ? "icon" : "default"}
                onClick={() => go(a.id)}
                title={`${t(a.labelKey)} (${i + 1})`}
                className={`relative ${alert ? "arcade-bomb-alert" : ""}`}
                style={
                  active
                    ? { borderColor: a.color, color: a.color, boxShadow: `0 0 12px ${a.color}66` }
                    : undefined
                }
              >
                <Icon />
                {!a.iconOnly && t(a.labelKey)}
                {alert && (
                  <span className="absolute -right-1 -top-1 size-2.5 rounded-full bg-rose-500 shadow" />
                )}
              </Button>
            );
          })}
        </div>
      </div>

      {/* Player HUD + controls — bottom-left, clear of the header illusion. */}
      <div className={`pointer-events-none absolute bottom-0 left-0 flex flex-col gap-2 p-4 ${ARCADE_PIXEL}`}>
        <div className="flex items-center gap-1.5">
          {Array.from({ length: hud.maxHealth }, (_, i) => (
            <Heart
              key={i}
              className={`size-5 ${i < hud.health ? "fill-rose-500 text-rose-400" : "text-white/20"}`}
            />
          ))}
        </div>
        <p className="text-[10px]">
          <span className="arcade-neon-yellow text-base tabular-nums">{hud.score}</span>
          <span className="ml-3" style={{ color: activeDef?.color }}>
            {activeDef?.label} · W{hud.wave}
          </span>
        </p>
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
      </div>

      <button
        type="button"
        onClick={() => finish(false)}
        className={`pointer-events-auto absolute bottom-4 right-4 rounded border border-white/30 bg-black/40 px-3 py-1.5 text-[8px] arcade-dim backdrop-blur transition hover:scale-105 hover:text-white ${ARCADE_PIXEL}`}
      >
        BANK &amp; EXIT
      </button>
    </div>
  );
}
