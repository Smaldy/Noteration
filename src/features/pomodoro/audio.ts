/**
 * Offline Pomodoro audio engine (Web Audio API).
 *
 * Ambient presets are *synthesized* (filtered noise) so they need no audio files
 * and work fully offline. "Custom" decodes a user-provided local file. The alarm
 * is a short synthesized chime. A small IndexedDB store persists the custom file
 * across reloads (object URLs don't survive a refresh).
 */

export type SoundKind = "none" | "rain" | "sea" | "custom";

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

function makeNoise(c: AudioContext, type: "white" | "brown"): AudioBuffer {
  const len = c.sampleRate * 4; // 4s seamless loop
  const buf = c.createBuffer(1, len, c.sampleRate);
  const data = buf.getChannelData(0);
  if (type === "white") {
    for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1;
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

  if (kind === "custom") {
    const src = c.createBufferSource();
    src.buffer = customBuffer;
    src.loop = true;
    src.connect(ambientGain);
    src.start();
    cleanups.push(() => src.stop());
  } else if (kind === "rain") {
    const src = c.createBufferSource();
    src.buffer = makeNoise(c, "white");
    src.loop = true;
    const hp = c.createBiquadFilter();
    hp.type = "highpass";
    hp.frequency.value = 900;
    const lp = c.createBiquadFilter();
    lp.type = "lowpass";
    lp.frequency.value = 7000;
    src.connect(hp).connect(lp).connect(ambientGain);
    src.start();
    cleanups.push(() => src.stop());
  } else {
    // sea: brown noise, softened, with a slow swell (LFO on a gain stage).
    const src = c.createBufferSource();
    src.buffer = makeNoise(c, "brown");
    src.loop = true;
    const lp = c.createBiquadFilter();
    lp.type = "lowpass";
    lp.frequency.value = 600;
    const swell = c.createGain();
    swell.gain.value = 0.7;
    const lfo = c.createOscillator();
    lfo.frequency.value = 0.12; // ~8s per wave
    const lfoDepth = c.createGain();
    lfoDepth.gain.value = 0.3;
    lfo.connect(lfoDepth).connect(swell.gain);
    src.connect(lp).connect(swell).connect(ambientGain);
    src.start();
    lfo.start();
    cleanups.push(() => {
      src.stop();
      lfo.stop();
    });
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
