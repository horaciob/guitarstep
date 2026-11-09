// Drawings for the rig, computed with plain math or filters in an offline context: nothing here makes sound.
// - clipPlot: one cycle of a test sine before and after a drive pedal (the same curves the pedals use)
// - comparePlots: soft, hard and asymmetric clipping side by side
// - stackCurve: the frequency response of an amp's tone stack for the current knobs
import { curve, dbToGain, lerp } from "./dsp.js";
import { AMPS } from "./effects.js";
import { t } from "../i18n.js";
import { esc } from "../ui.js";

// per drive pedal: [curve, curve amount, pre-gain in dB from its knobs] (mirrors the builds in effects.js)
const DRIVES = {
  overdrive: p => ["soft", 1.5, lerp(6, 40, p.drive / 10)],
  distortion: p => ["hard", 1, lerp(10, 50, p.drive / 10)],
  fuzz: p => ["fuzz", 6, lerp(12, 46, p.fuzz / 10)],
  transparent: p => ["soft", 1.2, lerp(0, 30, p.gain / 10), lerp(0.8, 0.35, p.gain / 10)],
  asym_drive: p => ["asym", 1.5, lerp(6, 36, p.drive / 10)],
  octave_fuzz: p => ["fuzz", 5, lerp(6, 30, p.fuzz / 10), 0, true],
  capture: p => ["soft", 1, lerp(0, 30, p.drive / 10)],
};
export const isDrive = type => type in DRIVES;

const INPUT = 0.08;             // roughly a guitar's level into a pedal
const look = (c, x) => c[Math.round((Math.max(-1, Math.min(1, x)) + 1) / 2 * (c.length - 1))];

function plot(ins, outs, w = 280, h = 120, label = true) {
  const pts = a => a.map((v, i) => `${(i / (a.length - 1) * w).toFixed(1)},${(h / 2 - v * (h / 2 - 6)).toFixed(1)}`).join(" ");
  return `<svg class="clip-plot" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true">
    <line x1="0" y1="${h / 2}" x2="${w}" y2="${h / 2}" class="cp-axis"/>
    <polyline points="${pts(ins)}" class="cp-in"/><polyline points="${pts(outs)}" class="cp-out"/>
    ${label ? `<text x="4" y="12" class="cp-l in">— ${esc(t("rig.clip_in"))}</text><text x="4" y="26" class="cp-l out">— ${esc(t("rig.clip_out"))}</text>` : ""}</svg>`;
}

/** The test sine (scaled to fit) and what the pedal's curve does to it at the current knob settings. */
export function clipPlot(type, params) {
  const [kind, amount, preDb, cleanMix = 0, rectify = false] = DRIVES[type](params);
  const c = curve(kind, amount), rc = curve("rect", 1), g = dbToGain(preDb);
  const ins = [], outs = [];
  for (let i = 0; i < 200; i++) {
    const s = Math.sin((i / 199) * 2 * Math.PI) * INPUT;
    let x = s;
    if (rectify) x = look(rc, x * 4) * INPUT;                  // folded: an octave up
    const y = look(c, x * g) * (1 - cleanMix) + (s / INPUT) * cleanMix;
    ins.push(s / INPUT); outs.push(y);
  }
  return plot(ins, outs);
}

/** Soft, hard and asymmetric clipping of the same sine at the same drive. */
export function comparePlots() {
  return ["soft", "hard", "asym"].map(kind => {
    const c = curve(kind, kind === "asym" ? 1.5 : 1), ins = [], outs = [];
    for (let i = 0; i < 120; i++) { const s = Math.sin((i / 119) * 2 * Math.PI); ins.push(s); outs.push(look(c, s * 2.5)); }
    return `<figure class="cp-mini">${plot(ins, outs, 150, 70, false)}<figcaption class="small">${esc(t(`rig.clip_${kind}`))}</figcaption></figure>`;
  }).join("");
}

/** The amp's bass/mid/treble/presence filters, drawn as one curve in dB (offline: never played). */
export function stackCurve(type, params) {
  const A = AMPS[type];
  if (!A) return "";
  const ctx = new OfflineAudioContext(1, 128, 44100);
  const [bF, mF, mQ, tF] = A.tone;
  const f = (kind, freq, q, gain) => { const n = ctx.createBiquadFilter(); n.type = kind; n.frequency.value = freq; n.Q.value = q; n.gain.value = gain; return n; };
  const nodes = [f("lowshelf", bF, 0.7, lerp(-12, 12, params.bass / 10)), f("peaking", mF, mQ, lerp(-12, 10, params.mid / 10)),
    f("highshelf", tF, 0.7, lerp(-12, 10, params.treble / 10)), f("highshelf", 4500, 0.7, lerp(-6, 8, params.presence / 10))];
  const N = 120, freqs = new Float32Array(N), total = new Float32Array(N).fill(0);
  for (let i = 0; i < N; i++) freqs[i] = 40 * Math.pow(12000 / 40, i / (N - 1));
  const mag = new Float32Array(N), ph = new Float32Array(N);
  for (const n of nodes) { n.getFrequencyResponse(freqs, mag, ph); for (let i = 0; i < N; i++) total[i] += 20 * Math.log10(Math.max(1e-6, mag[i])); }
  const W = 560, H = 140, lim = 24, x = i => (i / (N - 1)) * W, y = db => H / 2 - (db / lim) * (H / 2 - 8);
  const path = Array.from(total, (db, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(db).toFixed(1)}`).join(" ");
  const ticks = [100, 1000, 10000].map(fq => { const i = Math.log(fq / 40) / Math.log(12000 / 40) * (N - 1); return `<text x="${x(i)}" y="${H - 2}" class="cp-l" text-anchor="middle">${fq >= 1000 ? fq / 1000 + "k" : fq} Hz</text>`; }).join("");
  return `<svg class="stack-curve" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t("rig.stack_title"))}">
    <line x1="0" y1="${y(0)}" x2="${W}" y2="${y(0)}" class="cp-axis"/>
    <text x="4" y="${y(12) + 4}" class="cp-l">+12 dB</text><text x="4" y="${y(-12) + 4}" class="cp-l">−12 dB</text>
    <path d="${path}" class="sc-line"/>${ticks}</svg>`;
}
