import { AnimatePresence, motion } from "framer-motion";
import { Rocket, X } from "lucide-react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { useEasterEggStore } from "@/stores/easterEgg";

// The genuine article. (You knew this was coming the moment you read "supercharge".)
const RICKROLL_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ";

const CONFETTI_COLORS = [
  "#ff4d6d",
  "#ffd166",
  "#06d6a0",
  "#4cc9f0",
  "#b15cff",
  "#ff8fab",
  "#ffffff",
];

const FLOATERS = ["🎉", "🎈", "🥳", "✨", "💖", "🎊", "⭐", "🪩"];

interface ConfettiPiece {
  left: number;
  delay: number;
  duration: number;
  size: number;
  color: string;
  rotate: number;
  round: boolean;
}

export function CreditsOverlay() {
  const creditsOpen = useEasterEggStore((s) => s.creditsOpen);
  const closeCredits = useEasterEggStore((s) => s.closeCredits);
  const { t } = useTranslation();

  // Pre-compute a stable confetti field so it doesn't reshuffle on re-render.
  const confetti = useMemo<ConfettiPiece[]>(
    () =>
      Array.from({ length: 90 }, (_, i) => ({
        left: Math.random() * 100,
        delay: Math.random() * 3,
        duration: 3 + Math.random() * 3,
        size: 7 + Math.random() * 9,
        color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
        rotate: Math.random() * 360,
        round: Math.random() > 0.6,
      })),
    [],
  );

  return (
    <AnimatePresence>
      {creditsOpen && (
        <motion.div
          className="fixed inset-0 z-[100] flex items-center justify-center overflow-hidden"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.35 }}
          role="dialog"
          aria-modal="true"
          aria-label={t("credits.ariaLabel")}
        >
          {/* Scoped animations so the party stays self-contained. */}
          <style>{partyKeyframes}</style>

          {/* Festive backdrop: a shifting multi-colour wash, miles from the calm
              app palette — this is meant to feel like the lights came on. */}
          <div className="party-bg absolute inset-0" />
          <div className="absolute inset-0 bg-black/30" />

          {/* Confetti rain */}
          <div className="pointer-events-none absolute inset-0">
            {confetti.map((p, i) => (
              <span
                key={i}
                className="confetti absolute top-[-12%]"
                style={{
                  left: `${p.left}%`,
                  width: p.size,
                  height: p.round ? p.size : p.size * 0.45,
                  background: p.color,
                  borderRadius: p.round ? "999px" : "2px",
                  animationDelay: `${p.delay}s`,
                  animationDuration: `${p.duration}s`,
                  ["--spin" as string]: `${p.rotate}deg`,
                }}
              />
            ))}
          </div>

          {/* Drifting emoji */}
          <div className="pointer-events-none absolute inset-0">
            {FLOATERS.map((emoji, i) => (
              <span
                key={emoji}
                className="floater absolute text-3xl sm:text-4xl"
                style={{
                  left: `${6 + i * 11.5}%`,
                  bottom: "-10%",
                  animationDelay: `${i * 0.6}s`,
                  animationDuration: `${6 + (i % 4)}s`,
                }}
              >
                {emoji}
              </span>
            ))}
          </div>

          {/* Close (so the party isn't a trap) */}
          <button
            type="button"
            onClick={closeCredits}
            aria-label={t("credits.close")}
            className="absolute right-5 top-5 z-10 grid size-10 place-items-center rounded-full bg-white/15 text-white backdrop-blur transition hover:scale-110 hover:bg-white/25"
          >
            <X className="size-5" />
          </button>

          {/* Centerpiece */}
          <motion.div
            className="relative z-10 flex flex-col items-center px-6 text-center"
            initial={{ scale: 0.6, y: 30, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.7, opacity: 0 }}
            transition={{ type: "spring", stiffness: 220, damping: 16, delay: 0.1 }}
          >
            <motion.p
              className="mb-3 font-display text-sm font-bold uppercase tracking-[0.4em] text-white/80"
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3 }}
            >
              {t("credits.brand")}
            </motion.p>

            <h1
              className="party-title font-display text-5xl font-black leading-[1.05] sm:text-7xl md:text-8xl"
              style={{ letterSpacing: "-0.03em" }}
            >
              {t("credits.madeWith")}{" "}
              <motion.span
                className="inline-block"
                animate={{ scale: [1, 1.35, 1] }}
                transition={{ duration: 0.7, repeat: Infinity, ease: "easeInOut" }}
              >
                💖
              </motion.span>
              <br />
              {t("credits.by")}
            </h1>

            <motion.p
              className="mt-5 max-w-md font-display text-base font-medium text-white/85 sm:text-lg"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.55 }}
            >
              {t("credits.tagline")}
            </motion.p>

            <motion.button
              type="button"
              onClick={() => window.open(RICKROLL_URL, "_blank", "noopener")}
              className="group mt-10 inline-flex items-center gap-2.5 rounded-full bg-white px-8 py-4 font-display text-base font-bold text-[#b15cff] shadow-[0_12px_40px_-8px_rgba(0,0,0,0.5)] transition hover:shadow-[0_18px_55px_-8px_rgba(255,255,255,0.6)]"
              initial={{ opacity: 0, y: 20 }}
              animate={{
                opacity: 1,
                y: 0,
                scale: [1, 1.04, 1],
              }}
              transition={{
                opacity: { delay: 0.7 },
                y: { delay: 0.7 },
                scale: { duration: 1.6, repeat: Infinity, ease: "easeInOut", delay: 0.9 },
              }}
              whileHover={{ scale: 1.08 }}
              whileTap={{ scale: 0.95 }}
            >
              <Rocket className="size-5 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
              {t("credits.supercharge")}
            </motion.button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

const partyKeyframes = `
  .party-bg {
    background: linear-gradient(
      125deg,
      #ff4d6d, #ff8fab, #ffd166, #06d6a0, #4cc9f0, #b15cff
    );
    background-size: 300% 300%;
    animation: party-pan 9s ease infinite;
  }
  @keyframes party-pan {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
  }
  .party-title {
    color: #fff;
    text-shadow:
      0 2px 0 rgba(0,0,0,0.12),
      0 8px 30px rgba(0,0,0,0.35);
    animation: party-pop 2.4s ease-in-out infinite;
  }
  @keyframes party-pop {
    0%, 100% { transform: rotate(-1deg) scale(1); }
    50% { transform: rotate(1deg) scale(1.02); }
  }
  .confetti {
    animation-name: confetti-fall;
    animation-timing-function: linear;
    animation-iteration-count: infinite;
    opacity: 0.95;
  }
  @keyframes confetti-fall {
    0% { transform: translateY(0) rotate(0deg); opacity: 0; }
    8% { opacity: 1; }
    100% { transform: translateY(115vh) rotate(var(--spin)); opacity: 1; }
  }
  .floater {
    animation-name: floater-rise;
    animation-timing-function: ease-in;
    animation-iteration-count: infinite;
  }
  @keyframes floater-rise {
    0% { transform: translateY(0) rotate(-8deg); opacity: 0; }
    15% { opacity: 1; }
    100% { transform: translateY(-115vh) rotate(8deg); opacity: 0; }
  }
  @media (prefers-reduced-motion: reduce) {
    .party-bg, .party-title, .confetti, .floater { animation: none; }
    .confetti, .floater { display: none; }
  }
`;
