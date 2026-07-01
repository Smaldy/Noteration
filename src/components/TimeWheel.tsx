import { useLayoutEffect, useRef } from "react";

import { cn } from "@/lib/utils";

/**
 * An iOS-alarm-style scrolling wheel time picker. Two drums (hours · minutes)
 * with momentum scroll-snap, a 3D cylinder tilt, edge fade masks, and a centred
 * selection band. Value is a 24h "HH:MM" string.
 */

const ROW_H = 40; // px per row
const VISIBLE = 5; // rows shown (odd, so one is dead-centre)
const PAD = ((VISIBLE - 1) / 2) * ROW_H;

interface Props {
  /** "HH:MM" (24h). */
  value: string;
  onChange: (value: string) => void;
  /** Minute granularity (default 5). */
  minuteStep?: number;
  className?: string;
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/** Snap a minute to the nearest step on the wheel. */
function snapMinute(m: number, step: number): number {
  return Math.min(Math.round(m / step) * step, 60 - step);
}

export function TimeWheel({ value, onChange, minuteStep = 5, className }: Props) {
  const [hStr, mStr] = value.split(":");
  const hour = Math.max(0, Math.min(23, Number(hStr) || 0));
  const minute = snapMinute(Math.max(0, Math.min(59, Number(mStr) || 0)), minuteStep);

  const hours = Array.from({ length: 24 }, (_, i) => i);
  const minutes = Array.from(
    { length: Math.floor(60 / minuteStep) },
    (_, i) => i * minuteStep,
  );

  const setHour = (h: number) => onChange(`${pad2(h)}:${pad2(minute)}`);
  const setMinute = (m: number) => onChange(`${pad2(hour)}:${pad2(m)}`);

  return (
    <div className={cn("time-wheel", className)}>
      <Drum
        values={hours}
        index={hour}
        onIndex={(i) => setHour(hours[i])}
        format={pad2}
        ariaLabel="Hour"
      />
      <span className="time-wheel-colon" aria-hidden>
        :
      </span>
      <Drum
        values={minutes}
        index={minutes.indexOf(minute)}
        onIndex={(i) => setMinute(minutes[i])}
        format={pad2}
        ariaLabel="Minute"
      />
      <div className="time-wheel-band" aria-hidden />
    </div>
  );
}

interface DrumProps {
  values: number[];
  index: number;
  onIndex: (i: number) => void;
  format: (n: number) => string;
  ariaLabel: string;
}

function Drum({ values, index, onIndex, format, ariaLabel }: DrumProps) {
  const ref = useRef<HTMLDivElement>(null);
  const raf = useRef<number | undefined>(undefined);
  const settle = useRef<number | undefined>(undefined);
  const indexRef = useRef(index);
  indexRef.current = index;

  // Paint the 3D drum: each row tilts / fades / shrinks by its distance from
  // the viewport centre, so the strip reads as a rotating cylinder.
  function paint() {
    const el = ref.current;
    if (!el) return;
    const center = el.scrollTop / ROW_H;
    const items = el.querySelectorAll<HTMLElement>("[data-row]");
    items.forEach((item, i) => {
      const d = i - center;
      const ad = Math.abs(d);
      const rot = Math.max(-72, Math.min(72, d * -24));
      const op = Math.max(0, 1 - ad * 0.26);
      const scale = Math.max(0.62, 1 - ad * 0.1);
      item.style.opacity = String(op);
      item.style.transform = `translateZ(-${ad * 4}px) rotateX(${rot}deg) scale(${scale})`;
      item.style.fontWeight = ad < 0.5 ? "700" : "500";
    });
  }

  function scrollToIndex(i: number, smooth: boolean) {
    const el = ref.current;
    if (!el) return;
    el.scrollTo({ top: i * ROW_H, behavior: smooth ? "smooth" : "auto" });
  }

  // Position to the selected value on mount + whenever it changes externally.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (Math.abs(el.scrollTop - index * ROW_H) > 1) el.scrollTop = index * ROW_H;
    paint();
  }, [index, values.length]);

  function onScroll() {
    if (raf.current) cancelAnimationFrame(raf.current);
    raf.current = requestAnimationFrame(paint);
    if (settle.current) window.clearTimeout(settle.current);
    settle.current = window.setTimeout(() => {
      const el = ref.current;
      if (!el) return;
      const i = Math.max(
        0,
        Math.min(values.length - 1, Math.round(el.scrollTop / ROW_H)),
      );
      if (Math.abs(el.scrollTop - i * ROW_H) > 0.5) scrollToIndex(i, false);
      if (i !== indexRef.current) onIndex(i);
    }, 80);
  }

  return (
    <div className="time-wheel-drum" style={{ height: VISIBLE * ROW_H }}>
      <div
        ref={ref}
        role="listbox"
        aria-label={ariaLabel}
        onScroll={onScroll}
        className="time-wheel-track"
        style={{ paddingTop: PAD, paddingBottom: PAD }}
      >
        {values.map((v, i) => (
          <button
            type="button"
            data-row
            key={v}
            role="option"
            aria-selected={i === index}
            onClick={() => scrollToIndex(i, true)}
            style={{ height: ROW_H }}
            className="time-wheel-row"
          >
            {format(v)}
          </button>
        ))}
      </div>
    </div>
  );
}
