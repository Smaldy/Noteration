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
import { Heart, Lock, Shield, Waves, Zap } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { useArcadeStore } from "@/stores/arcade";

import { ARCADE_PIXEL } from "./crtStyles";
import { render } from "./game/render";
import {
  ARENAS,
  type ArenaId,
  arenaForPath,
  type FrameInput,
  sectorUnlocked,
  unlockedSectorIds,
  type World,
} from "./game/types";
import { loadoutFrom } from "./game/types";
import { bossActive, bulletsPerClick, createWorld, step, switchArena } from "./game/world";

/** Lightweight HUD mirror so React re-renders only when these change. */
interface Hud {
  health: number;
  maxHealth: number;
  score: number;
  wave: number;
  arena: ArenaId;
  bombArenas: ArenaId[];
  bombFuse: number; // soonest fuse (s) among bombs in other sectors
  boss: boolean; // a boss just spawned → show the scare banner
  bossAlive: boolean; // a boss is alive → sector is locked until it dies
  hasSlow: boolean;
  slowReady: boolean;
  slowActive: boolean;
  slowFrac: number; // cooldown remaining, 0..1 (0 = charged)
  hasPhase: boolean; // Phase Cloak owned
  phaseActive: boolean; // Phase Cloak currently up (ignore-damage window)
  phaseFrac: number; // time-to-next-window remaining, 0..1
  pusherReady: boolean; // Defuser Pusher charged (next defuse releases a shockwave)
  pusherFrac: number; // recharge remaining, 0..1 (0 = charged)
  waveLeft: number; // enemies left to clear this sector's wave
  waveTotal: number; // enemies this wave (for the progress bar)
}

export function GameCanvas() {
  const state = useArcadeStore((s) => s.state);
  const run = useArcadeStore((s) => s.run);
  const endRun = useArcadeStore((s) => s.endRun);
  const setBombSectors = useArcadeStore((s) => s.setBombSectors);
  const setUnlockedSectors = useArcadeStore((s) => s.setUnlockedSectors);
  const location = useLocation();
  const navigate = useNavigate();

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
  const lockTimer = useRef<number>();
  // A padlock pops where a locked control was clicked.
  const [lockFx, setLockFx] = useState<{ x: number; y: number; key: number } | null>(null);
  // The bottom-left HUD panel sits where the reticle (the cursor) can go; fade it
  // out while the cursor — OR a live enemy — is over it so it never hides them.
  const hudRef = useRef<HTMLDivElement | null>(null);
  const hudDimRef = useRef(false);
  const [hudDim, setHudDim] = useState(false);
  const enemyDimRef = useRef(false);
  const [hudEnemyDim, setHudEnemyDim] = useState(false);
  // Right-click HOLD warps back to the Library (5s, down to 0.5s with Recall).
  const rightDownRef = useRef<number | null>(null);
  const recallProgRef = useRef(0);
  const [recallProg, setRecallProg] = useState(0);

  const [hud, setHud] = useState<Hud>({
    health: 0,
    maxHealth: 0,
    score: run?.start_score ?? 0,
    wave: run?.start_wave ?? 1,
    arena: arenaForPath(location.pathname),
    bombArenas: [],
    bombFuse: 0,
    boss: false,
    bossAlive: false,
    hasSlow: false,
    slowReady: false,
    slowActive: false,
    slowFrac: 0,
    hasPhase: false,
    phaseActive: false,
    phaseFrac: 0,
    pusherReady: true,
    pusherFrac: 0,
    waveLeft: 0,
    waveTotal: 0,
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
    navigate("/"); // every run starts in the always-unlocked Library hub
    world.player.pos = { x: world.w / 2, y: world.h / 2 };
    inputRef.current.pointer = { ...world.player.pos };
    worldRef.current = world;

    // ── Input ────────────────────────────────────────────────────────────────
    // The whole overlay is click-through (pointer-events:none); input is captured
    // on window in the CAPTURE phase so the frozen app never sees the press. Only
    // two things stay live to the DOM: our own UI ("ui" — the BANK button) and the
    // app's nav buttons ("nav" — Library section buttons + each page's return).
    // EVERYTHING else ("play") is inert to the app but drives the GAME, so you can
    // shoot/defuse on top of notes, calendar chips, slides, toggles, etc. A click
    // navigates only an UNLOCKED nav button; a locked one pops a padlock instead.
    const targetKind = (t: EventTarget | null): "ui" | "nav" | "play" => {
      const el = t instanceof Element ? t : null;
      if (el?.closest("[data-arcade-ui]")) return "ui";
      if (el?.closest("[data-arcade-sector]")) return "nav";
      return "play";
    };
    const showLock = (x: number, y: number) => {
      setLockFx({ x, y, key: performance.now() });
      window.clearTimeout(lockTimer.current);
      lockTimer.current = window.setTimeout(() => setLockFx(null), 650);
    };
    const onMove = (e: MouseEvent) => {
      inputRef.current.pointer = { x: e.clientX, y: e.clientY };
      // Fade the HUD panel when the cursor is over it (it'd hide the reticle).
      const r = hudRef.current?.getBoundingClientRect();
      const over =
        !!r && e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
      if (over !== hudDimRef.current) {
        hudDimRef.current = over;
        setHudDim(over);
      }
    };
    const onDown = (e: MouseEvent) => {
      if (targetKind(e.target) !== "play") return; // our UI / a nav button — let the DOM handle it
      e.preventDefault();
      e.stopPropagation(); // the frozen app never receives this press
      if (e.button === 0) {
        inputRef.current.clicked = true;
        inputRef.current.held = true;
      } else if (e.button === 2) {
        inputRef.current.dodge = true;
        rightDownRef.current = performance.now(); // start the hold-to-recall timer
      }
    };
    const onClickCapture = (e: MouseEvent) => {
      const kind = targetKind(e.target);
      if (kind === "ui") return; // our own UI (BANK) — allow
      if (kind === "nav") {
        const navEl = (e.target as Element).closest("[data-arcade-sector]")!;
        const w = worldRef.current;
        const target = navEl.getAttribute("data-arcade-sector") as ArenaId;
        if (w && bossActive(w) && target !== w.arena) {
          // Boss duel: you're locked into its sector until it's dead.
          e.preventDefault();
          e.stopPropagation();
          showLock(e.clientX, e.clientY);
          return;
        }
        if (w && sectorUnlocked(target, w.wave)) {
          return; // an UNLOCKED nav button — let it navigate the real app
        }
        e.preventDefault();
        e.stopPropagation();
        showLock(e.clientX, e.clientY); // a LOCKED section — padlock pop, no navigation
        return;
      }
      // "play": any other clickable in the frozen app — block it (the press already
      // drove the game). No padlock; this is the playfield.
      e.preventDefault();
      e.stopPropagation();
    };
    const onUp = (e?: Event) => {
      // blur (no button) cancels everything; mouseup clears only its own button.
      const btn = e instanceof MouseEvent ? e.button : undefined;
      if (btn === undefined || btn === 0) inputRef.current.held = false;
      if (btn === undefined || btn === 2) rightDownRef.current = null;
    };
    const onContext = (e: MouseEvent) => {
      if (targetKind(e.target) === "play") e.preventDefault(); // right-click in the play area = dodge
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
    window.addEventListener("mousedown", onDown, true); // capture: block the press before the app
    window.addEventListener("click", onClickCapture, true); // capture: block before React
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
    let lastUnlockWave = -1;
    const frame = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;

      step(world, dt, inputRef.current);
      inputRef.current.clicked = false; // one-shot inputs consumed after the step
      inputRef.current.dodge = false;

      // Right-click HOLD → warp to the Library. Threshold shrinks 5s→0.5s with
      // the Recall Beacon level. Blocked while a boss locks the sector.
      const holdT =
        rightDownRef.current != null ? (now - rightDownRef.current) / 1000 : 0;
      const recallThr = Math.max(0.5, 5 - 0.45 * world.load.recallLevel);
      const recallable = world.arena !== "library" && !bossActive(world);
      const prog = recallable && holdT > 0 ? Math.min(1, holdT / recallThr) : 0;
      if (Math.abs(prog - recallProgRef.current) > 0.03 || (prog === 0 && recallProgRef.current !== 0)) {
        recallProgRef.current = prog;
        setRecallProg(prog);
      }
      if (prog >= 1) {
        rightDownRef.current = null;
        recallProgRef.current = 0;
        setRecallProg(0);
        navigate("/"); // the route effect switches the sector to Library
      }

      ctx.save();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      render(ctx, world);
      ctx.restore();

      hudAccum += dt;
      if (hudAccum >= 0.1) {
        hudAccum = 0;
        const bombArenas = [...new Set(world.bombs.map((b) => b.arena))];
        const others = world.bombs.filter((b) => b.arena !== world.arena);
        const st = world.arenas[world.arena];
        const aliveHere = world.enemies.reduce((n, e) => (e.arena === world.arena ? n + 1 : n), 0);
        setHud({
          health: world.player.health,
          maxHealth: world.player.maxHealth,
          score: world.score,
          wave: world.wave,
          arena: world.arena,
          bombArenas,
          bombFuse: others.length ? Math.min(...others.map((b) => b.fuse)) : 0,
          boss: world.bossBanner > 0,
          bossAlive: bossActive(world),
          hasSlow: world.load.slowMoLevel > 0,
          slowReady: world.slowmo.cooldown <= 0,
          slowActive: world.slowmo.active > 0,
          slowFrac: world.slowmo.cooldownMax > 0 ? world.slowmo.cooldown / world.slowmo.cooldownMax : 0,
          hasPhase: world.load.phaseShieldLevel > 0,
          phaseActive: world.phase.active > 0,
          phaseFrac: world.phase.interval > 0 ? world.phase.cooldown / world.phase.interval : 0,
          pusherReady: world.pusher.cooldown <= 0,
          pusherFrac: world.pusher.interval > 0 ? world.pusher.cooldown / world.pusher.interval : 0,
          waveLeft: st.pending + aliveHere,
          waveTotal: st.total,
        });
        // Fade the HUD panel when a live enemy is overlapping it (they'd hide
        // behind the slab otherwise). Panel rect ≈ world coords (full-window canvas).
        const pr = hudRef.current?.getBoundingClientRect();
        let enemyOver = false;
        if (pr) {
          for (const e of world.enemies) {
            if (e.arena !== world.arena) continue;
            if (
              e.pos.x + e.radius >= pr.left &&
              e.pos.x - e.radius <= pr.right &&
              e.pos.y + e.radius >= pr.top &&
              e.pos.y - e.radius <= pr.bottom
            ) {
              enemyOver = true;
              break;
            }
          }
        }
        if (enemyOver !== enemyDimRef.current) {
          enemyDimRef.current = enemyOver;
          setHudEnemyDim(enemyOver);
        }
        // Publish bomb sectors to the store (for the real nav glow) when changed.
        const key = [...bombArenas].sort().join(",");
        if (key !== lastBombKey) {
          lastBombKey = key;
          setBombSectors(bombArenas);
        }
        // Publish unlocked sectors when the wave crosses an unlock threshold.
        if (world.wave !== lastUnlockWave) {
          lastUnlockWave = world.wave;
          setUnlockedSectors(unlockedSectorIds(world.wave));
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
      window.clearTimeout(lockTimer.current);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mousedown", onDown, true);
      window.removeEventListener("click", onClickCapture, true);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("blur", onUp);
      window.removeEventListener("contextmenu", onContext);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", resize);
      setBombSectors([]); // clear the nav glow when the run ends
      setUnlockedSectors([]);
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

      {/* Recall (right-click hold) progress — warping back to the Library. */}
      {recallProg > 0 && (
        <div className="pointer-events-none absolute left-1/2 top-20 flex -translate-x-1/2 flex-col items-center gap-1.5">
          <div
            className={`rounded-full border border-cyan-300/60 bg-black/55 px-4 py-1.5 text-[9px] tracking-[0.2em] text-cyan-100 backdrop-blur ${ARCADE_PIXEL}`}
          >
            RECALLING TO LIBRARY
          </div>
          <div className="h-1.5 w-40 overflow-hidden rounded-full bg-white/15">
            <div
              className="h-full rounded-full bg-cyan-300"
              style={{ width: `${Math.round(recallProg * 100)}%` }}
            />
          </div>
        </div>
      )}

      {/* Sector lock while a boss lives — you can't leave until it's dead. */}
      {hud.bossAlive && (
        <div className="pointer-events-none absolute left-1/2 top-4 -translate-x-1/2">
          <div
            className={`flex items-center gap-2 rounded-full border border-rose-400/60 bg-rose-600/25 px-4 py-1.5 text-[10px] tracking-[0.18em] text-rose-100 backdrop-blur ${ARCADE_PIXEL}`}
          >
            <Lock className="size-3" />
            SECTOR LOCKED · DEFEAT THE BOSS
          </div>
        </div>
      )}

      {/* Boss spawn scare. */}
      {hud.boss && (
        <div className="pointer-events-none absolute inset-x-0 top-[28%] flex flex-col items-center text-center">
          <p className={`arcade-boss-title text-3xl text-rose-500 sm:text-5xl ${ARCADE_PIXEL}`}>
            A NEW BOSS SPAWNED
          </p>
          <p className={`arcade-boss-sub mt-5 text-base text-rose-300 sm:text-2xl ${ARCADE_PIXEL}`}>
            ARE YOU READY TO DIE??
          </p>
        </div>
      )}

      {/* Padlock pop where a locked control was clicked. */}
      {lockFx && (
        <div
          key={lockFx.key}
          className="pointer-events-none absolute z-20 -translate-x-1/2 -translate-y-1/2"
          style={{ left: lockFx.x, top: lockFx.y }}
        >
          <Lock className="arcade-lock-pop size-7 text-rose-300 drop-shadow-[0_0_6px_rgba(255,90,120,0.9)]" />
        </div>
      )}

      {/* Player HUD + controls — bottom-left. A backing panel lifts it off the
          busy frozen app behind so the hearts/score/abilities stay legible. */}
      <div className={`pointer-events-none absolute bottom-0 left-0 p-3 ${ARCADE_PIXEL}`}>
       <div
         ref={hudRef}
         className="arcade-hud-panel flex flex-col gap-2.5 rounded-2xl p-3.5 transition-opacity duration-150"
         style={{ opacity: hudDim || hudEnemyDim ? 0.12 : 1 }}
       >
        <div className="flex items-center gap-1.5">
          {Array.from({ length: hud.maxHealth }, (_, i) => (
            <Heart
              key={i}
              className={`size-[22px] transition-all ${
                i < hud.health
                  ? "fill-rose-500 text-rose-300 drop-shadow-[0_0_5px_rgba(255,70,110,0.9)]"
                  : "fill-white/5 text-white/25"
              }`}
            />
          ))}
        </div>
        <p className="text-[10px]">
          <span className="arcade-neon-primary text-base tabular-nums">{hud.score}</span>
          <span className="ml-3" style={{ color: activeDef?.color }}>
            {activeDef?.label} · W{hud.wave}
          </span>
        </p>

        {/* Wave clear-counter: how many enemies are left to advance the wave. */}
        {hud.waveTotal > 0 && (
          <div className="flex items-center gap-2">
            <span className="arcade-dim text-[7px] tabular-nums">
              {hud.waveLeft > 0 ? (
                <>
                  <span style={{ color: activeDef?.color }}>{hud.waveLeft}</span> LEFT
                </>
              ) : (
                <span className="arcade-neon-green">CLEAR!</span>
              )}
            </span>
            <div className="h-1 w-24 overflow-hidden rounded-full bg-white/15">
              <div
                className="h-full rounded-full transition-[width] duration-200"
                style={{
                  width: `${Math.round(((hud.waveTotal - hud.waveLeft) / hud.waveTotal) * 100)}%`,
                  backgroundColor: activeDef?.color,
                }}
              />
            </div>
          </div>
        )}

        <p className="arcade-dim text-[7px] leading-relaxed">
          {load.canShoot ? `CLICK — ZAP + ${bulletsPerClick(load)} SHOTS` : "CLICK TO ZAP"}
          {load.autoFireLevel > 0 && " · AUTO-TURRET ON"}
          {load.special === "electric" && " · ⚡ ELECTRIC ROUNDS"}
          {load.special === "love" && " · ♥ LOVE ROUNDS"}
          <br />
          HOLD ON A BOMB TO DEFUSE (PUSHES ENEMIES BACK) · NAV WITH THE APP&apos;S BUTTONS
          <br />
          HOLD RIGHT-CLICK TO RECALL TO LIBRARY
        </p>

        {/* Special-ability dock — each shows a charge ring + ready/active glow.
            Defuser Pusher is built-in (always shown); the rest are owned skills. */}
        <div className="flex items-center gap-2.5">
          <AbilityPip
            Icon={Waves}
            label="PUSHER"
            color="#ff7bd5"
            frac={hud.pusherFrac}
            ready={hud.pusherReady}
            active={false}
          />
          {hud.hasSlow && (
            <AbilityPip
              Icon={Zap}
              label="OVERCLOCK"
              hint="SPC"
              color="#6ffbff"
              frac={hud.slowFrac}
              ready={hud.slowReady}
              active={hud.slowActive}
            />
          )}
          {hud.hasPhase && (
            <AbilityPip
              Icon={Shield}
              label="PHASE"
              color="#74ff9c"
              frac={hud.phaseFrac}
              ready={hud.phaseActive}
              active={hud.phaseActive}
            />
          )}
        </div>
       </div>
      </div>

      <button
        type="button"
        data-arcade-ui
        onClick={() => finishRef.current(false)}
        className={`pointer-events-auto absolute bottom-4 right-4 rounded border border-white/30 bg-black/40 px-3 py-1.5 text-[8px] arcade-dim backdrop-blur transition hover:scale-105 hover:text-white ${ARCADE_PIXEL}`}
      >
        BANK &amp; EXIT
      </button>
    </div>
  );
}

/**
 * A special-ability gauge: an SVG charge ring that fills as the cooldown
 * recharges, with a ready pulse and an active glow. `frac` is the cooldown
 * *remaining* (1 = just used, 0 = charged).
 */
function AbilityPip({
  Icon,
  label,
  hint,
  color,
  frac,
  ready,
  active,
}: {
  Icon: typeof Zap;
  label: string;
  hint?: string;
  color: string;
  frac: number;
  ready: boolean;
  active: boolean;
}) {
  const R = 17;
  const CIRC = 2 * Math.PI * R;
  const charged = 1 - Math.max(0, Math.min(1, frac)); // 0..1 portion ready
  const lit = ready || active;
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative grid size-11 place-items-center">
        <svg className="absolute inset-0 size-full -rotate-90" viewBox="0 0 40 40">
          <circle cx="20" cy="20" r={R} fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="2.5" />
          <circle
            cx="20"
            cy="20"
            r={R}
            fill="none"
            stroke={color}
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeDasharray={CIRC}
            strokeDashoffset={CIRC * (1 - charged)}
            style={{ filter: lit ? `drop-shadow(0 0 5px ${color})` : "none" }}
          />
        </svg>
        <div
          className={`grid size-7 place-items-center rounded-lg transition-colors ${
            active ? "arcade-pip-active" : ""
          }`}
          style={{
            color: lit ? color : "rgba(255,255,255,0.4)",
            backgroundColor: lit ? `${color}1f` : "rgba(0,0,0,0.4)",
            boxShadow: lit ? `0 0 10px -2px ${color}` : "none",
          }}
        >
          <Icon className="size-4" />
        </div>
        {hint && (
          <span className="absolute -bottom-0.5 -right-0.5 rounded bg-black/70 px-0.5 text-[6px] leading-tight text-white/60">
            {hint}
          </span>
        )}
      </div>
      <span
        className="text-[6px] tracking-wider"
        style={{ color: lit ? color : "rgba(255,255,255,0.35)" }}
      >
        {active ? "ON" : ready ? "READY" : label}
      </span>
    </div>
  );
}
