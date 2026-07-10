/**
 * Offline Pomodoro audio engine (Web Audio API).
 *
 * Ambient presets are *synthesized* (filtered noise) so they need no audio files
 * and work fully offline. "Custom" decodes a user-provided local file. The alarm
 * is a short synthesized chime. A small IndexedDB store persists the custom file
 * across reloads (object URLs don't survive a refresh).
 */

export type SoundKind =
  | "none"
  | "rain"
  | "sea"
  | "white"
  | "pink"
  | "brown"
  | "wind"
  | "custom";

let ctx: AudioContext | null = null;
let ambientGain: GainNode | null = null;
let ambient: { stop: () => void } | null = null;
let customBuffer: AudioBuffer | null = null;

function context(): AudioContext {
  if (!ctx) {
    const Ctor =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext })
        .webkitAudioContext;
    ctx = new Ctor();
    ambientGain = ctx.createGain();
    ambientGain.gain.value = 0;
    ambientGain.connect(ctx.destination);
  }
  return ctx;
}

/** Resume the context — must be called from a user gesture (autoplay policy). */
export async function unlock(): Promise<void> {
  const c = context();
  if (c.state === "suspended") await c.resume();
}

/** Live ambient volume (0–1). Muting is just volume 0. */
export function setVolume(volume: number): void {
  const c = context();
  if (ambientGain) ambientGain.gain.setTargetAtTime(volume, c.currentTime, 0.08);
}

function makeNoise(c: AudioContext, type: "white" | "pink" | "brown"): AudioBuffer {
  const len = c.sampleRate * 4; // 4s seamless loop
  const buf = c.createBuffer(1, len, c.sampleRate);
  const data = buf.getChannelData(0);
  if (type === "white") {
    for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1;
  } else if (type === "pink") {
    // Paul Kellet's refined pink noise filter: -3 dB/octave, warm and even —
    // the classic "pleasant" broadband noise, far softer on the ear than white.
    let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
    for (let i = 0; i < len; i++) {
      const white = Math.random() * 2 - 1;
      b0 = 0.99886 * b0 + white * 0.0555179;
      b1 = 0.99332 * b1 + white * 0.0750759;
      b2 = 0.969 * b2 + white * 0.153852;
      b3 = 0.8665 * b3 + white * 0.3104856;
      b4 = 0.55 * b4 + white * 0.5329522;
      b5 = -0.7616 * b5 - white * 0.016898;
      data[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362) * 0.11;
      b6 = white * 0.115926;
    }
  } else {
    let last = 0; // brown noise = integrated white, lower/rumblier
    for (let i = 0; i < len; i++) {
      const white = Math.random() * 2 - 1;
      last = (last + 0.02 * white) / 1.02;
      data[i] = last * 3.5;
    }
  }
  return buf;
}

/** Start (or switch) the looping ambient bed. Stops any previous bed first. */
export function startAmbient(kind: SoundKind): void {
  const c = context();
  stopAmbient();
  if (kind === "none" || !ambientGain) return;
  if (kind === "custom" && !customBuffer) return;

  const cleanups: Array<() => void> = [];

  // Per-preset trim so every bed lands at a comparable loudness — full-band
  // white noise carries far more energy than a narrow filtered bed, so without
  // this, switching presets would jump in volume.
  const trim = c.createGain();
  trim.connect(ambientGain);
  cleanups.push(() => trim.disconnect());

  /** Looping noise source, started immediately and stopped on cleanup. */
  const loop = (buffer: AudioBuffer): AudioBufferSourceNode => {
    const src = c.createBufferSource();
    src.buffer = buffer;
    src.loop = true;
    src.start();
    cleanups.push(() => src.stop());
    return src;
  };

  /** Slow sine LFO driving an AudioParam around its current value. */
  const modulate = (param: AudioParam, hz: number, depth: number): void => {
    const lfo = c.createOscillator();
    lfo.frequency.value = hz;
    const lfoDepth = c.createGain();
    lfoDepth.gain.value = depth;
    lfo.connect(lfoDepth).connect(param);
    lfo.start();
    cleanups.push(() => lfo.stop());
  };

  if (kind === "custom") {
    trim.gain.value = 1;
    loop(customBuffer as AudioBuffer).connect(trim);
  } else if (kind === "rain") {
    // Gentle rain: pink noise (already soft) with the fizzy top rolled off and
    // a barely-there slow swell, like steady drizzle on a roof.
    trim.gain.value = 1.0;
    const hp = c.createBiquadFilter();
    hp.type = "highpass";
    hp.frequency.value = 300;
    const lp = c.createBiquadFilter();
    lp.type = "lowpass";
    lp.frequency.value = 4200;
    const drift = c.createGain();
    drift.gain.value = 0.9;
    modulate(drift.gain, 0.07, 0.08); // ±9% over ~14s — natural ebb, not a pulse
    loop(makeNoise(c, "pink")).connect(hp).connect(lp).connect(drift).connect(trim);
  } else if (kind === "sea") {
    // Sea: brown noise, softened, with a slow swell (LFO on a gain stage).
    trim.gain.value = 1;
    const lp = c.createBiquadFilter();
    lp.type = "lowpass";
    lp.frequency.value = 600;
    const swell = c.createGain();
    swell.gain.value = 0.7;
    modulate(swell.gain, 0.12, 0.3); // ~8s per wave
    loop(makeNoise(c, "brown")).connect(lp).connect(swell).connect(trim);
  } else if (kind === "white") {
    // Pure white noise, trimmed well down — flat spectrum reads much louder.
    trim.gain.value = 0.3;
    loop(makeNoise(c, "white")).connect(trim);
  } else if (kind === "pink") {
    trim.gain.value = 0.85;
    loop(makeNoise(c, "pink")).connect(trim);
  } else if (kind === "brown") {
    trim.gain.value = 1;
    loop(makeNoise(c, "brown")).connect(trim);
  } else {
    // wind: brown noise through a slowly wandering bandpass — the moving
    // resonance is what reads as gusts — plus a long loudness swell.
    trim.gain.value = 1.4;
    const bp = c.createBiquadFilter();
    bp.type = "bandpass";
    bp.frequency.value = 350;
    bp.Q.value = 0.8;
    modulate(bp.frequency, 0.05, 180); // sweep ~170–530 Hz over ~20s
    const swell = c.createGain();
    swell.gain.value = 0.75;
    modulate(swell.gain, 0.03, 0.2);
    loop(makeNoise(c, "brown")).connect(bp).connect(swell).connect(trim);
  }

  ambient = {
    stop: () => cleanups.forEach((fn) => fn()),
  };
}

export function stopAmbient(): void {
  if (ambient) {
    try {
      ambient.stop();
    } catch {
      // a source may already be stopped; ignore
    }
    ambient = null;
  }
}

/** Decode a local audio file into the custom buffer. Throws if undecodable. */
export async function loadCustomFromBytes(bytes: ArrayBuffer): Promise<void> {
  const c = context();
  // decodeAudioData detaches the buffer; pass a copy so callers can reuse bytes.
  customBuffer = await c.decodeAudioData(bytes.slice(0));
}

export function hasCustom(): boolean {
  return customBuffer !== null;
}

/** A gentle two-note chime to mark the end of a phase. No-op when muted. */
export function playAlarm(muted: boolean): void {
  if (muted) return;
  const c = context();
  const now = c.currentTime;
  const notes = [660, 880];
  notes.forEach((freq, i) => {
    const t = now + i * 0.18;
    const osc = c.createOscillator();
    const gain = c.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0, t);
    gain.gain.linearRampToValueAtTime(0.5, t + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.5);
    osc.connect(gain).connect(c.destination);
    osc.start(t);
    osc.stop(t + 0.55);
  });
}

// --- IndexedDB: persist the custom file's bytes across reloads ---------------

const DB_NAME = "noteration";
const STORE = "audio";
const KEY = "pomodoro-custom";

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE)) {
        req.result.createObjectStore(STORE);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function saveCustomBytes(bytes: ArrayBuffer): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put(bytes, KEY);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

export async function readCustomBytes(): Promise<ArrayBuffer | null> {
  const db = await openDb();
  const result = await new Promise<ArrayBuffer | null>((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).get(KEY);
    req.onsuccess = () => resolve((req.result as ArrayBuffer) ?? null);
    req.onerror = () => reject(req.error);
  });
  db.close();
  return result;
}

export async function clearCustomBytes(): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(KEY);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
  customBuffer = null;
}
