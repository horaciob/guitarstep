// Shared view helpers: DOM, API, toasts, chord diagrams and sound.
import { errorText, t } from "./i18n.js";

export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
/** A string as a literal inside a RegExp. */
export const escRe = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
export const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
export const OPEN = [40, 45, 50, 55, 59, 64];            // 6th … 1st
// Your instrument (Settings → Instrument): open strings from string 1 down, and handedness.
export const instrument = { tuning: "standard", left_handed: false, tab_low_on_top: true, strings: [64, 59, 55, 50, 45, 40] };

/** The line (0 = top) a string goes on in tab and in the sideways fretboard: the 6th string on top by default,
 *  or the 1st, as most printed tab does (Settings → Instrument). Strings are numbered from the 1st (highest). */
export const stringRow = (string, n = instrument.strings.length) => instrument.tab_low_on_top ? n - string : string - 1;
export async function loadInstrument() {
  try { Object.assign(instrument, await api("/api/instrument")); } catch { /* defaults */ }
  return instrument;
}
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
  if (r.status === 202 && data && data.job) {        // slow work in a job (web service): wait for it
    const job = await waitJob(data.job);
    if (!data.retry) return job.result;
    if ((opts.retries || 0) >= 3) throw new Error(t("errors.generic"));
    return api(path, { ...opts, retries: (opts.retries || 0) + 1 });      // what it needed is ready now
  }
  if (!r.ok) {
    const detail = data && (data.detail || data.error);
    if (r.status === 401 && detail && detail.code === "not_signed_in") location.href = "/";   // the session expired
    const err = new Error(errorText(detail) || `Error ${r.status}`);
    err.code = detail && detail.code;          // lets a form show the error under the right field
    throw err;
  }
  return data;
}

async function waitJob(job) {
  toast(t(`jobs.${job.kind}`, { defaultValue: t("jobs.working") }));
  for (let delay = 400; ; delay = Math.min(delay * 1.5, 3000)) {
    if (job.status === "done") return job;
    if (job.status === "failed") {
      const err = new Error(errorText(job.error) || t("errors.generic"));
      err.code = job.error && job.error.code;
      throw err;
    }
    await new Promise(res => setTimeout(res, delay));
    job = await api(`/api/jobs/${job.id}`);
  }
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

// First-run setup: done (or skipped) once per browser.
const ONBOARDED = "guitarr.onboarded";
export function isOnboarded() {
  try { return localStorage.getItem(ONBOARDED) === "1"; } catch { return true; }
}
export function markOnboarded() {
  try { localStorage.setItem(ONBOARDED, "1"); } catch { /* storage unavailable */ }
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
  // left-handed: the diagram is mirrored (6th string on the right)
  const nF = 4, fH = (H - top - H * 0.1) / nF, fy = n => top + n * fH;
  const sx = i => padX + (instrument.left_handed ? 5 - i : i) * gridW / 5;
  let s = `<svg class="chord-svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${esc(t("chords.diagram_label", { chord: ch.id }))}">`;
  for (let n = 0; n <= nF; n++)
    s += `<line x1="${sx(0)}" x2="${sx(5)}" y1="${fy(n)}" y2="${fy(n)}" stroke="currentColor" stroke-opacity="${n === 0 && base === 1 ? 1 : .35}" stroke-width="${n === 0 && base === 1 ? 3 : 1}"/>`;
  for (let i = 0; i < 6; i++)
    s += `<line x1="${sx(i)}" x2="${sx(i)}" y1="${fy(0)}" y2="${fy(nF)}" stroke="currentColor" stroke-opacity=".5" stroke-width="${1 + (5 - i) * 0.25}" data-string="${6 - i}" class="chord-string"/>`;
  if (base > 1) s += `<text x="${Math.max(sx(0), sx(5)) + 6}" y="${fy(0.6)}" font-size="${W * 0.09}" fill="currentColor" opacity=".7">${base}</text>`;
  if (ch.barre) {
    const y = fy(ch.barre.fret - base + 0.5);
    const xa = sx(6 - ch.barre.from_string), xb = sx(6 - ch.barre.to_string), x1 = Math.min(xa, xb), x2 = Math.max(xa, xb);
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
  const names = ["E", "A", "D", "G", "B", "E"];
  if (label) s += `<text x="${W / 2}" y="${H - 2}" text-anchor="middle" font-size="${W * 0.085}" fill="var(--muted)">${(instrument.left_handed ? names.reverse() : names).join("  ")}</text>`;
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

export function strum(ch, { down = true, gap = 0.018, capo = 0, when = 0 } = {}) {
  const idx = [0, 1, 2, 3, 4, 5].filter(i => ch.frets[i] >= 0);
  (down ? idx : idx.reverse()).forEach((i, k) => pluck(OPEN[i] + capo + ch.frets[i], when + k * gap, 0.22));
}

export function click(when, accent = false, level = 1) {
  const ac = audioCtx(), o = ac.createOscillator(), g = ac.createGain();
  o.frequency.value = accent ? 1600 : level < 1 ? 800 : 1000;
  g.gain.setValueAtTime(0.0001, when);
  g.gain.exponentialRampToValueAtTime((accent ? 0.5 : 0.3) * level, when + 0.002);
  g.gain.exponentialRampToValueAtTime(0.0001, when + 0.05);
  o.connect(g).connect(ac.destination);
  o.start(when);
  o.stop(when + 0.06);
}
