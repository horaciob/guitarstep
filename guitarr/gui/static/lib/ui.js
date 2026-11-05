// Shared view helpers: DOM, API, toasts, chord diagrams and sound.
import { errorText, t } from "./i18n.js";

export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
export const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
export const OPEN = [40, 45, 50, 55, 59, 64];            // 6th … 1st
export const noteName = p => NOTE_NAMES[((p % 12) + 12) % 12] + (Math.floor(p / 12) - 1);

export async function api(path, opts = {}) {
  const o = { ...opts };
  if (o.json !== undefined) {
    o.method = o.method || "POST";
    o.headers = { "Content-Type": "application/json" };
    o.body = JSON.stringify(o.json);
    delete o.json;
  }
  const r = await fetch(path, o);
  let data = null;
  try { data = await r.json(); } catch { /* no body */ }
  if (!r.ok) {
    const detail = data && (data.detail || data.error);
    const err = new Error(errorText(detail) || `Error ${r.status}`);
    err.code = detail && detail.code;          // lets a form show the error under the right field
    throw err;
  }
  return data;
}

// Toasts are queued, so two messages in a row (e.g. "+15 XP" and "20 min left today") both show.
const toastQueue = [];
let toastBusy = false;
export function toast(msg, ok = false) {
  if (!msg) return;
  const last = toastQueue[toastQueue.length - 1];
  if (last && last.msg === msg) return;
  toastQueue.push({ msg, ok });
  if (!toastBusy) nextToast();
}
function nextToast() {
  const item = toastQueue.shift(), el = $("#toast");
  if (!item) { toastBusy = false; el.hidden = true; return; }
  toastBusy = true;
  el.textContent = item.msg;
  el.className = "gl-toast" + (item.ok ? " ok" : "");
  el.hidden = false;
  setTimeout(nextToast, toastQueue.length ? 3200 : 4500);
}

export const progressChanged = () => window.dispatchEvent(new CustomEvent("guitarr:progress"));

export function youtubeSearch(q) {
  return "https://www.youtube.com/results?search_query=" + encodeURIComponent(q);
}

export function youtubeId(url) {
  const m = String(url).match(/(?:youtu\.be\/|v=|embed\/|shorts\/)([\w-]{11})/);
  return m ? m[1] : null;
}

// ------------------------------------------------------------------ chord diagram (SVG)
/** Vertical diagram: strings from the 6th (left) to the 1st (right), nut on top. */
export function chordSvg(ch, { size = 120, label = true } = {}) {
  const frets = ch.frets, fingers = ch.fingers || [];
  const pressed = frets.filter(f => f > 0);
  const lo = pressed.length ? Math.min(...pressed) : 1;
  const hi = pressed.length ? Math.max(...pressed) : 1;
  const base = hi <= 4 ? 1 : lo;                  // fret the drawing starts at
  const W = size, H = size * 1.15, padX = W * 0.16, top = H * 0.2, gridW = W - 2 * padX;
  const nF = 4, fH = (H - top - H * 0.1) / nF, sx = i => padX + i * gridW / 5, fy = n => top + n * fH;
  let s = `<svg class="chord-svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(t("chords.diagram_label", { chord: ch.id }))}">`;
  for (let n = 0; n <= nF; n++)
    s += `<line x1="${sx(0)}" x2="${sx(5)}" y1="${fy(n)}" y2="${fy(n)}" stroke="currentColor" stroke-opacity="${n === 0 && base === 1 ? 1 : .35}" stroke-width="${n === 0 && base === 1 ? 3 : 1}"/>`;
  for (let i = 0; i < 6; i++)
    s += `<line x1="${sx(i)}" x2="${sx(i)}" y1="${fy(0)}" y2="${fy(nF)}" stroke="currentColor" stroke-opacity=".5" stroke-width="${1 + (5 - i) * 0.25}" data-string="${6 - i}" class="chord-string"/>`;
  if (base > 1) s += `<text x="${sx(5) + 6}" y="${fy(0.6)}" font-size="${W * 0.09}" fill="currentColor" opacity=".7">${base}</text>`;
  if (ch.barre) {
    const y = fy(ch.barre.fret - base + 0.5), x1 = sx(6 - ch.barre.from_string), x2 = sx(6 - ch.barre.to_string);
    s += `<rect x="${x1 - 6}" y="${y - 6}" width="${x2 - x1 + 12}" height="12" rx="6" fill="var(--gl-accent)"/>`;
  }
  frets.forEach((f, i) => {
    const x = sx(i);
    if (f < 0) s += `<text x="${x}" y="${top - 6}" text-anchor="middle" font-size="${W * 0.1}" fill="var(--muted)">×</text>`;
    else if (f === 0) s += `<circle cx="${x}" cy="${top - 10}" r="${W * 0.03}" fill="none" stroke="var(--gl-ok)" stroke-width="1.5"/>`;
    else {
      const y = fy(f - base + 0.5);
      const inBarre = ch.barre && f === ch.barre.fret && fingers[i] === 1;
      if (!inBarre) s += `<circle cx="${x}" cy="${y}" r="${W * 0.055}" fill="var(--gl-accent)"/>`;
      if (fingers[i] && !inBarre) s += `<text x="${x}" y="${y + W * 0.035}" text-anchor="middle" font-size="${W * 0.08}" font-weight="700" fill="var(--gl-accent-ink)">${fingers[i]}</text>`;
    }
  });
  if (label) s += `<text x="${W / 2}" y="${H - 2}" text-anchor="middle" font-size="${W * 0.085}" fill="var(--muted)">${["E", "A", "D", "G", "B", "E"].join("  ")}</text>`;
  return s + "</svg>";
}

/** Makes the strings of a diagram clickable (plays that string). */
export function bindChordSvg(el, ch) {
  $$(".chord-string", el).forEach(line => {
    line.style.cursor = "pointer";
    line.addEventListener("click", () => {
      const s = +line.dataset.string, i = 6 - s, f = ch.frets[i];
      if (f >= 0) pluck(OPEN[i] + f);
    });
  });
}

// ------------------------------------------------------------------ sound (Karplus-Strong in Web Audio)
let ctx = null;
export function audioCtx() {
  if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
  if (ctx.state === "suspended") ctx.resume();
  return ctx;
}

const bufCache = new Map();
function pluckBuffer(midi, dur = 1.6) {
  const key = midi + ":" + dur;
  if (bufCache.has(key)) return bufCache.get(key);
  const ac = audioCtx(), sr = ac.sampleRate, n = Math.floor(sr * dur);
  const f = 440 * 2 ** ((midi - 69) / 12), P = Math.max(2, Math.round(sr / f - 0.5));
  const out = new Float32Array(n), buf = new Float32Array(P);
  for (let i = 0; i < P; i++) buf[i] = Math.random() * 2 - 1;
  for (let i = 0; i < n; i++) {
    const j = i % P;
    out[i] = buf[j];
    buf[j] = 0.996 * 0.5 * (buf[j] + buf[(j + 1) % P]);
  }
  for (let i = 0; i < 400 && i < n; i++) out[n - 1 - i] *= i / 400;
  const ab = ac.createBuffer(1, n, sr);
  ab.copyToChannel(out, 0);
  bufCache.set(key, ab);
  return ab;
}

export function pluck(midi, when = 0, gain = 0.35) {
  const ac = audioCtx(), src = ac.createBufferSource(), g = ac.createGain();
  src.buffer = pluckBuffer(midi);
  g.gain.value = gain;
  src.connect(g).connect(ac.destination);
  src.start(ac.currentTime + when);
}

export function strum(ch, { down = true, gap = 0.018, capo = 0 } = {}) {
  const idx = [0, 1, 2, 3, 4, 5].filter(i => ch.frets[i] >= 0);
  (down ? idx : idx.reverse()).forEach((i, k) => pluck(OPEN[i] + capo + ch.frets[i], k * gap, 0.22));
}

export function click(when, accent = false) {
  const ac = audioCtx(), o = ac.createOscillator(), g = ac.createGain();
  o.frequency.value = accent ? 1600 : 1000;
  g.gain.setValueAtTime(0.0001, when);
  g.gain.exponentialRampToValueAtTime(accent ? 0.5 : 0.3, when + 0.002);
  g.gain.exponentialRampToValueAtTime(0.0001, when + 0.05);
  o.connect(g).connect(ac.destination);
  o.start(when);
  o.stop(when + 0.06);
}
