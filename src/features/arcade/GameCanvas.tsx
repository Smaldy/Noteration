/**
 * NOTINVASION — the live game. React owns only the canvas, the rAF loop, and
 * input; all rules live in `game/world.ts` and drawing in `game/render.ts`.
 *
 * The player IS the cursor (a reticle). Click to zap (and, with the Sidearm, fire
 * a radiating bullet burst) the enemy under it; dodge the clocks' spikes. The game
 * plays over the *live* app: the active sector follows the real route, and you
 * navigate with the app's OWN buttons — the Library header buttons and each page's
 * "← Library" return button — which the game leaves clickable through a pass-
 * through strip at the top of the screen. Bombs in other sectors make the real
 * Library button glow (and an on-screen alert names them); go there and *hold* on
 * the bomb to defuse it before the fuse blows. Death or BANK & EXIT ends the run.
 */
import { Heart, Zap } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import { useArcadeStore } from "@/stores/arcade";

import { ARCADE_PIXEL } from "./crtStyles";
import { render } from "./game/render";
import { ARENAS, type ArenaId, arenaForPath, type FrameInput, type World } from "./game/types";
import { loadoutFrom } from "./game/types";
import { bulletsPerClick, createWorld, step, switchArena } from "./game/world";

/** Lightweight HUD mirror so React re-renders only when these change. */
interface Hud {
  health: number;
  maxHealth: number;
  score: number;
  wave: number;
  arena: ArenaId;
  bombArenas: ArenaId[];
  bombFuse: number; // soonest fuse (s) among bombs in other sectors
  slowReady: boolean;
  hasSlow: boolean;
}

export function GameCanvas() {
  const state = useArcadeStore((s) => s.state);
  const run = useArcadeStore((s) => s.run);
  const endRun = useArcadeStore((s) => s.endRun);
  const setBombSectors = useArcadeStore((s) => s.setBombSectors);
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
  const finishRef = useRef<(died: boolean) => void>(() => {});

  const [hud, setHud] = useState<Hud>({
    health: 0,
    maxHealth: 0,
    score: run?.start_score ?? 0,
    wave: run?.start_wave ?? 1,
    arena: arenaForPath(location.pathname),
    bombArenas: [],
    bombFuse: 0,
    slowReady: false,
    hasSlow: false,
  });

  // End the run exactly once, banking the global wave + score the world reached.
  finishRef.current = (died: boolean) => {
    if (endedRef.current) return;
    endedRef.current = true;
    const w = worldRef.current;
    void endRun(w?.wave ?? run?.start_wave ?? 1, w?.score ?? 0, died);
  };

  // Follow the real route: navigating with the app's own buttons switches sector.
  useEffect(() => {
    if (worldRef.current) switchArena(worldRef.current, arenaForPath(location.pathname));
  }, [location.pathname]);

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
    switchArena(world, arenaForPath(window.location.pathname)); // match the page we open on
    world.player.pos = { x: world.w / 2, y: world.h / 2 };
    inputRef.current.pointer = { ...world.player.pos };
    worldRef.current = world;

    // ── Input ────────────────────────────────────────────────────────────────
    // The whole overlay is click-through (pointer-events:none); input is captured
    // on window. A click only zaps when it ISN'T on a real control — clicking the
    // app's own nav/return buttons (or BANK) navigates them, untouched.
    const isControl = (t: EventTarget | null) =>
      t instanceof Element &&
      !!t.closest('a, button, [role="button"], input, select, textarea, label');
    const onMove = (e: MouseEvent) => {
      inputRef.current.pointer = { x: e.clientX, y: e.clientY };
    };
    const onDown = (e: MouseEvent) => {
      if (isControl(e.target)) return; // let the real button do its thing
      if (e.button === 0) {
        inputRef.current.clicked = true;
        inputRef.current.held = true;
      } else if (e.button === 2) {
        inputRef.current.dodge = true;
      }
    };
    const onUp = () => {
      inputRef.current.held = false;
    };
    const onContext = (e: MouseEvent) => {
      if (!isControl(e.target)) e.preventDefault(); // right-click in the play area = dodge
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === " ") {
        e.preventDefault();
        inputRef.current.dodge = true;
      } else if (e.key === "Escape") {
        finishRef.current(false);
      }
    };
    document.body.style.cursor = "none"; // the drawn reticle replaces the OS cursor
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mousedown", onDown);
    window.addEventListener("mouseup", onUp);
    window.addEventListener("blur", onUp);
    window.addEventListener("contextmenu", onContext);
    window.addEventListener("keydown", onKey);
    window.addEventListener("resize", resize);

    // ── Loop ─────────────────────────────────────────────────────────────────
    let raf = 0;
    let last = performance.now();
    let hudAccum = 0;
    let lastBombKey = "";
    const frame = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;

      step(world, dt, inputRef.current);
      inputRef.current.clicked = false; // one-shot inputs consumed after the step
      inputRef.current.dodge = false;

      ctx.save();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      render(ctx, world);
      ctx.restore();

      hudAccum += dt;
      if (hudAccum >= 0.1) {
        hudAccum = 0;
        const bombArenas = [...new Set(world.bombs.map((b) => b.arena))];
        const others = world.bombs.filter((b) => b.arena !== world.arena);
        setHud({
          health: world.player.health,
          maxHealth: world.player.maxHealth,
          score: world.score,
          wave: world.wave,
          arena: world.arena,
          bombArenas,
          bombFuse: others.length ? Math.min(...others.map((b) => b.fuse)) : 0,
          slowReady: world.slowmo.cooldown <= 0,
          hasSlow: world.load.slowMoLevel > 0,
        });
        // Publish bomb sectors to the store (for the real nav glow) when changed.
        const key = [...bombArenas].sort().join(",");
        if (key !== lastBombKey) {
          lastBombKey = key;
          setBombSectors(bombArenas);
        }
      }

      if (world.status === "over") {
        finishRef.current(true);
        return; // stop the loop; the store flips to the GAME OVER screen
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);

    return () => {
      cancelAnimationFrame(raf);
      document.body.style.cursor = "";
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("blur", onUp);
      window.removeEventListener("contextmenu", onContext);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", resize);
      setBombSectors([]); // clear the nav glow when the run ends
    };
    // Run once per mount: a run is a fresh world; loadout is fixed at start.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = loadoutFrom(state);
  const activeDef = ARENAS.find((a) => a.id === hud.arena);
  const otherBombs = hud.bombArenas.filter((a) => a !== hud.arena);

  return (
    // pointer-events-none so the real app behind stays interactive (input is
    // captured on window); only the BANK button opts back in.
    <div className="pointer-events-none absolute inset-0 select-none">
      <canvas ref={canvasRef} className="block h-full w-full" />

      {/* Bomb alert — names the sectors to navigate to (the real Library button
          also glows). A shining gradient pill with a ticking fuse countdown. */}
      {otherBombs.length > 0 && (
        <div className="pointer-events-none absolute left-1/2 top-4 -translate-x-1/2">
          <div className={`arcade-bomb-banner flex items-center gap-2.5 rounded-full px-4 py-1.5 text-[10px] tracking-[0.18em] text-white ${ARCADE_PIXEL}`}>
            <span className="text-sm leading-none">⚠</span>
            <span>{otherBombs.map((id) => ARENAS.find((a) => a.id === id)?.label).join(" · ")}</span>
            <span className="tabular-nums text-amber-200">{Math.max(0, Math.ceil(hud.bombFuse))}s</span>
          </div>
        </div>
      )}

      {/* Player HUD + controls — bottom-left. */}
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
          HOLD ON A BOMB TO DEFUSE · NAV WITH THE APP&apos;S BUTTONS
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
        onClick={() => finishRef.current(false)}
        className={`pointer-events-auto absolute bottom-4 right-4 rounded border border-white/30 bg-black/40 px-3 py-1.5 text-[8px] arcade-dim backdrop-blur transition hover:scale-105 hover:text-white ${ARCADE_PIXEL}`}
      >
        BANK &amp; EXIT
      </button>
    </div>
  );
}
