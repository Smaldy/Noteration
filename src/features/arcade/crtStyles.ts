/**
 * Styling for the arcade overlay. Injected as one <style> tag inside the overlay
 * (mirrors CreditsOverlay) so none of it leaks to the app's global CSS. All class
 * names are arcade-/cab-/prim- prefixed.
 *
 * The cabinet is NOT built from CSS 3D anymore. It is a flat blockout: parts are
 * absolutely-positioned primitives on a scaled design stage (see cabinetLayout.ts
 * + primitives.tsx). This file styles the primitives, the blockout overlay, the
 * live slot elements (CRT / buttons / lever / coin slot), and the shared neon FX.
 */

export const ARCADE_PIXEL = "arcade-pixel";

export const arcadeStyles = `
  .${ARCADE_PIXEL} {
    font-family: "Press Start 2P", ui-monospace, monospace;
    letter-spacing: 0.02em;
    line-height: 1.55;
  }

  /* Dark arcade hall behind the cabinet. */
  .arcade-room {
    background:
      radial-gradient(120% 80% at 50% -10%, rgba(80,30,120,0.5), transparent 55%),
      radial-gradient(80% 60% at 50% 120%, rgba(20,60,90,0.35), transparent 60%),
      rgba(3, 2, 8, 0.92);
    backdrop-filter: blur(3px);
  }

  /* ---- Stage (fixed design space, scaled to fit) -------------------------- */
  .cab-scaler { position: relative; }
  .cab-stage {
    position: absolute; top: 0; left: 0;
    transform-origin: top left;
  }
  .prim-skin { pointer-events: none; }
  .crt-screen .arcade-screen-inner, .cab-btn, .cab-lever, .coin-slot { pointer-events: auto; }

  /* ---- Blockout (press B) ------------------------------------------------- */
  .prim-block {
    outline: 1px dashed rgba(255,255,255,0.25);
  }
  .prim-block-fill {
    position: absolute; inset: 0;
    background: rgba(229,30,42,0.55);
    outline: 1px solid #ff5a5a;
  }
  .prim-label {
    position: absolute; top: 2px; left: 4px;
    font: 700 9px/1.1 ui-monospace, monospace;
    color: #fff; text-shadow: 0 1px 2px #000;
    pointer-events: none; white-space: nowrap;
  }
  .prim-dim {
    position: absolute; bottom: 12px; left: 4px;
    font: 600 8px/1.1 ui-monospace, monospace;
    color: #ffd34d; text-shadow: 0 1px 2px #000;
    pointer-events: none; white-space: nowrap;
  }
  .prim-center {
    position: absolute; bottom: 2px; left: 4px;
    font: 600 8px/1.1 ui-monospace, monospace;
    color: #6ffbff; text-shadow: 0 1px 2px #000;
    pointer-events: none; white-space: nowrap;
  }
  .prim-center .ok { color: #74ff9c; }
  .prim-center .no { color: transparent; }

  /* Center guide lines (blockout only). */
  .cab-guide-v {
    position: absolute; top: 0; bottom: 0; width: 0;
    border-left: 1px dashed rgba(110,251,255,0.7);
    transform: translateX(-0.5px); z-index: 999; pointer-events: none;
  }
  .cab-guide-h {
    position: absolute; left: 0; right: 0; height: 0;
    border-top: 1px dashed rgba(110,251,255,0.45);
    transform: translateY(-0.5px); z-index: 999; pointer-events: none;
  }
  .cab-guide-tag {
    position: absolute; top: 2px;
    transform: translateX(4px);
    font: 700 9px/1 ui-monospace, monospace;
    color: #6ffbff; text-shadow: 0 1px 2px #000;
    z-index: 999; pointer-events: none;
  }

  /* ---- Marquee title ------------------------------------------------------ */
  .marquee-text {
    background: linear-gradient(180deg, #fff 0%, #ffe3ff 42%, #ff8ee0 100%);
    -webkit-background-clip: text; background-clip: text; color: transparent;
    filter: drop-shadow(0 0 14px rgba(255,120,220,0.85)) drop-shadow(0 3px 0 rgba(50,10,60,0.8));
    font-size: 24px; letter-spacing: 0.14em;
  }

  /* ---- CRT screen --------------------------------------------------------- */
  .crt-screen {
    border-radius: 10px;
    background:
      radial-gradient(120% 110% at 50% 32%, rgba(22,78,102,0.45), rgba(1,5,10,0.99) 75%),
      #020407;
    box-shadow:
      inset 0 0 80px rgba(0,0,0,0.97),
      inset 0 0 26px rgba(70,210,255,0.13),
      0 0 0 6px #070412,
      0 0 0 9px rgba(140,90,220,0.25);
    overflow: hidden;
  }
  .crt-screen::before {  /* scanlines */
    content: ""; position: absolute; inset: 0; pointer-events: none; z-index: 5;
    background: repeating-linear-gradient(
      to bottom, rgba(255,255,255,0.045) 0, rgba(255,255,255,0.045) 1px, transparent 1px, transparent 3px);
  }
  .crt-screen::after {  /* vignette + flicker */
    content: ""; position: absolute; inset: 0; pointer-events: none; z-index: 6;
    background: radial-gradient(115% 115% at 50% 50%, transparent 54%, rgba(0,0,0,0.62) 100%);
    animation: arcade-flicker 5.5s infinite steps(55);
  }
  @keyframes arcade-flicker { 0%,95%,100%{opacity:1} 96%{opacity:0.87} 97%{opacity:0.98} 98%{opacity:0.92} }
  .arcade-screen-inner { position: absolute; inset: 0; z-index: 4; padding: 16px 18px; }

  /* ---- Deck buttons (single-colour glossy plastic) ------------------------ */
  .cab-btn {
    display: grid; place-items: center;
    border-radius: 50%;
    color: rgba(255,255,255,0.95); border: 2px solid rgba(255,255,255,0.22);
    background: radial-gradient(circle at 32% 26%, #ffb0b0 0%, #ff4d4d 34%, #d41c1c 70%, #a31414 100%);
    box-shadow: -2px 6px 0 #7a0c0c, -4px 11px 11px rgba(0,0,0,0.6);
    font-size: 18px; line-height: 1;
    cursor: pointer;
    transition: transform 0.1s ease, box-shadow 0.1s ease, filter 0.1s ease;
  }
  .cab-btn:hover:not(:disabled) { filter: brightness(1.08); }
  .cab-btn:active:not(:disabled) {
    transform: translateY(4px);
    box-shadow: -1px 1px 0 #7a0c0c, -1px 3px 6px rgba(0,0,0,0.45);
  }
  .cab-btn:disabled { opacity: 0.35; cursor: not-allowed; }

  /* ---- Slot-machine pull lever (profile) ---------------------------------- */
  .cab-lever { background: none; border: none; padding: 0; cursor: pointer; }
  .cab-lever.is-disabled { opacity: 0.5; cursor: not-allowed; }
  .cab-lever-base {
    position: absolute; left: 0; top: 40px;
    width: 24px; height: 90px; border-radius: 7px;
    background: linear-gradient(90deg, #2a2b34, #6a6c78 50%, #2a2b34);
    box-shadow: inset -2px 0 6px rgba(0,0,0,0.8), 0 8px 14px rgba(0,0,0,0.55);
  }
  .cab-lever-arm {
    position: absolute; left: 16px; top: 56px;
    transform-origin: left center;
  }
  .cab-lever-stick {
    display: block;
    width: 70px; height: 13px; border-radius: 8px;
    background: linear-gradient(180deg, #6a6c78 0%, #f2f3f8 46%, #6a6c78 100%);
    box-shadow: 0 3px 6px rgba(0,0,0,0.5);
  }
  .cab-lever-ball {
    position: absolute; right: -30px; top: 50%; transform: translateY(-50%);
    width: 46px; height: 46px; border-radius: 999px;
    background: radial-gradient(circle at 32% 26%, #ffc2c6 0%, #ff4d60 34%, #cc142c 64%, #8c0a1c 100%);
    box-shadow: 0 8px 16px rgba(0,0,0,0.55), inset 0 6px 9px rgba(255,255,255,0.7), inset 0 -8px 12px rgba(110,0,18,0.5);
    border: 2px solid rgba(255,255,255,0.16);
  }

  /* ---- Coin slot ---------------------------------------------------------- */
  .coin-slot {
    display: flex; align-items: center; justify-content: space-between; gap: 14px;
    padding: 12px 18px;
    background: linear-gradient(180deg, #160a30, #0a0418);
    border: 2px solid rgba(160,110,240,0.3);
    border-radius: 12px;
    box-shadow: inset 0 6px 12px rgba(0,0,0,0.85);
  }
  .arcade-slot-mouth {
    width: 46px; height: 10px; border-radius: 4px;
    background: #030207;
    box-shadow: inset 0 4px 6px rgba(0,0,0,0.95), 0 1px 0 rgba(255,255,255,0.08);
  }
  .arcade-coin {
    width: 24px; height: 24px; border-radius: 999px;
    background: radial-gradient(circle at 36% 30%, #fff4be, #ffcf3a 45%, #c2820c 100%);
    box-shadow: 0 4px 8px rgba(0,0,0,0.4), inset 0 1px 2px rgba(255,255,255,0.8);
    display: grid; place-items: center; color: #734a00; font-weight: 900; font-size: 12px;
  }

  /* ---- Neon text + effects (shared with the on-screen panels) ------------- */
  .arcade-neon-cyan { color:#6ffbff; text-shadow:0 0 8px rgba(80,230,255,0.8),0 0 2px rgba(80,230,255,0.9); }
  .arcade-neon-pink { color:#ff7bd5; text-shadow:0 0 8px rgba(255,100,210,0.8),0 0 2px rgba(255,100,210,0.9); }
  .arcade-neon-yellow { color:#ffe14d; text-shadow:0 0 8px rgba(255,220,70,0.8),0 0 2px rgba(255,220,70,0.9); }
  .arcade-neon-green { color:#74ff9c; text-shadow:0 0 8px rgba(90,255,150,0.7),0 0 2px rgba(90,255,150,0.9); }
  .arcade-dim { color:#6274a0; }

  .arcade-blink { animation: arcade-blink 1.1s steps(2,start) infinite; }
  @keyframes arcade-blink { 0%,50%{opacity:1} 50.01%,100%{opacity:0} }

  .arcade-slam { animation: arcade-slam 0.6s cubic-bezier(0.2,1.6,0.36,1) both; }
  @keyframes arcade-slam {
    0% { transform: scale(6); opacity: 0; filter: blur(8px); }
    60% { opacity: 1; } 70% { transform: scale(0.92); }
    100% { transform: scale(1); opacity: 1; filter: blur(0); }
  }

  @media (prefers-reduced-motion: reduce) {
    .crt-screen::after, .arcade-blink, .arcade-slam { animation: none; }
  }
`;
