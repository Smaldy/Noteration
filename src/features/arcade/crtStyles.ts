/**
 * True-3D CRT-arcade cabinet styling for the minigame overlay. Injected as one
 * <style> tag inside the overlay (mirrors CreditsOverlay) so none of it leaks to
 * the app's global CSS. All class names are arcade-/box-/lever-/deck- prefixed.
 *
 * The chassis is built from real geometric planes (perspective + preserve-3d +
 * rotateX/translateZ): a marquee that juts forward, a recessed screen housing,
 * a slanted control deck, and a flat coin base — assembled into a solid box.
 * Utility classes (neon text, pixel font, scanlines, coin) are shared with the
 * on-screen panels and the game layer.
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

  /* ---- 3D scene (the camera) ---------------------------------------------- */
  .arcade-scene {
    perspective: 1300px;
    perspective-origin: 50% 38%;
    display: flex; justify-content: center; align-items: center;
  }

  /* The chassis holding every plane together in one 3D space. */
  .cabinet-body {
    width: 460px; max-width: 88vw;
    transform-style: preserve-3d;
    display: flex; flex-direction: column;
    position: relative;
    background: #1b0e3d;
    border-radius: 14px;
    box-shadow: -18px 0 34px rgba(0,0,0,0.5), 18px 0 34px rgba(0,0,0,0.5);
  }
  .cabinet-body::after {  /* grounded contact shadow */
    content: ""; position: absolute; z-index: -3;
    left: 4%; right: 4%; bottom: -34px; height: 50px;
    background: radial-gradient(55% 55% at 50% 0, rgba(0,0,0,0.75), transparent 75%);
    filter: blur(9px);
  }

  /* ---- Marquee (juts forward, tilts toward the player) -------------------- */
  .box-marquee {
    position: relative; height: 92px;
    background:
      linear-gradient(180deg, rgba(255,255,255,0.14), transparent 45%),
      linear-gradient(180deg, #442375, #220e3b);
    border: 3px solid rgba(195,140,255,0.55);
    border-radius: 14px 14px 4px 4px;
    transform-origin: bottom center;
    transform: translateZ(34px) rotateX(-11deg);
    box-shadow:
      inset 0 0 22px rgba(255,170,255,0.16),
      0 24px 26px rgba(0,0,0,0.75);
    display: flex; justify-content: center; align-items: center;
    z-index: 10;
  }
  .marquee-text {
    background: linear-gradient(180deg, #fff 0%, #ffe3ff 42%, #ff8ee0 100%);
    -webkit-background-clip: text; background-clip: text; color: transparent;
    filter: drop-shadow(0 0 14px rgba(255,120,220,0.85)) drop-shadow(0 3px 0 rgba(50,10,60,0.8));
    font-size: 26px;
  }

  /* ---- Screen housing (pushed back so the marquee + deck pop) ------------- */
  .box-screen-housing {
    position: relative;
    padding: 30px 30px 26px;
    background: linear-gradient(160deg, #221638, #0e0a22);
    border-left: 4px solid #2e1859;
    border-right: 4px solid #2e1859;
    transform: translateZ(-18px);
    z-index: 5;
  }
  .crt-screen {
    position: relative;
    aspect-ratio: 4 / 3;
    border-radius: 22px / 30px;
    background:
      radial-gradient(120% 110% at 50% 32%, rgba(22,78,102,0.45), rgba(1,5,10,0.99) 75%),
      #020407;
    box-shadow:
      inset 0 0 80px rgba(0,0,0,0.97),
      inset 0 0 26px rgba(70,210,255,0.13),
      0 0 0 8px #070412,
      0 0 0 11px rgba(140,90,220,0.25);
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
  .arcade-screen-inner { position: absolute; inset: 0; z-index: 4; padding: 18px 20px; }

  /* ---- Control deck (slanted panel, passes 3D to its buttons) ------------- */
  .box-control-deck {
    position: relative; height: 132px;
    background: linear-gradient(180deg, #2c1856 0%, #160b2e 100%);
    border: 2px solid rgba(160,110,240,0.5);
    border-top: none;
    transform-origin: top center;
    transform: translateZ(-18px) rotateX(46deg);
    transform-style: preserve-3d;
    box-shadow: inset 0 6px 16px rgba(0,0,0,0.55), 0 16px 18px -5px rgba(0,0,0,0.8);
    display: flex; justify-content: center; align-items: center; gap: 14px;
    z-index: 8;
  }
  .deck-btn {
    position: relative; display: grid; place-items: center;
    width: 50px; height: 50px; border-radius: 50%;
    color: rgba(255,255,255,0.95); border: 2px solid rgba(255,255,255,0.22);
    background: radial-gradient(circle at 32% 26%, #ffb0b0 0%, #ff4d4d 34%, #d41c1c 70%, #a31414 100%);
    transform: translateZ(12px);
    box-shadow: -2px 6px 0 #7a0c0c, -4px 11px 11px rgba(0,0,0,0.6);
    cursor: pointer;
    transition: transform 0.1s ease, box-shadow 0.1s ease, filter 0.1s ease;
  }
  .deck-btn:hover:not(:disabled) { filter: brightness(1.08); }
  .deck-btn:active:not(:disabled) {
    transform: translateZ(3px);
    box-shadow: -1px 1px 0 #7a0c0c, -1px 3px 6px rgba(0,0,0,0.45);
  }
  .deck-btn:disabled { opacity: 0.35; cursor: not-allowed; }

  /* ---- Coin base (flat front face, drops down from the deck lip) ---------- */
  .box-coin-base {
    position: relative; height: 116px;
    background: linear-gradient(180deg, #1c0e3a, #0b0518);
    border: 2px solid rgba(160,110,240,0.3); border-top: none;
    border-radius: 0 0 14px 14px;
    transform-origin: top center;
    transform: translateZ(74px);
    display: flex; justify-content: center; align-items: center;
    box-shadow: inset 0 18px 22px rgba(0,0,0,0.55);
    z-index: 6;
  }
  .coin-slot {
    position: relative;
    display: flex; align-items: center; justify-content: space-between; gap: 14px;
    width: 230px; padding: 12px 18px;
    background: linear-gradient(180deg, #160a30, #0a0418);
    border: 2px solid rgba(160,110,240,0.3);
    border-radius: 10px;
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

  /* ---- Slot-machine pull lever (mounted on the screen housing's side) ----- */
  .lever-assembly {
    position: absolute; right: -74px; top: 46%;
    transform: translateY(-50%);
    z-index: 9;
  }
  .lever-base {
    width: 26px; height: 70px; border-radius: 7px;
    background: linear-gradient(90deg, #2a2b34, #6a6c78 50%, #2a2b34);
    box-shadow: inset -2px 0 6px rgba(0,0,0,0.8), 0 8px 14px rgba(0,0,0,0.55);
  }
  .lever-arm {
    position: absolute; left: 17px; top: 50%;
    transform-origin: left center;
  }
  .lever-stick {
    width: 76px; height: 14px; border-radius: 8px;
    background: linear-gradient(180deg, #6a6c78 0%, #f2f3f8 46%, #6a6c78 100%);
    box-shadow: 0 3px 6px rgba(0,0,0,0.5);
  }
  .lever-ball {
    position: absolute; right: -34px; top: 50%; transform: translateY(-50%);
    width: 50px; height: 50px; border-radius: 999px;
    background: radial-gradient(circle at 32% 26%, #ffc2c6 0%, #ff4d60 34%, #cc142c 64%, #8c0a1c 100%);
    box-shadow: 0 8px 16px rgba(0,0,0,0.55), inset 0 6px 9px rgba(255,255,255,0.7), inset 0 -8px 12px rgba(110,0,18,0.5);
    border: 2px solid rgba(255,255,255,0.16);
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
