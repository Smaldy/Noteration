/**
 * Scoped CRT-arcade styling for the minigame cabinet. Injected as a single
 * <style> tag inside the overlay (mirrors CreditsOverlay) so none of it leaks
 * into the real app's global CSS. All class names are arcade-prefixed.
 *
 * The look is a physical 2.5-D arcade machine: a backlit marquee, a wide curved
 * CRT, and an angled control deck (perspective tilt) carrying chunky semi-3-D
 * buttons, a ball-top lever, and a coin slot.
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
      rgba(3, 2, 8, 0.9);
    backdrop-filter: blur(3px);
  }

  /* ---- Cabinet body (2.5-D) ------------------------------------------------ */
  .arcade-cab {
    position: relative;
    filter: drop-shadow(0 40px 60px rgba(0,0,0,0.7));
  }
  .arcade-cab-side {
    background: linear-gradient(180deg, #2a1550, #140a2c 55%, #0a0518);
    border: 2px solid rgba(150,100,235,0.30);
    box-shadow: inset 0 0 60px rgba(120,70,220,0.16), inset 0 2px 0 rgba(255,255,255,0.05);
  }

  /* Marquee: backlit trapezoid header. */
  .arcade-marquee {
    clip-path: polygon(6% 0, 94% 0, 100% 100%, 0 100%);
    background:
      linear-gradient(180deg, rgba(255,255,255,0.10), transparent 40%),
      linear-gradient(180deg, #3a1d63, #25113f);
    border: 2px solid rgba(180,120,255,0.4);
    box-shadow: 0 0 30px -4px rgba(180,110,255,0.55), inset 0 0 24px rgba(255,170,255,0.18);
  }
  .arcade-marquee-title {
    background: linear-gradient(180deg, #fff 0%, #ffd6ff 45%, #ff7bd5 100%);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    filter: drop-shadow(0 0 10px rgba(255,120,220,0.65));
  }

  /* ---- The CRT screen (wide, old-TV) -------------------------------------- */
  .arcade-tv {
    background: linear-gradient(160deg, #1c1330, #0c0820);
    border: 3px solid rgba(160,110,235,0.35);
    box-shadow:
      inset 0 2px 0 rgba(255,255,255,0.06),
      0 10px 30px -10px rgba(0,0,0,0.8);
    padding: 14px;
    border-radius: 18px;
  }
  .arcade-screen {
    position: relative;
    aspect-ratio: 4 / 3;            /* old TV: wider than tall */
    border-radius: 22px / 30px;     /* gentle CRT bulge */
    background:
      radial-gradient(130% 120% at 50% 30%, rgba(20,70,90,0.4), rgba(1,6,12,0.98) 72%),
      #03060a;
    box-shadow:
      inset 0 0 90px rgba(0,0,0,0.95),
      inset 0 0 22px rgba(80,220,255,0.12),
      0 0 0 6px #05030c,
      0 0 0 8px rgba(120,80,200,0.25);
    overflow: hidden;
  }
  .arcade-screen::before {
    content: ""; position: absolute; inset: 0; pointer-events: none; z-index: 5;
    background: repeating-linear-gradient(
      to bottom, rgba(255,255,255,0.05) 0, rgba(255,255,255,0.05) 1px, transparent 1px, transparent 3px);
  }
  .arcade-screen::after {
    content: ""; position: absolute; inset: 0; pointer-events: none; z-index: 6;
    background: radial-gradient(120% 120% at 50% 50%, transparent 52%, rgba(0,0,0,0.62) 100%);
    animation: arcade-flicker 6s infinite steps(60);
  }
  @keyframes arcade-flicker { 0%,96%,100%{opacity:1} 97%{opacity:0.85} 98%{opacity:0.97} }
  .arcade-screen-inner { position: absolute; inset: 0; z-index: 4; padding: 18px 22px; }

  /* ---- Control deck (angled, 2.5-D) --------------------------------------- */
  .arcade-deck-wrap { perspective: 900px; }
  .arcade-deck {
    transform: rotateX(34deg);
    transform-origin: top center;
    background:
      linear-gradient(180deg, #2c1a52 0%, #1a0f38 70%, #120925 100%);
    border: 2px solid rgba(150,100,235,0.30);
    border-top: none;
    box-shadow:
      inset 0 14px 30px -14px rgba(255,255,255,0.10),
      inset 0 0 50px rgba(90,50,170,0.25),
      0 24px 40px -18px rgba(0,0,0,0.7);
    border-radius: 0 0 26px 26px;
  }
  .arcade-deck-lip {
    height: 18px;
    background: linear-gradient(180deg, #3a2566, #1c1038);
    border: 2px solid rgba(150,100,235,0.25);
    border-top: none;
    border-radius: 0 0 10px 10px;
    box-shadow: 0 10px 24px -10px rgba(0,0,0,0.8);
  }

  /* ---- Semi-3-D arcade buttons -------------------------------------------- */
  .arcade-btn {
    position: relative;
    display: grid; place-items: center;
    width: 46px; height: 46px;
    border-radius: 999px;
    color: #fff5f5;
    background: radial-gradient(circle at 36% 30%, #ff8d8d 0%, #ff3b3b 42%, #c01616 100%);
    border: none;
    box-shadow:
      0 6px 0 #7a0d0d,                 /* the button's depth/side wall */
      0 9px 12px rgba(0,0,0,0.55),
      inset 0 2px 4px rgba(255,255,255,0.55),
      inset 0 -4px 6px rgba(0,0,0,0.35);
    transition: transform 0.06s ease, box-shadow 0.06s ease;
    cursor: pointer;
  }
  .arcade-btn:hover { filter: brightness(1.08); }
  .arcade-btn:active:not(:disabled), .arcade-btn-press {
    transform: translateY(5px);
    box-shadow:
      0 1px 0 #7a0d0d,
      0 2px 5px rgba(0,0,0,0.5),
      inset 0 2px 4px rgba(255,255,255,0.4),
      inset 0 -3px 6px rgba(0,0,0,0.4);
  }
  .arcade-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .arcade-btn-amber { background: radial-gradient(circle at 36% 30%, #ffd98a 0%, #ffae2e 42%, #c97e0c 100%); box-shadow: 0 6px 0 #875200, 0 9px 12px rgba(0,0,0,0.55), inset 0 2px 4px rgba(255,255,255,0.6), inset 0 -4px 6px rgba(0,0,0,0.3); color:#3a2400; }

  /* ---- Lever (ball-top joystick) ------------------------------------------ */
  .arcade-lever { position: relative; width: 64px; height: 92px; }
  .arcade-lever-base {
    position: absolute; bottom: 0; left: 50%; transform: translateX(-50%);
    width: 56px; height: 20px; border-radius: 999px;
    background: radial-gradient(circle at 50% 30%, #4a4a55, #15151c 70%);
    box-shadow: 0 6px 14px rgba(0,0,0,0.6), inset 0 2px 3px rgba(255,255,255,0.2);
  }
  .arcade-lever-arm {
    position: absolute; bottom: 8px; left: 50%;
    transform-origin: bottom center;
    transition: transform 0.22s cubic-bezier(0.34, 1.56, 0.64, 1);
    display: flex; flex-direction: column; align-items: center;
    transform: translateX(-50%);
  }
  .arcade-lever-pulled .arcade-lever-arm { transform: translateX(-50%) rotate(-26deg) translateY(6px); }
  .arcade-lever-shaft {
    width: 9px; height: 52px;
    background: linear-gradient(90deg, #6b6b78, #c9c9d4 45%, #6b6b78);
    border-radius: 6px;
  }
  .arcade-lever-ball {
    width: 30px; height: 30px; border-radius: 999px; margin-bottom: -4px;
    background: radial-gradient(circle at 35% 28%, #ff9aa0 0%, #ff3b52 45%, #b3122a 100%);
    box-shadow: 0 4px 10px rgba(0,0,0,0.5), inset 0 3px 5px rgba(255,255,255,0.6);
  }

  /* ---- Coin slot ----------------------------------------------------------- */
  .arcade-slot {
    background: linear-gradient(180deg, #241640, #160c2c);
    border: 2px solid rgba(150,100,235,0.3);
    border-radius: 10px;
    box-shadow: inset 0 3px 8px rgba(0,0,0,0.6);
  }
  .arcade-slot-mouth {
    width: 34px; height: 8px; border-radius: 3px;
    background: #05030a;
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.9), 0 1px 0 rgba(255,255,255,0.08);
  }
  .arcade-coin {
    width: 22px; height: 22px; border-radius: 999px;
    background: radial-gradient(circle at 36% 30%, #fff1b0, #ffcf3a 45%, #d99412 100%);
    box-shadow: 0 0 10px rgba(255,200,60,0.7), inset 0 1px 2px rgba(255,255,255,0.7);
    display: grid; place-items: center;
    color: #8a5a00; font-weight: 900; font-size: 11px;
  }

  /* ---- Neon text ----------------------------------------------------------- */
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
    .arcade-screen::after, .arcade-blink, .arcade-slam, .arcade-lever-arm { animation: none; transition: none; }
  }
`;
