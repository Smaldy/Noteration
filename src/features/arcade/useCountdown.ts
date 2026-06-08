import { useEffect, useState } from "react";

/**
 * Ticks every second toward an ISO target time. Returns the seconds remaining
 * (0 once elapsed) and a `mm:ss` label. `null` target → inactive (0 / "").
 */
export function useCountdown(targetIso: string | null): {
  secondsLeft: number;
  label: string;
  active: boolean;
} {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (targetIso === null) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [targetIso]);

  if (targetIso === null) return { secondsLeft: 0, label: "", active: false };

  const target = new Date(targetIso).getTime();
  const secondsLeft = Math.max(0, Math.ceil((target - now) / 1000));
  const mm = Math.floor(secondsLeft / 60);
  const ss = secondsLeft % 60;
  const label = `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
  return { secondsLeft, label, active: secondsLeft > 0 };
}
