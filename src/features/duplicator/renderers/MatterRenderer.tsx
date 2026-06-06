import Matter from "matter-js";
import { useEffect, useRef } from "react";

import type { VizBlock } from "@/types/duplicator";

const W = 460;
const H = 240;
const ACCENT = "#6366f1";

function num(params: Record<string, unknown>, key: string, fallback: number): number {
  const v = params[key];
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
}

/** Populate the world for a named scenario. */
function build(scenario: string, params: Record<string, unknown>, engine: Matter.Engine): void {
  const { Bodies, Composite, Constraint, Body } = Matter;
  const wall = (x: number, y: number, w: number, h: number) =>
    Bodies.rectangle(x, y, w, h, {
      isStatic: true,
      render: { fillStyle: "#94a3b8" },
    });
  const ball = (x: number, y: number, r: number) =>
    Bodies.circle(x, y, r, { restitution: 0.6, render: { fillStyle: ACCENT } });

  const ground = wall(W / 2, H - 10, W, 20);
  Composite.add(engine.world, ground);

  if (scenario === "pendulum") {
    const anchor = { x: W / 2, y: 30 };
    const bob = Matter.Bodies.circle(W / 2 + 90, 120, 18, {
      render: { fillStyle: ACCENT },
    });
    const arm = Constraint.create({
      pointA: anchor,
      bodyB: bob,
      stiffness: 1,
      render: { strokeStyle: "#94a3b8" },
    });
    Composite.add(engine.world, [bob, arm]);
    return;
  }

  if (scenario === "inclined_plane") {
    const ramp = Bodies.rectangle(W / 2, H - 60, 320, 16, {
      isStatic: true,
      angle: -Math.PI / 7,
      render: { fillStyle: "#94a3b8" },
    });
    const block = Bodies.rectangle(W / 2 - 110, H - 150, 28, 28, {
      friction: 0.02,
      render: { fillStyle: ACCENT },
    });
    Composite.add(engine.world, [ramp, block]);
    return;
  }

  if (scenario === "collision") {
    const a = ball(80, H - 40, 18);
    const b = ball(W - 80, H - 40, 18);
    Body.setVelocity(a, { x: 6, y: 0 });
    Body.setVelocity(b, { x: -6, y: 0 });
    Composite.add(engine.world, [a, b]);
    return;
  }

  // Default: projectile launched at angle/v0.
  const angle = (num(params, "angle", 55) * Math.PI) / 180;
  const v0 = num(params, "v0", 14);
  const proj = ball(40, H - 40, 14);
  Body.setVelocity(proj, { x: Math.cos(angle) * v0, y: -Math.sin(angle) * v0 });
  Composite.add(engine.world, [proj, wall(W - 5, H / 2, 10, H)]);
}

/**
 * Physics simulations via the raw Matter.js engine (no React wrapper) mounted on
 * a canvas ref. Scenario is `viz.params.scenario`: projectile · pendulum ·
 * inclined_plane · collision. Everything is torn down on unmount.
 */
export function MatterRenderer({ viz }: { viz: VizBlock }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const { Engine, Render, Runner, Composite } = Matter;

    const engine = Engine.create();
    const render = Render.create({
      canvas,
      engine,
      options: {
        width: W,
        height: H,
        wireframes: false,
        background: "transparent",
      },
    });

    const params = (viz.params ?? {}) as Record<string, unknown>;
    const scenario = typeof params.scenario === "string" ? params.scenario : "projectile";
    build(scenario, params, engine);

    const runner = Runner.create();
    Runner.run(runner, engine);
    Render.run(render);

    return () => {
      Render.stop(render);
      Runner.stop(runner);
      Composite.clear(engine.world, false);
      Engine.clear(engine);
      render.textures = {};
    };
  }, [viz]);

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <canvas ref={canvasRef} width={W} height={H} className="w-full" />
    </div>
  );
}
